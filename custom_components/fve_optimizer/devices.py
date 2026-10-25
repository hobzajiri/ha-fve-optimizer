"""Managed devices that the dispatcher hands surplus power to.

Every device type implements the same small interface:

* ``read()``      – refresh its view of the world from HA states
* ``plan()``      – decide what it wants given a power budget (pure logic)
* ``apply()``     – push the decision to HA (service calls, only on change)
* ``release()``   – switch off what the optimizer switched on

New device types only need a subclass and a subentry flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
import math
import time
from typing import Any

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .hdo import plan_windows
from .const import (
    CONF_CHARGE_SWITCH,
    BORROW_STEP_SHARE,
    CURRENT_UP_DELAY,
    CONF_CONNECTED_ENTITY,
    CONF_CURRENT_ENTITY,
    CONF_DEADLINE_EARLIEST,
    CONF_DEADLINE_ENABLED,
    CONF_DEADLINE_HDO_ONLY,
    CONF_DEADLINE_HYSTERESIS,
    CONF_DEADLINE_SAFETY,
    CONF_DEADLINE_TEMPERATURE,
    CONF_DEADLINE_TIME,
    CONF_EV_CAPACITY,
    CONF_EV_DEADLINE_ENABLED,
    CONF_EV_DEADLINE_HDO_ONLY,
    CONF_EV_DEADLINE_SAFETY,
    CONF_EV_DEADLINE_SOC,
    CONF_EV_DEADLINE_TIME,
    CONF_EV_EFFICIENCY,
    CONF_EV_SOC_SENSOR,
    CONF_EV_TARGET_HYSTERESIS,
    CONF_EV_TARGET_SOC,
    CONF_EV_TARGET_SOC_ENTITY,
    EV_HOLD_SOC,
    CONF_MAX_CURRENT,
    CONF_LEGIONELLA_ENABLED,
    CONF_LEGIONELLA_INTERVAL_DAYS,
    CONF_LEGIONELLA_TEMPERATURE,
    CONF_MAX_TEMP_HYSTERESIS,
    CONF_MAX_TEMPERATURE,
    CONF_MIN_BEFORE_BATTERY,
    CONF_MIN_CURRENT,
    CONF_MIN_OFF_TIME,
    CONF_MIN_ON_TIME,
    CONF_NAME,
    CONF_NOMINAL_POWER,
    CONF_OFF_DELAY,
    CONF_OFF_TOLERANCE,
    CONF_ON_DELAY,
    CONF_ON_MARGIN,
    CONF_PHASE_SWITCH,
    CONF_PHASE_SWITCH_INTERVAL,
    CONF_PHASES,
    CONF_POWER_SENSOR,
    CONF_PRIORITY,
    CONF_SWITCH_ENTITY,
    CONF_TANK_VOLUME,
    CONF_TEMPERATURE_SENSOR,
    DEVICE_DEFAULTS,
    NOMINAL_VOLTAGE,
    SUBENTRY_EV_CHARGER,
    SUBENTRY_SWITCHED,
)

_LOGGER = logging.getLogger(__name__)

# Energy to heat one litre of water by one kelvin.
WH_PER_LITRE_KELVIN = 1.163
# Extra time added before the computed start of deadline heating.
DEADLINE_LEAD = timedelta(minutes=10)
# Forgive tiny overruns vs HDO windows (rounding, sensor lag, safety ≈1.01 h in a 1 h slot).
DEADLINE_FIT_SLACK = timedelta(minutes=2)


def state_float(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Return the numeric state of an entity, or None."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
        return None
    try:
        return float(state.state)
    except ValueError:
        return None


_POWER_FACTORS = {"W": 1.0, "kW": 1000.0, "MW": 1_000_000.0}


def state_power(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Numeric power state in W (kW / MW sensors are converted)."""
    value = state_float(hass, entity_id)
    if value is None or not entity_id:
        return value
    state = hass.states.get(entity_id)
    unit = state.attributes.get("unit_of_measurement") if state else None
    return value * _POWER_FACTORS.get(unit, 1.0)


