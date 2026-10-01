"""End-to-end tests of the config flow and the dispatch loop."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.fve_optimizer.const import DOMAIN

MAIN = {
    "grid_power": "sensor.grid",
    "grid_import_positive": True,
    "battery_power": "sensor.batt",
    "battery_charge_positive": True,
    "battery_soc": "sensor.soc",
    "battery_capacity_kwh": 10.0,
    "battery_target_soc": 90.0,
    "forecast_min_soc": 50.0,
    "forecast_safety_factor": 1.3,
    "house_avg_power_w": 500.0,
    "export_limit_entity": "input_number.export_limit",
    "export_limit_normal": 0.0,
    "export_limit_raised": 10000.0,
    "main_breaker_a": 25.0,
    "breaker_margin_a": 2.0,
    "reserve_w": 100.0,
    "update_interval": 15,
    # Tests jump in time without re-reporting sensors; the fail-safe has its own tests.
    "input_timeout_s": 0,
}

BOILER = {
    "name": "Bojler",
    "switch_entity": "switch.boiler",
    "nominal_power_w": 2000.0,
    "phases": "1",
    "max_temperature": 60.0,
    "min_on_time_s": 0,
    "min_off_time_s": 0,
    "priority": 1,
    "on_delay_s": 0,
    "off_delay_s": 0,
    "on_margin_w": 200.0,
    "off_tolerance_w": 300.0,
}

EV = {
    "name": "EcoVolter",
    "charge_switch": "switch.ev_charge",
    "current_entity": "input_number.ev_current",
    "three_phase_switch": "switch.ev_3f",
    "phases": "3",
    "connected_entity": "binary_sensor.ev_connected",
    "min_current": 6,
    "max_current": 16,
    "phase_switch_interval_s": 0,
    "priority": 2,
    "on_delay_s": 0,
    "off_delay_s": 0,
    "on_margin_w": 200.0,
    "off_tolerance_w": 300.0,
}


def _entry(*devices: tuple[str, dict]) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="FVE Optimizer",
        data=MAIN,
        subentries_data=[
            ConfigSubentryData(data=data, subentry_type=kind, title=data["name"], unique_id=None)
            for kind, data in devices
        ],
    )


def _states(hass: HomeAssistant, grid: float, batt: float, soc: float, **extra: str) -> None:
    hass.states.async_set("sensor.grid", str(grid))
    hass.states.async_set("sensor.batt", str(batt))
    hass.states.async_set("sensor.soc", str(soc))
    hass.states.async_set("input_number.export_limit", extra.pop("limit", "0"))
    for entity_id, value in extra.items():
        hass.states.async_set(entity_id.replace("__", "."), value)


class Recorder:
    """Records turn_on / turn_off / set_value calls and mirrors them into states."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.calls: list[tuple[str, str, object]] = []
        for service in ("turn_on", "turn_off"):
            hass.services.async_register("homeassistant", service, self._turn)
        hass.services.async_register("input_number", "set_value", self._set)

    async def _turn(self, call: ServiceCall) -> None:
        for entity_id in call.data["entity_id"] if isinstance(call.data["entity_id"], list) else [call.data["entity_id"]]:
            on = call.service == "turn_on"
            self.calls.append((call.service, entity_id, None))
            self.hass.states.async_set(entity_id, "on" if on else "off")

    async def _set(self, call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        entity_id = entity_id[0] if isinstance(entity_id, list) else entity_id
        self.calls.append(("set_value", entity_id, call.data["value"]))
        self.hass.states.async_set(entity_id, str(call.data["value"]))


async def _setup(hass: HomeAssistant, entry: MockConfigEntry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.fve_optimizer.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "grid_power": "sensor.grid",
                "grid_import_positive": True,
                "battery_power": "sensor.batt",
                "battery_charge_positive": True,
                "battery_soc": "sensor.soc",
            },
        )
        assert result["step_id"] == "battery"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "control"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "hdo"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"hdo_source": "none"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["battery_target_soc"] == 90.0
    with patch("custom_components.fve_optimizer.async_unload_entry", return_value=True):
        await hass.config_entries.async_remove(result["result"].entry_id)


