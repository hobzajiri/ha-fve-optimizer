"""Config flow: main entry (energy sources) + subentries (managed devices)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .hdo import (
    HDO_CALENDAR,
    HDO_EGD,
    HDO_ENTITY,
    HDO_MANUAL,
    HDO_NONE,
    HDO_PRE,
    HDO_SOURCES,
    HdoError,
    async_egd_records,
    async_egd_region,
    async_pre_page,
    egd_matching,
    parse_ranges,
    pre_options,
    pre_windows,
)
from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CHARGE_POSITIVE,
    CONF_BATTERY_MAX_CHARGE_W,
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC,
    CONF_BATTERY_RESERVE_SOC,
    CONF_BATTERY_TARGET_SOC,
    CONF_NIGHT_EXTRA_H,
    CONF_NIGHT_POWER_W,
    CONF_NIGHT_TARGET,
    CONF_BREAKER_MARGIN_A,
    CONF_CHARGE_SWITCH,
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
    CONF_HDO_ENTITY,
    CONF_HOUSE_POWER,
    CONF_MAIN_BREAKER_A,
    CONF_NOMINAL_VOLTAGE,
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
    CONF_PHASE_CURRENTS,
    CONF_PHASE_SWITCH,
    CONF_PHASE_SWITCH_INTERVAL,
    CONF_PHASES,
    CONF_POWER_SENSOR,
    CONF_PRIORITY,
    CONF_PV_POWER,
    CONF_RESERVE_W,
    CONF_SWITCH_ENTITY,
    CONF_TANK_VOLUME,
    CONF_TEMPERATURE_SENSOR,
    CONF_UPDATE_INTERVAL,
    CONF_INPUT_TIMEOUT,
    CONF_DRY_RUN,
    DEFAULTS,
    DEVICE_DEFAULTS,
    DEVICE_TUNABLES,
    DOMAIN,
    HUB_TUNABLES,
    SUBENTRY_EV_CHARGER,
    SUBENTRY_SWITCHED,
)

# -- selector helpers ---------------------------------------------------------


def _entity(domain: str | list[str], multiple: bool = False, device_class: str | None = None):
    config = selector.EntitySelectorConfig(domain=domain, multiple=multiple)
    if device_class:
        config["device_class"] = device_class
    return selector.EntitySelector(config)


def _number(minimum: float, maximum: float, step: float, unit: str | None = None):
    config = selector.NumberSelectorConfig(
        min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


_TUNABLES = {t.key: t for t in HUB_TUNABLES} | {
    t.key: t for tunables in DEVICE_TUNABLES.values() for t in tunables
}


def _tunable(key: str):
    """Number field with the same range as the matching number entity."""
    t = _TUNABLES[key]
    return _number(t.minimum, t.maximum, t.step, t.unit)


_PHASES = selector.SelectSelector(
    selector.SelectSelectorConfig(options=["1", "3"], translation_key="phases")
)


def _req(key: str, values: dict[str, Any], defaults: dict[str, Any]) -> vol.Required:
    return vol.Required(key, default=values.get(key, defaults.get(key)))


def _opt(key: str, values: dict[str, Any]) -> vol.Optional:
    """Optional field that can be cleared again in the UI."""
    return vol.Optional(key, description={"suggested_value": values.get(key)})


# -- main entry schemas -------------------------------------------------------


def _sources_schema(v: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            _req(CONF_GRID_POWER, v, {}): _entity("sensor"),
            _req(CONF_GRID_IMPORT_POSITIVE, v, DEFAULTS): selector.BooleanSelector(),
            _req(CONF_BATTERY_POWER, v, {}): _entity("sensor"),
            _req(CONF_BATTERY_CHARGE_POSITIVE, v, DEFAULTS): selector.BooleanSelector(),
            _req(CONF_BATTERY_SOC, v, {}): _entity("sensor"),
            _opt(CONF_PV_POWER, v): _entity("sensor"),
            _opt(CONF_HOUSE_POWER, v): _entity("sensor"),
        }
    )


def _battery_schema(v: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            _req(CONF_BATTERY_CAPACITY_KWH, v, DEFAULTS): _tunable(CONF_BATTERY_CAPACITY_KWH),
            _req(CONF_BATTERY_TARGET_SOC, v, DEFAULTS): _tunable(CONF_BATTERY_TARGET_SOC),
            _req(CONF_BATTERY_MAX_CHARGE_W, v, DEFAULTS): _tunable(CONF_BATTERY_MAX_CHARGE_W),
            _req(CONF_NIGHT_TARGET, v, DEFAULTS): selector.BooleanSelector(),
            _req(CONF_NIGHT_POWER_W, v, DEFAULTS): _tunable(CONF_NIGHT_POWER_W),
            _req(CONF_NIGHT_EXTRA_H, v, DEFAULTS): _tunable(CONF_NIGHT_EXTRA_H),
            _req(CONF_BATTERY_RESERVE_SOC, v, DEFAULTS): _tunable(CONF_BATTERY_RESERVE_SOC),
            _opt(CONF_FORECAST_REMAINING, v): _entity("sensor"),
            _req(CONF_FORECAST_MIN_SOC, v, DEFAULTS): _tunable(CONF_FORECAST_MIN_SOC),
            _req(CONF_FORECAST_SAFETY, v, DEFAULTS): _tunable(CONF_FORECAST_SAFETY),
            _req(CONF_HOUSE_AVG_POWER_W, v, DEFAULTS): _tunable(CONF_HOUSE_AVG_POWER_W),
        }
    )


def _control_schema(v: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            _opt(CONF_EXPORT_LIMIT_ENTITY, v): _entity(["number", "input_number"]),
            _req(CONF_EXPORT_CONTROL, v, DEFAULTS): selector.BooleanSelector(),
            _req(CONF_EXPORT_RERAISE, v, DEFAULTS): selector.BooleanSelector(),
            _req(CONF_BATTERY_FULL_SOC, v, DEFAULTS): _tunable(CONF_BATTERY_FULL_SOC),
            _req(CONF_BATTERY_BORROW, v, DEFAULTS): selector.BooleanSelector(),
            _req(CONF_EXPORT_LIMIT_NORMAL, v, DEFAULTS): _tunable(CONF_EXPORT_LIMIT_NORMAL),
            _req(CONF_EXPORT_LIMIT_RAISED, v, DEFAULTS): _tunable(CONF_EXPORT_LIMIT_RAISED),
            _opt(CONF_PHASE_CURRENTS, v): _entity("sensor", multiple=True),
            _req(CONF_MAIN_BREAKER_A, v, DEFAULTS): _tunable(CONF_MAIN_BREAKER_A),
            _req(CONF_BREAKER_MARGIN_A, v, DEFAULTS): _tunable(CONF_BREAKER_MARGIN_A),
            _req(CONF_RESERVE_W, v, DEFAULTS): _tunable(CONF_RESERVE_W),
            _req(CONF_NOMINAL_VOLTAGE, v, DEFAULTS): _tunable(CONF_NOMINAL_VOLTAGE),
            _req(CONF_UPDATE_INTERVAL, v, DEFAULTS): _tunable(CONF_UPDATE_INTERVAL),
            _req(CONF_INPUT_TIMEOUT, v, DEFAULTS): _tunable(CONF_INPUT_TIMEOUT),
            _req(CONF_DRY_RUN, v, DEFAULTS): selector.BooleanSelector(),
        }
    )


def _validate_control(hass, data: dict[str, Any]) -> dict[str, str]:
    """Catch export limits entered in the wrong unit."""
    normal = float(data.get(CONF_EXPORT_LIMIT_NORMAL, 0))
    raised = float(data.get(CONF_EXPORT_LIMIT_RAISED, 0))
    entity_id = data.get(CONF_EXPORT_LIMIT_ENTITY)
    if not entity_id or not data.get(CONF_EXPORT_CONTROL, True):
        return {}
    if raised <= normal:
        return {CONF_EXPORT_LIMIT_RAISED: "raised_not_above_normal"}
    state = hass.states.get(entity_id)
    unit = state.attributes.get("unit_of_measurement") if state else None
    if unit == "W" and raised < 1000:
        return {CONF_EXPORT_LIMIT_RAISED: "raised_too_low_watts"}
    return {}


def _control_placeholders(hass, data: dict[str, Any]) -> dict[str, str]:
    entity_id = data.get(CONF_EXPORT_LIMIT_ENTITY)
    state = hass.states.get(entity_id) if entity_id else None
    unit = state.attributes.get("unit_of_measurement") if state else None
    return {"export_unit": unit or "?"}


HDO_KEYS = (
    "hdo_source",
    CONF_HDO_ENTITY,
    "hdo_egd_psc",
    "hdo_egd_region",
    "hdo_egd_code",
    "hdo_pre_povel",
    "hdo_manual_workday",
    "hdo_manual_weekend",
)


class _HdoSteps:
    """HDO source selection, shared by the config and the options flow."""

    _data: dict[str, Any]

    def _values(self) -> dict[str, Any]:
        return self._data

    async def _async_finish(self) -> ConfigFlowResult:
        raise NotImplementedError

    async def async_step_hdo(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            source = user_input["hdo_source"]
            # Forget the settings of other sources.
            for key in HDO_KEYS:
                self._data.pop(key, None)
            self._data["hdo_source"] = source
            if source == HDO_NONE:
                return await self._async_finish()
            return await getattr(self, f"async_step_hdo_{source}")()
        v = self._values()
        source = v.get("hdo_source") or (HDO_ENTITY if v.get(CONF_HDO_ENTITY) else HDO_NONE)
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="hdo",
            data_schema=vol.Schema(
                {
                    vol.Required("hdo_source", default=source): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=HDO_SOURCES, translation_key="hdo_source"
                        )
                    )
                }
            ),
        )

    async def async_step_hdo_egd(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            psc = user_input["hdo_egd_psc"].replace(" ", "")
            code = user_input["hdo_egd_code"].strip()
            try:
                region = await async_egd_region(self.hass, psc)  # type: ignore[attr-defined]
                records = await async_egd_records(self.hass)  # type: ignore[attr-defined]
                if not egd_matching(records, region, code):
                    errors["hdo_egd_code"] = "egd_code_not_found"
            except HdoError as err:
                errors["base"] = "egd_unknown_psc" if "PSČ" in str(err) else "cannot_connect"
            if not errors:
                self._data.update(hdo_egd_psc=psc, hdo_egd_code=code, hdo_egd_region=region)
                return await self._async_finish()
        v = {**self._values(), **(user_input or {})}
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="hdo_egd",
            data_schema=vol.Schema(
                {
                    vol.Required("hdo_egd_psc", default=v.get("hdo_egd_psc", "")): selector.TextSelector(),
                    vol.Required("hdo_egd_code", default=v.get("hdo_egd_code", "")): selector.TextSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_hdo_pre(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            povel = user_input["hdo_pre_povel"].strip()
            try:
                pre_windows(await async_pre_page(self.hass, povel), dt_util.now().date(), dt_util.now().tzinfo)  # type: ignore[attr-defined]
            except HdoError:
                errors["hdo_pre_povel"] = "pre_povel_not_found"
            if not errors:
                self._data["hdo_pre_povel"] = povel
                return await self._async_finish()
        options: dict[str, str] = {}
        try:
            options = pre_options(await async_pre_page(self.hass))  # type: ignore[attr-defined]
        except HdoError:
            pass  # offline – fall back to a text field
        default = (user_input or self._values()).get("hdo_pre_povel", "")
        field = (
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=k, label=l) for k, l in options.items()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )
            if options
            else selector.TextSelector()
        )
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="hdo_pre",
            data_schema=vol.Schema({vol.Required("hdo_pre_povel", default=default): field}),
            errors=errors,
        )

    async def async_step_hdo_calendar(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_HDO_ENTITY] = user_input[CONF_HDO_ENTITY]
            return await self._async_finish()
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="hdo_calendar",
            data_schema=vol.Schema(
                {_req(CONF_HDO_ENTITY, self._values(), {}): _entity("calendar")}
            ),
        )

    async def async_step_hdo_entity(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_HDO_ENTITY] = user_input[CONF_HDO_ENTITY]
            return await self._async_finish()
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="hdo_entity",
            data_schema=vol.Schema(
                {
                    _req(CONF_HDO_ENTITY, self._values(), {}): _entity(
                        ["binary_sensor", "input_boolean", "schedule", "switch"]
                    )
                }
            ),
        )

    async def async_step_hdo_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            workday = user_input.get("hdo_manual_workday", "")
            weekend = user_input.get("hdo_manual_weekend", "")
            if not parse_ranges(workday):
                errors["hdo_manual_workday"] = "invalid_times"
            elif weekend and not parse_ranges(weekend):
                errors["hdo_manual_weekend"] = "invalid_times"
            else:
                self._data.update(hdo_manual_workday=workday, hdo_manual_weekend=weekend)
                return await self._async_finish()
        v = {**self._values(), **(user_input or {})}
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="hdo_manual",
            data_schema=vol.Schema(
                {
                    vol.Required("hdo_manual_workday", default=v.get("hdo_manual_workday", "")): selector.TextSelector(),
                    vol.Optional("hdo_manual_weekend", default=v.get("hdo_manual_weekend", "")): selector.TextSelector(),
                }
            ),
            errors=errors,
        )


class FveOptimizerConfigFlow(_HdoSteps, ConfigFlow, domain=DOMAIN):
    """Main setup wizard: sources → battery & forecast → control."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_battery()
        return self.async_show_form(step_id="user", data_schema=_sources_schema(self._data))

    async def async_step_battery(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_control()
        return self.async_show_form(step_id="battery", data_schema=_battery_schema(self._data))

    async def async_step_control(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_control(self.hass, user_input)
            if not errors:
                self._data.update(user_input)
                return await self.async_step_hdo()
        values = {**self._data, **(user_input or {})}
        return self.async_show_form(
            step_id="control",
            data_schema=_control_schema(values),
            errors=errors,
            description_placeholders=_control_placeholders(self.hass, values),
        )

    async def _async_finish(self) -> ConfigFlowResult:
        return self.async_create_entry(title="FVE Optimizer", data=self._data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FveOptimizerOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            SUBENTRY_SWITCHED: SwitchedDeviceFlow,
            SUBENTRY_EV_CHARGER: EvChargerFlow,
        }


class FveOptimizerOptionsFlow(_HdoSteps, OptionsFlow):
    """Same three steps, prefilled with the current values."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options, **self._data}

    def _values(self) -> dict[str, Any]:
        return self._current()

    async def _async_finish(self) -> ConfigFlowResult:
        # Optional fields left empty must drop out of the merged config.
        merged = {**self.config_entry.data, **self.config_entry.options}
        for key in (
            CONF_PV_POWER,
            CONF_HOUSE_POWER,
            CONF_FORECAST_REMAINING,
            CONF_EXPORT_LIMIT_ENTITY,
            CONF_PHASE_CURRENTS,
            *HDO_KEYS,
        ):
            if key not in self._data:
                merged.pop(key, None)
        return self.async_create_entry(data={**merged, **self._data})

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_battery()
        return self.async_show_form(step_id="init", data_schema=_sources_schema(self._current()))

    async def async_step_battery(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_control()
        return self.async_show_form(step_id="battery", data_schema=_battery_schema(self._current()))

    async def async_step_control(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_control(self.hass, user_input)
        if user_input is not None and not errors:
            self._data.update(user_input)
            return await self.async_step_hdo()
        values = {**self._current(), **(user_input or {})}
        return self.async_show_form(
            step_id="control",
            data_schema=_control_schema(values),
            errors=errors,
            description_placeholders=_control_placeholders(self.hass, values),
        )


# -- device subentries --------------------------------------------------------


def _common_device_fields(v: dict[str, Any]) -> dict[Any, Any]:
    return {
        _req(CONF_PRIORITY, v, DEVICE_DEFAULTS): _tunable(CONF_PRIORITY),
        _req(CONF_ON_DELAY, v, DEVICE_DEFAULTS): _tunable(CONF_ON_DELAY),
        _req(CONF_OFF_DELAY, v, DEVICE_DEFAULTS): _tunable(CONF_OFF_DELAY),
        _req(CONF_ON_MARGIN, v, DEVICE_DEFAULTS): _tunable(CONF_ON_MARGIN),
        _req(CONF_OFF_TOLERANCE, v, DEVICE_DEFAULTS): _tunable(CONF_OFF_TOLERANCE),
    }


def _switched_schema(v: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            _req(CONF_NAME, v, {CONF_NAME: "Bojler"}): selector.TextSelector(),
            _req(CONF_SWITCH_ENTITY, v, {}): _entity(["switch", "input_boolean", "light"]),
            _req(CONF_NOMINAL_POWER, v, DEVICE_DEFAULTS): _tunable(CONF_NOMINAL_POWER),
            _req(CONF_PHASES, v, DEVICE_DEFAULTS): _PHASES,
            _opt(CONF_POWER_SENSOR, v): _entity("sensor"),
            _opt(CONF_TEMPERATURE_SENSOR, v): _entity("sensor"),
            _req(CONF_MAX_TEMPERATURE, v, DEVICE_DEFAULTS): _tunable(CONF_MAX_TEMPERATURE),
            _req(CONF_MAX_TEMP_HYSTERESIS, v, DEVICE_DEFAULTS): _tunable(CONF_MAX_TEMP_HYSTERESIS),
            _req(CONF_MIN_ON_TIME, v, DEVICE_DEFAULTS): _tunable(CONF_MIN_ON_TIME),
            _req(CONF_MIN_OFF_TIME, v, DEVICE_DEFAULTS): _tunable(CONF_MIN_OFF_TIME),
            **_common_device_fields(v),
            # Deadline heating – used only with a temperature sensor.
            _req(CONF_DEADLINE_ENABLED, v, DEVICE_DEFAULTS): selector.BooleanSelector(),
            _req(CONF_DEADLINE_TIME, v, DEVICE_DEFAULTS): selector.TimeSelector(),
            _req(CONF_DEADLINE_HDO_ONLY, v, DEVICE_DEFAULTS): selector.BooleanSelector(),
            _req(CONF_DEADLINE_EARLIEST, v, DEVICE_DEFAULTS): selector.TimeSelector(),
            _req(CONF_MIN_BEFORE_BATTERY, v, DEVICE_DEFAULTS): selector.BooleanSelector(),
            _req(CONF_DEADLINE_TEMPERATURE, v, DEVICE_DEFAULTS): _tunable(CONF_DEADLINE_TEMPERATURE),
            _req(CONF_TANK_VOLUME, v, DEVICE_DEFAULTS): _tunable(CONF_TANK_VOLUME),
            _req(CONF_DEADLINE_HYSTERESIS, v, DEVICE_DEFAULTS): _tunable(CONF_DEADLINE_HYSTERESIS),
            _req(CONF_DEADLINE_SAFETY, v, DEVICE_DEFAULTS): _tunable(CONF_DEADLINE_SAFETY),
            _req(CONF_LEGIONELLA_ENABLED, v, DEVICE_DEFAULTS): selector.BooleanSelector(),
            _req(CONF_LEGIONELLA_TEMPERATURE, v, DEVICE_DEFAULTS): _tunable(CONF_LEGIONELLA_TEMPERATURE),
            _req(CONF_LEGIONELLA_INTERVAL_DAYS, v, DEVICE_DEFAULTS): _tunable(CONF_LEGIONELLA_INTERVAL_DAYS),
        }
    )


def _ev_schema(v: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            _req(CONF_NAME, v, {CONF_NAME: "EcoVolter"}): selector.TextSelector(),
            _req(CONF_CHARGE_SWITCH, v, {}): _entity(["switch", "input_boolean"]),
            _req(CONF_CURRENT_ENTITY, v, {}): _entity(["number", "input_number"]),
            _opt(CONF_PHASE_SWITCH, v): _entity(["switch", "input_boolean"]),
            _req(CONF_PHASES, v, {CONF_PHASES: "3"}): _PHASES,
            _opt(CONF_POWER_SENSOR, v): _entity("sensor"),
            _opt(CONF_CONNECTED_ENTITY, v): _entity(["binary_sensor", "sensor"]),
            _req(CONF_MIN_CURRENT, v, DEVICE_DEFAULTS): _tunable(CONF_MIN_CURRENT),
            _req(CONF_MAX_CURRENT, v, DEVICE_DEFAULTS): _tunable(CONF_MAX_CURRENT),
            _req(CONF_PHASE_SWITCH_INTERVAL, v, DEVICE_DEFAULTS): _tunable(CONF_PHASE_SWITCH_INTERVAL),
            **_common_device_fields(v),
            # "At least X % by the morning" – used only with the car SoC sensor.
            _opt(CONF_EV_SOC_SENSOR, v): _entity("sensor"),
            _req(CONF_EV_DEADLINE_ENABLED, v, DEVICE_DEFAULTS): selector.BooleanSelector(),
            _req(CONF_EV_DEADLINE_TIME, v, DEVICE_DEFAULTS): selector.TimeSelector(),
            _req(CONF_EV_DEADLINE_SOC, v, DEVICE_DEFAULTS): _tunable(CONF_EV_DEADLINE_SOC),
            _req(CONF_EV_DEADLINE_HDO_ONLY, v, DEVICE_DEFAULTS): selector.BooleanSelector(),
            _req(CONF_MIN_BEFORE_BATTERY, v, DEVICE_DEFAULTS): selector.BooleanSelector(),
            _req(CONF_EV_CAPACITY, v, DEVICE_DEFAULTS): _tunable(CONF_EV_CAPACITY),
            _req(CONF_EV_EFFICIENCY, v, DEVICE_DEFAULTS): _tunable(CONF_EV_EFFICIENCY),
            _req(CONF_EV_DEADLINE_SAFETY, v, DEVICE_DEFAULTS): _tunable(CONF_EV_DEADLINE_SAFETY),
        }
    )


class _DeviceFlow(ConfigSubentryFlow):
    """Shared add / reconfigure logic for device subentries."""

    schema_fn = staticmethod(_switched_schema)

    def _validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate(user_input)
            if not errors:
                return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=self.schema_fn(user_input or {}), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate(user_input)
            if not errors:
                # The entry's update listener decides between in-place apply
                # and reload, so the flow must not schedule a reload itself.
                self.hass.config_entries.async_update_subentry(
                    self._get_entry(), subentry, title=user_input[CONF_NAME], data=user_input
                )
                return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.schema_fn(user_input or dict(subentry.data)),
            errors=errors,
        )


class SwitchedDeviceFlow(_DeviceFlow):
    """Boiler, heater, pump – anything on/off with a known power."""

    schema_fn = staticmethod(_switched_schema)


class EvChargerFlow(_DeviceFlow):
    """EV charger with current control (EcoVolter)."""

    schema_fn = staticmethod(_ev_schema)

    def _validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        if user_input[CONF_MIN_CURRENT] > user_input[CONF_MAX_CURRENT]:
            return {CONF_MAX_CURRENT: "max_below_min"}
        return {}
