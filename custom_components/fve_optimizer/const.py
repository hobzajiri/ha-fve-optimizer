"""Constants for FVE Optimizer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

DOMAIN: Final = "fve_optimizer"

PLATFORMS: Final = ["sensor", "binary_sensor", "switch", "number", "select", "time"]

NOMINAL_VOLTAGE: Final = 230.0

# --- Main entry: energy flow -------------------------------------------------
CONF_GRID_POWER: Final = "grid_power"
CONF_GRID_IMPORT_POSITIVE: Final = "grid_import_positive"
CONF_BATTERY_POWER: Final = "battery_power"
CONF_BATTERY_CHARGE_POSITIVE: Final = "battery_charge_positive"
CONF_BATTERY_SOC: Final = "battery_soc"
CONF_PV_POWER: Final = "pv_power"
CONF_HOUSE_POWER: Final = "house_power"

# --- Main entry: battery and forecast ----------------------------------------
CONF_BATTERY_CAPACITY_KWH: Final = "battery_capacity_kwh"
CONF_BATTERY_TARGET_SOC: Final = "battery_target_soc"
CONF_BATTERY_MAX_CHARGE_W: Final = "battery_max_charge_w"
CONF_FORECAST_REMAINING: Final = "forecast_remaining_today"
CONF_FORECAST_MIN_SOC: Final = "forecast_min_soc"
CONF_FORECAST_SAFETY: Final = "forecast_safety_factor"
CONF_HOUSE_AVG_POWER_W: Final = "house_avg_power_w"
# Battery target from the energy needed while there is no production
CONF_NIGHT_TARGET: Final = "night_target"
CONF_NIGHT_POWER_W: Final = "night_power_w"
CONF_NIGHT_EXTRA_H: Final = "night_extra_hours"
CONF_BATTERY_RESERVE_SOC: Final = "battery_reserve_soc"

# --- Main entry: export limit, breaker, control ------------------------------
CONF_EXPORT_LIMIT_ENTITY: Final = "export_limit_entity"
CONF_EXPORT_CONTROL: Final = "export_limit_control"
CONF_EXPORT_RERAISE: Final = "export_limit_reraise"
CONF_BATTERY_FULL_SOC: Final = "battery_full_soc"
# Round device power up to the next step from a full battery
CONF_BATTERY_BORROW: Final = "battery_borrow"
BORROW_STEP_SHARE: Final = 0.5  # at most half a step comes from the battery
BORROW_SOC_BAND: Final = 5.0  # stop borrowing this much below "full"
CURRENT_UP_DELAY: Final = 30  # s a higher charging current must hold before it is set
CONF_HDO_ENTITY: Final = "hdo_entity"
CONF_EXPORT_LIMIT_NORMAL: Final = "export_limit_normal"
CONF_EXPORT_LIMIT_RAISED: Final = "export_limit_raised"
CONF_PHASE_CURRENTS: Final = "phase_current_sensors"
CONF_MAIN_BREAKER_A: Final = "main_breaker_a"
CONF_BREAKER_MARGIN_A: Final = "breaker_margin_a"
CONF_RESERVE_W: Final = "reserve_w"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_INPUT_TIMEOUT: Final = "input_timeout_s"  # stale / missing inverter data → fail-safe
CONF_DRY_RUN: Final = "dry_run"  # compute and show, never switch anything

DEFAULTS: Final[dict[str, object]] = {
    CONF_GRID_IMPORT_POSITIVE: True,
    CONF_BATTERY_CHARGE_POSITIVE: True,
    CONF_BATTERY_CAPACITY_KWH: 10.0,
    CONF_BATTERY_TARGET_SOC: 90.0,
    CONF_BATTERY_MAX_CHARGE_W: 5000.0,
    CONF_FORECAST_MIN_SOC: 50.0,
    CONF_FORECAST_SAFETY: 1.3,
    CONF_HOUSE_AVG_POWER_W: 500.0,
    CONF_NIGHT_TARGET: True,
    CONF_NIGHT_POWER_W: 400.0,
    CONF_NIGHT_EXTRA_H: 2.0,
    CONF_BATTERY_RESERVE_SOC: 10.0,
    CONF_EXPORT_CONTROL: True,
    CONF_EXPORT_RERAISE: False,
    CONF_BATTERY_FULL_SOC: 99.0,
    CONF_BATTERY_BORROW: True,
    CONF_EXPORT_LIMIT_NORMAL: 0.0,
    CONF_EXPORT_LIMIT_RAISED: 10000.0,
    CONF_MAIN_BREAKER_A: 25.0,
    CONF_BREAKER_MARGIN_A: 2.0,
    CONF_RESERVE_W: 100.0,
    CONF_UPDATE_INTERVAL: 15,
    CONF_INPUT_TIMEOUT: 300,
    CONF_DRY_RUN: False,
}

# --- Subentries: managed devices ---------------------------------------------
SUBENTRY_SWITCHED: Final = "switched"
SUBENTRY_EV_CHARGER: Final = "ev_charger"

CONF_NAME: Final = "name"
CONF_PRIORITY: Final = "priority"
CONF_PHASES: Final = "phases"
CONF_POWER_SENSOR: Final = "power_sensor"
CONF_ON_DELAY: Final = "on_delay_s"
# Surplus goes to a pending minimum (deadline temperature / car SoC) before
# the battery – avoids charging the battery only to discharge it into the load.
CONF_MIN_BEFORE_BATTERY: Final = "minimum_before_battery"
CONF_OFF_DELAY: Final = "off_delay_s"
CONF_ON_MARGIN: Final = "on_margin_w"
CONF_OFF_TOLERANCE: Final = "off_tolerance_w"

# switched (boiler, heater, pump...)
CONF_SWITCH_ENTITY: Final = "switch_entity"
CONF_NOMINAL_POWER: Final = "nominal_power_w"
CONF_TEMPERATURE_SENSOR: Final = "temperature_sensor"
CONF_MAX_TEMPERATURE: Final = "max_temperature"
CONF_MAX_TEMP_HYSTERESIS: Final = "max_temperature_hysteresis"
CONF_MIN_ON_TIME: Final = "min_on_time_s"
CONF_MIN_OFF_TIME: Final = "min_off_time_s"
# "heat to X °C by HH:MM" – needs the temperature sensor
CONF_DEADLINE_ENABLED: Final = "deadline_enabled"
CONF_DEADLINE_TIME: Final = "deadline_time"
CONF_DEADLINE_TEMPERATURE: Final = "deadline_temperature"
CONF_DEADLINE_HYSTERESIS: Final = "deadline_hysteresis"
CONF_DEADLINE_SAFETY: Final = "deadline_safety_factor"
CONF_TANK_VOLUME: Final = "tank_volume_l"
CONF_DEADLINE_HDO_ONLY: Final = "deadline_hdo_only"
CONF_DEADLINE_EARLIEST: Final = "deadline_earliest"
# periodic anti-legionella heating
CONF_LEGIONELLA_ENABLED: Final = "legionella_enabled"
CONF_LEGIONELLA_TEMPERATURE: Final = "legionella_temperature"
CONF_LEGIONELLA_INTERVAL_DAYS: Final = "legionella_interval_days"

# EV charger (EcoVolter)
CONF_CHARGE_SWITCH: Final = "charge_switch"
CONF_CURRENT_ENTITY: Final = "current_entity"
CONF_PHASE_SWITCH: Final = "three_phase_switch"
CONF_CONNECTED_ENTITY: Final = "connected_entity"
CONF_MIN_CURRENT: Final = "min_current"
CONF_MAX_CURRENT: Final = "max_current"
CONF_PHASE_SWITCH_INTERVAL: Final = "phase_switch_interval_s"
# "at least X % by HH:MM" – needs the car SoC sensor
CONF_EV_SOC_SENSOR: Final = "ev_soc_sensor"
CONF_EV_CAPACITY: Final = "ev_capacity_kwh"
CONF_EV_DEADLINE_ENABLED: Final = "ev_deadline_enabled"
CONF_EV_DEADLINE_TIME: Final = "ev_deadline_time"
CONF_EV_DEADLINE_SOC: Final = "ev_deadline_soc"
CONF_EV_DEADLINE_HDO_ONLY: Final = "ev_deadline_hdo_only"
CONF_EV_EFFICIENCY: Final = "ev_charge_efficiency"
CONF_EV_DEADLINE_SAFETY: Final = "ev_deadline_safety_factor"

DEVICE_DEFAULTS: Final[dict[str, object]] = {
    CONF_PRIORITY: 10,
    CONF_MIN_BEFORE_BATTERY: True,
    CONF_PHASES: "1",
    CONF_ON_DELAY: 60,
    CONF_OFF_DELAY: 60,
    CONF_ON_MARGIN: 200.0,
    CONF_OFF_TOLERANCE: 300.0,
    CONF_NOMINAL_POWER: 2000.0,
    CONF_MAX_TEMPERATURE: 60.0,
    CONF_MAX_TEMP_HYSTERESIS: 3.0,
    CONF_MIN_ON_TIME: 300,
    CONF_MIN_OFF_TIME: 300,
    CONF_MIN_CURRENT: 6,
    CONF_MAX_CURRENT: 16,
    CONF_PHASE_SWITCH_INTERVAL: 900,
    CONF_EV_CAPACITY: 77.0,
    CONF_EV_DEADLINE_ENABLED: False,
    CONF_EV_DEADLINE_TIME: "07:00:00",
    CONF_EV_DEADLINE_SOC: 60.0,
    CONF_EV_DEADLINE_HDO_ONLY: True,
    CONF_EV_EFFICIENCY: 0.9,
    CONF_EV_DEADLINE_SAFETY: 1.2,
    CONF_DEADLINE_ENABLED: False,
    CONF_DEADLINE_TIME: "19:00:00",
    CONF_DEADLINE_TEMPERATURE: 50.0,
    CONF_DEADLINE_HYSTERESIS: 2.0,
    CONF_DEADLINE_SAFETY: 1.2,
    CONF_TANK_VOLUME: 160.0,
    CONF_DEADLINE_HDO_ONLY: True,
    CONF_DEADLINE_EARLIEST: "00:00:00",
    CONF_LEGIONELLA_ENABLED: False,
    CONF_LEGIONELLA_TEMPERATURE: 65.0,
    CONF_LEGIONELLA_INTERVAL_DAYS: 7,
}

CONF_NOMINAL_VOLTAGE: Final = "nominal_voltage"
DEFAULTS[CONF_NOMINAL_VOLTAGE] = NOMINAL_VOLTAGE


# --- Tunables ------------------------------------------------------------------
# Parameters exposed both in the config flow and as number / select entities.
# Changing them is applied in place, without reloading the integration.


@dataclass(frozen=True)
class Tunable:
    """A runtime-adjustable parameter."""

    key: str
    minimum: float = 0
    maximum: float = 0
    step: float = 1
    unit: str | None = None
    options: tuple[str, ...] | None = None
    kind: str = "number"  # number | select | switch | time
    requires: str | None = None  # only offered when this config key is set


HUB_TUNABLES: Final[tuple[Tunable, ...]] = (
    Tunable(CONF_BATTERY_CAPACITY_KWH, 1, 200, 0.1, "kWh"),
    Tunable(CONF_BATTERY_TARGET_SOC, 10, 100, 1, "%"),
    Tunable(CONF_BATTERY_MAX_CHARGE_W, 100, 30000, 100, "W"),
    Tunable(CONF_NIGHT_TARGET, kind="switch"),
    Tunable(CONF_NIGHT_POWER_W, 0, 10000, 50, "W"),
    Tunable(CONF_NIGHT_EXTRA_H, 0, 8, 0.5, "h"),
    Tunable(CONF_BATTERY_RESERVE_SOC, 0, 80, 1, "%"),
    Tunable(CONF_FORECAST_MIN_SOC, 10, 100, 1, "%"),
    Tunable(CONF_FORECAST_SAFETY, 1, 3, 0.05),
    Tunable(CONF_HOUSE_AVG_POWER_W, 0, 10000, 50, "W"),
    Tunable(CONF_EXPORT_CONTROL, kind="switch"),
    Tunable(CONF_EXPORT_RERAISE, kind="switch"),
    Tunable(CONF_BATTERY_FULL_SOC, 80, 100, 0.5, "%"),
    Tunable(CONF_BATTERY_BORROW, kind="switch"),
    Tunable(CONF_EXPORT_LIMIT_NORMAL, 0, 100000, 1),
    Tunable(CONF_EXPORT_LIMIT_RAISED, 0, 100000, 1),
    Tunable(CONF_MAIN_BREAKER_A, 6, 100, 1, "A"),
    Tunable(CONF_BREAKER_MARGIN_A, 0, 20, 0.5, "A"),
    Tunable(CONF_RESERVE_W, 0, 2000, 10, "W"),
    Tunable(CONF_NOMINAL_VOLTAGE, 200, 250, 1, "V"),
    Tunable(CONF_UPDATE_INTERVAL, 5, 300, 1, "s"),
    Tunable(CONF_INPUT_TIMEOUT, 0, 3600, 10, "s"),
    Tunable(CONF_DRY_RUN, kind="switch"),
)

PHASES_TUNABLE: Final = Tunable(CONF_PHASES, options=("1", "3"), kind="select")

COMMON_DEVICE_TUNABLES: Final[tuple[Tunable, ...]] = (
    Tunable(CONF_PRIORITY, 1, 100, 1),
    Tunable(CONF_ON_DELAY, 0, 3600, 1, "s"),
    Tunable(CONF_OFF_DELAY, 0, 3600, 1, "s"),
    Tunable(CONF_ON_MARGIN, 0, 5000, 10, "W"),
    Tunable(CONF_OFF_TOLERANCE, 0, 5000, 10, "W"),
)

DEVICE_TUNABLES: Final[dict[str, tuple[Tunable, ...]]] = {
    SUBENTRY_SWITCHED: (
        Tunable(CONF_NOMINAL_POWER, 50, 30000, 50, "W"),
        PHASES_TUNABLE,
        Tunable(CONF_MAX_TEMPERATURE, 20, 95, 0.5, "°C", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_MAX_TEMP_HYSTERESIS, 0, 20, 0.5, "°C", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_MIN_ON_TIME, 0, 3600, 1, "s"),
        Tunable(CONF_MIN_OFF_TIME, 0, 3600, 1, "s"),
        *COMMON_DEVICE_TUNABLES,
        Tunable(CONF_DEADLINE_ENABLED, kind="switch", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_DEADLINE_TIME, kind="time", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_DEADLINE_HDO_ONLY, kind="switch", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_MIN_BEFORE_BATTERY, kind="switch", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_DEADLINE_EARLIEST, kind="time", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_DEADLINE_TEMPERATURE, 20, 95, 0.5, "°C", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_DEADLINE_HYSTERESIS, 0, 10, 0.5, "°C", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_TANK_VOLUME, 10, 2000, 10, "L", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_DEADLINE_SAFETY, 1, 3, 0.05, requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_LEGIONELLA_ENABLED, kind="switch", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_LEGIONELLA_TEMPERATURE, 55, 90, 0.5, "°C", requires=CONF_TEMPERATURE_SENSOR),
        Tunable(CONF_LEGIONELLA_INTERVAL_DAYS, 1, 60, 1, "d", requires=CONF_TEMPERATURE_SENSOR),
    ),
    SUBENTRY_EV_CHARGER: (
        PHASES_TUNABLE,
        Tunable(CONF_MIN_CURRENT, 1, 32, 1, "A"),
        Tunable(CONF_MAX_CURRENT, 1, 32, 1, "A"),
        Tunable(CONF_PHASE_SWITCH_INTERVAL, 0, 7200, 1, "s"),
        *COMMON_DEVICE_TUNABLES,
        Tunable(CONF_EV_DEADLINE_ENABLED, kind="switch", requires=CONF_EV_SOC_SENSOR),
        Tunable(CONF_EV_DEADLINE_TIME, kind="time", requires=CONF_EV_SOC_SENSOR),
        Tunable(CONF_EV_DEADLINE_SOC, 10, 100, 1, "%", requires=CONF_EV_SOC_SENSOR),
        Tunable(CONF_EV_DEADLINE_HDO_ONLY, kind="switch", requires=CONF_EV_SOC_SENSOR),
        Tunable(CONF_MIN_BEFORE_BATTERY, kind="switch", requires=CONF_EV_SOC_SENSOR),
        Tunable(CONF_EV_CAPACITY, 5, 200, 0.5, "kWh", requires=CONF_EV_SOC_SENSOR),
        Tunable(CONF_EV_EFFICIENCY, 0.5, 1, 0.01, requires=CONF_EV_SOC_SENSOR),
        Tunable(CONF_EV_DEADLINE_SAFETY, 1, 3, 0.05, requires=CONF_EV_SOC_SENSOR),
    ),
}

HUB_TUNABLE_KEYS: Final = frozenset(t.key for t in HUB_TUNABLES)