async def test_subentry_flow_adds_boiler(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=MAIN)
    entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "switched"), context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.fve_optimizer.async_setup_entry", return_value=True):
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {"name": "Bojler", "switch_entity": "switch.boiler", "nominal_power_w": 2000},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(entry.subentries) == 1
    with patch("custom_components.fve_optimizer.async_unload_entry", return_value=True):
        await hass.config_entries.async_remove(entry.entry_id)


async def test_battery_priority_holds_devices(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    # 3 kW goes into the battery, SoC 40 % < 90 %, no forecast → battery first.
    _states(hass, grid=0, batt=3000, soc=40, switch__boiler="off")
    coordinator = await _setup(hass, _entry(("switched", BOILER)))
    assert coordinator.data.battery_priority
    assert ("turn_on", "switch.boiler", None) not in rec.calls
    # The boiler can store energy and there is no forecast → raised once in the morning.
    assert coordinator.data.export_limit_raised


async def test_boiler_then_ev_share_surplus(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    # Battery full, 7 kW exported (limit already raised).
    _states(
        hass, grid=-7000, batt=0, soc=95, limit="10000",
        switch__boiler="off", switch__ev_charge="off", input_number__ev_current="6",
        switch__ev_3f="on", binary_sensor__ev_connected="on",
    )
    coordinator = await _setup(hass, _entry(("switched", BOILER), ("ev_charger", EV)))
    snap = coordinator.data
    assert snap.budget_w == 6900
    assert ("turn_on", "switch.boiler", None) in rec.calls
    # 6900 - 2000 = 4900 W → 3 phases × 7 A = 4830 W
    assert ("set_value", "input_number.ev_current", 7) in rec.calls
    assert ("turn_on", "switch.ev_charge", None) in rec.calls
    assert snap.export_limit_raised


async def test_ev_drops_to_one_phase_then_stops(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    ev = {**EV, "priority": 1}
    # Charging 3f/6 A (4140 W), clouds: 1500 W imported → budget 2540 W.
    _states(
        hass, grid=1500, batt=0, soc=95,
        switch__ev_charge="on", input_number__ev_current="6",
        switch__ev_3f="on", binary_sensor__ev_connected="on",
    )
    coordinator = await _setup(hass, _entry(("ev_charger", ev)))
    assert ("turn_off", "switch.ev_3f", None) in rec.calls
    assert ("set_value", "input_number.ev_current", 11) in rec.calls  # floor(2540 / 230)
    del rec.calls[:]

    # Now 1ph/11 A = 2530 W and big import: budget 2530 - 2500 - 100 < 1380 - 300 → stop.
    hass.states.async_set("sensor.grid", "2500")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_off", "switch.ev_charge", None) in rec.calls


async def test_boiler_temperature_blocks(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    boiler = {**BOILER, "temperature_sensor": "sensor.water"}
    _states(hass, grid=-5000, batt=0, soc=95, switch__boiler="off", sensor__water="61")
    coordinator = await _setup(hass, _entry(("switched", boiler)))
    assert coordinator.data.devices[next(iter(coordinator.devices))]["reason"] == "temperature_reached"
    assert ("turn_on", "switch.boiler", None) not in rec.calls


async def test_forecast_lowers_battery_target(hass: HomeAssistant) -> None:
    Recorder(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, data={**MAIN, "forecast_remaining_today": "sensor.forecast"}
    )
    _states(hass, grid=0, batt=3000, soc=60, sensor__forecast="30")
    coordinator = await _setup(hass, entry)
    assert coordinator.data.forecast_covers_battery
    assert coordinator.data.effective_target_soc == 50.0
    assert not coordinator.data.battery_priority


async def test_breaker_limits_ev_current(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**MAIN, "phase_current_sensors": ["sensor.l1", "sensor.l2", "sensor.l3"]},
        subentries_data=[
            ConfigSubentryData(data={**EV, "priority": 1}, subentry_type="ev_charger", title="EV", unique_id=None)
        ],
    )
    # Plenty of surplus, but L2 already at 15 A: headroom 25 - 2 - 15 = 8 A.
    _states(
        hass, grid=-11000, batt=0, soc=95, limit="10000",
        switch__ev_charge="off", input_number__ev_current="6", switch__ev_3f="on",
        binary_sensor__ev_connected="on", sensor__l1="5", sensor__l2="15", sensor__l3="4",
    )
    await _setup(hass, entry)
    assert ("set_value", "input_number.ev_current", 8) in rec.calls


async def test_disable_restores_export_limit(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    _states(
        hass, grid=-3000, batt=0, soc=95,
        switch__ev_charge="off", input_number__ev_current="6", switch__ev_3f="on",
        binary_sensor__ev_connected="on",
    )
    entry = _entry(("ev_charger", EV))
    coordinator = await _setup(hass, entry)
    assert ("set_value", "input_number.export_limit", 10000.0) in rec.calls
    del rec.calls[:]
    await coordinator.async_set_enabled(False)
    await hass.async_block_till_done()
    assert ("set_value", "input_number.export_limit", 0.0) in rec.calls
    assert ("turn_off", "switch.ev_charge", None) in rec.calls


def _entity_id(hass: HomeAssistant, domain: str, unique_suffix: str) -> str:
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    matches = [
        e.entity_id
        for e in registry.entities.values()
        if e.domain == domain and e.unique_id.endswith(unique_suffix)
    ]
    assert len(matches) == 1, matches
    return matches[0]


async def test_hub_number_applies_without_reload(hass: HomeAssistant) -> None:
    Recorder(hass)
    _states(hass, grid=0, batt=3000, soc=80, switch__boiler="off")
    entry = _entry(("switched", BOILER))
    coordinator = await _setup(hass, entry)
    assert coordinator.data.battery_priority

    entity_id = _entity_id(hass, "number", "_battery_target_soc")
    assert hass.states.get(entity_id).state == "90.0"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 70}, blocking=True
    )
    await hass.async_block_till_done()

    assert entry.runtime_data is coordinator  # no reload happened
    assert entry.options["battery_target_soc"] == 70
    assert hass.states.get(entity_id).state == "70.0"
    assert not coordinator.data.battery_priority


async def test_device_number_and_select(hass: HomeAssistant) -> None:
    Recorder(hass)
    _states(hass, grid=0, batt=0, soc=95, switch__boiler="off")
    entry = _entry(("switched", BOILER))
    coordinator = await _setup(hass, entry)
    subentry_id = next(iter(entry.subentries))

    power_id = _entity_id(hass, "number", f"{subentry_id}_nominal_power_w")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": power_id, "value": 3000}, blocking=True
    )
    phases_id = _entity_id(hass, "select", f"{subentry_id}_phases")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": phases_id, "option": "3"}, blocking=True
    )
    await hass.async_block_till_done()

    assert entry.runtime_data is coordinator
    device = coordinator.devices[subentry_id]
    assert device.nominal_w == 3000
    assert device.phases == 3
    assert entry.subentries[subentry_id].data["nominal_power_w"] == 3000
    assert hass.states.get(phases_id).state == "3"


