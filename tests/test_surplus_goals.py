"""Scenarios S1–S8: goal-first dispatch, taper export, sticky EV phases."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fve_optimizer.const import DOMAIN

from .test_dispatcher import BOILER, EV, MAIN, Recorder, _setup, _states


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


def _hub(**extra):
    return {
        "night_target": False,
        "battery_reserve_soc": 40.0,
        "battery_max_charge_w": 5000.0,
        "battery_borrow": True,
        **extra,
    }


def _boiler(**extra):
    return {
        **BOILER,
        "name": "Bojler",
        "nominal_power_w": 2200.0,
        "priority": 9,
        "on_margin_w": 100.0,
        "max_temperature": 72.0,
        **extra,
    }


def _car(**extra):
    return {
        **EV,
        "name": "EcoVolter",
        "priority": 10,
        "on_margin_w": 200.0,
        "phase_switch_interval_s": 900,
        **extra,
    }


async def test_s1_taper_export_starts_ev_one_phase(hass: HomeAssistant) -> None:
    """S1: battery absorbs little + 1.4 kW export → EV starts on 1φ (not 3φ)."""
    rec = Recorder(hass)
    # Boiler already at max → surplus goes to the car.
    boiler = _boiler(temperature_sensor="sensor.water", max_temperature=60.0)
    _states(
        hass,
        grid=-1400,
        batt=500,
        soc=55,
        limit="10000",
        switch__boiler="off",
        sensor__water="61",
        switch__ev_charge="off",
        input_number__ev_current="6",
        switch__ev_3f="off",
        binary_sensor__ev_connected="on",
    )
    coordinator = await _setup(
        hass, _entry(_hub(), ("switched", boiler), ("ev_charger", _car()))
    )
    snap = coordinator.data
    assert not snap.battery_priority
    assert snap.budget_w >= 1300
    assert snap.budget_parts["battery_reserved"] == 0.0
    assert ("turn_on", "switch.ev_charge", None) in rec.calls
    assert ("turn_on", "switch.ev_3f", None) not in rec.calls


async def test_s1_hard_priority_reserves_only_observed_on_export(hass: HomeAssistant) -> None:
    """Below reserve with export: reserve observed charge only."""
    Recorder(hass)
    _states(hass, grid=-1400, batt=500, soc=5, limit="10000", switch__boiler="off")
    coordinator = await _setup(
        hass, _entry(_hub(battery_reserve_soc=10.0), ("switched", _boiler()))
    )
    snap = coordinator.data
    assert snap.battery_priority
    assert snap.budget_parts["battery_reserved"] == 500
    assert snap.budget_w == 1300  # 1400 + 500 − 100 − 500


async def test_s2_boiler_minimum_before_battery(hass: HomeAssistant) -> None:
    """S2: boiler below deadline temp uses full budget under hard battery priority."""
    rec = Recorder(hass)
    boiler = _boiler(
        temperature_sensor="sensor.water",
        deadline_enabled=True,
        deadline_time="19:00:00",
        deadline_temperature=54.0,
        deadline_hdo_only=False,
    )
    _states(hass, grid=0, batt=3000, soc=5, switch__boiler="off", sensor__water="40")
    coordinator = await _setup(
        hass, _entry(_hub(battery_reserve_soc=10.0), ("switched", boiler))
    )
    assert coordinator.data.battery_priority
    assert ("turn_on", "switch.boiler", None) in rec.calls
    sid = next(iter(coordinator.devices))
    assert coordinator.data.devices[sid]["reason"] == "running"


async def test_s4_soft_battery_no_idle_dump(hass: HomeAssistant) -> None:
    """S4: minima N/A, EV unplugged, boiler at max → no pointless start."""
    rec = Recorder(hass)
    boiler = _boiler(temperature_sensor="sensor.water", max_temperature=60.0)
    _states(
        hass,
        grid=-2000,
        batt=0,
        soc=55,
        limit="10000",
        switch__boiler="off",
        sensor__water="61",
        switch__ev_charge="off",
        input_number__ev_current="6",
        switch__ev_3f="off",
        binary_sensor__ev_connected="off",
    )
    await _setup(hass, _entry(_hub(), ("switched", boiler), ("ev_charger", _car())))
    assert ("turn_on", "switch.boiler", None) not in rec.calls
    assert ("turn_on", "switch.ev_charge", None) not in rec.calls


async def test_s5_surplus_dump_prefers_three_phase(hass: HomeAssistant) -> None:
    """S5: large surplus, EV under max SoC → start on 3φ."""
    rec = Recorder(hass)
    _states(
        hass,
        grid=-6000,
        batt=0,
        soc=55,
        limit="10000",
        switch__boiler="off",
        switch__ev_charge="off",
        input_number__ev_current="6",
        switch__ev_3f="off",
        binary_sensor__ev_connected="on",
    )
    await _setup(hass, _entry(_hub(), ("ev_charger", _car(priority=1))))
    assert ("turn_on", "switch.ev_3f", None) in rec.calls
    assert ("turn_on", "switch.ev_charge", None) in rec.calls


async def test_s6_sticky_three_phase_short_dip(hass: HomeAssistant) -> None:
    """S6: running 3φ, short dip below 3φ min → stay on 3φ (no switch to 1φ)."""
    rec = Recorder(hass)
    _states(
        hass,
        grid=-6000,
        batt=0,
        soc=55,
        limit="10000",
        switch__ev_charge="on",
        input_number__ev_current="6",
        switch__ev_3f="on",
        binary_sensor__ev_connected="on",
    )
    coordinator = await _setup(
        hass, _entry(_hub(), ("ev_charger", _car(priority=1, off_delay_s=60)))
    )
    assert ("turn_off", "switch.ev_3f", None) not in rec.calls
    del rec.calls[:]

    hass.states.async_set("sensor.grid", "1500")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_off", "switch.ev_3f", None) not in rec.calls


async def test_s7_one_to_three_after_stable_surplus(hass: HomeAssistant) -> None:
    """S7: start 1φ; after surplus rises → switch to 3φ."""
    rec = Recorder(hass)
    car = _car(priority=1, off_delay_s=0, phase_switch_interval_s=0)
    _states(
        hass,
        grid=-1600,
        batt=0,
        soc=55,
        limit="10000",
        switch__ev_charge="off",
        input_number__ev_current="6",
        switch__ev_3f="off",
        binary_sensor__ev_connected="on",
    )
    coordinator = await _setup(hass, _entry(_hub(), ("ev_charger", car)))
    assert ("turn_on", "switch.ev_charge", None) in rec.calls
    assert ("turn_on", "switch.ev_3f", None) not in rec.calls
    del rec.calls[:]

    hass.states.async_set("sensor.grid", "-6000")
    hass.states.async_set("switch.ev_charge", "on")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_on", "switch.ev_3f", None) in rec.calls


async def test_s8_hard_reserve_holds_devices(hass: HomeAssistant) -> None:
    """S8: SoC below reserve, no export → hard priority blocks surplus dump."""
    rec = Recorder(hass)
    _states(
        hass,
        grid=0,
        batt=2000,
        soc=35,
        limit="10000",
        switch__boiler="off",
        switch__ev_charge="off",
        input_number__ev_current="6",
        switch__ev_3f="off",
        binary_sensor__ev_connected="on",
    )
    coordinator = await _setup(
        hass,
        _entry(_hub(battery_reserve_soc=40.0), ("switched", _boiler()), ("ev_charger", _car())),
    )
    assert coordinator.data.battery_priority
    assert coordinator.data.budget_parts["battery_reserved"] == 5000.0
    assert ("turn_on", "switch.boiler", None) not in rec.calls
    assert ("turn_on", "switch.ev_charge", None) not in rec.calls
