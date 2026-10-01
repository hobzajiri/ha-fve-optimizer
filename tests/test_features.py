"""Battery night target, EV morning minimum, anti-legionella, last decision."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fve_optimizer.const import DOMAIN

from .test_dispatcher import BOILER, EV, MAIN, Recorder, _setup, _states

PRAGUE = ZoneInfo("Europe/Prague")


def _entry(data=None, *devices):
    return MockConfigEntry(
        domain=DOMAIN,
        title="FVE Optimizer",
        data={**MAIN, **(data or {})},
        subentries_data=[
            ConfigSubentryData(data=d, subentry_type=k, title=d["name"], unique_id=None)
            for k, d in devices
        ],
    )


def _sun(hass: HomeAssistant, state: str, setting: datetime, rising: datetime) -> None:
    hass.states.async_set(
        "sun.sun",
        state,
        {"next_setting": setting.isoformat(), "next_rising": rising.isoformat()},
    )


async def test_battery_target_covers_time_without_production(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 12, 0, tzinfo=PRAGUE))
    # Sunset 18:50, sunrise 07:00 → 12.2 h + 2 h extra = 14.2 h × 0.4 kW = 5.7 kWh
    # → 10 % reserve + 56.8 % = 66.8 %.
    _sun(hass, "above_horizon", datetime(2026, 9, 30, 18, 50, tzinfo=PRAGUE),
         datetime(2026, 10, 1, 7, 2, tzinfo=PRAGUE))
    _states(hass, grid=0, batt=3000, soc=60)
    coordinator = await _setup(hass, _entry({"battery_target_soc": 100.0}))
    snap = coordinator.data
    assert snap.night_target_soc == 66.8
    assert snap.effective_target_soc == 66.8
    assert snap.battery_priority  # 60 % < 66.8 %

    hass.states.async_set("sensor.soc", "70")
    await coordinator.async_refresh()
    assert not coordinator.data.battery_priority

    # Switched off → the plain target (100 %) applies again.
    entry = coordinator.config_entry
    hass.config_entries.async_update_entry(entry, options={**entry.data, "night_target": False})
    await hass.async_block_till_done()
    assert coordinator.data.effective_target_soc == 100.0


def _ev(**extra):
    return {
        **EV,
        "priority": 1,
        "ev_soc_sensor": "sensor.car_soc",
        "ev_deadline_enabled": True,
        "ev_deadline_time": "07:00:00",
        "ev_deadline_soc": 60.0,
        "ev_capacity_kwh": 77.0,
        "ev_charge_efficiency": 0.9,
        "ev_deadline_safety_factor": 1.2,
        **extra,
    }


def _ev_states(hass: HomeAssistant, soc: str) -> None:
    _states(
        hass, grid=300, batt=0, soc=20,
        switch__ev_charge="off", input_number__ev_current="6", switch__ev_3f="on",
        binary_sensor__ev_connected="on", sensor__car_soc=soc,
    )


async def test_ev_morning_minimum_just_in_time(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    # 40 → 60 % of 77 kWh / 0.9 = 17.1 kWh at 11 kW (3f 16 A) × 1.2 = 1.87 h
    # → start 07:00 − 1:52 − 0:10 ≈ 04:58.
    freezer.move_to(datetime(2026, 9, 30, 22, 0, tzinfo=PRAGUE))
    _ev_states(hass, "40")
    coordinator = await _setup(hass, _entry({}, ("ev_charger", _ev(ev_deadline_hdo_only=False))))
    device_id = next(iter(coordinator.devices))
    data = coordinator.data.devices[device_id]
    assert data["deadline"].startswith("2026-10-01T07:00")
    assert data["deadline_start"].startswith("2026-10-01T04:5")
    assert ("turn_on", "switch.ev_charge", None) not in rec.calls

    freezer.move_to(datetime(2026, 10, 1, 5, 0, tzinfo=PRAGUE))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.devices[device_id]["reason"] == "deadline_charging"
    assert ("set_value", "input_number.ev_current", 16) in rec.calls
    assert ("turn_on", "switch.ev_charge", None) in rec.calls

    # Target reached → back to surplus-only; the 11 kW now come from the grid → stop.
    hass.states.async_set("sensor.grid", "11340")
    hass.states.async_set("sensor.car_soc", "61")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_off", "switch.ev_charge", None) in rec.calls


async def test_ev_morning_minimum_only_in_hdo(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 22, 0, tzinfo=PRAGUE))
    _ev_states(hass, "40")
    entry = _entry(
        {"hdo_source": "manual", "hdo_manual_workday": "00:00-02:00; 04:00-06:00"},
        ("ev_charger", _ev()),
    )
    coordinator = await _setup(hass, entry)
    device_id = next(iter(coordinator.devices))
    data = coordinator.data.devices[device_id]
    # 1.87 h needed: all of 04:00–06:00 is not needed, only the last 1:52.
    assert data["deadline_plan"] == ["01.10. 04:08-06:00"]
    assert data["reason"] == "waiting_for_hdo"

    freezer.move_to(datetime(2026, 10, 1, 4, 30, tzinfo=PRAGUE))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_on", "switch.ev_charge", None) in rec.calls
    assert coordinator.data.devices[device_id]["reason"] == "deadline_charging"


def _legionella_boiler(**extra):
    return {
        **BOILER,
        "temperature_sensor": "sensor.water",
        "max_temperature": 60.0,
        "legionella_enabled": True,
        "legionella_temperature": 65.0,
        "legionella_interval_days": 7,
        **extra,
    }


async def test_legionella_raises_surplus_maximum_until_done(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 12, 0, tzinfo=PRAGUE))
    # 62 °C is above the normal maximum (60) but below the legionella target (65).
    _states(hass, grid=-4000, batt=0, soc=95, switch__boiler="off", sensor__water="62")
    entry = _entry({}, ("switched", _legionella_boiler()))
    coordinator = await _setup(hass, entry)
    device_id = next(iter(coordinator.devices))
    assert coordinator.data.devices[device_id]["legionella_due"] is True
    assert ("turn_on", "switch.boiler", None) in rec.calls

    hass.states.async_set("sensor.water", "65.2")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    data = coordinator.data.devices[device_id]
    assert data["legionella_due"] is False
    assert data["reason"] == "temperature_reached"
    assert data["legionella_last"].startswith("2026-09-30T12:00")

    # Restart: the last run survives, so 3 days later it is still not due.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    freezer.move_to(datetime(2026, 10, 3, 12, 0, tzinfo=PRAGUE))
    hass.states.async_set("sensor.water", "50")
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    assert coordinator.data.devices[device_id]["legionella_due"] is False

    freezer.move_to(datetime(2026, 10, 7, 12, 1, tzinfo=PRAGUE))
    await coordinator.async_refresh()
    assert coordinator.data.devices[device_id]["legionella_due"] is True


async def test_legionella_uses_deadline_heating(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 18, 0, tzinfo=PRAGUE))
    _states(hass, grid=500, batt=0, soc=95, switch__boiler="off", sensor__water="55")
    boiler = _legionella_boiler(
        deadline_enabled=True, deadline_time="19:00:00", deadline_temperature=50.0,
        deadline_hdo_only=False,
    )
    coordinator = await _setup(hass, _entry({}, ("switched", boiler)))
    data = coordinator.data.devices[next(iter(coordinator.devices))]
    # 55 °C would satisfy the 50 °C deadline, but legionella is due → heat to 65.
    assert data["reason"] == "deadline_heating"


async def test_last_decision_entity(hass: HomeAssistant) -> None:
    hass.config.language = "cs"
    Recorder(hass)
    _states(
        hass, grid=-7000, batt=0, soc=95, limit="10000", switch__boiler="off",
        switch__ev_charge="off", input_number__ev_current="6", switch__ev_3f="on",
        binary_sensor__ev_connected="on",
    )
    await _setup(hass, _entry({}, ("switched", BOILER), ("ev_charger", EV)))
    state = [s for s in hass.states.async_all("sensor") if s.entity_id.endswith("last_decision")
             or "posledni" in s.entity_id][0]
    assert state.state.startswith("Baterie 95 % → cíl 90 % (přednost zařízení)")
    assert "Bojler: běží 2000 W" in state.state
    assert "EcoVolter: spouští se 4830 W (3f 7 A)" in state.state
    assert state.attributes["details"][0].startswith("dispatching")
    assert state.attributes["changed_at"]


def _min_boiler(**extra):
    return {
        **BOILER,
        "temperature_sensor": "sensor.water",
        "deadline_enabled": True,
        "deadline_time": "19:00:00",
        "deadline_temperature": 50.0,
        "deadline_hdo_only": False,
        **extra,
    }


async def test_boiler_minimum_gets_surplus_before_battery(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 10, 0, tzinfo=PRAGUE))  # long before the deadline
    # Battery 40 % < 90 % has priority and takes all 3 kW of surplus.
    _states(hass, grid=0, batt=3000, soc=40, switch__boiler="off", sensor__water="40")
    entry = _entry({"night_target": False}, ("switched", _min_boiler()))
    coordinator = await _setup(hass, entry)
    device_id = next(iter(coordinator.devices))
    data = coordinator.data.devices[device_id]
    assert coordinator.data.battery_priority
    assert data["reason"] == "running"  # below the 50 °C minimum → before the battery
    assert ("turn_on", "switch.boiler", None) in rec.calls

    # Minimum reached → the battery is first again, the boiler stops.
    hass.states.async_set("switch.boiler", "on")
    hass.states.async_set("sensor.batt", "1000")  # boiler now takes 2 kW of the 3 kW
    hass.states.async_set("sensor.water", "50.5")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_off", "switch.boiler", None) in rec.calls


async def test_boiler_minimum_before_battery_can_be_disabled(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 10, 0, tzinfo=PRAGUE))
    _states(hass, grid=0, batt=3000, soc=40, switch__boiler="off", sensor__water="40")
    entry = _entry({"night_target": False}, ("switched", _min_boiler(minimum_before_battery=False)))
    await _setup(hass, entry)
    assert ("turn_on", "switch.boiler", None) not in rec.calls


async def test_ev_minimum_gets_surplus_before_battery(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 10, 0, tzinfo=PRAGUE))
    _states(
        hass, grid=0, batt=5000, soc=40,
        switch__ev_charge="off", input_number__ev_current="6", switch__ev_3f="on",
        binary_sensor__ev_connected="on", sensor__car_soc="40",
    )
    entry = _entry({"night_target": False}, ("ev_charger", _ev(ev_deadline_hdo_only=False)))
    coordinator = await _setup(hass, entry)
    device_id = next(iter(coordinator.devices))
    # 5000 − 100 W → 3 phases × 7 A
    assert ("set_value", "input_number.ev_current", 7) in rec.calls
    assert coordinator.data.devices[device_id]["reason"] == "starting"


async def test_running_device_gives_way_to_battery(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    # Boiler (no minimum) runs 2 kW, battery 40 % gets only 1 kW → boiler must stop.
    _states(hass, grid=0, batt=1000, soc=40, switch__boiler="on")
    coordinator = await _setup(hass, _entry({"night_target": False}, ("switched", BOILER)))
    assert coordinator.data.battery_priority
    assert ("turn_off", "switch.boiler", None) in rec.calls


async def test_devices_get_surplus_above_battery_max_charge(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    # Battery charges at its 5 kW maximum and 2.5 kW still goes to the grid.
    _states(hass, grid=-2500, batt=5000, soc=40, limit="10000", switch__boiler="off")
    coordinator = await _setup(
        hass, _entry({"night_target": False, "battery_max_charge_w": 5000.0}, ("switched", BOILER))
    )
    assert coordinator.data.budget_w == 2400  # 2500 + 5000 − 5000 − 100
    assert ("turn_on", "switch.boiler", None) in rec.calls


async def test_small_surplus_stays_in_battery(hass: HomeAssistant) -> None:
    """Boiler 2.2 kW on/off, car ≥ 4.14 kW (3 phases, no switching)."""
    rec = Recorder(hass)
    boiler = {**BOILER, "nominal_power_w": 2200.0, "priority": 1}
    car = {**EV, "priority": 2, "three_phase_switch": None, "phases": "3"}
    car.pop("three_phase_switch")
    # 1.5 kW goes into the battery (no priority any more, SoC 95 %).
    _states(
        hass, grid=0, batt=1500, soc=95, limit="10000", switch__boiler="off",
        switch__ev_charge="off", input_number__ev_current="6",
        binary_sensor__ev_connected="on",
    )
    coordinator = await _setup(hass, _entry({"night_target": False}, ("switched", boiler), ("ev_charger", car)))
    assert not coordinator.data.battery_priority
    assert coordinator.data.budget_w == 1400
    assert not rec.calls or all(c[0] == "set_value" and "export" in c[1] for c in rec.calls)

    # 3 kW: enough for the boiler (2.2 + 0.2 margin), not for the car → rest to the battery.
    hass.states.async_set("sensor.batt", "3000")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_on", "switch.boiler", None) in rec.calls
    assert ("turn_on", "switch.ev_charge", None) not in rec.calls
    assert coordinator.data.allocated_w == 2200


async def _forecast_case(hass: HomeAssistant, freezer, forecast_kwh: str):
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 9, 0, tzinfo=PRAGUE))
    # 10 h of sun left, house 500 W → 5 kWh for the house.
    _sun(hass, "above_horizon", datetime(2026, 9, 30, 19, 0, tzinfo=PRAGUE),
         datetime(2026, 10, 1, 7, 0, tzinfo=PRAGUE))
    _states(hass, grid=300, batt=0, soc=95, switch__boiler="off", sensor__water="40",
            sensor__forecast=forecast_kwh)
    boiler = _min_boiler(deadline_hdo_only=True, tank_volume_l=160.0, deadline_safety_factor=1.2)
    entry = _entry(
        {"night_target": False, "forecast_remaining_today": "sensor.forecast",
         "hdo_source": "manual", "hdo_manual_workday": "02:00-06:00; 14:00-18:00"},
        ("switched", boiler),
    )
    coordinator = await _setup(hass, entry)
    return rec, coordinator.data.devices[next(iter(coordinator.devices))]


async def test_deadline_sunny_day_plans_no_grid(hass: HomeAssistant, freezer) -> None:
    # 20 / 1.3 − 5 = 10.4 kWh of sun for devices ≥ 1.86 kWh needed.
    rec, data = await _forecast_case(hass, freezer, "20")
    assert data["deadline_mode"] == "solar"
    assert data["deadline_grid_kwh"] == 0
    assert data["reason"] != "waiting_for_hdo"


async def test_deadline_cloudy_day_plans_latest_hdo(hass: HomeAssistant, freezer) -> None:
    # 5 / 1.3 − 5 < 0 → everything from the grid: 1.86 kWh / 2 kW × 1.2 = 67 min.
    rec, data = await _forecast_case(hass, freezer, "5")
    assert data["deadline_solar_kwh"] == 0
    assert data["deadline_plan"] == ["16:53-18:00"]
    assert data["reason"] == "waiting_for_hdo"


async def test_deadline_partly_sunny_plans_only_the_rest(hass: HomeAssistant, freezer) -> None:
    # 7.8 / 1.3 − 5 = 1.0 kWh from the sun → 0.86 kWh from the grid → 31 min.
    rec, data = await _forecast_case(hass, freezer, "7.8")
    assert data["deadline_solar_kwh"] == 1.0
    assert data["deadline_grid_kwh"] == 0.86
    assert data["deadline_plan"] == ["17:29-18:00"]


async def test_export_limit_once_a_day(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    limit_writes = lambda: [c for c in rec.calls if c[1] == "input_number.export_limit"]  # noqa: E731
    freezer.move_to(datetime(2026, 9, 30, 5, 0, tzinfo=PRAGUE))
    _sun(hass, "below_horizon", datetime(2026, 9, 30, 18, 50, tzinfo=PRAGUE),
         datetime(2026, 9, 30, 7, 0, tzinfo=PRAGUE))
    _states(hass, grid=0, batt=0, soc=60, switch__boiler="off", sensor__water="40")
    entry = _entry({"night_target": False}, ("switched", {**BOILER, "temperature_sensor": "sensor.water"}))
    coordinator = await _setup(hass, entry)
    assert limit_writes() == []  # night: no write, the current limit (0) is taken over

    # Morning: production, the boiler can store → raise.
    freezer.move_to(datetime(2026, 9, 30, 7, 30, tzinfo=PRAGUE))
    _sun(hass, "above_horizon", datetime(2026, 9, 30, 18, 50, tzinfo=PRAGUE),
         datetime(2026, 10, 1, 7, 0, tzinfo=PRAGUE))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert limit_writes() == [("set_value", "input_number.export_limit", 10000.0)]

    # Battery nearly full but the boiler still heats → stays raised.
    hass.states.async_set("sensor.soc", "100")
    await coordinator.async_refresh()
    assert len(limit_writes()) == 1

    # Boiler hot + battery full → nowhere to store → lower.
    hass.states.async_set("sensor.water", "61")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert limit_writes()[-1] == ("set_value", "input_number.export_limit", 0.0)

    # Water cools down later: not raised again the same day (2 writes in total).
    hass.states.async_set("sensor.water", "50")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(limit_writes()) == 2

    # Next morning it is allowed again.
    freezer.move_to(datetime(2026, 10, 1, 7, 30, tzinfo=PRAGUE))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert limit_writes()[-1] == ("set_value", "input_number.export_limit", 10000.0)


async def test_export_limit_reraise_option(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    limit_writes = lambda: [c for c in rec.calls if c[1] == "input_number.export_limit"]  # noqa: E731
    freezer.move_to(datetime(2026, 9, 30, 9, 0, tzinfo=PRAGUE))
    _sun(hass, "above_horizon", datetime(2026, 9, 30, 18, 50, tzinfo=PRAGUE),
         datetime(2026, 10, 1, 7, 0, tzinfo=PRAGUE))
    _states(hass, grid=0, batt=0, soc=100, switch__boiler="off", sensor__water="61")
    entry = _entry({"night_target": False, "export_limit_reraise": True},
                   ("switched", {**BOILER, "temperature_sensor": "sensor.water"}))
    coordinator = await _setup(hass, entry)
    assert limit_writes() == []  # nowhere to store
    hass.states.async_set("sensor.water", "50")  # can store again
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert limit_writes() == [("set_value", "input_number.export_limit", 10000.0)]


async def test_export_limit_not_raised_when_forecast_is_poor(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 9, 0, tzinfo=PRAGUE))
    _sun(hass, "above_horizon", datetime(2026, 9, 30, 19, 0, tzinfo=PRAGUE),
         datetime(2026, 10, 1, 7, 0, tzinfo=PRAGUE))
    # 6 kWh forecast ÷ 1.3 − house 5 kWh < battery 4 kWh to full → pointless.
    _states(hass, grid=0, batt=2000, soc=60, switch__boiler="off", sensor__water="40",
            sensor__forecast="6")
    entry = _entry({"night_target": False, "forecast_remaining_today": "sensor.forecast"},
                   ("switched", {**BOILER, "temperature_sensor": "sensor.water"}))
    await _setup(hass, entry)
    assert not any(c[1] == "input_number.export_limit" for c in rec.calls)


async def test_export_limit_kept_after_restart(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 12, 0, tzinfo=PRAGUE))
    _sun(hass, "above_horizon", datetime(2026, 9, 30, 18, 50, tzinfo=PRAGUE),
         datetime(2026, 10, 1, 7, 0, tzinfo=PRAGUE))
    _states(hass, grid=-2000, batt=0, soc=100, limit="10000", switch__boiler="off", sensor__water="40")
    entry = _entry({"night_target": False}, ("switched", {**BOILER, "temperature_sensor": "sensor.water"}))
    coordinator = await _setup(hass, entry)
    assert coordinator.data.export_limit_raised
    assert not any(c[1] == "input_number.export_limit" for c in rec.calls)


async def test_export_limit_untouched_after_sunset(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 20, 0, tzinfo=PRAGUE))
    _sun(hass, "below_horizon", datetime(2026, 10, 1, 18, 50, tzinfo=PRAGUE),
         datetime(2026, 10, 1, 7, 0, tzinfo=PRAGUE))
    # Raised from the day, battery full, boiler hot → nowhere to store, but no production.
    _states(hass, grid=300, batt=0, soc=100, limit="10000", switch__boiler="off", sensor__water="61")
    entry = _entry({"night_target": False}, ("switched", {**BOILER, "temperature_sensor": "sensor.water"}))
    coordinator = await _setup(hass, entry)
    assert coordinator.data.export_limit_raised
    assert not any(c[1] == "input_number.export_limit" for c in rec.calls)


async def test_round_up_from_full_battery(hass: HomeAssistant, freezer) -> None:
    """The case from the log: 5400 W → 8 A (5520 W) instead of exporting 670 W."""
    rec = Recorder(hass)
    car = {**EV, "priority": 1}
    car.pop("three_phase_switch")
    _states(
        hass, grid=-670, batt=0, soc=100, limit="10000",
        switch__ev_charge="on", input_number__ev_current="7",
        binary_sensor__ev_connected="on",
    )
    coordinator = await _setup(hass, _entry({"night_target": False}, ("ev_charger", car)))
    assert coordinator.data.borrow_active
    # A higher current must hold for 30 s first (no hunting on clouds).
    assert ("set_value", "input_number.ev_current", 8) not in rec.calls
    freezer.tick(31)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("set_value", "input_number.ev_current", 8) in rec.calls

    # Battery drained to 96 % – still inside the band → keeps 8 A.
    hass.states.async_set("input_number.ev_current", "8")
    hass.states.async_set("sensor.grid", "0")
    hass.states.async_set("sensor.batt", "-120")
    hass.states.async_set("sensor.soc", "96")
    await coordinator.async_refresh()
    assert coordinator.data.borrow_active
    assert coordinator.data.devices[next(iter(coordinator.devices))]["current"] == 8

    # Below 94 % → stop borrowing, back to 7 A, the battery recharges.
    hass.states.async_set("sensor.soc", "93.5")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not coordinator.data.borrow_active
    assert ("set_value", "input_number.ev_current", 7) in rec.calls

    # Not again before the battery is full.
    hass.states.async_set("sensor.soc", "97")
    await coordinator.async_refresh()
    assert not coordinator.data.borrow_active


async def test_boiler_starts_at_half_power_from_full_battery(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    boiler = {**BOILER, "nominal_power_w": 2200.0}
    # 1.4 kW to the grid, battery full: 1300 + 1100 borrowed ≥ 2200 + 200 margin.
    _states(hass, grid=-1400, batt=0, soc=100, limit="10000", switch__boiler="off")
    await _setup(hass, _entry({"night_target": False}, ("switched", boiler)))
    assert ("turn_on", "switch.boiler", None) in rec.calls


async def test_round_up_can_be_disabled(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    boiler = {**BOILER, "nominal_power_w": 2200.0}
    _states(hass, grid=-1400, batt=0, soc=100, limit="10000", switch__boiler="off")
    await _setup(hass, _entry({"night_target": False, "battery_borrow": False}, ("switched", boiler)))
    assert ("turn_on", "switch.boiler", None) not in rec.calls


async def test_card_is_served(hass: HomeAssistant, hass_client) -> None:
    Recorder(hass)
    _states(hass, grid=0, batt=0, soc=95)
    coordinator = await _setup(hass, _entry({}))
    client = await hass_client()
    resp = await client.get("/fve_optimizer/fve-optimizer-card.js")
    assert resp.status == 200
    assert "customElements.define" in await resp.text()
    status = [s for s in hass.states.async_all("sensor") if s.attributes.get("data", {}).get("devices") is not None]
    assert status, "status sensor exposes live data for the card"


async def test_separate_positive_sensors_and_kw(hass: HomeAssistant) -> None:
    """Growatt style: import/export and charge/discharge as positive sensors, some in kW."""
    rec = Recorder(hass)
    config = {**_entry({"night_target": False}).data}
    config.pop("grid_power"); config.pop("battery_power")
    config.update(grid_import_power="sensor.imp", grid_export_power="sensor.exp",
                  battery_charge_power="sensor.chg", battery_discharge_power="sensor.dis")
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from homeassistant.config_entries import ConfigSubentryData
    from custom_components.fve_optimizer.const import DOMAIN
    entry = MockConfigEntry(domain=DOMAIN, title="FVE Optimizer", data=config, subentries_data=[
        ConfigSubentryData(data=BOILER, subentry_type="switched", title="Bojler", unique_id=None)])
    _states(hass, grid=0, batt=0, soc=95, limit="10000", switch__boiler="off")
    hass.states.async_set("sensor.imp", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.exp", "3.1", {"unit_of_measurement": "kW"})  # 3100 W export
    hass.states.async_set("sensor.chg", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.dis", "0", {"unit_of_measurement": "W"})
    coordinator = await _setup(hass, entry)
    assert coordinator.data.grid_w == -3100
    assert coordinator.data.battery_w == 0
    assert ("turn_on", "switch.boiler", None) in rec.calls

    hass.states.async_set("sensor.dis", "800", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.exp", "0", {"unit_of_measurement": "kW"})
    await coordinator.async_refresh()
    assert coordinator.data.battery_w == -800


async def test_sources_step_requires_one_way(hass: HomeAssistant) -> None:
    from custom_components.fve_optimizer.const import DOMAIN
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"grid_import_power": "sensor.imp", "battery_power": "sensor.batt", "battery_soc": "sensor.soc"},
    )
    assert result["errors"] == {"grid_power": "grid_source"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"grid_import_power": "sensor.imp", "grid_export_power": "sensor.exp",
         "battery_charge_power": "sensor.chg", "battery_discharge_power": "sensor.dis",
         "battery_soc": "sensor.soc"},
    )
    assert result["step_id"] == "battery"


async def test_grid_import_computed_from_house_load(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.fve_optimizer.const import DOMAIN
    Recorder(hass)
    config = {**_entry({"night_target": False}).data}
    config.pop("grid_power"); config.pop("battery_power")
    config.update(grid_export_power="sensor.exp", house_power="sensor.house", pv_power="sensor.pv",
                  battery_charge_power="sensor.chg", battery_discharge_power="sensor.dis")
    entry = MockConfigEntry(domain=DOMAIN, title="FVE Optimizer", data=config)
    _states(hass, grid=0, batt=0, soc=60)
    # Evening: house 1500 W, PV 300 W, battery discharging 900 W → 300 W from the grid.
    for e, v in (("sensor.exp", "0"), ("sensor.house", "1500"), ("sensor.pv", "300"),
                 ("sensor.chg", "0"), ("sensor.dis", "900")):
        hass.states.async_set(e, v, {"unit_of_measurement": "W"})
    coordinator = await _setup(hass, entry)
    assert coordinator.data.grid_w == 300
    # Noon: PV 6 kW, house 1 kW, charging 3 kW, export 2 kW → no import.
    for e, v in (("sensor.exp", "2000"), ("sensor.house", "1000"), ("sensor.pv", "6000"),
                 ("sensor.chg", "3000"), ("sensor.dis", "0")):
        hass.states.async_set(e, v, {"unit_of_measurement": "W"})
    await coordinator.async_refresh()
    assert coordinator.data.grid_w == -2000