def state_on(hass: HomeAssistant, entity_id: str | None) -> bool | None:
    """Return True/False for an on/off entity, None when unknown."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    return state.state in (STATE_ON, "home", "connected", "plugged", "true")


async def async_turn(hass: HomeAssistant, entity_id: str, on: bool) -> None:
    """Turn any switch-like entity on or off."""
    await hass.services.async_call(
        "homeassistant",
        "turn_on" if on else "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )


async def async_set_number(hass: HomeAssistant, entity_id: str, value: float) -> None:
    """Set a number / input_number entity."""
    domain = entity_id.split(".", 1)[0]
    await hass.services.async_call(
        domain, "set_value", {"entity_id": entity_id, "value": value}, blocking=True
    )


@dataclass
class Headroom:
    """Remaining per-phase current before the main breaker trips."""

    amps: float = math.inf
    voltage: float = NOMINAL_VOLTAGE

    def watts(self, phases: int) -> float:
        return self.amps * self.voltage * phases

    def consume(self, watts: float, phases: int) -> None:
        if watts > 0 and math.isfinite(self.amps):
            self.amps -= watts / (self.voltage * phases)


class Debounce:
    """A condition must hold for ``delay`` seconds before it is accepted."""

    def __init__(self) -> None:
        self._since: float | None = None

    def check(self, condition: bool, now: float, delay: float) -> bool:
        if not condition:
            self._since = None
            return False
        if self._since is None:
            self._since = now
        return now - self._since >= delay

    def reset(self) -> None:
        self._since = None


@dataclass
class DeviceStatus:
    """What the device reports to diagnostic entities."""

    allocated_w: float = 0.0
    actual_w: float = 0.0
    active: bool = False
    wants_power: bool = False
    # Runs regardless of surplus (e.g. deadline heating) – planned first.
    urgent: bool = False
    # Below its minimum – got surplus before the battery in this cycle.
    min_first: bool = False
    reason: str = "init"
    extra: dict[str, Any] = field(default_factory=dict)


class ManagedDevice:
    """Base class for devices controlled by the dispatcher."""

    kind: str = ""

    def __init__(self, hass: HomeAssistant, subentry_id: str, config: dict[str, Any]) -> None:
        self.hass = hass
        self.subentry_id = subentry_id
        self.config: dict[str, Any] = {}
        self.update_config(config)
        self.voltage = NOMINAL_VOLTAGE
        # Low tariff (HDO) state from the hub: None when no HDO entity is set.
        self.hdo_active: bool | None = None
        # Known future HDO windows (EG.D, PRE, calendar, manual), else None.
        self.hdo_schedule: Any = None
        # May round its power up by half a step from a full battery this cycle.
        self.borrow = False
        # Away mode: defer surplus heating so the EV can take it before leave.
        self.away_defer_surplus = False
        # Solar energy (kWh) this device can still expect today, None = no forecast.
        self.solar_kwh: float | None = None
        self._solar_used = 0.0
        self.enabled: bool = True
        self.status = DeviceStatus()
        # While enabled the optimizer fully controls the device. ``_owned``
        # only decides whether disabling it should switch the load off.
        self._owned = False
        self._on_debounce = Debounce()
        self._off_debounce = Debounce()

    def update_config(self, config: dict[str, Any]) -> None:
        """Apply new settings in place (tunables change without reload)."""
        self.config = {**DEVICE_DEFAULTS, **config}

    def persistent(self) -> dict[str, Any]:
        """State that must survive a restart (stored by the coordinator)."""
        return {"owned": self._owned}

    @property
    def minimum_pending(self) -> bool:
        """Below its guaranteed minimum – gets surplus before the battery."""
        return False

    @property
    def surplus_thermal_dump(self) -> bool:
        """Heating only as surplus storage above the deadline minimum."""
        return False

    @property
    def wants_surplus_charge(self) -> bool:
        """EV (or similar) wants non-urgent surplus charging below its target."""
        return False

    def update_deadline(self, now: datetime) -> float:
        """Decide deadline (urgent) mode; return solar kWh the device counts on."""
        self.status.urgent = False
        return 0.0

    def outlook(self) -> dict[str, Any]:
        """Structured expectation for the rest of today (card + AI review)."""
        return {"mode": "off" if not self.enabled else "idle"}

    def state_now(self) -> dict[str, Any]:
        """Actual state for the recommendation table: on, current, phases."""
        return {}

    def pending_actions(self) -> list[tuple[Any, ...]]:
        """What :meth:`apply` would change now: ("on",), ("current", 8)…

        Used in watch-only mode to recommend manual actions.
        """
        return []

    def _solar_for(self, deadline: datetime, now: datetime, need_kwh: float) -> float:
        """Part of ``need_kwh`` the forecast covers before a deadline later today."""
        if self.solar_kwh is None or deadline.date() != now.date() or now >= deadline:
            return 0.0
        return min(need_kwh, max(self.solar_kwh, 0.0))

    def restore(self, data: dict[str, Any]) -> None:
        """Take over state saved by :meth:`persistent`."""
        if "owned" in data:
            self._owned = bool(data["owned"])

    @property
    def name(self) -> str:
        return self.config[CONF_NAME]

    @property
    def priority(self) -> int:
        return int(self.config[CONF_PRIORITY])

    def cfg(self, key: str) -> float:
        return float(self.config[key])

    # -- interface ------------------------------------------------------------
    def read(self) -> None:
        raise NotImplementedError

    def plan(self, budget: float, headroom: Headroom, now: float) -> float:
        """Decide the target and return the power (W) it will consume."""
        raise NotImplementedError

    async def apply(self) -> None:
        raise NotImplementedError

    async def release(self) -> None:
        raise NotImplementedError

    def _decide_on(self, is_on: bool, keep_ok: bool, start_ok: bool, now: float) -> bool:
        """Common hysteresis: delayed start, delayed stop."""
        if is_on:
            self._on_debounce.reset()
            return not self._off_debounce.check(not keep_ok, now, self.cfg(CONF_OFF_DELAY))
        self._off_debounce.reset()
        return self._on_debounce.check(start_ok, now, self.cfg(CONF_ON_DELAY))


class SwitchedDevice(ManagedDevice):
    """Fixed-power on/off load, e.g. a boiler on a Shelly relay."""

    kind = SUBENTRY_SWITCHED

    def __init__(self, hass: HomeAssistant, subentry_id: str, config: dict[str, Any]) -> None:
        super().__init__(hass, subentry_id, config)
        self._is_on: bool | None = None
        self._target_on = False
        # Last *observed* switch (not decision) – minimum on/off times count from it,
        # so watch-only mode and manual switching behave correctly.
        self._last_change: float = -math.inf
        self._temperature: float | None = None
        self._max_reached = False
        self._last_max_for_hyst: float | None = None
        self._legionella_last: datetime | None = None
        self._deadline_day: object | None = None  # date of an active deadline run
        # Date when the deadline temperature was already reached today. Draining
        # afterwards must not reopen deadline heating or "at risk" alerts.
        self._deadline_met_day: date | None = None
        self._deadline_info: dict[str, Any] = {}
        self._waiting_for_hdo = False
        # One-shot / calendar: heat to temp by deadline {"temp", "deadline", "source"}.
        self._heat_order: dict[str, Any] | None = None
        self._order_completed: dict[str, Any] | None = None
        # Satisfied calendar order (temp+deadline) – do not re-apply until the event ends.
        self._calendar_order_done: dict[str, Any] | None = None
        # Calendar absence: temporary cap on surplus max temperature (°C).
        self._max_temp_override: float | None = None

    @property
    def phases(self) -> int:
        return int(self.config[CONF_PHASES])

    @property
    def nominal_w(self) -> float:
        return self.cfg(CONF_NOMINAL_POWER)

    @property
    def switch_entity(self) -> str:
        return self.config[CONF_SWITCH_ENTITY]

    def read(self) -> None:
        was_on = self._is_on
        self._is_on = state_on(self.hass, self.switch_entity)
        if was_on is not None and self._is_on is not None and was_on != self._is_on:
            self._last_change = time.monotonic()
        measured = state_power(self.hass, self.config.get(CONF_POWER_SENSOR))
        if measured is not None:
            self.status.actual_w = max(measured, 0.0)
        else:
            self.status.actual_w = self.nominal_w if self._is_on else 0.0
        self._temperature = state_float(self.hass, self.config.get(CONF_TEMPERATURE_SENSOR))
        now = dt_util.now()
        if (
            self._temperature is not None
            and self._temperature >= self.cfg(CONF_LEGIONELLA_TEMPERATURE)
        ):
            self._legionella_last = now

    def update_deadline(self, now: datetime) -> float:
        self.status.urgent = self._deadline_due(now)
        return self._solar_used

    def outlook(self) -> dict[str, Any]:
        if not self.enabled:
            return {"mode": "off"}
        out: dict[str, Any] = {
            "mode": "surplus",
            "temperature": self._temperature,
            "max_temperature": self.max_temperature,
            "min_before_battery": bool(self.config.get(CONF_MIN_BEFORE_BATTERY)),
            "minimum_pending": self.minimum_pending,
            "urgent_now": self.status.urgent,
            "reason": self.status.reason,
            "heat_order": self.heat_order,
        }
        info = self._deadline_info
        order = self._heat_order
        if order and self._temperature is not None and self._temperature < float(order["temp"]):
            out.update({
                "mode": "deadline",
                "deadline": info.get("deadline") or order.get("deadline"),
                "deadline_start": info.get("deadline_start"),
                "target": float(order["temp"]),
                "deadline_mode": info.get("deadline_mode"),
                "plan": info.get("deadline_plan"),
                "need_kwh": info.get("deadline_need_kwh"),
                "solar_kwh": info.get("deadline_solar_kwh"),
                "grid_kwh": info.get("deadline_grid_kwh"),
                "heating_h": info.get("deadline_heating_h"),
                "at_risk": bool(info.get("deadline_at_risk")),
                "waiting_for_hdo": self._waiting_for_hdo,
                "source": order.get("source") or "order",
            })
            return out
        if not self.config.get(CONF_DEADLINE_ENABLED):
            return out
        if info.get("deadline_mode") == "met" or self._deadline_met_day == dt_util.now().date():
            out.update({
                "mode": "deadline_met",
                "deadline": info.get("deadline"),
                "target": self.deadline_temperature,
                "at_risk": False,
            })
            return out
        out.update({
            "mode": "deadline",
            "deadline": info.get("deadline"),
            "deadline_start": info.get("deadline_start"),
            "target": self.deadline_temperature,
            "deadline_mode": info.get("deadline_mode"),
            "plan": info.get("deadline_plan"),
            "need_kwh": info.get("deadline_need_kwh"),
            "solar_kwh": info.get("deadline_solar_kwh"),
            "grid_kwh": info.get("deadline_grid_kwh"),
            "heating_h": info.get("deadline_heating_h"),
            "at_risk": bool(info.get("deadline_at_risk")),
            "waiting_for_hdo": self._waiting_for_hdo,
            "source": info.get("deadline_source", "daily"),
        })
        return out

    def persistent(self) -> dict[str, Any]:
        data = super().persistent()
        last = self._legionella_last
        data.update({
            "legionella_last": last.isoformat() if last else None,
            "max_reached": self._max_reached,
            "deadline_day": self._deadline_day.isoformat() if self._deadline_day else None,
            "deadline_met_day": (
                self._deadline_met_day.isoformat() if self._deadline_met_day else None
            ),
            "heat_order": self._heat_order,
            "calendar_order_done": self._calendar_order_done,
        })
        return data

    def restore(self, data: dict[str, Any]) -> None:
        super().restore(data)
        if value := data.get("legionella_last"):
            self._legionella_last = dt_util.parse_datetime(value)
        if "max_reached" in data:
            self._max_reached = bool(data["max_reached"])
        if value := data.get("deadline_day"):
            try:
                self._deadline_day = date.fromisoformat(value)
            except ValueError:
                self._deadline_day = None
        if value := data.get("deadline_met_day"):
            try:
                self._deadline_met_day = date.fromisoformat(value)
            except ValueError:
                self._deadline_met_day = None
        order = data.get("heat_order")
        if isinstance(order, dict) and order.get("temp") is not None and order.get("deadline"):
            self._heat_order = {
                "temp": float(order["temp"]),
                "deadline": str(order["deadline"]),
                "source": str(order.get("source") or "manual"),
            }
        else:
            self._heat_order = None
        done = data.get("calendar_order_done")
        if isinstance(done, dict) and done.get("temp") is not None and done.get("deadline"):
            self._calendar_order_done = {
                "temp": float(done["temp"]),
                "deadline": str(done["deadline"]),
            }
        else:
            self._calendar_order_done = None

    @property
    def legionella_due(self) -> bool:
        """Anti-legionella heating is due (never done or older than the interval)."""
        if not self.config.get(CONF_LEGIONELLA_ENABLED) or self._temperature is None:
            return False
        if self._legionella_last is None:
            return True
        age = dt_util.now() - self._legionella_last
        return age >= timedelta(days=self.cfg(CONF_LEGIONELLA_INTERVAL_DAYS))

    @property
    def max_temperature(self) -> float:
        """Surplus storage limit – raised to the legionella temperature when due."""
        maximum = self.cfg(CONF_MAX_TEMPERATURE)
        if self.legionella_due:
            maximum = max(maximum, self.cfg(CONF_LEGIONELLA_TEMPERATURE))
        if self._max_temp_override is not None:
            maximum = min(maximum, float(self._max_temp_override))
        return maximum

    def set_heat_order(self, target_temp: float, deadline: datetime) -> dict[str, Any]:
        """One-shot: heat to ``target_temp`` by ``deadline``."""
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=dt_util.now().tzinfo)
        temp = round(float(target_temp), 1)
        self._heat_order = {
            "temp": temp,
            "deadline": deadline.isoformat(),
            "source": "manual",
        }
        return dict(self._heat_order)

    def clear_heat_order(self) -> None:
        """Cancel the active heat order.

        Calendar-sourced clears are remembered so sync does not re-apply the same
        event until it ends (same as after auto-complete).
        """
        order = self._heat_order
        if order and order.get("source") == "calendar":
            self._calendar_order_done = {
                "temp": float(order["temp"]),
                "deadline": str(order["deadline"]),
            }
        self._heat_order = None

    def complete_heat_order(self) -> dict[str, Any] | None:
        """Clear because the target temperature was reached; queue a completion event."""
        order = self.heat_order
        if not order:
            return None
        # Reuse clear so calendar orders stay suppressed until the event ends.
        self.clear_heat_order()
        self._order_completed = order
        return order

    def pop_order_completed(self) -> dict[str, Any] | None:
        """Return and clear a pending auto-completed order (for notify/event)."""
        event = self._order_completed
        self._order_completed = None
        return event

    def clear_calendar_heat_order(self) -> None:
        if self._heat_order and self._heat_order.get("source") == "calendar":
            self._heat_order = None
        # Event gone – allow the next occurrence (e.g. recurring) to apply.
        self._calendar_order_done = None

    def release_calendar_order_event(self) -> bool:
        """Calendar order event ended or was removed.

        Unmet calendar orders stay for catch-up past the event end (same as a
        manual order past its deadline). Only the satisfied/cancelled marker is
        cleared so a later occurrence can apply. Returns True if state changed.
        """
        changed = False
        if self._calendar_order_done is not None:
            self._calendar_order_done = None
            changed = True
        return changed

    def set_calendar_heat_order(self, target_temp: float, deadline: datetime) -> None:
        """Apply calendar order only when no manual order is active."""
        if self._heat_order and self._heat_order.get("source") == "manual":
            return
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=dt_util.now().tzinfo)
        temp = round(float(target_temp), 1)
        deadline_iso = deadline.isoformat()
        done = self._calendar_order_done
        if (
            done
            and float(done.get("temp", -1)) == temp
            and str(done.get("deadline")) == deadline_iso
        ):
            return
        # Already at/above the calendar target (e.g. after a manual order) –
        # mark this event satisfied instead of restarting deadline logic.
        if self._temperature is not None and self._temperature >= temp:
            self._heat_order = None
            self._calendar_order_done = {"temp": temp, "deadline": deadline_iso}
            return
        self._heat_order = {
            "temp": temp,
            "deadline": deadline_iso,
            "source": "calendar",
        }

    def set_max_temp_override(self, temp: float | None) -> None:
        self._max_temp_override = None if temp is None else float(temp)

    @property
    def heat_order(self) -> dict[str, Any] | None:
        return dict(self._heat_order) if self._heat_order else None

    def heat_need_kwh(self, target: float | None = None) -> float:
        """kWh to heat the tank from the current temperature to ``target``."""
        if self._temperature is None:
            return 0.0
        if target is None:
            if self.config.get(CONF_DEADLINE_ENABLED):
                target = self.deadline_temperature
            else:
                target = self.max_temperature
        delta_k = max(float(target) - self._temperature, 0.0)
        return self.cfg(CONF_TANK_VOLUME) * WH_PER_LITRE_KELVIN * delta_k / 1000

    @property
    def minimum_pending(self) -> bool:
        if self.away_defer_surplus:
            return False
        if not bool(self.config.get(CONF_MIN_BEFORE_BATTERY)) or self._temperature is None:
            return False
        if self._heat_order and self._temperature < float(self._heat_order["temp"]):
            return True
        return (
            bool(self.config.get(CONF_DEADLINE_ENABLED))
            and self._temperature < self.deadline_temperature
        )

    @property
    def surplus_thermal_dump(self) -> bool:
        """Deadline already met; only filling toward max surplus temperature."""
        if self.status.urgent or self.minimum_pending or self.away_defer_surplus:
            return False
        if self._temperature is None:
            return False
        floor = self.deadline_temperature if self.config.get(CONF_DEADLINE_ENABLED) else 0.0
        if self._heat_order:
            floor = max(floor, float(self._heat_order["temp"]))
        if not self.config.get(CONF_DEADLINE_ENABLED) and not self._heat_order:
            return False
        return floor <= self._temperature < self.max_temperature

    @property
    def deadline_temperature(self) -> float:
        target = self.cfg(CONF_DEADLINE_TEMPERATURE)
        if self.legionella_due:
            return max(target, self.cfg(CONF_LEGIONELLA_TEMPERATURE))
        return target

    def _deadline_due(self, now: datetime) -> bool:
        """Heat to the deadline temperature by the deadline, surplus or not.

        Only the part the solar forecast will not cover is heated from the grid
        (``solar_kwh`` from the coordinator).

        Just in time (default): starts when the remaining time is just enough
        to heat that part (energy at nominal power × safety factor).

        HDO only: heats from the grid only while the low tariff is active,
        between the "earliest" time and the deadline. The future HDO windows
        are unknown, so it uses every window in that span.

        Once started it keeps heating until the temperature is reached, even
        past the deadline (in HDO mode only while HDO lasts), but never into
        the next day. New runs start only before the deadline.

        Reaching the target temperature counts as the day's deadline done.
        Later draining (cold refill) does not reopen grid/HDO deadline heating
        or at-risk notifications – only surplus heating may warm it again.
        """
        self._deadline_info = {}
        self._waiting_for_hdo = False
        self._solar_used = 0.0
        order = self._heat_order
        if self._temperature is None:
            self._deadline_day = None
            return False
        # Resolve target + deadline: one-shot order wins over the daily schedule.
        order_active = False
        if order:
            order_temp = float(order["temp"])
            if self._temperature >= order_temp:
                self.complete_heat_order()
                order = None
            else:
                raw = dt_util.parse_datetime(str(order["deadline"]))
                if raw is None:
                    self.clear_heat_order()
                    order = None
                else:
                    if raw.tzinfo is None:
                        raw = raw.replace(tzinfo=now.tzinfo)
                    target = order_temp
                    deadline = raw
                    deadline_time = deadline.timetz().replace(tzinfo=None)
                    order_active = True
                    self._deadline_info["deadline_source"] = order.get("source") or "order"
        if not order_active:
            if not self.config.get(CONF_DEADLINE_ENABLED):
                self._deadline_day = None
                return False
            target = self.deadline_temperature
            deadline_time = dt_util.parse_time(str(self.config[CONF_DEADLINE_TIME]))
            if deadline_time is None:
                return False
            deadline = datetime.combine(now.date(), deadline_time, tzinfo=now.tzinfo)
        delta_k = max(target - self._temperature, 0.0)
        need_kwh = self.cfg(CONF_TANK_VOLUME) * WH_PER_LITRE_KELVIN * delta_k / 1000
        self._solar_used = self._solar_for(deadline, now, need_kwh)
        grid_kwh = need_kwh - self._solar_used
        hours = grid_kwh * 1000 / self.nominal_w * self.cfg(CONF_DEADLINE_SAFETY)
        start = deadline - timedelta(hours=hours) - DEADLINE_LEAD
        self._deadline_info.update({
            "deadline": deadline.isoformat(),
            "deadline_start": start.isoformat(),
            "deadline_need_kwh": round(need_kwh, 2),
            "deadline_solar_kwh": round(self._solar_used, 2),
            "deadline_grid_kwh": round(grid_kwh, 2),
            "deadline_heating_h": round(hours, 2),
            "heat_order": self.heat_order,
        })

        if self._temperature >= target:
            if order_active:
                self.complete_heat_order()
            else:
                self._deadline_met_day = now.date()
            self._deadline_day = None
            self._deadline_info["deadline_mode"] = "met"
            return False
        if not order_active and self._deadline_met_day == now.date():
            # Already hit the target earlier today (e.g. water was drawn off).
            self._deadline_day = None
            self._deadline_info["deadline_mode"] = "met"
            return False
        if grid_kwh <= 0:
            # The sun will do it – no grid heating planned (yet).
            self._deadline_info["deadline_mode"] = "solar"
            self._deadline_day = None
            return False

        hdo_only = bool(self.config.get(CONF_DEADLINE_HDO_ONLY)) and self.hdo_active is not None
        if hdo_only:
            earliest_time = dt_util.parse_time(str(self.config[CONF_DEADLINE_EARLIEST]))
            # Anchor to today so multi-day orders still use NT windows between now
            # and the deadline (not only slots on the deadline's calendar day).
            earliest = datetime.combine(
                now.date(), earliest_time or deadline_time, tzinfo=now.tzinfo
            )
            if earliest > deadline:
                earliest = datetime.combine(
                    deadline.date(), deadline_time, tzinfo=now.tzinfo
                ) - timedelta(hours=max(hours, 1))
            self._deadline_info.update(
                deadline_mode="hdo",
                deadline_start=earliest.isoformat(),
                # Not enough time left even with continuous heating (tiny slack).
                deadline_at_risk=now + timedelta(hours=hours) - DEADLINE_FIT_SLACK > deadline,
            )
            running = self._deadline_day == now.date()
            needs_heat = running or (
                self._temperature <= target - self.cfg(CONF_DEADLINE_HYSTERESIS)
            )
            windows = (
                self.hdo_schedule.windows_between(earliest, deadline)
                if self.hdo_schedule is not None
                else None
            )
            if windows is not None:
                # Known schedule: heat in the latest HDO windows that are just
                # enough, so surplus gets as much time as possible.
                plan, enough = plan_windows(
                    windows, now, timedelta(hours=hours), slack=DEADLINE_FIT_SLACK
                )
                self._deadline_info.update(
                    deadline_mode="hdo_plan",
                    deadline_plan=[f"{a:%H:%M}-{b:%H:%M}" for a, b in plan],
                    deadline_at_risk=not enough,
                    deadline_start=plan[0][0].isoformat() if plan else None,
                )
                if not needs_heat:
                    self._deadline_day = None
                    return False
                in_plan = any(a <= now < b for a, b in plan)
                # Past the deadline: catch up in any HDO (running daily, or one-shot order).
                catch_up = (
                    (running or order_active)
                    and now >= deadline
                    and bool(self.hdo_active)
                )
                if in_plan or catch_up:
                    self._deadline_day = now.date()
                    return True
                self._waiting_for_hdo = now < deadline or running or order_active
                return False

            # Unknown future (plain on/off entity): use every HDO window.
            in_window = earliest <= now < deadline and needs_heat
            order_catch_up = order_active and now >= deadline and needs_heat
            if not running and not in_window and not order_catch_up:
                self._deadline_day = None
                return False
            self._deadline_day = now.date()
            self._waiting_for_hdo = not self.hdo_active
            return bool(self.hdo_active)

        self._deadline_info["deadline_mode"] = "just_in_time"
        if self._deadline_day == now.date():
            return True  # already running – continue until target
        below = self._temperature <= target - self.cfg(CONF_DEADLINE_HYSTERESIS)
        # Daily: only before the deadline. One-shot order: also catch up after it.
        if (
            start <= now
            and below
            and (now < deadline or order_active)
        ):
            self._deadline_day = now.date()
            return True
        self._deadline_day = None
        return False

    def _blocked(self) -> str | None:
        if self._is_on is None:
            return "unavailable"
        if self._temperature is not None:
            # Surplus storage limit with hysteresis: after reaching the maximum
            # the boiler waits until the water cools down by the hysteresis.
            # Raising the max clears the latch when temperature is still below it.
            maximum = self.max_temperature
            if self._last_max_for_hyst is not None and maximum > self._last_max_for_hyst:
                if self._temperature < maximum:
                    self._max_reached = False
            self._last_max_for_hyst = maximum
            if self._temperature >= maximum:
                self._max_reached = True
            elif self._temperature <= maximum - self.cfg(CONF_MAX_TEMP_HYSTERESIS):
                self._max_reached = False
            if self._max_reached:
                return "temperature_reached"
        return None

    def plan(self, budget: float, headroom: Headroom, now: float) -> float:
        status = self.status
        status.extra = {
            "temperature": self._temperature,
            "heat_order": self.heat_order,
            "max_temperature": self.max_temperature,
            "supports_order": bool(self.config.get(CONF_TEMPERATURE_SENSOR)),
            **self._deadline_info,
        }
        if self.config.get(CONF_LEGIONELLA_ENABLED):
            status.extra["legionella_due"] = self.legionella_due
            status.extra["legionella_last"] = (
                self._legionella_last.isoformat() if self._legionella_last else None
            )
        is_on = bool(self._is_on)
        blocked = "unavailable" if self._is_on is None else None
        if not blocked and not status.urgent:
            blocked = self._blocked()
        # Planned EV departure: afternoon sun will reheat – free surplus for the car.
        if not blocked and not status.urgent and self.away_defer_surplus:
            blocked = "away_deferred"
        status.wants_power = blocked is None

        if blocked:
            target, reason = False, blocked
        elif status.urgent:
            # Deadline heating ignores the surplus but never the main breaker.
            target = is_on or headroom.watts(self.phases) >= self.nominal_w
            reason = "deadline_heating" if target else "breaker_limit"
            self._on_debounce.reset()
            self._off_debounce.reset()
        else:
            # From a full battery up to half of the power may be borrowed.
            borrow = self.nominal_w * BORROW_STEP_SHARE if self.borrow else 0.0
            keep_ok = budget + borrow >= status.actual_w - self.cfg(CONF_OFF_TOLERANCE)
            start_ok = (
                budget + borrow >= self.nominal_w + self.cfg(CONF_ON_MARGIN)
                and headroom.watts(self.phases) >= self.nominal_w
            )
            target = self._decide_on(is_on, keep_ok, start_ok, now)
            if target:
                reason = "running"
            elif self._waiting_for_hdo and not start_ok:
                reason = "waiting_for_hdo"
            elif is_on:
                reason = "no_surplus"
            else:
                reason = "waiting_for_surplus" if not start_ok else "starting"

        # Minimum on/off times protect contactors – but never override a hard stop
        # (temperature / unavailable) or an urgent breaker shed.
        if target != is_on:
            min_time = self.cfg(CONF_MIN_ON_TIME if is_on else CONF_MIN_OFF_TIME)
            hard_stop = blocked is not None or reason == "breaker_limit"
            if now - self._last_change < min_time and not hard_stop:
                target = is_on
                reason = "min_on_time" if is_on else "min_off_time"

        self._target_on = target
        # Ownership is claimed only in ``apply()`` (when we actually switch).
        # Claiming here would stick in watch-only mode and later ``release()``
        # could turn off loads the integration never controlled.
        status.active = target
        status.reason = reason
        if not target:
            status.allocated_w = 0.0
        else:
            status.allocated_w = status.actual_w if is_on else self.nominal_w
            if not is_on:
                headroom.consume(self.nominal_w, self.phases)
        return status.allocated_w

    def state_now(self) -> dict[str, Any]:
        return {"on": self._is_on}

    def pending_actions(self) -> list[tuple[Any, ...]]:
        if self._is_on is None or self._target_on == self._is_on:
            return []
        return [("on",) if self._target_on else ("off",)]

    async def apply(self) -> None:
        if self._is_on is None:
            return
        if self._target_on:
            self._owned = True
        if self._target_on == self._is_on:
            return
        _LOGGER.debug("%s: turning %s", self.name, "on" if self._target_on else "off")
        await async_turn(self.hass, self.switch_entity, self._target_on)
        self._owned = self._target_on

    async def release(self) -> None:
        if self._owned and state_on(self.hass, self.switch_entity):
            await async_turn(self.hass, self.switch_entity, False)
        self._owned = False
        self.status = DeviceStatus(reason="disabled")

class EvChargerDevice(ManagedDevice):
    """Current-regulated EV charger with optional 1/3 phase switching."""

    kind = SUBENTRY_EV_CHARGER

    def __init__(self, hass: HomeAssistant, subentry_id: str, config: dict[str, Any]) -> None:
        super().__init__(hass, subentry_id, config)
        self._charging: bool | None = None
        self._connected: bool | None = None
        self._current_a: float | None = None
        self._phases_now = int(self.config[CONF_PHASES])
        self._target_on = False
        self._target_a = int(self.config[CONF_MIN_CURRENT])
        self._target_phases = self._phases_now
        self._last_phase_switch: float = -math.inf
        self._plan_now: float = 0.0
        self._phase_debounce = Debounce()
        # Damping of current changes: (since, lowest wanted) for increases,
        # since for small decreases.
        self._up: tuple[float, int] | None = None
        self._down_since: float | None = None
        self._ev_soc: float | None = None
        self._soc_reached = False
        self._last_target_for_hyst: float | None = None
        self._target_soc_entity_last: float | None = None
        self._deadline_day: date | None = None  # active catch-up day (like boiler)
        self._deadline_active: datetime | None = None  # deadline being charged for
        self._deadline_info: dict[str, Any] = {}
        self._waiting_for_hdo = False
        # One-shot "charge order": higher SoC by a given datetime (trip / appointment).
        self._charge_order: dict[str, Any] | None = None
        # Set when SoC reaches the order target; coordinator consumes for notify/event.
        self._order_completed: dict[str, Any] | None = None
        # Satisfied calendar charge order – do not re-apply until the event ends.
        self._calendar_order_done: dict[str, Any] | None = None
        # Fast charge from now: full current until target SoC (ignores surplus/HDO).
        self._boost: dict[str, Any] | None = None
        # Planned absence: leave_at / optional return_at – prefer surplus into EV before leave.
        self._away: dict[str, Any] | None = None
        # Dismissed calendar away (leave/return) – do not re-apply until the event ends.
        self._calendar_away_done: dict[str, Any] | None = None
        # House-battery kWh the forecast can refill after leave (info + release battery).
        self.battery_lend_kwh: float = 0.0
        # Afternoon sun covers battery refill + boiler – prefer the car until leave.
        self.away_prefer: bool = False
        # Estimated kWh that can go into the car before leave (display).
        self.away_car_budget_kwh: float = 0.0

    @property
    def min_a(self) -> int:
        return int(self.config[CONF_MIN_CURRENT])

    @property
    def max_a(self) -> int:
        return max(int(self.config[CONF_MAX_CURRENT]), self.min_a)

    @property
    def can_switch_phases(self) -> bool:
        return bool(self.config.get(CONF_PHASE_SWITCH))

    def _power(self, amps: float, phases: int) -> float:
        return amps * self.voltage * phases

    def persistent(self) -> dict[str, Any]:
        data = super().persistent()
        data.update({
            "soc_reached": self._soc_reached,
            "deadline_day": self._deadline_day.isoformat() if self._deadline_day else None,
            "target_soc_entity_last": self._target_soc_entity_last,
            "charge_order": self._charge_order,
            "calendar_order_done": self._calendar_order_done,
            "calendar_away_done": self._calendar_away_done,
            "boost": self._boost,
            "away": self._away,
        })
        return data

    def restore(self, data: dict[str, Any]) -> None:
        super().restore(data)
        if "soc_reached" in data:
            self._soc_reached = bool(data["soc_reached"])
        if value := data.get("deadline_day"):
            try:
                self._deadline_day = date.fromisoformat(value)
            except ValueError:
                self._deadline_day = None
        if data.get("target_soc_entity_last") is not None:
            try:
                self._target_soc_entity_last = float(data["target_soc_entity_last"])
            except (TypeError, ValueError):
                self._target_soc_entity_last = None
        order = data.get("charge_order")
        if isinstance(order, dict) and order.get("soc") is not None and order.get("deadline"):
            self._charge_order = {
                "soc": float(order["soc"]),
                "deadline": str(order["deadline"]),
                "source": str(order.get("source") or "manual"),
            }
        else:
            self._charge_order = None
        done = data.get("calendar_order_done")
        if isinstance(done, dict) and done.get("soc") is not None and done.get("deadline"):
            self._calendar_order_done = {
                "soc": float(done["soc"]),
                "deadline": str(done["deadline"]),
            }
        else:
            self._calendar_order_done = None
        boost = data.get("boost")
        if isinstance(boost, dict) and boost.get("soc") is not None:
            self._boost = {"soc": float(boost["soc"])}
        else:
            self._boost = None
        away = data.get("away")
        if isinstance(away, dict) and away.get("leave_at"):
            restored: dict[str, Any] = {
                "leave_at": str(away["leave_at"]),
                "source": str(away.get("source") or "manual"),
            }
            if away.get("return_at"):
                restored["return_at"] = str(away["return_at"])
            self._away = restored
        else:
            self._away = None
        away_done = data.get("calendar_away_done")
        if isinstance(away_done, dict) and away_done.get("leave_at"):
            restored_done: dict[str, Any] = {"leave_at": str(away_done["leave_at"])}
            if away_done.get("return_at"):
                restored_done["return_at"] = str(away_done["return_at"])
            self._calendar_away_done = restored_done
        else:
            self._calendar_away_done = None

    def set_charge_order(self, target_soc: float, deadline: datetime) -> dict[str, Any]:
        """One-shot: charge to ``target_soc`` by ``deadline`` (grid/HDO as needed)."""
        soc = max(1.0, min(100.0, float(target_soc)))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=dt_util.now().tzinfo)
        self._boost = None  # order replaces an active boost
        self._charge_order = {
            "soc": soc,
            "deadline": deadline.isoformat(),
            "source": "manual",
        }
        return dict(self._charge_order)

    def clear_charge_order(self) -> None:
        """Cancel the active charge order.

        Calendar-sourced clears are remembered so sync does not re-apply the same
        event until it ends (same as after auto-complete).
        """
        order = self._charge_order
        if order and order.get("source") == "calendar":
            self._calendar_order_done = {
                "soc": float(order["soc"]),
                "deadline": str(order["deadline"]),
            }
        self._charge_order = None

    def clear_calendar_charge_order(self) -> None:
        if self._charge_order and self._charge_order.get("source") == "calendar":
            self._charge_order = None
        self._calendar_order_done = None

    def release_calendar_order_event(self) -> bool:
        """Calendar charge-order event ended or was removed; keep unmet catch-up."""
        changed = False
        if self._calendar_order_done is not None:
            self._calendar_order_done = None
            changed = True
        return changed

    def set_calendar_charge_order(self, target_soc: float, deadline: datetime) -> None:
        """Apply calendar order only when no manual order / boost is active."""
        if self._boost:
            return  # boost outranks calendar; do not clear it
        if self._charge_order and self._charge_order.get("source") == "manual":
            return
        soc = max(1.0, min(100.0, float(target_soc)))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=dt_util.now().tzinfo)
        deadline_iso = deadline.isoformat()
        done = self._calendar_order_done
        if (
            done
            and float(done.get("soc", -1)) == soc
            and str(done.get("deadline")) == deadline_iso
        ):
            return
        # Already at/above the calendar SoC (e.g. after a manual order / boost) –
        # mark this event satisfied instead of restarting deadline logic.
        if self._ev_soc is not None and self._ev_soc >= soc:
            self._charge_order = None
            self._calendar_order_done = {"soc": soc, "deadline": deadline_iso}
            return
        self._charge_order = {
            "soc": soc,
            "deadline": deadline_iso,
            "source": "calendar",
        }

    def complete_charge_order(self) -> dict[str, Any] | None:
        """Clear because the target SoC was reached; queue a completion event."""
        order = self.charge_order
        if not order:
            return None
        self.clear_charge_order()
        self._order_completed = order
        return order

    def pop_order_completed(self) -> dict[str, Any] | None:
        """Return and clear a pending auto-completed order (for notify/event)."""
        event = self._order_completed
        self._order_completed = None
        return event

    @property
    def charge_order(self) -> dict[str, Any] | None:
        return dict(self._charge_order) if self._charge_order else None

    def start_boost(self, target_soc: float | None = None) -> dict[str, Any]:
        """Charge at full power from now until ``target_soc`` (default: surplus max)."""
        if target_soc is None:
            target_soc = self.target_soc if self._ev_soc is not None else 100.0
        soc = max(1.0, min(100.0, float(target_soc)))
        # Drop the active order without marking calendar done – set_calendar_*
        # already skips while boost is on; after stop_boost the event can return.
        self._charge_order = None
        self._boost = {"soc": soc}
        return dict(self._boost)

    def stop_boost(self) -> None:
        self._boost = None

    @property
    def boost(self) -> dict[str, Any] | None:
        return dict(self._boost) if self._boost else None

    def set_away(
        self, leave_at: datetime, return_at: datetime | None = None
    ) -> dict[str, Any]:
        """Plan absence: fill the car before ``leave_at`` (surplus + lendable battery)."""
        if leave_at.tzinfo is None:
            leave_at = leave_at.replace(tzinfo=dt_util.now().tzinfo)
        away: dict[str, Any] = {"leave_at": leave_at.isoformat(), "source": "manual"}
        if return_at is not None:
            if return_at.tzinfo is None:
                return_at = return_at.replace(tzinfo=leave_at.tzinfo)
            if return_at <= leave_at:
                raise ValueError("return_at must be after leave_at")
            away["return_at"] = return_at.isoformat()
        self._away = away
        return dict(self._away)

    def set_calendar_away(
        self, leave_at: datetime, return_at: datetime | None = None
    ) -> None:
        """Apply calendar away only when no manual away is active."""
        if self._away and self._away.get("source") == "manual":
            return
        if leave_at.tzinfo is None:
            leave_at = leave_at.replace(tzinfo=dt_util.now().tzinfo)
        leave_iso = leave_at.isoformat()
        ret_iso: str | None = None
        if return_at is not None:
            if return_at.tzinfo is None:
                return_at = return_at.replace(tzinfo=leave_at.tzinfo)
            if return_at > leave_at:
                ret_iso = return_at.isoformat()
        done = self._calendar_away_done
        if (
            done
            and str(done.get("leave_at")) == leave_iso
            and done.get("return_at") == ret_iso
        ):
            return
        away: dict[str, Any] = {"leave_at": leave_iso, "source": "calendar"}
        if ret_iso is not None:
            away["return_at"] = ret_iso
        self._away = away

    def clear_calendar_away(self) -> None:
        """Event gone – drop calendar away and allow a later occurrence."""
        if self._away and self._away.get("source") == "calendar":
            self._away = None
            self.battery_lend_kwh = 0.0
            self.away_prefer = False
            self.away_car_budget_kwh = 0.0
        self._calendar_away_done = None

    def clear_away(self) -> None:
        """Cancel away. Calendar clears are remembered until the event ends."""
        if self._away and self._away.get("source") == "calendar":
            done: dict[str, Any] = {"leave_at": str(self._away["leave_at"])}
            if self._away.get("return_at"):
                done["return_at"] = str(self._away["return_at"])
            self._calendar_away_done = done
        self._away = None
        self.battery_lend_kwh = 0.0
        self.away_prefer = False
        self.away_car_budget_kwh = 0.0

    @property
    def away(self) -> dict[str, Any] | None:
        return dict(self._away) if self._away else None

    def _parse_away_time(self, key: str, now: datetime) -> datetime | None:
        if not self._away or not self._away.get(key):
            return None
        raw = dt_util.parse_datetime(str(self._away[key]))
        if raw is None:
            return None
        if raw.tzinfo is None:
            raw = raw.replace(tzinfo=now.tzinfo)
        return raw

    def _away_housekeep(self, now: datetime) -> None:
        """Auto-clear after return, or after leave once the car is unplugged."""
        if not self._away:
            return
        leave = self._parse_away_time("leave_at", now)
        ret = self._parse_away_time("return_at", now)
        if leave is None:
            self.clear_away()
            return
        if ret is not None and now >= ret:
            self.clear_away()
            return
        if now >= leave and not self._connected:
            self.clear_away()

    def _away_pending(self, now: datetime) -> bool:
        """Car is home today and will leave later – prefer surplus into the EV."""
        leave = self._parse_away_time("leave_at", now)
        if leave is None or leave.date() != now.date() or now >= leave:
            return False
        if not self._connected or self._ev_soc is None:
            return False
        return self._ev_soc < self.target_soc

    def away_releases_battery(self, now: datetime | None = None) -> bool:
        """Afternoon forecast covers battery (+ boiler) after leave – prefer the car."""
        now = now or dt_util.now()
        return self._away_pending(now) and bool(self.away_prefer)

    def _boost_eta(self, now: datetime, target: float) -> tuple[float, datetime | None]:
        """Return (hours_needed, eta) at max charger power, or (0, None) if done."""
        if self._ev_soc is None:
            return 0.0, None
        need_kwh = (
            max(target - self._ev_soc, 0.0) / 100 * self.cfg(CONF_EV_CAPACITY)
            / self.cfg(CONF_EV_EFFICIENCY)
        )
        if need_kwh <= 0:
            return 0.0, None
        phases = 3 if self.can_switch_phases else int(self.config[CONF_PHASES])
        power_w = self._power(self.max_a, phases)
        if power_w <= 0:
            return 0.0, None
        hours = need_kwh * 1000 / power_w
        return hours, now + timedelta(hours=hours)

    def read(self) -> None:
        self._charging = state_on(self.hass, self.config[CONF_CHARGE_SWITCH])
        self._current_a = state_float(self.hass, self.config[CONF_CURRENT_ENTITY])
        connected_entity = self.config.get(CONF_CONNECTED_ENTITY)
        self._connected = state_on(self.hass, connected_entity) if connected_entity else True
        if self.can_switch_phases:
            three = state_on(self.hass, self.config[CONF_PHASE_SWITCH])
            if three is not None:
                self._phases_now = 3 if three else 1
        else:
            self._phases_now = int(self.config[CONF_PHASES])
        measured = state_power(self.hass, self.config.get(CONF_POWER_SENSOR))
        if measured is not None:
            self.status.actual_w = max(measured, 0.0)
        elif self._charging and self._current_a is not None:
            self.status.actual_w = self._power(self._current_a, self._phases_now)
        else:
            self.status.actual_w = 0.0
        self._ev_soc = state_float(self.hass, self.config.get(CONF_EV_SOC_SENSOR))

    def update_deadline(self, now: datetime) -> float:
        self._away_housekeep(now)
        if self._boost_due(now):
            self.status.urgent = True
            return 0.0
        self.status.urgent = self._deadline_due(now)
        return self._solar_used

    def _boost_due(self, now: datetime) -> bool:
        """Fast charge from now at full power until the boost target SoC."""
        self._waiting_for_hdo = False
        self._solar_used = 0.0
        if not self._boost:
            return False
        if self._ev_soc is None or not self._connected:
            self._deadline_info = {
                "deadline_source": "boost",
                "deadline_mode": "boost",
                "deadline_soc": float(self._boost["soc"]),
                "boost": self.boost,
            }
            return False
        target = float(self._boost["soc"])
        if self._ev_soc >= target:
            self.stop_boost()
            self._deadline_info = {}
            return False
        hours, eta = self._boost_eta(now, target)
        need_kwh = (
            max(target - self._ev_soc, 0.0) / 100 * self.cfg(CONF_EV_CAPACITY)
            / self.cfg(CONF_EV_EFFICIENCY)
        )
        self._deadline_info = {
            "soc": self._ev_soc,
            "deadline": eta.isoformat() if eta else None,
            "deadline_eta": eta.isoformat() if eta else None,
            "deadline_need_kwh": round(need_kwh, 2),
            "deadline_solar_kwh": 0.0,
            "deadline_grid_kwh": round(need_kwh, 2),
            "deadline_charging_h": round(hours, 2),
            "deadline_soc": target,
            "deadline_source": "boost",
            "deadline_mode": "boost",
            "boost": self.boost,
        }
        self._deadline_active = eta
        return True

    def outlook(self) -> dict[str, Any]:
        if not self.enabled:
            return {"mode": "off"}
        out: dict[str, Any] = {
            "mode": "surplus",
            "soc": self._ev_soc,
            "target_soc": self.target_soc if self._ev_soc is not None else None,
            "deadline_soc": (
                self.cfg(CONF_EV_DEADLINE_SOC)
                if self.config.get(CONF_EV_DEADLINE_ENABLED) else None
            ),
            "charge_order": self.charge_order,
            "boost": self.boost,
            "away": self.away,
            "connected": self._connected,
            "min_before_battery": bool(self.config.get(CONF_MIN_BEFORE_BATTERY)),
            "minimum_pending": self.minimum_pending,
            "urgent_now": self.status.urgent,
            "reason": self.status.reason,
        }
        info = self._deadline_info
        if self._boost and self._ev_soc is not None and self._ev_soc < float(self._boost["soc"]):
            out.update({
                "mode": "boost",
                "deadline": info.get("deadline_eta") or info.get("deadline"),
                "target": float(self._boost["soc"]),
                "deadline_mode": "boost",
                "need_kwh": info.get("deadline_need_kwh"),
                "charging_h": info.get("deadline_charging_h"),
                "eta": info.get("deadline_eta"),
                "source": "boost",
            })
            return out
        if self._away and self._away_pending(dt_util.now()):
            leave = self._parse_away_time("leave_at", dt_util.now())
            out.update({
                "mode": "away",
                "deadline": leave.isoformat() if leave else self._away.get("leave_at"),
                "target": self.target_soc,
                "deadline_mode": "away",
                "battery_lend_kwh": round(self.battery_lend_kwh, 2),
                "car_budget_kwh": round(self.away_car_budget_kwh, 2),
                "releases_battery": self.away_releases_battery(),
                "source": "away",
                "away": self.away,
            })
            return out
        if self._charge_order and self._ev_soc is not None:
            order_soc = float(self._charge_order["soc"])
            if self._ev_soc >= order_soc:
                out["mode"] = "order_met"
            else:
                info = self._deadline_info
                out.update({
                    "mode": "deadline",
                    "deadline": info.get("deadline") or self._charge_order.get("deadline"),
                    "deadline_start": info.get("deadline_start"),
                    "target": info.get("deadline_soc", order_soc),
                    "deadline_mode": info.get("deadline_mode"),
                    "plan": info.get("deadline_plan"),
                    "need_kwh": info.get("deadline_need_kwh"),
                    "solar_kwh": info.get("deadline_solar_kwh"),
                    "grid_kwh": info.get("deadline_grid_kwh"),
                    "charging_h": info.get("deadline_charging_h"),
                    "at_risk": bool(info.get("deadline_at_risk")),
                    "waiting_for_hdo": self._waiting_for_hdo,
                    "source": info.get("deadline_source", "order"),
                })
                return out
        if not self.config.get(CONF_EV_DEADLINE_ENABLED) or self._ev_soc is None:
            return out
        info = self._deadline_info
        if not info and self._ev_soc >= self.cfg(CONF_EV_DEADLINE_SOC):
            out["mode"] = "deadline_met"
            return out
        out.update({
            "mode": "deadline",
            "deadline": info.get("deadline"),
            "deadline_start": info.get("deadline_start"),
            "target": info.get("deadline_soc", self.cfg(CONF_EV_DEADLINE_SOC)),
            "deadline_mode": info.get("deadline_mode"),
            "plan": info.get("deadline_plan"),
            "need_kwh": info.get("deadline_need_kwh"),
            "solar_kwh": info.get("deadline_solar_kwh"),
            "grid_kwh": info.get("deadline_grid_kwh"),
            "charging_h": info.get("deadline_charging_h"),
            "at_risk": bool(info.get("deadline_at_risk")),
            "waiting_for_hdo": self._waiting_for_hdo,
            "source": info.get("deadline_source", "daily"),
        })
        return out

    @property
    def minimum_pending(self) -> bool:
        if not bool(self._connected) or self._ev_soc is None:
            return False
        # Planned departure: prefer surplus into the car only when the forecast
        # can refill the house battery after leave (otherwise keep battery first).
        if self.away_releases_battery():
            return True
        if not bool(self.config.get(CONF_MIN_BEFORE_BATTERY)):
            return False
        if self._charge_order and self._ev_soc < float(self._charge_order["soc"]):
            order_soc = float(self._charge_order["soc"])
            # Top-up above the hold band waits for the deadline window – not surplus.
            if order_soc > EV_HOLD_SOC and self._ev_soc >= EV_HOLD_SOC:
                return False
            return True
        if self._boost and self._ev_soc < float(self._boost["soc"]):
            return True
        return (
            bool(self.config.get(CONF_EV_DEADLINE_ENABLED))
            and self._ev_soc < self.cfg(CONF_EV_DEADLINE_SOC)
        )

    @property
    def wants_surplus_charge(self) -> bool:
        """Connected and below surplus SoC target – outranks boiler thermal dump."""
        if self.status.urgent or self.minimum_pending:
            return False
        if not bool(self._connected) or self._ev_soc is None:
            return False
        # Order hold band: do not claim surplus ahead of the boiler for 80–100 %.
        if self._charge_order:
            order_soc = float(self._charge_order["soc"])
            if order_soc > EV_HOLD_SOC and self._ev_soc >= EV_HOLD_SOC:
                return False
        return self._ev_soc < self.target_soc and self._blocked() is None

    def _chase_soc(self, final_target: float) -> tuple[float, str]:
        """SoC to chase now: fill to hold first; 80–100 % only just before deadline.

        Returns (effective_target, phase) where phase is ``to_hold`` or ``top_up``.
        """
        if self._ev_soc is None or final_target <= EV_HOLD_SOC:
            return final_target, "full"
        if self._ev_soc < EV_HOLD_SOC:
            return EV_HOLD_SOC, "to_hold"
        return final_target, "top_up"

    @property
    def target_soc(self) -> float:
        """Max SoC from surplus: car entity when available, else last good / fixed."""
        entity_id = self.config.get(CONF_EV_TARGET_SOC_ENTITY)
        from_entity = state_float(self.hass, entity_id) if entity_id else None
        if from_entity is not None:
            self._target_soc_entity_last = max(0.0, min(100.0, from_entity))
            return self._target_soc_entity_last
        # Brief entity blip: keep the last known car limit instead of jumping to 100 %.
        if entity_id and self._target_soc_entity_last is not None:
            return self._target_soc_entity_last
        return self.cfg(CONF_EV_TARGET_SOC)

    def _blocked(self) -> str | None:
        """Surplus storage limit with lower hysteresis only.

        Charging stops at the target (never aims above it – the car would refuse
        anyway) and resumes only after SoC drops by the hysteresis. Raising the
        target clears the latch when SoC is still below the new limit.
        """
        if self._ev_soc is None:
            return None
        # With an order above the hold band, do not surplus-charge 80–100 % early.
        if self._charge_order:
            order_soc = float(self._charge_order["soc"])
            if order_soc > EV_HOLD_SOC and self._ev_soc >= EV_HOLD_SOC:
                return "hold_until_deadline"
        target = self.target_soc
        if self._last_target_for_hyst is not None and target > self._last_target_for_hyst:
            if self._ev_soc < target:
                self._soc_reached = False
        self._last_target_for_hyst = target
        if self._ev_soc >= target:
            self._soc_reached = True
        elif self._ev_soc <= target - self.cfg(CONF_EV_TARGET_HYSTERESIS):
            self._soc_reached = False
        if self._soc_reached:
            return "soc_reached"
        return None

    def _deadline_goals(self, now: datetime) -> list[tuple[datetime, float, str]]:
        """Unmet (deadline, target_soc, source) goals: daily minimum and/or charge order."""
        goals: list[tuple[datetime, float, str]] = []
        if self._charge_order:
            order_soc = float(self._charge_order["soc"])
            if self._ev_soc is not None and self._ev_soc >= order_soc:
                self.complete_charge_order()
            else:
                raw = dt_util.parse_datetime(str(self._charge_order["deadline"]))
                if raw is not None:
                    if raw.tzinfo is None:
                        raw = raw.replace(tzinfo=now.tzinfo)
                    goals.append((raw, order_soc, "order"))
        if self.config.get(CONF_EV_DEADLINE_ENABLED):
            deadline_time = dt_util.parse_time(str(self.config[CONF_EV_DEADLINE_TIME]))
            target = self.cfg(CONF_EV_DEADLINE_SOC)
            if deadline_time is not None and self._ev_soc is not None and self._ev_soc < target:
                deadline_today = datetime.combine(now.date(), deadline_time, tzinfo=now.tzinfo)
                running = self._deadline_day == now.date()
                deadline = (
                    deadline_today
                    if (deadline_today > now or running)
                    else deadline_today + timedelta(days=1)
                )
                goals.append((deadline, target, "daily"))
        return goals

    def _pick_deadline_goal(
        self, goals: list[tuple[datetime, float, str]]
    ) -> tuple[datetime, float, str]:
        """Drive timing from the earliest unmet goal and that goal's own SoC.

        Never pair a later order's high SoC with an earlier daily deadline
        (that would top-up to 100 % the night before the morning minimum).
        """
        return min(goals, key=lambda g: (g[0], -g[1]))

    def _deadline_due(self, now: datetime) -> bool:
        """Charge to a target SoC by a deadline when surplus is not enough.

        Goals come from the recurring morning minimum and/or a one-shot charge
        order. Only one goal is active at a time: the earliest unmet deadline,
        using that goal's SoC (hold band still applies for targets above 80 %).
        Without HDO: just in time. HDO only: latest known windows before the
        deadline. A started run continues until the SoC target – even past the
        clock (same day for daily; until met for orders).
        """
        self._deadline_info = {}
        self._waiting_for_hdo = False
        self._solar_used = 0.0
        if self._ev_soc is None or not self._connected:
            self._deadline_active = None
            self._deadline_day = None
            return False

        goals = self._deadline_goals(now)
        if not goals:
            self._deadline_active = None
            self._deadline_day = None
            return False

        deadline, final_target, source = self._pick_deadline_goal(goals)
        target, phase = self._chase_soc(final_target)
        running = self._deadline_day == now.date() or (
            source == "order" and self._deadline_active is not None and self._ev_soc < final_target
        )

        need_kwh = (
            max(target - self._ev_soc, 0.0) / 100 * self.cfg(CONF_EV_CAPACITY)
            / self.cfg(CONF_EV_EFFICIENCY)
        )
        phases = 3 if self.can_switch_phases else int(self.config[CONF_PHASES])
        self._solar_used = self._solar_for(deadline, now, need_kwh)
        grid_kwh = need_kwh - self._solar_used
        hours = grid_kwh * 1000 / self._power(self.max_a, phases) * self.cfg(CONF_EV_DEADLINE_SAFETY)
        self._deadline_info = {
            "soc": self._ev_soc,
            "deadline": deadline.isoformat(),
            "deadline_need_kwh": round(need_kwh, 2),
            "deadline_solar_kwh": round(self._solar_used, 2),
            "deadline_grid_kwh": round(grid_kwh, 2),
            "deadline_charging_h": round(hours, 2),
            "deadline_soc": final_target,
            "deadline_chase_soc": target,
            "deadline_phase": phase,
            "deadline_hold_soc": EV_HOLD_SOC,
            "deadline_source": source,
            "charge_order": self.charge_order,
        }
        if grid_kwh <= 0 and not running:
            # Waiting for the top-up window (already at hold, solar covers rest, etc.).
            if phase == "top_up" and self._ev_soc < final_target:
                self._deadline_info["deadline_mode"] = "hold_until_deadline"
            self._deadline_active = None
            self._deadline_day = None
            return False

        hdo_only = bool(self.config.get(CONF_EV_DEADLINE_HDO_ONLY)) and self.hdo_active is not None
        if hdo_only:
            windows = (
                self.hdo_schedule.windows_between(now, deadline)
                if self.hdo_schedule is not None
                else None
            )
            if windows is not None:
                plan, enough = plan_windows(
                    windows, now, timedelta(hours=hours), slack=DEADLINE_FIT_SLACK
                )
                self._deadline_info.update(
                    deadline_mode="hdo_plan",
                    deadline_plan=[f"{a:%d.%m. %H:%M}-{b:%H:%M}" for a, b in plan],
                    deadline_at_risk=not enough,
                )
                in_plan = any(a <= now < b for a, b in plan)
                # One-shot / calendar order: catch up after the deadline even if
                # charging never started (same idea as boiler heat orders).
                order_active = source == "order"
                catch_up = (
                    (running or order_active)
                    and now >= deadline
                    and bool(self.hdo_active)
                )
                due = in_plan or catch_up or (running and bool(self.hdo_active))
            else:
                self._deadline_info["deadline_mode"] = "hdo"
                due = bool(self.hdo_active) and (
                    running or now < deadline or self._ev_soc < target
                )
            if due:
                self._deadline_active = deadline
                self._deadline_day = now.date()
            else:
                self._waiting_for_hdo = True
                if not running:
                    self._deadline_day = None
            return due

        start = deadline - timedelta(hours=hours) - DEADLINE_LEAD
        self._deadline_info.update(deadline_mode="just_in_time", deadline_start=start.isoformat())
        if running and self._ev_soc < final_target:
            self._deadline_active = deadline
            return True
        # Just in time for the current chase target (hold first, then top-up).
        if start <= now and (now < deadline or self._ev_soc < final_target):
            self._deadline_active = deadline
            self._deadline_day = now.date()
            return True
        self._deadline_active = None
        self._deadline_day = None
        return False

    def _choose_phases(self, budget: float, now: float, charging: bool) -> int:
        if not self.can_switch_phases:
            return self._phases_now
        three_min = self._power(self.min_a, 3)
        if not charging:
            # Nothing to interrupt yet – pick the phase count for the start.
            self._phase_debounce.reset()
            return 3 if budget >= three_min + self.cfg(CONF_ON_MARGIN) else 1
        if self._phases_now == 1:
            wanted = 3 if budget >= three_min + self.cfg(CONF_ON_MARGIN) else 1
        else:
            wanted = 1 if budget < three_min - self.cfg(CONF_OFF_TOLERANCE) else 3
        switch_ok = self._phase_debounce.check(
            wanted != self._phases_now, now, self.cfg(CONF_OFF_DELAY)
        )
        interval_ok = now - self._last_phase_switch >= self.cfg(CONF_PHASE_SWITCH_INTERVAL)
        if switch_ok and interval_ok:
            return wanted
        return self._phases_now

    def plan(self, budget: float, headroom: Headroom, now: float) -> float:
        status = self.status
        charging = bool(self._charging)

        if self._charging is None or self._current_a is None:
            blocked = "unavailable"
        elif not self._connected:
            blocked = "not_connected"
        elif status.urgent:
            # Urgent deadline charging may go past the surplus SoC limit up to
            # the morning minimum (same idea as boiler ignoring max temp).
            blocked = None
        else:
            # Target SoC is a hard stop for surplus – the car will not take more.
            blocked = self._blocked()
        status.wants_power = blocked is None

        if blocked:
            self._target_on = False
            status.active = False
            status.allocated_w = 0.0
            status.reason = blocked
            status.extra = self._extra(self._phases_now, self._current_a)
            # While unplugged, still count surplus stability so on_delay does not
            # restart from zero the moment the cable is plugged in.
            if blocked == "not_connected":
                self._tick_start_ready(budget, headroom, now)
            else:
                self._on_debounce.reset()
            return 0.0

        self._plan_now = now
        if status.urgent:
            return self._plan_urgent(headroom, charging)
        phases = self._choose_phases(budget, now, charging)
        min_w = self._power(self.min_a, phases)
        # From a full battery the current is rounded to the nearest step
        # (at most half a step, e.g. 345 W on 3 phases, is borrowed).
        borrow = self._power(1, phases) * BORROW_STEP_SHARE if self.borrow else 0.0
        keep_ok = budget + borrow >= min_w - self.cfg(CONF_OFF_TOLERANCE)
        start_ok = (
            budget + borrow >= min_w + self.cfg(CONF_ON_MARGIN) and headroom.watts(phases) >= min_w
        )
        target_on = self._decide_on(charging, keep_ok, start_ok, now)

        if not target_on:
            self._target_on = False
            status.active = False
            status.allocated_w = 0.0
            status.reason = "no_surplus" if charging else "waiting_for_surplus"
            if self._waiting_for_hdo and not start_ok:
                status.reason = "waiting_for_hdo"
            status.extra = self._extra(phases, self._current_a)
            self._target_phases = phases
            return 0.0

        amps = math.floor((budget + borrow) / (self.voltage * phases))
        current_now = self._current_a if charging and phases == self._phases_now else 0.0
        breaker_cap = (
            math.floor(current_now + headroom.amps) if math.isfinite(headroom.amps) else self.max_a
        )
        amps = max(self.min_a, min(self.max_a, amps, breaker_cap))
        if charging and phases == self._phases_now and self._current_a is not None:
            amps = self._damp(amps, int(self._current_a), budget + borrow, phases, now)
            amps = max(self.min_a, min(amps, breaker_cap))
        else:
            self._up = None
            self._down_since = None

        self._target_on = True
        self._target_a = amps
        self._target_phases = phases
        allocated = self._power(amps, phases)
        headroom.consume(allocated - self._power(current_now, phases), phases)
        status.active = True
        status.allocated_w = allocated
        status.reason = "charging" if charging else "starting"
        status.extra = self._extra(phases, amps)
        return allocated

    def _extra(self, phases: int, current: float | None) -> dict[str, Any]:
        entity_id = self.config.get(CONF_EV_TARGET_SOC_ENTITY)
        source = "entity" if (entity_id and self._target_soc_entity_last is not None
                              and state_float(self.hass, entity_id) is not None) else (
            "entity_held" if entity_id and self._target_soc_entity_last is not None else "fixed"
        )
        return {
            "phases": phases,
            "current": current,
            **self._deadline_info,
            "soc": self._ev_soc,
            "target_soc": self.target_soc if self._ev_soc is not None else None,
            "target_soc_source": source if self._ev_soc is not None else None,
            "connected": self._connected,
            "charge_order": self.charge_order,
            "boost": self.boost,
            "away": self.away,
            "battery_lend_kwh": (
                round(self.battery_lend_kwh, 2) if self._away else None
            ),
            "car_budget_kwh": (
                round(self.away_car_budget_kwh, 2) if self._away else None
            ),
        }

    def _tick_start_ready(self, budget: float, headroom: Headroom, now: float) -> None:
        """Advance on_delay while unplugged if surplus would already allow a start."""
        phases = self._choose_phases(budget, now, charging=False)
        min_w = self._power(self.min_a, phases)
        borrow = self._power(1, phases) * BORROW_STEP_SHARE if self.borrow else 0.0
        start_ok = (
            budget + borrow >= min_w + self.cfg(CONF_ON_MARGIN) and headroom.watts(phases) >= min_w
        )
        self._off_debounce.reset()
        self._on_debounce.check(start_ok, now, self.cfg(CONF_ON_DELAY))

    def _damp(self, wanted: int, current: int, budget: float, phases: int, now: float) -> int:
        """Avoid hunting the current on a fluctuating surplus.

        Higher current only after it held for CURRENT_UP_DELAY (then the lowest
        value seen in that time). Lower current at once when the shortfall is
        larger than the turn-off tolerance, otherwise after the turn-off delay –
        the battery covers the small gap meanwhile.
        """
        if wanted > current:
            self._down_since = None
            since, lowest = self._up if self._up else (now, wanted)
            lowest = min(lowest, wanted)
            if now - since >= CURRENT_UP_DELAY:
                self._up = None
                return lowest
            self._up = (since, lowest)
            return current
        self._up = None
        if wanted < current:
            shortfall = self._power(current, phases) - budget
            if shortfall > self.cfg(CONF_OFF_TOLERANCE):
                self._down_since = None
                return wanted
            if self._down_since is None:
                self._down_since = now
            if now - self._down_since >= self.cfg(CONF_OFF_DELAY):
                self._down_since = None
                return wanted
            return current
        self._down_since = None
        return current

    def _plan_urgent(self, headroom: Headroom, charging: bool) -> float:
        """Deadline charging: full current regardless of surplus, within the breaker."""
        status = self.status
        phases = 3 if self.can_switch_phases else self._phases_now
        current_now = self._current_a if charging and phases == self._phases_now else 0.0
        amps = self.max_a
        if math.isfinite(headroom.amps):
            amps = min(amps, math.floor((current_now or 0.0) + headroom.amps))
        if amps < self.min_a:
            self._target_on = False
            status.active = False
            status.allocated_w = 0.0
            status.reason = "breaker_limit"
            status.extra = self._extra(phases, self._current_a)
            return 0.0
        self._target_on = True
        self._target_a = amps
        self._target_phases = phases
        allocated = self._power(amps, phases)
        headroom.consume(allocated - self._power(current_now or 0.0, phases), phases)
        status.active = True
        status.allocated_w = allocated
        status.reason = "boost_charging" if self._boost else "deadline_charging"
        status.extra = self._extra(phases, amps)
        return allocated

    def state_now(self) -> dict[str, Any]:
        return {"on": self._charging, "current": self._current_a, "phases": self._phases_now}

    def pending_actions(self) -> list[tuple[Any, ...]]:
        if self._charging is None:
            return []
        if not self._target_on:
            return [("stop",)] if self._charging else []
        actions: list[tuple[Any, ...]] = []
        if self.can_switch_phases and self._target_phases != self._phases_now:
            actions.append(("phases", self._target_phases))
        if self._current_a != self._target_a:
            actions.append(("current", self._target_a))
        if not self._charging:
            actions.append(("start", self._target_a, self._target_phases))
        return actions

    async def apply(self) -> None:
        if self._charging is None:
            return
        charge_switch = self.config[CONF_CHARGE_SWITCH]
        if not self._target_on:
            if self._charging:
                _LOGGER.debug("%s: stop charging", self.name)
                await async_turn(self.hass, charge_switch, False)
                self._owned = False
            return

        if self.can_switch_phases and self._target_phases != self._phases_now:
            _LOGGER.debug("%s: switching to %s phase(s)", self.name, self._target_phases)
            await async_turn(self.hass, self.config[CONF_PHASE_SWITCH], self._target_phases == 3)
            if self._charging:
                # Only a switch during charging interrupts it and counts.
                self._last_phase_switch = self._plan_now
            self._phase_debounce.reset()
        if self._current_a != self._target_a:
            await async_set_number(self.hass, self.config[CONF_CURRENT_ENTITY], self._target_a)
        if not self._charging:
            _LOGGER.debug("%s: start charging at %s A", self.name, self._target_a)
            await async_turn(self.hass, charge_switch, True)
        self._owned = True

    async def release(self) -> None:
        if self._owned and state_on(self.hass, self.config[CONF_CHARGE_SWITCH]):
            await async_turn(self.hass, self.config[CONF_CHARGE_SWITCH], False)
        self._owned = False
        self.status = DeviceStatus(reason="disabled")


DEVICE_TYPES: dict[str, type[ManagedDevice]] = {
    SUBENTRY_SWITCHED: SwitchedDevice,
    SUBENTRY_EV_CHARGER: EvChargerDevice,
}
