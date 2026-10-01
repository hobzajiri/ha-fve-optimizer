"""Fail-safe on missing / frozen inverter data, watch-only mode, current damping."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant

from .test_dispatcher import BOILER, EV, Recorder, _setup, _states
from .test_features import _entry, _min_boiler

PRAGUE = ZoneInfo("Europe/Prague")
TIMEOUT = {"night_target": False, "input_timeout_s": 300}


def _car():
    car = {**EV, "priority": 1}
    car.pop("three_phase_switch")
    return car


async def test_frozen_inverter_data_triggers_failsafe(hass: HomeAssistant, freezer) -> None:
    rec = Recorder(hass)
    _states(hass, grid=-3000, batt=0, soc=95, limit="10000", switch__boiler="on")
    coordinator = await _setup(hass, _entry(TIMEOUT, ("switched", BOILER)))
    assert coordinator.data.reason == "dispatching"

    # 2 minutes without any report: within the timeout → normal.
    freezer.tick(120)
    await coordinator.async_refresh()
    assert coordinator.data.reason == "dispatching"
    assert not coordinator.data.stale_inputs

    # 5+ minutes without a report = frozen → fail-safe stops the surplus-driven boiler.
    freezer.tick(200)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.reason == "failsafe"
    assert ("turn_off", "switch.boiler", None) in rec.calls

    # Data back (re-reported, same values) → normal operation again.
    for entity_id, value in (("sensor.grid", "-3000"), ("sensor.batt", "0"), ("sensor.soc", "95")):
        hass.states.async_set(entity_id, value, force_update=True)
    await coordinator.async_refresh()
    assert coordinator.data.reason == "dispatching"
    assert not coordinator.data.stale_inputs


async def test_unavailable_sensor_holds_then_failsafe(hass: HomeAssistant, freezer) -> None:
    rec = Recorder(hass)
    _states(hass, grid=-3000, batt=0, soc=95, limit="10000", switch__boiler="on")
    coordinator = await _setup(hass, _entry(TIMEOUT, ("switched", BOILER)))
    hass.states.async_set("sensor.grid", "unavailable")
    await coordinator.async_refresh()
    assert coordinator.data.reason == "missing_input"
    assert ("turn_off", "switch.boiler", None) not in rec.calls

    freezer.tick(301)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.reason == "failsafe"
    assert ("turn_off", "switch.boiler", None) in rec.calls


async def test_deadline_continues_in_failsafe(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    freezer.move_to(datetime(2026, 9, 30, 18, 30, tzinfo=PRAGUE))
    _states(hass, grid=500, batt=0, soc=95, switch__boiler="off", sensor__water="40")
    coordinator = await _setup(hass, _entry(TIMEOUT, ("switched", _min_boiler())))
    hass.states.async_set("sensor.soc", "unavailable")
    await coordinator.async_refresh()
    assert coordinator.data.reason == "missing_input"
    freezer.tick(301)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.reason == "failsafe"
    data = coordinator.data.devices[next(iter(coordinator.devices))]
    assert data["reason"] == "deadline_heating"
    assert ("turn_on", "switch.boiler", None) in rec.calls


async def test_watch_only_switches_nothing(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    _states(hass, grid=-7000, batt=0, soc=95, switch__boiler="off",
            switch__ev_charge="off", input_number__ev_current="6", binary_sensor__ev_connected="on")
    car = _car()
    coordinator = await _setup(hass, _entry({**TIMEOUT, "dry_run": True}, ("switched", BOILER), ("ev_charger", car)))
    assert rec.calls == []
    snap = coordinator.data
    assert snap.dry_run
    assert snap.allocated_w > 0  # it still shows what it would do
    assert snap.export_limit_raised  # virtually
    assert snap.decision.startswith("Watch only") or snap.decision.startswith("Jen sledování")


async def test_current_damping(hass: HomeAssistant, freezer) -> None:
    rec = Recorder(hass)
    car = {**_car(), "off_delay_s": 60, "off_tolerance_w": 300.0}
    # Charging 3f 10 A = 6900 W from surplus.
    _states(hass, grid=0, batt=0, soc=95, switch__ev_charge="on", input_number__ev_current="10",
            binary_sensor__ev_connected="on")
    coordinator = await _setup(hass, _entry({**TIMEOUT, "battery_borrow": False}, ("ev_charger", car)))
    rec.calls.clear()

    # Small dip: 250 W short (≤ 300 W tolerance) → wait for the turn-off delay.
    hass.states.async_set("sensor.grid", "150")  # budget 6900 − 150 − 100 = 6650 → wanted 9 A
    await coordinator.async_refresh()
    assert not any(c[1] == "input_number.ev_current" for c in rec.calls)
    freezer.tick(61)
    hass.states.async_set("sensor.grid", "151")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("set_value", "input_number.ev_current", 9) in rec.calls

    # Big drop (cloud): 2 kW short → immediately.
    rec.calls.clear()
    hass.states.async_set("input_number.ev_current", "9")
    hass.states.async_set("sensor.grid", "2000")  # 6210 − 2000 − 100 = 4110 → 5 A → min 6 A
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("set_value", "input_number.ev_current", 6) in rec.calls

    # Increase only after 30 s, to the lowest value seen meanwhile.
    rec.calls.clear()
    hass.states.async_set("input_number.ev_current", "6")
    hass.states.async_set("sensor.grid", "-3000")  # 4140 + 3000 − 100 = 7040 → 10 A
    await coordinator.async_refresh()
    freezer.tick(15)
    hass.states.async_set("sensor.grid", "-2000")  # → 8 A
    await coordinator.async_refresh()
    assert not any(c[1] == "input_number.ev_current" for c in rec.calls)
    freezer.tick(16)
    hass.states.async_set("sensor.grid", "-3001")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("set_value", "input_number.ev_current", 8) in rec.calls