async def test_subentry_reconfigure(hass: HomeAssistant) -> None:
    Recorder(hass)
    _states(hass, grid=0, batt=0, soc=95, switch__boiler="off")
    entry = _entry(("switched", BOILER))
    coordinator = await _setup(hass, entry)
    subentry_id = next(iter(entry.subentries))

    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**BOILER, "priority": 5}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.runtime_data is coordinator  # only a tunable changed
    assert coordinator.devices[subentry_id].priority == 5

    # Changing the controlled entity is structural → reload.
    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**BOILER, "switch_entity": "switch.other"}
    )
    await hass.async_block_till_done()
    assert entry.runtime_data is not coordinator


async def test_boiler_deadline_heating(hass: HomeAssistant, freezer) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    await hass.config.async_set_time_zone("Europe/Prague")
    prague = ZoneInfo("Europe/Prague")
    rec = Recorder(hass)
    boiler = {
        **BOILER,
        "temperature_sensor": "sensor.water",
        "deadline_enabled": True,
        "deadline_time": "19:00:00",
        "deadline_temperature": 50.0,
        "tank_volume_l": 160.0,
        "deadline_hysteresis": 2.0,
        "deadline_safety_factor": 1.2,
    }
    # 160 l × 1.163 × 10 K = 1861 Wh → 0.93 h × 1.2 = 67 min + 10 min → start 17:43.
    freezer.move_to(datetime(2026, 9, 30, 17, 30, tzinfo=prague))
    _states(hass, grid=800, batt=0, soc=95, switch__boiler="off", sensor__water="40")
    entry = _entry(("switched", boiler))
    coordinator = await _setup(hass, entry)
    subentry_id = next(iter(entry.subentries))
    data = coordinator.data.devices[subentry_id]
    assert data["reason"] == "waiting_for_surplus"
    assert data["deadline_start"].startswith("2026-09-30T17:43")

    freezer.move_to(datetime(2026, 9, 30, 17, 45, tzinfo=prague))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_on", "switch.boiler", None) in rec.calls
    assert coordinator.data.devices[subentry_id]["reason"] == "deadline_heating"

    # Still heating past the deadline until the temperature is reached.
    freezer.move_to(datetime(2026, 9, 30, 19, 10, tzinfo=prague))
    hass.states.async_set("sensor.water", "49")
    await coordinator.async_refresh()
    assert coordinator.data.devices[subentry_id]["reason"] == "deadline_heating"

    hass.states.async_set("sensor.water", "50.5")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_off", "switch.boiler", None) in rec.calls


