"""The dispatcher: computes the surplus and hands it out by priority."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import math
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.sun import get_astral_event_next
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CHARGE_POSITIVE,
    CONF_BATTERY_MAX_CHARGE_W,
    CONF_BATTERY_POWER,
    CONF_BATTERY_CHARGE,
    CONF_BATTERY_DISCHARGE,
    CONF_BATTERY_SOC,
    CONF_GRID_EXPORT,
    CONF_GRID_IMPORT,
    CONF_BATTERY_RESERVE_SOC,
    CONF_BATTERY_TARGET_SOC,
    CONF_NIGHT_EXTRA_H,
    CONF_NIGHT_POWER_W,
    CONF_NIGHT_TARGET,
    CONF_BREAKER_MARGIN_A,
    BORROW_SOC_BAND,
    CHARGE_FORECAST_INTERVAL_H,
    CHARGE_FORECAST_LATEST_HOUR,
    CONF_AI_CHARGE_FORECAST,
    CONF_AI_MORNING_ENABLED,
    CONF_AI_MORNING_TIME,
    CONF_AI_OUTLOOK_CHECK,
    CONF_AI_REVIEW_ENABLED,
    CONF_AI_REVIEW_TIME,
    CONF_AI_TASK_ENTITY,
    CONF_BATTERY_BORROW,
    CONF_BATTERY_FULL_SOC,
    CONF_EXPORT_CONTROL,
    CONF_EXPORT_RERAISE,
    CONF_EXPORT_LIMIT_ENTITY,
    CONF_EXPORT_LIMIT_NORMAL,
    CONF_EXPORT_LIMIT_RAISED,
    CONF_FORECAST_MIN_SOC,
    CONF_FORECAST_REMAINING,
    CONF_FORECAST_SAFETY,
    CONF_GRID_IMPORT_POSITIVE,
    CONF_GRID_POWER,
    CONF_HOUSE_AVG_POWER_W,
    CONF_HOUSE_POWER,
    CONF_INPUT_TIMEOUT,
    CONF_DRY_RUN,
    CONF_EV_CAPACITY,
    CONF_EV_EFFICIENCY,
    CONF_MAIN_BREAKER_A,
    CONF_MIN_BEFORE_BATTERY,
    CONF_NOMINAL_VOLTAGE,
    CONF_NOTIFY_ON_AT_RISK,
    CONF_NOTIFY_ON_BOOST,
    CONF_NOTIFY_ON_FAILSAFE,
    CONF_NOTIFY_ON_ORDER,
    CONF_NOTIFY_ON_REVIEW,
    CONF_NOTIFY_REVIEW_MAX_SCORE,
    CONF_PHASE_CURRENTS,
    CONF_PRICE_NT,
    CONF_PRICE_VT,
    CONF_PV_POWER,
    CONF_RESERVE_W,
    CONF_UPDATE_INTERVAL,
    DEFAULTS,
    DEVICE_TUNABLES,
    DOMAIN,
    HUB_TUNABLE_KEYS,
)
from .hdo import HdoSchedule, settings_from_conf
from .notify import (
    EVENT_AWAY,
    EVENT_BOOST,
    EVENT_CHARGE_ORDER,
    EVENT_DEADLINE_RISK,
    EVENT_FAILSAFE,
    EVENT_FAILSAFE_CLEARED,
    EVENT_OUTLOOK_CHECK,
    EVENT_PROPOSAL_APPLIED,
    EVENT_REVIEW_DONE,
    async_dismiss,
    async_notify,
    fire_event,
    msg_at_risk,
    msg_boost,
    msg_failsafe,
    msg_failsafe_cleared,
    msg_order,
    msg_outlook_check,
    msg_review,
    review_should_notify,
)
from .devices import (
    DEVICE_TYPES,
    Headroom,
    ManagedDevice,
    async_set_number,
    state_float,
    state_power,
)

_LOGGER = logging.getLogger(__name__)

DECISION_LOG_SIZE = 20
STAT_KEYS = ("total", "solar", "battery", "grid", "cost")
DAY_LOG_SIZE = 150
SRC_OPTIMIZER = "integrace"
SRC_RECOMMENDATION = "tlačítko Provést"
SRC_EXTERNAL = "mimo integraci"
REVIEW_HISTORY = 14


@dataclass
class DispatchSnapshot:
    """Result of one dispatcher cycle, read by the entities."""

    grid_w: float | None = None
    battery_w: float | None = None
    battery_soc: float | None = None
    pv_w: float | None = None
    house_w: float | None = None
    managed_w: float = 0.0
    budget_w: float = 0.0
    # What the budget is made of (for the card): devices, export, import, battery…
    budget_parts: dict[str, float] = field(default_factory=dict)
    allocated_w: float = 0.0
    battery_priority: bool = True
    effective_target_soc: float | None = None
    forecast_covers_battery: bool = False
    export_limit_raised: bool = False
    headroom_a: float | None = None
    forecast_remaining_kwh: float | None = None
    forecast_need_kwh: float | None = None
    hours_until_sunset: float | None = None
    night_hours: float | None = None
    night_kwh: float | None = None
    night_target_soc: float | None = None
    solar_for_devices_kwh: float | None = None
    borrow_active: bool = False
    dry_run: bool = False
    stale_inputs: list[str] = field(default_factory=list)
    # Watch-only: manual actions that would bring reality in line with the plan.
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    hdo_active: bool | None = None
    reason: str = "init"
    devices: dict[str, dict[str, Any]] = field(default_factory=dict)
    decision: str | None = None
    decision_lines: list[str] = field(default_factory=list)
    decision_changed_at: str | None = None
    decision_data: dict[str, Any] = field(default_factory=dict)
    # Same structure as decision_data, refreshed every cycle (for the card).
    live_data: dict[str, Any] = field(default_factory=dict)


class FveOptimizerCoordinator(DataUpdateCoordinator[DispatchSnapshot]):
    """Runs the dispatch loop every few seconds."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.conf: dict[str, Any] = {**DEFAULTS, **entry.data, **entry.options}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=int(self.conf[CONF_UPDATE_INTERVAL])),
        )
        self.enabled = True
        self.hub_device_id: str | None = None
        self.devices: dict[str, ManagedDevice] = {}
        for subentry_id, subentry in entry.subentries.items():
            device_cls = DEVICE_TYPES.get(subentry.subentry_type)
            if device_cls is None:
                _LOGGER.warning("Unknown device type %s", subentry.subentry_type)
                continue
            self.devices[subentry_id] = device_cls(hass, subentry_id, dict(subentry.data))
        self._export_raised: bool | None = None
        self._borrow_active = False
        self._inputs_bad_since: float | None = None
        self._recommended_since: dict[str, str] = {}
        # Last decisions for the card's short log (newest first, survives restarts).
        self._decision_log: list[dict[str, str]] = []
        # Energy / cost statistics per device: {sid: {total, solar, battery, grid, cost,
        # day, today: {...}}} – survive restarts.
        self._stats: dict[str, dict[str, Any]] = {}
        # Today's overview for the AI review (grid, switching, fail-safe, decisions).
        self._day: dict[str, Any] = {}
        self._prev_on: dict[str, bool | None] = {}
        # Who caused the next on/off change of a device: (source, monotonic time).
        self._expected: dict[str, tuple[str, float]] = {}
        # Open watch-only recommendations: key → {id, text, since}; keys executed by hand.
        self._open_recs: dict[str, dict[str, str]] = {}
        self._executed_recs: set[str] = set()
        self.reviews: list[dict[str, Any]] = []  # newest first
        self._review_day_data: dict[str, Any] | None = None  # snapshot for discussion
        self.morning_plan: dict[str, Any] | None = None  # today's morning baseline
        self.charge_forecast: dict[str, Any] | None = None  # mid-day charge outlook
        self.review_error: str | None = None
        self.review_running = False
        self.review_asking = False
        self.morning_running = False
        self.charge_running = False
        self._last_accounting: float | None = None
        self._save_due: float | None = None
        self._failsafe_logged = False
        # Deadline at_risk edge detection + AI outlook-check rate limit (device_id → date).
        self._at_risk_ids: set[str] = set()
        self._outlook_check_day: dict[str, str] = {}
        self._boost_ids: set[str] = set()
        # Days the limit was raised / lowered – at most one raise per day.
        self._export_raised_day: str | None = None
        self._export_lowered_day: str | None = None
        # Last good grid / battery / SoC – display only across brief unavailable blips.
        self._last_good_inputs: tuple[float, float, float] | None = None
        self._last_live_data: dict[str, Any] = {}
        self.hdo = HdoSchedule(hass, entry.entry_id, settings_from_conf(self.conf))
        self._state_store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.state.{entry.entry_id}")
        self._saved_state: dict[str, Any] = {}
        self._last_decision: tuple[Any, ...] | None = None
        self._decision: tuple[str | None, list[str], str | None, dict[str, Any]] = (
            None,
            [],
            None,
            {},
        )
        self.structure = config_structure(entry)

    async def async_load_state(self) -> None:
        """Restore per-device runtime state (e.g. last anti-legionella run)."""
        self._saved_state = await self._state_store.async_load() or {}
        for subentry_id, device in self.devices.items():
            device.restore(self._saved_state.get(subentry_id, {}))
        self._decision_log = list(self._saved_state.get("_decision_log", []))[:DECISION_LOG_SIZE]
        self._stats = {
            sid: dict(v) for sid, v in self._saved_state.get("_stats", {}).items() if sid in self.devices
        }
        self._day = dict(self._saved_state.get("_day", {}))
        self.reviews = list(self._saved_state.get("_reviews", []))[:REVIEW_HISTORY]
        for review in self.reviews:
            review.setdefault("discussion", [])
            review.setdefault("proposals", [])
        self._review_day_data = self._saved_state.get("_review_day_data")
        self.morning_plan = self._saved_state.get("_morning_plan")
        self.charge_forecast = self._saved_state.get("_charge_forecast")
        export = self._saved_state.get("_export", {})
        self._export_raised_day = export.get("raised_day")
        self._export_lowered_day = export.get("lowered_day")

    def _save_state(self) -> None:
        state: dict[str, Any] = {sid: d.persistent() for sid, d in self.devices.items()}
        state["_export"] = {
            "raised_day": self._export_raised_day,
            "lowered_day": self._export_lowered_day,
        }
        state["_decision_log"] = self._decision_log
        state["_stats"] = self._stats
        state["_day"] = self._day
        state["_reviews"] = self.reviews
        state["_review_day_data"] = self._review_day_data
        state["_morning_plan"] = self.morning_plan
        state["_charge_forecast"] = self.charge_forecast
        if state != self._saved_state:
            self._saved_state = state
            # Statistics change every cycle: write at most once a minute (the store
            # postpones a delayed save on every call, so keep a fixed deadline).
            now = time.monotonic()
            if self._save_due is None or now >= self._save_due:
                self._save_due = now + 60
            self._state_store.async_delay_save(lambda: state, max(self._save_due - now, 1))

    # -- configuration --------------------------------------------------------
    def apply_config(self, entry: ConfigEntry) -> None:
        """Take over changed tunables without a reload."""
        self.conf = {**DEFAULTS, **entry.data, **entry.options}
        self.update_interval = timedelta(seconds=int(self.conf[CONF_UPDATE_INTERVAL]))
        for subentry_id, subentry in entry.subentries.items():
            if device := self.devices.get(subentry_id):
                device.update_config(dict(subentry.data))

    # -- helpers --------------------------------------------------------------
    def _f(self, key: str) -> float:
        return float(self.conf[key])

    def _read(self, key: str) -> float | None:
        return state_float(self.hass, self.conf.get(key))

    @property
    def dry_run(self) -> bool:
        return bool(self.conf.get(CONF_DRY_RUN))

    def _input_groups(self) -> list[list[str]]:
        """Critical input groups. A pair is healthy when either side is readable.

        Import/export and charge/discharge often stay at 0 (or unavailable) while
        the other direction is active; integrations may also rewrite a state only
        when it changes. Grouping avoids false 'missing' / 'frozen' alarms.
        """
        groups: list[list[str]] = [[CONF_BATTERY_SOC]]
        if self.conf.get(CONF_GRID_POWER):
            groups.append([CONF_GRID_POWER])
        elif self._grid_computed():
            groups.extend([[CONF_GRID_EXPORT], [CONF_HOUSE_POWER], [CONF_PV_POWER]])
        else:
            groups.append([CONF_GRID_IMPORT, CONF_GRID_EXPORT])
        if self.conf.get(CONF_BATTERY_POWER):
            groups.append([CONF_BATTERY_POWER])
        else:
            groups.append([CONF_BATTERY_CHARGE, CONF_BATTERY_DISCHARGE])
        return groups

    def _input_problems(self) -> tuple[list[str], list[str]]:
        """(missing, frozen) critical inputs.

        Missing = a whole group is unavailable / unknown. Frozen = *every*
        group has been silent longer than the timeout (same inverter). One quiet
        entity in a pair (e.g. charge stays 0 W for hours) is fine.
        """
        timeout = float(self.conf.get(CONF_INPUT_TIMEOUT) or 0)
        missing: list[str] = []
        group_seen: list[tuple[list[str], Any]] = []
        now = dt_util.utcnow()
        for group in self._input_groups():
            readable: list[tuple[str, Any]] = []
            configured: list[str] = []
            for key in group:
                entity_id = self.conf.get(key)
                if not entity_id:
                    continue
                configured.append(str(entity_id))
                state = self.hass.states.get(entity_id)
                if state is None or state_float(self.hass, entity_id) is None:
                    continue
                seen = getattr(state, "last_reported", None) or state.last_updated
                readable.append((str(entity_id), seen))
            if not configured:
                continue
            if not readable:
                missing.extend(configured)
                continue
            newest = max(seen for _, seen in readable)
            group_seen.append((configured, newest))
        frozen: list[str] = []
        # timeout=0 disables the fail-safe entirely (hold forever / ignore frozen).
        if (
            timeout > 0
            and group_seen
            and not missing
            and all((now - seen).total_seconds() > timeout for _, seen in group_seen)
        ):
            frozen = [entity_id for entities, _ in group_seen for entity_id in entities]
        return missing, frozen

    def _power(self, key: str) -> float | None:
        return state_power(self.hass, self.conf.get(key))

    def _signed(self, single: str, positive: str, plus: str, minus: str) -> float | None:
        """One signed sensor, or two positive ones (plus − minus).

        When using a pair, a missing side counts as 0 W – idle direction is often
        unavailable or not rewritten until it changes.
        """
        if self.conf.get(single):
            value = self._power(single)
            if value is None:
                return None
            return value if self.conf[positive] else -value
        a, b = self._power(plus), self._power(minus)
        if a is None and b is None:
            return None
        return abs(a or 0.0) - abs(b or 0.0)

    def _grid_computed(self) -> bool:
        """No import sensor: derive it from the house load (Growatt "local load")."""
        c = self.conf
        return (
            not c.get(CONF_GRID_POWER)
            and not c.get(CONF_GRID_IMPORT)
            and bool(c.get(CONF_GRID_EXPORT))
            and bool(c.get(CONF_HOUSE_POWER))
            and bool(c.get(CONF_PV_POWER))
        )

    def _grid_import_w(self) -> float | None:
        """Grid power, positive = import from grid."""
        if self._grid_computed():
            # PV + import + discharge = house + export + charge
            house, export, pv = (
                self._power(CONF_HOUSE_POWER),
                self._power(CONF_GRID_EXPORT),
                self._power(CONF_PV_POWER),
            )
            battery = self._battery_charge_w()
            if None in (house, export, pv, battery):
                return None
            imported = max(abs(house) + abs(export) + battery - abs(pv), 0.0)  # type: ignore[arg-type]
            return imported - abs(export)  # type: ignore[arg-type]
        return self._signed(CONF_GRID_POWER, CONF_GRID_IMPORT_POSITIVE, CONF_GRID_IMPORT, CONF_GRID_EXPORT)

    def _battery_charge_w(self) -> float | None:
        """Battery power, positive = charging."""
        return self._signed(
            CONF_BATTERY_POWER, CONF_BATTERY_CHARGE_POSITIVE, CONF_BATTERY_CHARGE, CONF_BATTERY_DISCHARGE
        )

    def _sun(self) -> tuple[bool, datetime | None, datetime | None] | None:
        """(sun up, next rising, next setting), None without the sun entity.

        The sun entity's attributes can be stale (e.g. after the host slept
        through a sunrise), so past values are recomputed from the location.
        """
        sun = self.hass.states.get("sun.sun")
        if sun is None:
            return None
        now = dt_util.utcnow()
        rising = dt_util.parse_datetime(str(sun.attributes.get("next_rising", "")))
        setting = dt_util.parse_datetime(str(sun.attributes.get("next_setting", "")))
        if rising and setting and rising > now and setting > now:
            return sun.state == "above_horizon", rising, setting
        rising = get_astral_event_next(self.hass, SUN_EVENT_SUNRISE, now)
        setting = get_astral_event_next(self.hass, SUN_EVENT_SUNSET, now)
        return setting < rising, rising, setting

    def _producing(self) -> bool:
        """Daylight (assumed when the sun entity is missing)."""
        sun = self._sun()
        return sun is None or sun[0]

    def _hours_until_sunset(self) -> float:
        sun = self._sun()
        if sun is None or not sun[0] or sun[2] is None:
            return 0.0
        return max((sun[2] - dt_util.utcnow()).total_seconds() / 3600, 0.0)

    def _hours_without_production(self) -> float | None:
        """Hours from sunset (or now, at night) to the next sunrise."""
        sun = self._sun()
        if sun is None or sun[1] is None:
            return None
        up, rising, setting = sun
        start = setting if up and setting is not None else dt_util.utcnow()
        return max((rising - start).total_seconds() / 3600, 0.0)

    def _night_target(self, snap: DispatchSnapshot) -> float:
        """SoC needed to get through the time without production.

        (night power × (night hours + extra)) / capacity + reserve, capped by
        the configured target SoC. Weak production after sunrise and before
        sunset is covered by the extra hours.
        """
        cap = self._f(CONF_BATTERY_TARGET_SOC)
        if not self.conf.get(CONF_NIGHT_TARGET):
            return cap
        hours = self._hours_without_production()
        if hours is None:
            return cap
        hours += self._f(CONF_NIGHT_EXTRA_H)
        kwh = self._f(CONF_NIGHT_POWER_W) / 1000 * hours
        need = self._f(CONF_BATTERY_RESERVE_SOC) + kwh / self._f(CONF_BATTERY_CAPACITY_KWH) * 100
        target = round(min(max(need, self._f(CONF_BATTERY_RESERVE_SOC)), cap), 1)
        snap.night_hours = round(hours, 2)
        snap.night_kwh = round(kwh, 2)
        snap.night_target_soc = target
        return target

    def _solar_for_devices(self, house_w: float | None) -> float | None:
        """Solar kWh left today for devices: forecast ÷ safety − house until sunset."""
        remaining = self._read(CONF_FORECAST_REMAINING)
        if remaining is None:
            return None
        house_kw = (house_w if house_w is not None else self._f(CONF_HOUSE_AVG_POWER_W)) / 1000
        return max(remaining / self._f(CONF_FORECAST_SAFETY) - house_kw * self._hours_until_sunset(), 0.0)

    def _away_boiler_need_kwh(self) -> float:
        """kWh still needed to finish surplus/deadline heating on all boilers."""
        from .devices import SwitchedDevice  # noqa: PLC0415

        total = 0.0
        for device in self.devices.values():
            if not isinstance(device, SwitchedDevice) or not device.enabled:
                continue
            total += device.heat_need_kwh()
        return total

    def _away_energy_plan(
        self,
        snap: DispatchSnapshot,
        soc: float,
        leave_at: datetime,
        house_w: float | None,
        ev: Any,
    ) -> dict[str, float | bool]:
        """Estimate what may go into the EV before leave.

        Afternoon sun after leave (forecast share ÷ safety − house) must still
        cover bringing the house battery to target and reheating the boiler.
        When it does, surplus (and lendable battery energy) prefers the car now.
        """
        empty: dict[str, float | bool] = {
            "lendable_kwh": 0.0,
            "car_budget_kwh": 0.0,
            "boiler_need_kwh": 0.0,
            "afternoon_net_kwh": 0.0,
            "prefers_car": False,
        }
        remaining = self._read(CONF_FORECAST_REMAINING)
        if remaining is None:
            return empty
        now = dt_util.now()
        if leave_at.tzinfo is None:
            leave_at = leave_at.replace(tzinfo=now.tzinfo)
        if leave_at.date() != now.date() or now >= leave_at:
            return empty
        hours_sunset = self._hours_until_sunset()
        if hours_sunset <= 0:
            return empty
        hours_to_leave = max((leave_at - now).total_seconds() / 3600, 0.0)
        hours_after = max(hours_sunset - hours_to_leave, 0.0)
        frac_after = hours_after / hours_sunset
        house_kw = (house_w if house_w is not None else self._f(CONF_HOUSE_AVG_POWER_W)) / 1000
        safety = self._f(CONF_FORECAST_SAFETY)
        afternoon_net = max(
            remaining * frac_after / safety - house_kw * hours_after,
            0.0,
        )
        solar_before = max(
            remaining * (1.0 - frac_after) / safety - house_kw * hours_to_leave,
            0.0,
        )
        capacity = self._f(CONF_BATTERY_CAPACITY_KWH)
        if capacity <= 0:
            return empty
        target = snap.effective_target_soc
        if target is None:
            target = self._f(CONF_BATTERY_TARGET_SOC)
        reserve = self._f(CONF_BATTERY_RESERVE_SOC)
        battery_need = capacity * max(float(target) - soc, 0.0) / 100
        boiler_need = self._away_boiler_need_kwh()
        # Afternoon must cover battery refill + boiler reheat → free surplus for the car now.
        prefers_car = afternoon_net + 1e-6 >= battery_need + boiler_need
        available_for_battery = max(afternoon_net - boiler_need, 0.0)
        min_soc = max(reserve, float(target) - available_for_battery / capacity * 100)
        lendable = max((soc - min_soc) / 100 * capacity, 0.0)
        car_room = 0.0
        if getattr(ev, "_ev_soc", None) is not None:
            try:
                car_room = (
                    max(float(ev.target_soc) - float(ev._ev_soc), 0.0)
                    / 100
                    * float(ev.cfg(CONF_EV_CAPACITY))
                    / float(ev.cfg(CONF_EV_EFFICIENCY))
                )
            except (TypeError, ValueError, KeyError):
                car_room = 0.0
        car_budget = min(car_room, solar_before + lendable) if prefers_car else 0.0
        return {
            "lendable_kwh": lendable,
            "car_budget_kwh": car_budget,
            "boiler_need_kwh": boiler_need,
            "afternoon_net_kwh": afternoon_net,
            "prefers_car": prefers_car,
        }

    def _prepare_away_lend(
        self, snap: DispatchSnapshot, soc: float, house_w: float | None
    ) -> None:
        """Apply away energy plan: prefer EV, defer boiler surplus when afternoon covers."""
        from .devices import EvChargerDevice, SwitchedDevice  # noqa: PLC0415

        now = dt_util.now()
        prefer_any = False
        for device in self.devices.values():
            device.away_defer_surplus = False
            if not isinstance(device, EvChargerDevice):
                continue
            device.battery_lend_kwh = 0.0
            device.away_prefer = False
            device.away_car_budget_kwh = 0.0
            away = device.away
            if not away:
                continue
            leave = dt_util.parse_datetime(str(away["leave_at"]))
            if leave is None:
                continue
            if leave.tzinfo is None:
                leave = leave.replace(tzinfo=now.tzinfo)
            plan = self._away_energy_plan(snap, soc, leave, house_w, device)
            device.battery_lend_kwh = float(plan["lendable_kwh"])
            device.away_car_budget_kwh = float(plan["car_budget_kwh"])
            device.away_prefer = bool(plan["prefers_car"])
            if device.away_prefer and device._away_pending(now):
                prefer_any = True
        if prefer_any:
            for device in self.devices.values():
                if isinstance(device, SwitchedDevice) and device.enabled:
                    # Urgent deadline / legionella still runs; surplus heating waits.
                    device.away_defer_surplus = True

    def _update_deadlines(
        self, snap: DispatchSnapshot, solar_kwh: float | None, battery_need_kwh: float
    ) -> None:
        """Let devices decide deadline mode, sharing the expected solar energy.

        Devices are served in priority order. A device with "minimum before
        battery" gets solar before the battery, otherwise only what is left
        after charging the battery.
        """
        snap.solar_for_devices_kwh = None if solar_kwh is None else round(solar_kwh, 2)
        now = dt_util.now()
        left = solar_kwh
        for device in sorted(self.devices.values(), key=lambda d: d.priority):
            if left is None:
                device.solar_kwh = None
            elif device.config.get(CONF_MIN_BEFORE_BATTERY):
                device.solar_kwh = left
            else:
                device.solar_kwh = max(left - battery_need_kwh, 0.0)
            used = device.update_deadline(now) if device.enabled else 0.0
            if left is not None:
                left = max(left - used, 0.0)

    def _headroom(self) -> Headroom:
        voltage = self._f(CONF_NOMINAL_VOLTAGE)
        sensors = self.conf.get(CONF_PHASE_CURRENTS) or []
        currents = [c for c in (state_float(self.hass, s) for s in sensors) if c is not None]
        if not currents:
            return Headroom(voltage=voltage)
        worst = max(abs(c) for c in currents)
        amps = self._f(CONF_MAIN_BREAKER_A) - self._f(CONF_BREAKER_MARGIN_A) - worst
        return Headroom(amps, voltage)

    def _battery_target(
        self, soc: float, house_w: float | None, snap: DispatchSnapshot
    ) -> tuple[float, bool]:
        """Return (effective target SoC, forecast covers battery)."""
        target = self._night_target(snap)
        remaining_kwh = self._read(CONF_FORECAST_REMAINING)
        if remaining_kwh is None:
            return target, False
        battery_need = self._f(CONF_BATTERY_CAPACITY_KWH) * max(target - soc, 0.0) / 100
        house_kw = (house_w if house_w is not None else self._f(CONF_HOUSE_AVG_POWER_W)) / 1000
        hours = self._hours_until_sunset()
        need = (battery_need + house_kw * hours) * self._f(CONF_FORECAST_SAFETY)
        snap.forecast_remaining_kwh = remaining_kwh
        snap.forecast_need_kwh = round(need, 2)
        snap.hours_until_sunset = round(hours, 2)
        covered = remaining_kwh >= need
        if covered:
            return min(target, self._f(CONF_FORECAST_MIN_SOC)), True
        return target, False

    # -- main loop ------------------------------------------------------------
    async def _async_update_data(self) -> DispatchSnapshot:
        snap = DispatchSnapshot()
        now = time.monotonic()

        await self.hdo.async_refresh()
        hdo = self.hdo.is_active(dt_util.now())
        snap.hdo_active = hdo
        for device in self.devices.values():
            device.voltage = self._f(CONF_NOMINAL_VOLTAGE)
            device.hdo_active = hdo
            device.hdo_schedule = self.hdo if self.hdo.knows_future else None
            device.read()

        grid = self._grid_import_w()
        battery = self._battery_charge_w()
        soc = self._read(CONF_BATTERY_SOC)
        snap.grid_w, snap.battery_w, snap.battery_soc = grid, battery, soc
        snap.pv_w = self._power(CONF_PV_POWER)
        snap.house_w = self._power(CONF_HOUSE_POWER)

        active = [d for d in self.devices.values() if d.enabled]
        snap.managed_w = sum(d.status.actual_w for d in active)

        if not self.enabled:
            self._update_deadlines(snap, None, 0.0)
            snap.reason = "disabled"
            return self._finish(snap)

        snap.dry_run = self.dry_run
        missing, frozen = self._input_problems()
        snap.stale_inputs = missing + frozen
        timeout = float(self.conf.get(CONF_INPUT_TIMEOUT) or 0)
        if snap.stale_inputs:
            # Frozen data is already older than the timeout → fail-safe now.
            # Missing data: keep going on the last good values until the timeout.
            # timeout=0 disables the fail-safe (permanent hold) – see UI description.
            if self._inputs_bad_since is None:
                self._inputs_bad_since = now
            if timeout > 0 and (frozen or now - self._inputs_bad_since >= timeout):
                return await self._async_failsafe(snap, active, now)
        else:
            if self._failsafe_logged:
                _LOGGER.warning("Inverter data is back – fail-safe ended")
                self.hass.async_create_task(self._async_on_failsafe_cleared())
            self._inputs_bad_since = None
            self._failsafe_logged = False

        if grid is not None and battery is not None and soc is not None:
            self._last_good_inputs = (grid, battery, soc)

        if grid is None or battery is None or soc is None:
            # Hold actuators – do not invent a budget from stale readings.
            # Keep last good values only for display on the card.
            if self._last_good_inputs is not None:
                snap.grid_w, snap.battery_w, snap.battery_soc = self._last_good_inputs
            self._update_deadlines(snap, None, 0.0)
            snap.reason = "missing_input"
            _LOGGER.debug("Missing grid/battery/SoC input, holding current state")
            return self._finish(snap)

        # House sensors (e.g. Growatt load power) include the managed devices;
        # the forecast check needs the base load only.
        base_house_w = (
            max(snap.house_w - snap.managed_w, 0.0) if snap.house_w is not None else None
        )
        self._account(grid, battery, snap.hdo_active, now)
        target_soc, covered = self._battery_target(soc, base_house_w, snap)
        snap.effective_target_soc = target_soc
        snap.forecast_covers_battery = covered
        snap.battery_priority = soc < target_soc
        self._prepare_away_lend(snap, soc, base_house_w)
        # Away + refillable after leave: do not hold surplus in the house battery.
        from .devices import EvChargerDevice  # noqa: PLC0415

        if any(
            isinstance(d, EvChargerDevice) and d.away_releases_battery()
            for d in self.devices.values()
        ):
            snap.battery_priority = False
        self._update_deadlines(
            snap,
            self._solar_for_devices(base_house_w),
            self._f(CONF_BATTERY_CAPACITY_KWH) * max(target_soc - soc, 0.0) / 100,
        )

        # Full budget = what managed devices use now + battery charging + export,
        # minus imports. While the battery has priority it first gets up to its
        # maximum charging power; only what is left beyond that is surplus for
        # the devices – so running devices give way to the battery as well.
        full_budget = snap.managed_w - grid + battery - self._f(CONF_RESERVE_W)
        budget = full_budget
        if snap.battery_priority:
            budget -= self._f(CONF_BATTERY_MAX_CHARGE_W)
        snap.budget_w = budget
        snap.budget_parts = {
            "devices": snap.managed_w,
            "export": max(-grid, 0.0),
            "import": max(grid, 0.0),
            "battery": battery,
            "battery_reserved": self._f(CONF_BATTERY_MAX_CHARGE_W) if snap.battery_priority else 0.0,
            "reserve": self._f(CONF_RESERVE_W),
        }

        headroom = self._headroom()
        snap.headroom_a = headroom.amps if math.isfinite(headroom.amps) else None

        # Order: urgent runs (they consume power anyway), then devices below
        # their minimum, then the rest. The first two groups may also use the
        # power the battery would get – charging the battery only to discharge
        # it into the boiler / car in the evening would be a wasted cycle.
        # Everyone after them shares the budget without the battery's part.
        # Away + refillable forecast: EV outranks other non-urgent loads (boiler)
        # so surplus goes into the car before leave.
        borrow = self._borrow_allowed(snap, soc)
        snap.borrow_active = borrow
        for device in active:
            device.borrow = borrow
        first = [d for d in active if d.status.urgent or d.minimum_pending]
        rest = [d for d in active if d not in first]
        consumed = 0.0
        for device in sorted(first, key=self._dispatch_key):
            device.status.min_first = not device.status.urgent
            consumed += device.plan(full_budget - consumed, headroom, now)
        for device in sorted(rest, key=self._dispatch_key):
            device.status.min_first = False
            consumed += device.plan(budget - consumed, headroom, now)
        snap.allocated_w = consumed

        await self._async_apply(active)

        await self._control_export_limit(snap, active, soc, base_house_w)
        snap.reason = "battery_priority" if snap.battery_priority else "dispatching"
        return self._finish(snap)

    def _dispatch_key(self, device: ManagedDevice) -> tuple:
        """Sort key: urgent → away EV (refillable) → priority number."""
        from .devices import EvChargerDevice  # noqa: PLC0415

        away_first = isinstance(device, EvChargerDevice) and device.away_releases_battery()
        return (not device.status.urgent, not away_first, device.priority)

    def _finish(self, snap: DispatchSnapshot) -> DispatchSnapshot:
        snap.export_limit_raised = bool(self._export_raised)
        self._track_switching()
        snap.recommendations = self._recommendations()
        self._save_state()
        self._log_decision(snap)
        devices = sorted(self.devices.values(), key=lambda d: (not d.status.urgent, d.priority))
        if snap.reason == "missing_input" and self._last_live_data:
            # Keep gauges steady during a brief sensor gap, but never offer
            # stale watch-only actions and mark the payload as held.
            held = dict(self._last_live_data)
            held["stale"] = True
            held["recommendations"] = []
            held["reason"] = "missing_input"
            snap.live_data = held
        else:
            snap.live_data = self._decision_data(snap, devices, dt_util.now().isoformat())
            if snap.reason not in ("missing_input", "failsafe"):
                self._last_live_data = snap.live_data
            elif snap.reason == "failsafe":
                snap.live_data = {**snap.live_data, "stale": True}
        for subentry_id, device in self.devices.items():
            status = device.status
            snap.devices[subentry_id] = {
                "allocated_w": status.allocated_w,
                "actual_w": status.actual_w,
                "active": status.active,
                "urgent": status.urgent,
                "reason": status.reason if device.enabled else "disabled",
                **status.extra,
            }
        self._schedule_alert_edges(snap)
        return snap

    def _schedule_alert_edges(self, snap: DispatchSnapshot) -> None:
        """Detect at_risk / boost / order-completed edges and schedule notifies."""
        at_risk: set[str] = set()
        boosting: set[str] = set()
        completed_orders: list[tuple[str, ManagedDevice, dict[str, Any]]] = []
        for sid, device in self.devices.items():
            if device.status.extra.get("deadline_at_risk"):
                at_risk.add(sid)
            if getattr(device, "boost", None):
                boosting.add(sid)
            pop = getattr(device, "pop_order_completed", None)
            if callable(pop):
                info = pop()
                if info:
                    completed_orders.append((sid, device, info))
        new_risk = at_risk - self._at_risk_ids
        self._at_risk_ids = at_risk
        ended_boost = self._boost_ids - boosting
        self._boost_ids = boosting
        if new_risk or ended_boost or completed_orders:
            self.hass.async_create_task(
                self._async_handle_alert_edges(snap, new_risk, ended_boost, completed_orders)
            )

    async def _async_handle_alert_edges(
        self,
        snap: DispatchSnapshot,
        new_risk: set[str],
        ended_boost: set[str],
        completed_orders: list[tuple[str, ManagedDevice, dict[str, Any]]] | None = None,
    ) -> None:
        for sid, device, order in completed_orders or []:
            fire_event(
                self.hass,
                self,
                EVENT_CHARGE_ORDER,
                {
                    "device_id": sid,
                    "device": device.name,
                    "action": "completed",
                    **order,
                },
            )
            detail = f"{order.get('soc')} %"
            title, message = msg_order(
                self.hass, device.name, False, detail, completed=True
            )
            await async_notify(
                self.hass,
                self,
                title=title,
                message=message,
                notification_id=f"order_{sid}",
                enabled=bool(self.conf.get(CONF_NOTIFY_ON_ORDER)),
            )
            await async_dismiss(self.hass, self, f"order_{sid}")

        for sid in new_risk:
            device = self.devices.get(sid)
            if not device:
                continue
            extra = device.status.extra
            detail_bits = []
            if extra.get("deadline"):
                detail_bits.append(str(extra["deadline"])[11:16] if len(str(extra["deadline"])) > 16 else str(extra["deadline"]))
            if extra.get("deadline_plan"):
                detail_bits.append("NT: " + ", ".join(extra["deadline_plan"]))
            if extra.get("deadline_grid_kwh") is not None:
                detail_bits.append(f"síť {extra['deadline_grid_kwh']} kWh")
            detail = " · ".join(detail_bits)
            fire_event(
                self.hass,
                self,
                EVENT_DEADLINE_RISK,
                {
                    "device_id": sid,
                    "device": device.name,
                    "kind": device.kind,
                    "detail": detail,
                    "extra": {
                        k: extra.get(k)
                        for k in (
                            "deadline",
                            "deadline_plan",
                            "deadline_grid_kwh",
                            "deadline_soc",
                            "deadline_mode",
                        )
                    },
                },
            )
            title, message = msg_at_risk(self.hass, device.name, detail)
            await async_notify(
                self.hass,
                self,
                title=title,
                message=message,
                notification_id=f"at_risk_{sid}",
                enabled=bool(self.conf.get(CONF_NOTIFY_ON_AT_RISK)),
            )
            if self.conf.get(CONF_AI_OUTLOOK_CHECK) and self.conf.get(CONF_AI_TASK_ENTITY):
                today = dt_util.now().date().isoformat()
                if self._outlook_check_day.get(sid) != today:
                    self._outlook_check_day[sid] = today
                    self.hass.async_create_task(self._async_outlook_check(sid))

        for sid in ended_boost:
            device = self.devices.get(sid)
            if not device:
                continue
            fire_event(
                self.hass,
                self,
                EVENT_BOOST,
                {"device_id": sid, "device": device.name, "action": "finished"},
            )
            title, message = msg_boost(self.hass, device.name, started=False)
            await async_notify(
                self.hass,
                self,
                title=title,
                message=message,
                notification_id=f"boost_{sid}",
                enabled=bool(self.conf.get(CONF_NOTIFY_ON_BOOST)),
            )
            await async_dismiss(self.hass, self, f"boost_{sid}")

    async def _async_outlook_check(self, device_id: str) -> None:
        from .review import async_outlook_check  # noqa: PLC0415

        try:
            advice = await async_outlook_check(self, device_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("AI outlook check failed for %s: %s", device_id, err)
            return
        fire_event(self.hass, self, EVENT_OUTLOOK_CHECK, advice)
        title, message = msg_outlook_check(
            self.hass, advice.get("device", device_id), advice.get("advice", "")
        )
        await async_notify(
            self.hass,
            self,
            title=title,
            message=message,
            notification_id=f"outlook_{device_id}",
            enabled=bool(self.conf.get(CONF_NOTIFY_ON_AT_RISK)),
        )

    async def _async_on_failsafe(self, sensors: list[str]) -> None:
        fire_event(
            self.hass,
            self,
            EVENT_FAILSAFE,
            {"sensors": sensors},
        )
        title, message = msg_failsafe(self.hass, sensors)
        await async_notify(
            self.hass,
            self,
            title=title,
            message=message,
            notification_id=f"failsafe_{self.config_entry.entry_id}",
            enabled=bool(self.conf.get(CONF_NOTIFY_ON_FAILSAFE)),
        )

    async def _async_on_failsafe_cleared(self) -> None:
        fire_event(self.hass, self, EVENT_FAILSAFE_CLEARED, {})
        title, message = msg_failsafe_cleared(self.hass)
        await async_notify(
            self.hass,
            self,
            title=title,
            message=message,
            notification_id=f"failsafe_clear_{self.config_entry.entry_id}",
            enabled=bool(self.conf.get(CONF_NOTIFY_ON_FAILSAFE)),
        )
        await async_dismiss(self.hass, self, f"failsafe_{self.config_entry.entry_id}")
    def _log_decision(self, snap: DispatchSnapshot) -> None:
        """Log why the dispatcher decided what it did – only when it changes."""
        # Brief sensor gaps: hold without spamming "Chybí data ze střídače".
        if snap.reason == "missing_input" and self._decision[0] is not None:
            (
                snap.decision,
                snap.decision_lines,
                snap.decision_changed_at,
                snap.decision_data,
            ) = self._decision
            return
        devices = sorted(
            (d for d in self.devices.values()), key=lambda d: (not d.status.urgent, d.priority)
        )
        decision = (
            snap.reason,
            snap.dry_run,
            snap.battery_priority,
            snap.forecast_covers_battery,
            bool(self._export_raised),
            tuple(
                (d.name, d.enabled, d.status.reason, round(d.status.allocated_w, -2))
                for d in devices
            ),
        )
        if decision == self._last_decision:
            (
                snap.decision,
                snap.decision_lines,
                snap.decision_changed_at,
                snap.decision_data,
            ) = self._decision
            return
        self._last_decision = decision
        lines = [
            f"{snap.reason}: grid {_w(snap.grid_w)}, battery {_w(snap.battery_w)}, "
            f"SoC {snap.battery_soc}% → target {snap.effective_target_soc}% "
            f"({'battery first' if snap.battery_priority else 'devices first'}), "
            f"budget {_w(snap.budget_w)}, allocated {_w(snap.allocated_w)}, "
            f"export limit {'raised' if self._export_raised else 'normal'}"
            + ("" if snap.hdo_active is None else f", HDO {'on' if snap.hdo_active else 'off'}")
            + (", rounding up from battery" if snap.borrow_active else "")
            + (" [WATCH ONLY]" if snap.dry_run else "")
            + (f", stale: {', '.join(snap.stale_inputs)}" if snap.stale_inputs else "")
        ]
        if snap.forecast_remaining_kwh is not None:
            lines.append(
                f"  forecast {snap.forecast_remaining_kwh} kWh vs need "
                f"{snap.forecast_need_kwh} kWh ({snap.hours_until_sunset} h to sunset) → "
                f"{'covers' if snap.forecast_covers_battery else 'does not cover'}"
            )
        if snap.headroom_a is not None:
            lines.append(f"  breaker headroom {snap.headroom_a:.1f} A")
        for d in devices:
            status = d.status
            extra = ", ".join(f"{k}={v}" for k, v in status.extra.items() if v is not None)
            lines.append(
                f"  [{d.priority}] {d.name}: {status.reason if d.enabled else 'disabled'}, "
                f"allocated {_w(status.allocated_w)}, actual {_w(status.actual_w)}"
                + (" URGENT" if status.urgent else "")
                + (" MIN-FIRST" if status.min_first else "")
                + (f" ({extra})" if extra else "")
            )
        changed_at = dt_util.now().isoformat()
        self._decision = (
            self._summary(snap, devices),
            lines,
            changed_at,
            self._decision_data(snap, devices, changed_at),
        )
        snap.decision, snap.decision_lines, snap.decision_changed_at, snap.decision_data = (
            self._decision
        )
        self._decision_log = [{"at": changed_at, "text": self._decision[0]}, *self._decision_log][
            :DECISION_LOG_SIZE
        ]
        day_log = self.today()["log"]
        day_log.append(f"{dt_util.now():%H:%M} {self._decision[0]}")
        del day_log[:-DAY_LOG_SIZE]
        _LOGGER.debug("Decision changed\n%s", "\n".join(lines))

    def _outlook(self, snap: DispatchSnapshot) -> dict[str, Any]:
        """Rest-of-day expectation for the card and AI (deterministic)."""
        from .review import build_outlook  # noqa: PLC0415 - avoid import cycle at load

        return build_outlook(self, snap)

    def _decision_data(
        self, snap: DispatchSnapshot, devices: list[ManagedDevice], changed_at: str
    ) -> dict[str, Any]:
        """Structured decision for dashboards (localized reason texts)."""
        cs = (self.hass.config.language or "").startswith("cs")
        text = _SUMMARY_CS if cs else _SUMMARY_EN
        return {
            "changed_at": changed_at,
            "reason": snap.reason,
            "headline": self._summary(snap, []),
            "grid_w": snap.grid_w,
            "pv_w": snap.pv_w,
            "house_w": snap.house_w,
            "managed_w": round(snap.managed_w),
            "battery_w": snap.battery_w,
            "battery_soc": snap.battery_soc,
            "battery_target_soc": snap.effective_target_soc,
            "battery_priority": snap.battery_priority,
            "budget_w": round(snap.budget_w),
            "budget_parts": {k: round(v) for k, v in snap.budget_parts.items()},
            "allocated_w": round(snap.allocated_w),
            "forecast_kwh": snap.forecast_remaining_kwh,
            "forecast_need_kwh": snap.forecast_need_kwh,
            "forecast_covers": snap.forecast_covers_battery,
            "outlook": self._outlook(snap),
            "export_raised": bool(self._export_raised),
            "export_limit_now": state_float(self.hass, self.conf.get(CONF_EXPORT_LIMIT_ENTITY)),
            "export_limit_controlled": self._export_controlled(),
            "export_limit_target": (
                self._f(CONF_EXPORT_LIMIT_RAISED if self._export_raised else CONF_EXPORT_LIMIT_NORMAL)
                if self._export_controlled() and self._export_raised is not None
                else None
            ),
            "export_limit_unit": self._export_unit(),
            "hdo": snap.hdo_active,
            **self._tariff_data(),
            "borrow": snap.borrow_active,
            "dry_run": snap.dry_run,
            "recommendations": snap.recommendations,
            "log": self._decision_log,
            "review": self._review_for_ui(),
            "review_history": [
                {"date": r.get("date"), "score": r.get("score")} for r in self.reviews
            ],
            "review_enabled": bool(self.conf.get(CONF_AI_TASK_ENTITY)),
            "review_running": self.review_running,
            "review_asking": self.review_asking,
            "review_error": self.review_error,
            "morning_plan": self.morning_plan_for_ui(),
            "morning_running": self.morning_running,
            "charge_forecast": self.charge_forecast_for_ui(),
            "charge_running": self.charge_running,
            "stale_inputs": snap.stale_inputs,
            "stale": snap.reason in ("missing_input", "failsafe"),
            "headroom_a": None if snap.headroom_a is None else round(snap.headroom_a, 1),
            "devices": [
                {
                    "id": d.subentry_id,
                    "now": d.state_now(),
                    "pending": bool(d.pending_actions()) if d.enabled else False,
                    "name": d.name,
                    "kind": d.kind,
                    "priority": d.priority,
                    "state": (
                        text["reasons"].get(d.status.reason, d.status.reason)
                        if d.enabled
                        else text["reasons"]["disabled"]
                    ),
                    "active": d.status.active,
                    "allocated_w": round(d.status.allocated_w),
                    "actual_w": round(d.status.actual_w),
                    "urgent": d.status.urgent,
                    "min_first": d.status.min_first,
                    "today": {
                        k: round(v, 3)
                        for k, v in self._stats.get(d.subentry_id, {}).get("today", {}).items()
                    },
                    "current": d.status.extra.get("current"),
                    "phases": d.status.extra.get("phases"),
                    "temperature": d.status.extra.get("temperature"),
                    "soc": d.status.extra.get("soc"),
                    "target_soc": d.status.extra.get("target_soc"),
                    "target_soc_source": d.status.extra.get("target_soc_source"),
                    "deadline_soc": d.status.extra.get("deadline_soc"),
                    "deadline_mode": d.status.extra.get("deadline_mode"),
                    "deadline_source": d.status.extra.get("deadline_source"),
                    "deadline_eta": d.status.extra.get("deadline_eta"),
                    "deadline_phase": d.status.extra.get("deadline_phase"),
                    "deadline_chase_soc": d.status.extra.get("deadline_chase_soc"),
                    "charge_order": d.status.extra.get("charge_order"),
                    "boost": d.status.extra.get("boost"),
                    "away": d.status.extra.get("away"),
                    "battery_lend_kwh": d.status.extra.get("battery_lend_kwh"),
                    "car_budget_kwh": d.status.extra.get("car_budget_kwh"),
                    "legionella_due": d.status.extra.get("legionella_due"),
                    "connected": d.status.extra.get("connected"),
                    "plan": d.status.extra.get("deadline_plan"),
                    "at_risk": d.status.extra.get("deadline_at_risk"),
                }
                for d in devices
            ],
        }

    def _summary(self, snap: DispatchSnapshot, devices: list[ManagedDevice]) -> str:
        """One line for the 'last decision' entity and the logbook (≤ 255 chars)."""
        cs = (self.hass.config.language or "").startswith("cs")
        text = _SUMMARY_CS if cs else _SUMMARY_EN
        if snap.reason in ("disabled", "missing_input", "failsafe"):
            head = text[snap.reason]
        else:
            head = text["battery"].format(
                soc=_n(snap.battery_soc),
                target=_n(snap.effective_target_soc),
                who=text["battery_first" if snap.battery_priority else "devices_first"],
            )
            if snap.hdo_active is not None:
                head += " · " + text["hdo_on" if snap.hdo_active else "hdo_off"]
        if snap.dry_run:
            head = f"{text['dry_run']} · {head}"
        parts = [head]
        for d in devices:
            status = d.status
            reason = text["reasons"].get(status.reason, status.reason) if d.enabled else text["reasons"]["disabled"]
            part = f"{d.name}: {reason}"
            if status.allocated_w:
                part += f" {status.allocated_w:.0f} W"
            if d.kind == "ev_charger" and status.active:
                part += f" ({status.extra.get('phases')}f {status.extra.get('current')} A)"
            parts.append(part)
        summary = " · ".join(parts)
        return summary if len(summary) <= 255 else summary[:252] + "…"

    async def _control_export_limit(
        self,
        snap: DispatchSnapshot,
        active: list[ManagedDevice],
        soc: float,
        house_w: float | None,
    ) -> None:
        """Raise the limit at most once a day, lower it only when nothing can store.

        Raise (allow export) when production runs, something can still store
        energy (a device wants power) and the forecast says there will be
        surplus beyond the house and the battery – the raised limit makes that
        hidden surplus visible for the devices. Lower it only when there is
        nowhere to store (battery full, no device wants power) while producing;
        the end of production needs no write. Few writes spare the inverter's
        memory.
        """
        if not self._export_controlled():
            self._export_raised = None
            return
        self._sync_export_state()
        today = dt_util.now().date().isoformat()
        devices_want = any(d.status.wants_power and not d.status.urgent for d in active)
        can_store = devices_want or soc < self._f(CONF_BATTERY_FULL_SOC)
        producing = self._producing()

        if self._export_raised:
            # Without production nothing flows out, so the evening needs no
            # write – the limit only goes down when nothing can store any more.
            if producing and not can_store:
                await self._set_export_raised(False)
                self._export_lowered_day = today
            return

        if not producing or not devices_want:
            return
        if self._export_raised_day == today and not self.conf.get(CONF_EXPORT_RERAISE):
            return  # already raised (and lowered again) today
        if not self._export_makes_sense(snap, active, soc, house_w):
            return
        await self._set_export_raised(True)
        if not self.dry_run:
            self._export_raised_day = today

    def _recommendations(self) -> list[dict[str, Any]]:
        """Watch-only: what to switch by hand so reality follows the plan."""
        if not self.dry_run or not self.enabled:
            self._recommended_since = {}
            return []
        cs = (self.hass.config.language or "").startswith("cs")
        text = _SUMMARY_CS if cs else _SUMMARY_EN
        items: list[dict[str, Any]] = []
        for subentry_id, device in self.devices.items():
            if not device.enabled:
                continue
            actions = device.pending_actions()
            if not actions:
                continue
            parts = []
            for action in actions:
                kind = action[0]
                if kind == "current":
                    parts.append(text["rec_current"].format(a=action[1]))
                elif kind == "phases":
                    parts.append(text["rec_phases"].format(p=action[1]))
                elif kind == "start":
                    parts.append(text["rec_start"].format(a=action[1], p=action[2]))
                else:
                    parts.append(text[f"rec_{kind}"])
            items.append(
                {"id": subentry_id, "device": device.name, "text": f"{device.name}: {', '.join(parts)}"}
            )
        export = self._export_recommendation(text)
        if export:
            items.append(export)
        now = dt_util.now().isoformat()
        since = {i["id"]: self._recommended_since.get(i["id"] + i["text"], now) for i in items}
        self._recommended_since = {i["id"] + i["text"]: since[i["id"]] for i in items}
        for item in items:
            item["since"] = since[item["id"]]
        self._close_recommendations(items)
        return items

    def _close_recommendations(self, items: list[dict[str, Any]]) -> None:
        """Log how each watch-only recommendation ended (for the review)."""
        current = {i["id"] + i["text"]: i for i in items}
        day = self.today()
        hhmm = lambda iso: dt_util.as_local(dt_util.parse_datetime(iso)).strftime("%H:%M")  # noqa: E731
        for key, rec in list(self._open_recs.items()):
            if key in current:
                continue
            if key in self._executed_recs:
                outcome = "provedeno tlačítkem Provést"
            elif any(
                s.endswith(f"({SRC_EXTERNAL})") and s[:5] >= hhmm(rec["since"])
                for s in day.get("switches", {}).get(rec["id"], [])
            ):
                outcome = "vyřešeno mimo integraci (ručně, automatizací nebo zařízením)"
            else:
                outcome = "odvoláno – situace se změnila"
            day.setdefault("recommendations", []).append(
                {"from": hhmm(rec["since"]), "to": dt_util.now().strftime("%H:%M"),
                 "text": rec["text"], "outcome": outcome}
            )
            del day["recommendations"][:-DAY_LOG_SIZE]
            del self._open_recs[key]
            self._executed_recs.discard(key)
        for key, item in current.items():
            self._open_recs.setdefault(key, {"id": item["id"], "text": item["text"], "since": item["since"]})

    def open_recommendations(self) -> list[dict[str, str]]:
        return list(self._open_recs.values())

    def _account(self, grid: float, battery: float, hdo: bool | None, now: float) -> None:
        """Add this cycle's energy of every device, split by source, and its cost.

        Managed devices are the flexible loads, so grid import and battery
        discharge are attributed to them first (the house takes solar first):
        grid = min(import, devices), battery = min(discharge, rest), solar = rest.
        Grid energy is priced by the tariff in force (NT in HDO, VT otherwise).
        """
        last, self._last_accounting = self._last_accounting, now
        if last is None:
            return
        hours = min(now - last, 3 * float(self.conf[CONF_UPDATE_INTERVAL])) / 3600
        day = self.today()
        for key, watts in (
            ("import_kwh", max(grid, 0.0)),
            ("export_kwh", max(-grid, 0.0)),
            ("battery_charge_kwh", max(battery, 0.0)),
            ("battery_discharge_kwh", max(-battery, 0.0)),
        ):
            day[key] = day.get(key, 0.0) + watts * hours / 1000
        powers = {sid: max(d.status.actual_w, 0.0) for sid, d in self.devices.items()}
        total = sum(powers.values())
        today = dt_util.now().date().isoformat()
        grid_w = min(max(grid, 0.0), total)
        battery_w = min(max(-battery, 0.0), total - grid_w)
        solar_w = total - grid_w - battery_w
        price = self._f(CONF_PRICE_NT if hdo else CONF_PRICE_VT)
        for sid, power in powers.items():
            stats = self._stats.setdefault(sid, {k: 0.0 for k in STAT_KEYS})
            if stats.get("day") != today:
                stats["day"], stats["today"] = today, {k: 0.0 for k in STAT_KEYS}
            if power <= 0 or total <= 0:
                continue
            share = power / total
            add = {
                "total": power * hours / 1000,
                "solar": solar_w * share * hours / 1000,
                "battery": battery_w * share * hours / 1000,
                "grid": grid_w * share * hours / 1000,
            }
            add["cost"] = add["grid"] * price
            for key, value in add.items():
                stats[key] = stats.get(key, 0.0) + value
                stats["today"][key] = stats["today"].get(key, 0.0) + value

    def _review_for_ui(self) -> dict[str, Any] | None:
        """Latest review for the card (without the bulky day_data snapshot)."""
        if not self.reviews:
            return None
        return {k: v for k, v in self.reviews[0].items() if k != "day_data"}

    def morning_plan_for_ui(self) -> dict[str, Any] | None:
        """Morning plan for the card (without the bulky numeric snapshot)."""
        if not self.morning_plan:
            return None
        today = dt_util.now().date().isoformat()
        if self.morning_plan.get("date") != today:
            return None
        return {k: v for k, v in self.morning_plan.items() if k != "snapshot"}

    def morning_plan_for_ai(self) -> dict[str, Any] | None:
        """Morning plan for evening review (full, same calendar day only)."""
        if not self.morning_plan:
            return None
        today = dt_util.now().date().isoformat()
        if self.morning_plan.get("date") != today:
            return None
        return self.morning_plan

    def charge_forecast_for_ui(self) -> dict[str, Any] | None:
        """Charge forecast for the card (without bulky snapshot)."""
        if not self.charge_forecast:
            return None
        today = dt_util.now().date().isoformat()
        if self.charge_forecast.get("date") != today:
            return None
        return {k: v for k, v in self.charge_forecast.items() if k != "snapshot"}

    def charge_forecast_for_ai(self) -> dict[str, Any] | None:
        """Full charge forecast for evening review (same calendar day)."""
        if not self.charge_forecast:
            return None
        today = dt_util.now().date().isoformat()
        if self.charge_forecast.get("date") != today:
            return None
        return self.charge_forecast

    def _ai_busy(self) -> bool:
        return (
            self.review_running
            or self.review_asking
            or self.morning_running
            or self.charge_running
        )

    def _sync_review_live(self) -> None:
        """Push review / morning / charge flags into the current live_data for the card."""
        if self.data is None:
            return
        live = self.data.live_data
        live["review"] = self._review_for_ui()
        live["review_history"] = [
            {"date": r.get("date"), "score": r.get("score")} for r in self.reviews
        ]
        live["review_running"] = self.review_running
        live["review_asking"] = self.review_asking
        live["review_error"] = self.review_error
        live["morning_plan"] = self.morning_plan_for_ui()
        live["morning_running"] = self.morning_running
        live["charge_forecast"] = self.charge_forecast_for_ui()
        live["charge_running"] = self.charge_running
        if self._last_live_data is not None:
            self._last_live_data.update(
                {
                    "review": live["review"],
                    "review_history": live["review_history"],
                    "review_running": self.review_running,
                    "review_asking": self.review_asking,
                    "review_error": self.review_error,
                    "morning_plan": live["morning_plan"],
                    "morning_running": self.morning_running,
                    "charge_forecast": live["charge_forecast"],
                    "charge_running": self.charge_running,
                }
            )
        self.async_update_listeners()

    async def async_run_review(self) -> dict[str, Any]:
        """Run the AI review now (scheduled or on request) and keep it."""
        from .review import async_review  # noqa: PLC0415 - avoid an import cycle

        self.review_running = True
        self._sync_review_live()
        try:
            review, day_data = await async_review(self)
        except Exception as err:
            self.review_error = str(err)
            _LOGGER.warning("AI review failed: %s", err)
            raise
        finally:
            self.review_running = False
        self.review_error = None
        self._review_day_data = day_data
        self.reviews = [review, *self.reviews][:REVIEW_HISTORY]
        self._save_state()
        await self.async_request_refresh()
        self._sync_review_live()
        fire_event(
            self.hass,
            self,
            EVENT_REVIEW_DONE,
            {
                "date": review.get("date"),
                "score": review.get("score"),
                "summary": review.get("summary"),
                "suggestions": review.get("suggestions"),
                "proposals": [
                    {
                        "id": p.get("id"),
                        "target": p.get("target"),
                        "key": p.get("key"),
                        "status": p.get("status"),
                    }
                    for p in (review.get("proposals") or [])
                ],
                "problems": review.get("problems"),
                "outlook": review.get("outlook"),
            },
        )
        max_score = float(self.conf.get(CONF_NOTIFY_REVIEW_MAX_SCORE) or 7)
        if review_should_notify(review, max_score):
            title, message = msg_review(self.hass, review)
            await async_notify(
                self.hass,
                self,
                title=title,
                message=message,
                notification_id=f"review_{review.get('date')}",
                enabled=bool(self.conf.get(CONF_NOTIFY_ON_REVIEW)),
            )
        return review

    async def async_ask_review(self, question: str) -> dict[str, Any]:
        """Ask a follow-up about the latest review; append to its discussion thread."""
        from .review import (  # noqa: PLC0415
            DISCUSSION_MAX_TURNS,
            async_ask_review,
            build_day_data,
        )

        if self._ai_busy():
            raise HomeAssistantError("Review AI is already busy")
        self.review_asking = True
        self.review_error = None
        self._sync_review_live()
        try:
            day_data = self._review_day_data
            if day_data is None or (
                self.reviews and day_data.get("date") != self.reviews[0].get("date")
            ):
                day_data = build_day_data(self)
                self._review_day_data = day_data
            turn = await async_ask_review(self, question, day_data)
        except Exception as err:
            self.review_error = str(err)
            _LOGGER.warning("AI review discuss failed: %s", err)
            raise
        finally:
            self.review_asking = False
        thread = list(self.reviews[0].get("discussion") or [])
        thread.append(turn)
        self.reviews[0]["discussion"] = thread[-DISCUSSION_MAX_TURNS:]
        self._save_state()
        await self.async_request_refresh()
        self._sync_review_live()
        return turn

    def _find_proposal(self, proposal_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self.reviews:
            raise HomeAssistantError("No review to apply a proposal from")
        pid = (proposal_id or "").strip()
        if not pid:
            raise HomeAssistantError("Proposal id is required")
        for prop in self.reviews[0].get("proposals") or []:
            if prop.get("id") == pid:
                return self.reviews[0], prop
        raise HomeAssistantError(f"Unknown proposal id: {pid}")

    def _write_proposal_value(self, prop: dict[str, Any]) -> None:
        """Persist a validated proposal into entry options / device subentry."""
        key = prop["key"]
        value = prop["to"]
        entry = self.config_entry
        if prop.get("scope") == "hub":
            options = {**entry.data, **entry.options, key: value}
            self.hass.config_entries.async_update_entry(entry, options=options)
            return
        sid = prop.get("subentry_id")
        if not sid or sid not in entry.subentries:
            raise HomeAssistantError("Proposal device no longer exists")
        subentry = entry.subentries[sid]
        self.hass.config_entries.async_update_subentry(
            entry, subentry, data={**subentry.data, key: value}
        )

    async def async_apply_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Apply one pending AI setting proposal (never switches devices)."""
        if self._ai_busy():
            raise HomeAssistantError("Review AI is already busy")
        _review, prop = self._find_proposal(proposal_id)
        if prop.get("status") != "pending":
            raise HomeAssistantError(f"Proposal is not pending ({prop.get('status')})")
        self._write_proposal_value(prop)
        prop["status"] = "applied"
        prop["applied_at"] = dt_util.now().isoformat()
        self._save_state()
        await self.async_request_refresh()
        self._sync_review_live()
        fire_event(
            self.hass,
            self,
            EVENT_PROPOSAL_APPLIED,
            {
                "id": prop.get("id"),
                "target": prop.get("target"),
                "key": prop.get("key"),
                "from": prop.get("from"),
                "to": prop.get("to"),
                "reason": prop.get("reason"),
            },
        )
        return prop

    async def async_dismiss_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Mark a pending AI setting proposal as dismissed (no conf change)."""
        _review, prop = self._find_proposal(proposal_id)
        if prop.get("status") != "pending":
            raise HomeAssistantError(f"Proposal is not pending ({prop.get('status')})")
        prop["status"] = "dismissed"
        prop["dismissed_at"] = dt_util.now().isoformat()
        self._save_state()
        self._sync_review_live()
        return prop

    async def async_scheduled_review(self, now: datetime) -> None:
        """Called every minute: run the review once a day at the configured time."""
        if not self.conf.get(CONF_AI_TASK_ENTITY) or not self.conf.get(CONF_AI_REVIEW_ENABLED):
            return
        at = dt_util.parse_time(str(self.conf.get(CONF_AI_REVIEW_TIME) or ""))
        local = dt_util.as_local(now)
        if at is None or (local.hour, local.minute) != (at.hour, at.minute):
            return
        if self.reviews and self.reviews[0].get("date") == local.date().isoformat():
            return
        try:
            await self.async_run_review()
        except Exception:  # noqa: BLE001 - logged in async_run_review
            pass

    async def async_run_morning_brief(self) -> dict[str, Any]:
        """Run the morning AI day plan now and keep it as today's baseline."""
        from .review import async_morning_brief  # noqa: PLC0415

        if self._ai_busy():
            raise HomeAssistantError("Review AI is already busy")
        self.morning_running = True
        self.review_error = None
        self._sync_review_live()
        try:
            plan = await async_morning_brief(self)
        except Exception as err:
            self.review_error = str(err)
            _LOGGER.warning("AI morning brief failed: %s", err)
            raise
        finally:
            self.morning_running = False
        self.review_error = None
        self.morning_plan = plan
        self._save_state()
        await self.async_request_refresh()
        self._sync_review_live()
        # First charge forecast right after the morning baseline.
        if self.conf.get(CONF_AI_CHARGE_FORECAST):
            try:
                await self.async_run_charge_forecast()
            except Exception:  # noqa: BLE001 - logged in async_run_charge_forecast
                pass
        return plan

    async def async_scheduled_morning(self, now: datetime) -> None:
        """Called every minute: morning brief once a day at the configured time."""
        if not self.conf.get(CONF_AI_TASK_ENTITY) or not self.conf.get(CONF_AI_MORNING_ENABLED):
            return
        at = dt_util.parse_time(str(self.conf.get(CONF_AI_MORNING_TIME) or ""))
        local = dt_util.as_local(now)
        if at is None or (local.hour, local.minute) != (at.hour, at.minute):
            return
        if self.morning_plan and self.morning_plan.get("date") == local.date().isoformat():
            return
        try:
            await self.async_run_morning_brief()
        except Exception:  # noqa: BLE001 - logged in async_run_morning_brief
            pass

    async def async_run_charge_forecast(self) -> dict[str, Any]:
        """Refresh the mid-day AI charge forecast (does not touch morning_plan)."""
        from .review import async_charge_forecast  # noqa: PLC0415

        if self._ai_busy():
            raise HomeAssistantError("Review AI is already busy")
        self.charge_running = True
        self.review_error = None
        self._sync_review_live()
        try:
            forecast = await async_charge_forecast(self)
        except Exception as err:
            self.review_error = str(err)
            _LOGGER.warning("AI charge forecast failed: %s", err)
            raise
        finally:
            self.charge_running = False
        self.review_error = None
        self.charge_forecast = forecast
        self._save_state()
        await self.async_request_refresh()
        self._sync_review_live()
        return forecast

    def _charge_forecast_slot_due(self, now: datetime) -> bool:
        """True on a 3 h boundary after morning time, until sunset or 18:00."""
        morning = dt_util.parse_time(str(self.conf.get(CONF_AI_MORNING_TIME) or "07:00:00"))
        if morning is None:
            return False
        local = dt_util.as_local(now)
        if (local.hour, local.minute) == (morning.hour, morning.minute):
            return False  # morning brief owns this slot
        if local.minute != morning.minute:
            return False
        start = local.replace(hour=morning.hour, minute=morning.minute, second=0, microsecond=0)
        if local <= start:
            return False
        delta_h = (local - start).total_seconds() / 3600
        if delta_h < CHARGE_FORECAST_INTERVAL_H - 0.01:
            return False
        if abs(delta_h % CHARGE_FORECAST_INTERVAL_H) > 0.05:
            return False
        latest = local.replace(
            hour=CHARGE_FORECAST_LATEST_HOUR, minute=morning.minute, second=0, microsecond=0
        )
        if local > latest:
            return False
        snap = self.data
        if snap and snap.hours_until_sunset is not None and snap.hours_until_sunset <= 0:
            return False
        if self.charge_forecast and self.charge_forecast.get("date") == local.date().isoformat():
            at = dt_util.parse_datetime(str(self.charge_forecast.get("at") or ""))
            if at is not None:
                at_local = dt_util.as_local(at)
                if (at_local.hour, at_local.minute) == (local.hour, local.minute):
                    return False
        return True

    async def async_scheduled_charge_forecast(self, now: datetime) -> None:
        """Called every minute: refresh charge forecast every 3 h after morning."""
        if not self.conf.get(CONF_AI_TASK_ENTITY) or not self.conf.get(CONF_AI_CHARGE_FORECAST):
            return
        if not self._charge_forecast_slot_due(now):
            return
        try:
            await self.async_run_charge_forecast()
        except Exception:  # noqa: BLE001 - logged in async_run_charge_forecast
            pass

    def today(self) -> dict[str, Any]:
        """Today's overview bucket (reset at local midnight)."""
        date = dt_util.now().date().isoformat()
        if self._day.get("date") != date:
            self._day = {"date": date, "switches": {}, "log": [], "failsafe_s": 0.0}
        return self._day

    def _track_switching(self) -> None:
        """Record observed on/off changes per device (for the review)."""
        day = self.today()
        now = dt_util.now().strftime("%H:%M")
        for sid, device in self.devices.items():
            on = device.state_now().get("on")
            prev = self._prev_on.get(sid)
            if prev is not None and on is not None and on != prev:
                source, at = self._expected.pop(sid, (SRC_EXTERNAL, 0.0))
                if time.monotonic() - at > 120:
                    source = SRC_EXTERNAL
                day["switches"].setdefault(sid, []).append(f"{now} {'on' if on else 'off'} ({source})")
            self._prev_on[sid] = on
        if self.dry_run:
            # How often reality matched the plan (watch-only).
            match = day.setdefault("plan_match", {})
            for sid, device in self.devices.items():
                if device.enabled:
                    counts = match.setdefault(sid, [0, 0])
                    counts[1] += 1
                    counts[0] += 0 if device.pending_actions() else 1

    def device_stats(self, subentry_id: str) -> dict[str, Any]:
        return self._stats.get(subentry_id, {})

    def _tariff_data(self) -> dict[str, Any]:
        """Prices and the current / next low-tariff window for the card."""
        data: dict[str, Any] = {
            "price_vt": self._f(CONF_PRICE_VT) or None,
            "price_nt": self._f(CONF_PRICE_NT) or None,
        }
        if self.hdo.knows_future and self.hdo.windows:
            now = dt_util.now()
            current, upcoming = self.hdo.current_and_next(now)
            iso = lambda w: [w[0].isoformat(), w[1].isoformat()] if w else None  # noqa: E731
            data["hdo_window"] = iso(current)
            data["hdo_next_window"] = iso(upcoming)
        return data

    def _export_unit(self) -> str:
        entity_id = self.conf.get(CONF_EXPORT_LIMIT_ENTITY)
        state = self.hass.states.get(entity_id) if entity_id else None
        return (state.attributes.get("unit_of_measurement") if state else None) or ""

    def _export_recommendation(self, text: dict[str, Any]) -> dict[str, Any] | None:
        entity_id = self.conf.get(CONF_EXPORT_LIMIT_ENTITY)
        if not self._export_controlled() or self._export_raised is None:
            return None
        wanted = self._f(CONF_EXPORT_LIMIT_RAISED if self._export_raised else CONF_EXPORT_LIMIT_NORMAL)
        current = state_float(self.hass, entity_id)
        if current is None or abs(current - wanted) < 0.5:
            return None
        state = self.hass.states.get(entity_id)
        unit = (state.attributes.get("unit_of_measurement") if state else None) or ""
        key = "rec_export_raise" if self._export_raised else "rec_export_lower"
        return {
            "id": "export_limit",
            "device": "export_limit",
            "text": text[key].format(v=f"{wanted:g} {unit}".strip()),
        }

    async def async_execute_recommendation(self, rec_id: str | None = None) -> int:
        """Carry out one (or all) watch-only recommendations on request."""
        done = 0
        for item in list((self.data.recommendations if self.data else []) or []):
            if rec_id and item["id"] != rec_id:
                continue
            if item["id"] == "export_limit":
                value = self._f(CONF_EXPORT_LIMIT_RAISED if self._export_raised else CONF_EXPORT_LIMIT_NORMAL)
                await async_set_number(self.hass, self.conf[CONF_EXPORT_LIMIT_ENTITY], value)
            elif device := self.devices.get(item["id"]):
                self._expect_switch(device, SRC_RECOMMENDATION)
                await device.apply()
            self._executed_recs.add(item["id"] + item["text"])
            _LOGGER.info("Recommendation carried out by hand: %s", item["text"])
            done += 1
        if done:
            await self.async_request_refresh()
        return done

    def _ev_by_id_or_name(self, device_id: str | None = None, name: str | None = None):
        """Resolve an EV charger by subentry id or name."""
        from .devices import EvChargerDevice  # noqa: PLC0415

        if device_id and (device := self.devices.get(device_id)):
            if isinstance(device, EvChargerDevice):
                return device
            raise ValueError(f"{device_id} is not an EV charger")
        if name:
            for device in self.devices.values():
                if isinstance(device, EvChargerDevice) and device.name == name:
                    return device
            raise ValueError(f"No EV charger named {name!r}")
        evs = [d for d in self.devices.values() if isinstance(d, EvChargerDevice)]
        if len(evs) == 1:
            return evs[0]
        if not evs:
            raise ValueError("No EV charger configured")
        raise ValueError("Several EV chargers – pass device_id or name")

    async def async_set_ev_charge_order(
        self,
        target_soc: float,
        deadline: datetime,
        device_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """One-shot charge order: reach target_soc by deadline."""
        device = self._ev_by_id_or_name(device_id, name)
        order = device.set_charge_order(target_soc, deadline)
        self._save_state()
        await self.async_request_refresh()
        _LOGGER.info(
            "%s: charge order %s %% by %s",
            device.name,
            order["soc"],
            order["deadline"],
        )
        fire_event(
            self.hass,
            self,
            EVENT_CHARGE_ORDER,
            {"device_id": device.subentry_id, "device": device.name, "action": "set", **order},
        )
        title, message = msg_order(
            self.hass,
            device.name,
            True,
            f"{order['soc']} % · {order['deadline']}",
        )
        await async_notify(
            self.hass,
            self,
            title=title,
            message=message,
            notification_id=f"order_{device.subentry_id}",
            enabled=bool(self.conf.get(CONF_NOTIFY_ON_ORDER)),
        )
        return {"device": device.name, "id": device.subentry_id, **order}

    async def async_clear_ev_charge_order(
        self, device_id: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Cancel an active EV charge order."""
        device = self._ev_by_id_or_name(device_id, name)
        device.clear_charge_order()
        self._save_state()
        await self.async_request_refresh()
        fire_event(
            self.hass,
            self,
            EVENT_CHARGE_ORDER,
            {"device_id": device.subentry_id, "device": device.name, "action": "cleared"},
        )
        title, message = msg_order(self.hass, device.name, False)
        await async_notify(
            self.hass,
            self,
            title=title,
            message=message,
            notification_id=f"order_{device.subentry_id}",
            enabled=bool(self.conf.get(CONF_NOTIFY_ON_ORDER)),
        )
        await async_dismiss(self.hass, self, f"order_{device.subentry_id}")
        return {"device": device.name, "id": device.subentry_id, "cleared": True}

    async def async_start_ev_boost(
        self,
        target_soc: float | None = None,
        device_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Fast charge from now until target SoC; returns ETA estimate."""
        device = self._ev_by_id_or_name(device_id, name)
        boost = device.start_boost(target_soc)
        self._save_state()
        await self.async_request_refresh()
        extra = (self.data.devices.get(device.subentry_id) if self.data else {}) or {}
        _LOGGER.info(
            "%s: boost to %s %% (eta %s)",
            device.name,
            boost["soc"],
            extra.get("deadline_eta"),
        )
        result = {
            "device": device.name,
            "id": device.subentry_id,
            **boost,
            "eta": extra.get("deadline_eta"),
            "hours": extra.get("deadline_charging_h"),
            "need_kwh": extra.get("deadline_need_kwh"),
        }
        self._boost_ids.add(device.subentry_id)
        fire_event(
            self.hass,
            self,
            EVENT_BOOST,
            {"device_id": device.subentry_id, "action": "started", **result},
        )
        detail = f"→ {boost['soc']} %"
        if result.get("eta"):
            detail += f" · ETA {str(result['eta'])[11:16]}"
        title, message = msg_boost(self.hass, device.name, True, detail)
        await async_notify(
            self.hass,
            self,
            title=title,
            message=message,
            notification_id=f"boost_{device.subentry_id}",
            enabled=bool(self.conf.get(CONF_NOTIFY_ON_BOOST)),
        )
        return result

    async def async_stop_ev_boost(
        self, device_id: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Stop fast charging."""
        device = self._ev_by_id_or_name(device_id, name)
        device.stop_boost()
        self._boost_ids.discard(device.subentry_id)
        self._save_state()
        await self.async_request_refresh()
        fire_event(
            self.hass,
            self,
            EVENT_BOOST,
            {"device_id": device.subentry_id, "device": device.name, "action": "stopped"},
        )
        title, message = msg_boost(self.hass, device.name, False)
        await async_notify(
            self.hass,
            self,
            title=title,
            message=message,
            notification_id=f"boost_{device.subentry_id}",
            enabled=bool(self.conf.get(CONF_NOTIFY_ON_BOOST)),
        )
        await async_dismiss(self.hass, self, f"boost_{device.subentry_id}")
        return {"device": device.name, "id": device.subentry_id, "stopped": True}

    async def async_set_ev_away(
        self,
        leave_at: datetime,
        return_at: datetime | None = None,
        device_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Plan EV absence: release battery for surplus when forecast refills after leave."""
        device = self._ev_by_id_or_name(device_id, name)
        away = device.set_away(leave_at, return_at)
        self._save_state()
        await self.async_request_refresh()
        _LOGGER.info(
            "%s: away leave %s return %s",
            device.name,
            away.get("leave_at"),
            away.get("return_at"),
        )
        fire_event(
            self.hass,
            self,
            EVENT_AWAY,
            {"device_id": device.subentry_id, "device": device.name, "action": "set", **away},
        )
        extra = (self.data.devices.get(device.subentry_id) if self.data else {}) or {}
        return {
            "device": device.name,
            "id": device.subentry_id,
            **away,
            "battery_lend_kwh": extra.get("battery_lend_kwh"),
        }

    async def async_clear_ev_away(
        self, device_id: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Cancel a planned EV absence."""
        device = self._ev_by_id_or_name(device_id, name)
        device.clear_away()
        self._save_state()
        await self.async_request_refresh()
        fire_event(
            self.hass,
            self,
            EVENT_AWAY,
            {"device_id": device.subentry_id, "device": device.name, "action": "cleared"},
        )
        return {"device": device.name, "id": device.subentry_id, "cleared": True}

    async def _async_apply(self, active: list[ManagedDevice]) -> None:
        if self.dry_run:
            return  # "watch only": decisions are shown, nothing is switched
        for device in active:
            self._expect_switch(device, SRC_OPTIMIZER)
            try:
                await device.apply()
            except Exception:  # noqa: BLE001 - one device must not stop the others
                _LOGGER.exception("Failed to control %s", device.name)

    def _expect_switch(self, device: ManagedDevice, source: str) -> None:
        """Remember who causes an on/off change that ``apply`` is about to make."""
        if any(a[0] in ("on", "off", "start", "stop") for a in device.pending_actions()):
            self._expected[device.subentry_id] = (source, time.monotonic())

    async def _async_failsafe(
        self, snap: DispatchSnapshot, active: list[ManagedDevice], now: float
    ) -> DispatchSnapshot:
        """Inverter data lost: stop surplus-driven loads, keep deadline runs.

        Devices switch off through their normal delays and minimum times.
        Deadline runs (boiler minimum, car by the morning) do not depend on the
        inverter data and continue. The export limit is left as it is.
        """
        if not self._failsafe_logged:
            _LOGGER.warning(
                "No fresh data from %s – fail-safe: surplus-driven devices are stopped",
                ", ".join(snap.stale_inputs),
            )
            self._failsafe_logged = True
            self.hass.async_create_task(self._async_on_failsafe(list(snap.stale_inputs)))
        self._update_deadlines(snap, None, 0.0)
        day = self.today()
        day["failsafe_s"] = day.get("failsafe_s", 0.0) + float(self.conf[CONF_UPDATE_INTERVAL])
        headroom = self._headroom()
        for device in sorted(active, key=lambda d: (not d.status.urgent, d.priority)):
            device.borrow = False
            device.status.min_first = False
            device.plan(0.0 if device.status.urgent else -1e9, headroom, now)
        await self._async_apply(active)
        snap.reason = "failsafe"
        return self._finish(snap)

    def _borrow_allowed(self, snap: DispatchSnapshot, soc: float) -> bool:
        """Round devices up from the battery: from "full" down to full − band.

        Only while producing and the battery has no priority. The hysteresis
        keeps the battery in shallow cycles at the top and the devices from
        toggling; their own delays and minimum times still apply.
        """
        producing = self._producing()
        full = self._f(CONF_BATTERY_FULL_SOC)
        if not self.conf.get(CONF_BATTERY_BORROW) or snap.battery_priority or not producing:
            self._borrow_active = False
        elif soc >= full:
            self._borrow_active = True
        elif soc < full - BORROW_SOC_BAND:
            self._borrow_active = False
        return self._borrow_active

    def _export_makes_sense(
        self, snap: DispatchSnapshot, active: list[ManagedDevice], soc: float, house_w: float | None
    ) -> bool:
        """Will there be surplus for the devices beyond the house and the battery?"""
        remaining = self._read(CONF_FORECAST_REMAINING)
        if remaining is None:
            return True
        if any(d.minimum_pending for d in active):
            return True  # served before the battery
        house_kw = (house_w if house_w is not None else self._f(CONF_HOUSE_AVG_POWER_W)) / 1000
        battery_kwh = self._f(CONF_BATTERY_CAPACITY_KWH) * max(self._f(CONF_BATTERY_FULL_SOC) - soc, 0.0) / 100
        expected = remaining / self._f(CONF_FORECAST_SAFETY) - house_kw * self._hours_until_sunset()
        return expected - battery_kwh > 0

    def _export_controlled(self) -> bool:
        return bool(self.conf.get(CONF_EXPORT_LIMIT_ENTITY)) and bool(self.conf.get(CONF_EXPORT_CONTROL))

    def _sync_export_state(self) -> None:
        """Align internal raised/normal with the entity (restart + later drift).

        In watch-only mode the entity is never written, so once we have a
        virtual decision keep it – otherwise every refresh would snap back to
        the real (usually normal) limit and flap recommendations.
        """
        if self.dry_run and self._export_raised is not None:
            return
        current = state_float(self.hass, self.conf.get(CONF_EXPORT_LIMIT_ENTITY))
        if current is None:
            return
        raised, normal = self._f(CONF_EXPORT_LIMIT_RAISED), self._f(CONF_EXPORT_LIMIT_NORMAL)
        self._export_raised = abs(current - raised) < abs(current - normal)

    async def _set_export_raised(self, raised: bool, force: bool = False) -> None:
        entity_id = self.conf.get(CONF_EXPORT_LIMIT_ENTITY)
        if not self._export_controlled():
            # Hands off: the limit stays exactly as the user set it.
            self._export_raised = None
            return
        if raised == self._export_raised and not force:
            return
        if self.dry_run:
            _LOGGER.info("Watch only: would set the export limit %s", "raised" if raised else "normal")
            # Do not persist the day-flag – dry-run must not burn the real raise.
            self._export_raised = raised
            return
        value = self._f(CONF_EXPORT_LIMIT_RAISED if raised else CONF_EXPORT_LIMIT_NORMAL)
        current = state_float(self.hass, entity_id)
        try:
            if current != value:
                _LOGGER.info("Setting export limit to %s", value)
                await async_set_number(self.hass, entity_id, value)
            self._export_raised = raised
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to set export limit on %s", entity_id)

    # -- lifecycle ------------------------------------------------------------
    async def async_set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            await self.async_release_all()
        await self.async_request_refresh()

    async def async_set_device_enabled(self, subentry_id: str, enabled: bool) -> None:
        device = self.devices[subentry_id]
        device.enabled = enabled
        if not enabled:
            await device.release()
        await self.async_request_refresh()

    async def async_release_all(self) -> None:
        for device in self.devices.values():
            try:
                await device.release()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Failed to release %s", device.name)
        if self._export_controlled():
            await self._set_export_raised(False, force=True)


def config_structure(entry: ConfigEntry) -> tuple[Any, ...]:
    """Everything except tunables – a change here needs a full reload."""
    conf = {**entry.data, **entry.options}
    main = tuple(sorted((k, repr(v)) for k, v in conf.items() if k not in HUB_TUNABLE_KEYS))
    devices = []
    for subentry_id, subentry in sorted(entry.subentries.items()):
        tunable = {t.key for t in DEVICE_TUNABLES.get(subentry.subentry_type, ())}
        data = tuple(sorted((k, repr(v)) for k, v in subentry.data.items() if k not in tunable))
        devices.append((subentry_id, subentry.subentry_type, subentry.title, data))
    return main, tuple(devices)


def _w(value: float | None) -> str:
    return "?" if value is None else f"{value:.0f} W"


def _n(value: float | None) -> str:
    return "?" if value is None else f"{value:.0f}"


_SUMMARY_CS: dict[str, Any] = {
    "disabled": "Optimalizace vypnuta",
    "missing_input": "Chybí data ze střídače",
    "failsafe": "Pojistka: chybí data ze střídače, přebytková zařízení se vypínají",
    "dry_run": "Jen sledování",
    "rec_on": "zapnout",
    "rec_off": "vypnout",
    "rec_stop": "zastavit nabíjení",
    "rec_start": "spustit nabíjení ({a} A, {p} f)",
    "rec_current": "nastavit {a} A",
    "rec_phases": "přepnout na {p} f",
    "rec_export_raise": "Limit přetoku: zvýšit na {v}",
    "rec_export_lower": "Limit přetoku: snížit na {v}",
    "battery": "Baterie {soc} % → cíl {target} % ({who})",
    "battery_first": "přednost baterie",
    "devices_first": "přednost zařízení",
    "hdo_on": "HDO",
    "hdo_off": "VT",
    "reasons": {
        "init": "start", "disabled": "neřízeno", "unavailable": "nedostupné",
        "not_connected": "auto nepřipojeno", "temperature_reached": "nahřáto",
        "soc_reached": "nabito",
        "waiting_for_surplus": "čeká na přebytek", "starting": "spouští se",
        "running": "běží", "charging": "nabíjí", "no_surplus": "málo přebytků",
        "min_on_time": "min. doba zapnutí", "min_off_time": "min. doba vypnutí",
        "deadline_heating": "nahřívá do termínu", "deadline_charging": "nabíjí do termínu",
        "boost_charging": "rychlé nabíjení",
        "away_charging": "nabíjí před odjezdem",
        "away_deferred": "odloženo (odjezd auta)",
        "hold_until_deadline": "drží ~80 % do termínu",
        "breaker_limit": "omezeno jističem", "waiting_for_hdo": "čeká na HDO",
    },
}

_SUMMARY_EN: dict[str, Any] = {
    "disabled": "Optimization disabled",
    "missing_input": "Missing inverter data",
    "failsafe": "Fail-safe: no inverter data, surplus devices are stopped",
    "dry_run": "Watch only",
    "rec_on": "turn on",
    "rec_off": "turn off",
    "rec_stop": "stop charging",
    "rec_start": "start charging ({a} A, {p} ph)",
    "rec_current": "set {a} A",
    "rec_phases": "switch to {p} ph",
    "rec_export_raise": "Export limit: raise to {v}",
    "rec_export_lower": "Export limit: lower to {v}",
    "battery": "Battery {soc} % → target {target} % ({who})",
    "battery_first": "battery first",
    "devices_first": "devices first",
    "hdo_on": "low tariff",
    "hdo_off": "high tariff",
    "reasons": {
        "init": "starting", "disabled": "not controlled", "unavailable": "unavailable",
        "not_connected": "car not connected", "temperature_reached": "hot",
        "soc_reached": "charged",
        "waiting_for_surplus": "waiting for surplus", "starting": "starting",
        "running": "running", "charging": "charging", "no_surplus": "low surplus",
        "min_on_time": "min on time", "min_off_time": "min off time",
        "deadline_heating": "heating for deadline", "deadline_charging": "charging for deadline",
        "boost_charging": "fast charging",
        "away_charging": "charging before departure",
        "away_deferred": "deferred (EV away)",
        "hold_until_deadline": "holding ~80 % until deadline",
        "breaker_limit": "breaker limit", "waiting_for_hdo": "waiting for HDO",
    },
}