async def test_boiler_deadline_not_started_after_deadline(hass: HomeAssistant, freezer) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    boiler = {**BOILER, "temperature_sensor": "sensor.water", "deadline_enabled": True}
    freezer.move_to(datetime(2026, 9, 30, 19, 30, tzinfo=ZoneInfo("Europe/Prague")))
    _states(hass, grid=800, batt=0, soc=95, switch__boiler="off", sensor__water="30")
    await _setup(hass, _entry(("switched", boiler)))
    assert ("turn_on", "switch.boiler", None) not in rec.calls


async def test_deadline_entities_only_with_temperature(hass: HomeAssistant) -> None:
    Recorder(hass)
    _states(hass, grid=0, batt=0, soc=95, switch__boiler="off", sensor__water="40")
    entry = _entry(("switched", BOILER), ("switched", {**BOILER, "name": "Bojler 2", "temperature_sensor": "sensor.water"}))
    await _setup(hass, entry)
    times = sorted(s.entity_id for s in hass.states.async_all("time"))
    assert times == ["time.bojler_2_deadline_time", "time.bojler_2_grid_heating_not_before"]
    assert hass.states.get("time.bojler_2_deadline_time").state == "19:00:00"
    await hass.services.async_call(
        "time", "set_value", {"entity_id": "time.bojler_2_deadline_time", "time": "18:30"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("time.bojler_2_deadline_time").state == "18:30:00"
    assert hass.states.get("switch.bojler_2_heat_by_deadline").state == "off"


async def test_boiler_max_temperature_hysteresis(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    boiler = {**BOILER, "temperature_sensor": "sensor.water", "max_temperature": 75.0,
              "max_temperature_hysteresis": 3.0}
    _states(hass, grid=-5000, batt=0, soc=95, switch__boiler="on", sensor__water="75")
    entry = _entry(("switched", boiler))
    coordinator = await _setup(hass, entry)
    subentry_id = next(iter(entry.subentries))
    assert ("turn_off", "switch.boiler", None) in rec.calls
    assert coordinator.data.devices[subentry_id]["reason"] == "temperature_reached"
    del rec.calls[:]

    hass.states.async_set("sensor.water", "73")  # within hysteresis → stay off
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.devices[subentry_id]["reason"] == "temperature_reached"
    assert not rec.calls

    hass.states.async_set("sensor.water", "72")  # 75 - 3 → surplus heating again
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_on", "switch.boiler", None) in rec.calls


async def test_forecast_uses_house_load_without_managed(hass: HomeAssistant, freezer) -> None:
    Recorder(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**MAIN, "forecast_remaining_today": "sensor.forecast", "house_power": "sensor.load"},
        subentries_data=[
            ConfigSubentryData(data={**EV, "priority": 1}, subentry_type="ev_charger", title="EV", unique_id=None)
        ],
    )
    # EV draws 7 kW; total load 7.5 kW but base house load is only 500 W.
    _states(
        hass, grid=0, batt=2000, soc=60, sensor__forecast="12", sensor__load="7500",
        switch__ev_charge="on", input_number__ev_current="10", switch__ev_3f="on",
        binary_sensor__ev_connected="on", sensor__ev_power="7000",
    )
    hass.states.async_set(
        "sun.sun", "above_horizon", {"next_setting": "2026-09-30T16:00:00+00:00"}
    )
    freezer.move_to("2026-09-30T12:00:00+00:00")
    coordinator = await _setup(hass, entry)
    # need = 10 kWh × 30 % + 0.5 kW × 4 h = 5 kWh × 1.3 = 6.5 ≤ 12 → covered.
    # With the 7.5 kW total it would be (3 + 30) × 1.3 = 42.9 kWh → not covered.
    assert coordinator.data.forecast_covers_battery


async def test_control_step_rejects_low_watt_limit(hass: HomeAssistant) -> None:
    hass.states.async_set("input_number.export_limit", "0", {"unit_of_measurement": "W"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"grid_power": "sensor.grid", "battery_power": "sensor.batt", "battery_soc": "sensor.soc"},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"export_limit_entity": "input_number.export_limit", "export_limit_normal": 10, "export_limit_raised": 100},
    )
    assert result["errors"] == {"export_limit_raised": "raised_too_low_watts"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"export_limit_entity": "input_number.export_limit", "export_limit_normal": 100, "export_limit_raised": 100},
    )
    assert result["errors"] == {"export_limit_raised": "raised_not_above_normal"}


async def test_export_limit_hands_off(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    _states(
        hass, grid=-3000, batt=0, soc=95, limit="30",
        switch__ev_charge="off", input_number__ev_current="6", switch__ev_3f="on",
        binary_sensor__ev_connected="on",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**MAIN, "export_limit_control": False},
        subentries_data=[
            ConfigSubentryData(data=EV, subentry_type="ev_charger", title="EV", unique_id=None)
        ],
    )
    coordinator = await _setup(hass, entry)
    assert not any(c[1] == "input_number.export_limit" for c in rec.calls)
    assert ("turn_on", "switch.ev_charge", None) in rec.calls  # still dispatches
    await coordinator.async_set_enabled(False)
    assert not any(c[1] == "input_number.export_limit" for c in rec.calls)


async def test_control_step_percent_and_hands_off(hass: HomeAssistant) -> None:
    hass.states.async_set("input_number.export_limit", "0", {"unit_of_measurement": "%"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"grid_power": "sensor.grid", "battery_power": "sensor.batt", "battery_soc": "sensor.soc"},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    # Hands off: any values are accepted.
    with patch("custom_components.fve_optimizer.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"export_limit_entity": "input_number.export_limit", "export_limit_control": False,
             "export_limit_normal": 30, "export_limit_raised": 30},
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"hdo_source": "none"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    with patch("custom_components.fve_optimizer.async_unload_entry", return_value=True):
        await hass.config_entries.async_remove(result["result"].entry_id)


async def test_ev_starts_on_one_phase_when_three_is_too_much(hass: HomeAssistant) -> None:
    rec = Recorder(hass)
    ev = {**EV, "priority": 1, "phase_switch_interval_s": 900}
    # 3400 W: below 3f minimum (4140 W) but enough for 1f.
    _states(
        hass, grid=-3500, batt=0, soc=95, limit="100",
        switch__ev_charge="off", input_number__ev_current="6", switch__ev_3f="on",
        binary_sensor__ev_connected="on",
    )
    coordinator = await _setup(hass, _entry(("ev_charger", ev)))
    assert ("turn_off", "switch.ev_3f", None) in rec.calls
    assert ("set_value", "input_number.ev_current", 14) in rec.calls  # floor(3400/230)
    assert ("turn_on", "switch.ev_charge", None) in rec.calls
    # The start does not consume the phase switch interval.
    device = next(iter(coordinator.devices.values()))
    assert device._last_phase_switch == float("-inf")


async def test_boiler_deadline_only_in_hdo(hass: HomeAssistant, freezer) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    await hass.config.async_set_time_zone("Europe/Prague")
    prague = ZoneInfo("Europe/Prague")
    rec = Recorder(hass)
    boiler = {
        **BOILER,
        "temperature_sensor": "sensor.water",
        "deadline_enabled": True,
        "deadline_time": "19:00:00",
        "deadline_temperature": 50.0,
        "deadline_hdo_only": True,
        "deadline_earliest": "14:00:00",
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**MAIN, "hdo_entity": "binary_sensor.hdo"},
        subentries_data=[
            ConfigSubentryData(data=boiler, subentry_type="switched", title="Bojler", unique_id=None)
        ],
    )
    # 13:00, cold water, HDO on – too early: surplus still has its chance.
    freezer.move_to(datetime(2026, 9, 30, 13, 0, tzinfo=prague))
    _states(hass, grid=500, batt=0, soc=95, switch__boiler="off", sensor__water="40",
            binary_sensor__hdo="on")
    coordinator = await _setup(hass, entry)
    subentry_id = next(iter(entry.subentries))
    assert ("turn_on", "switch.boiler", None) not in rec.calls

    # 15:00, HDO off (high tariff) → waits.
    freezer.move_to(datetime(2026, 9, 30, 15, 0, tzinfo=prague))
    hass.states.async_set("binary_sensor.hdo", "off")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.devices[subentry_id]["reason"] == "waiting_for_hdo"
    assert ("turn_on", "switch.boiler", None) not in rec.calls

    # 15:30 HDO on → heats from the grid.
    freezer.move_to(datetime(2026, 9, 30, 15, 30, tzinfo=prague))
    hass.states.async_set("binary_sensor.hdo", "on")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_on", "switch.boiler", None) in rec.calls
    assert coordinator.data.devices[subentry_id]["reason"] == "deadline_heating"

    # 16:00 HDO off again at 45 °C → stops (min on time 0, off delay 0).
    freezer.move_to(datetime(2026, 9, 30, 16, 0, tzinfo=prague))
    hass.states.async_set("binary_sensor.hdo", "off")
    hass.states.async_set("sensor.water", "45")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_off", "switch.boiler", None) in rec.calls
    assert coordinator.data.devices[subentry_id]["reason"] == "waiting_for_hdo"

    # 17:00 HDO back → continues (45 °C is inside the hysteresis, but the run
    # already started today).
    del rec.calls[:]
    freezer.move_to(datetime(2026, 9, 30, 17, 0, tzinfo=prague))
    hass.states.async_set("binary_sensor.hdo", "on")
    hass.states.async_set("sensor.water", "49")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_on", "switch.boiler", None) in rec.calls


async def test_boiler_deadline_hdo_switch_off_uses_just_in_time(hass: HomeAssistant, freezer) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    await hass.config.async_set_time_zone("Europe/Prague")
    rec = Recorder(hass)
    boiler = {**BOILER, "temperature_sensor": "sensor.water", "deadline_enabled": True,
              "deadline_hdo_only": False}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**MAIN, "hdo_entity": "binary_sensor.hdo"},
        subentries_data=[
            ConfigSubentryData(data=boiler, subentry_type="switched", title="Bojler", unique_id=None)
        ],
    )
    freezer.move_to(datetime(2026, 9, 30, 18, 0, tzinfo=ZoneInfo("Europe/Prague")))
    _states(hass, grid=500, batt=0, soc=95, switch__boiler="off", sensor__water="40",
            binary_sensor__hdo="off")
    await _setup(hass, entry)
    assert ("turn_on", "switch.boiler", None) in rec.calls
