"""HDO sources (EG.D, PRE, manual) and deadline planning in HDO windows."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fve_optimizer import hdo
from custom_components.fve_optimizer.const import DOMAIN

from .test_dispatcher import BOILER, MAIN, Recorder, _setup, _states

FIXTURES = Path(__file__).parent / "fixtures"
PRAGUE = ZoneInfo("Europe/Prague")


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _hm(windows) -> list[str]:
    return [f"{a:%a %H:%M}-{b:%a %H:%M}" for a, b in windows]


def test_egd_windows_classic_and_command_code() -> None:
    records = json.loads(_fixture("egd_casy.json"))
    classic = hdo.egd_windows(records, "ZAPAD", "A1B4DP04", date(2026, 9, 30), PRAGUE)
    assert _hm(classic)[:2] == ["Wed 02:00-Wed 06:00", "Wed 14:00-Wed 18:00"]
    assert hdo.egd_windows(records, "ZAPAD", "a1 b4 dp4", date(2026, 9, 30), PRAGUE) == classic
    assert hdo.egd_windows(records, "ZAPAD", "152", date(2026, 9, 30), PRAGUE) == classic


def test_egd_holiday_uses_sunday_and_season_validity() -> None:
    records = json.loads(_fixture("egd_casy.json"))
    # 28 Oct 2026 (Wednesday) is a public holiday → Sunday table; still in the Sep–Oct season.
    assert date(2026, 10, 28) in hdo.czech_holidays(2026)
    assert hdo.schedule_weekday(date(2026, 10, 28)) == 7
    # 2026-11-05 is outside the Sep–Oct validity of the fixture records.
    try:
        windows = hdo.egd_windows(records, "ZAPAD", "A1B4DP04", date(2026, 11, 5), PRAGUE)
    except hdo.HdoError:
        windows = []
    assert windows == []


def test_easter() -> None:
    assert hdo._easter_sunday(2026) == date(2026, 4, 5)
    assert date(2026, 4, 3) in hdo.czech_holidays(2026)  # Good Friday
    assert date(2026, 4, 6) in hdo.czech_holidays(2026)  # Easter Monday


def test_pre_parsing() -> None:
    windows = hdo.pre_windows(_fixture("pre_485.html"), date(2026, 9, 30), PRAGUE)
    assert _hm(windows)[:2] == ["Wed 00:00-Wed 02:40", "Wed 03:20-Wed 07:20"]
    # 23:40-24:00 today merges with 00:00-02:40 tomorrow
    assert "Wed 23:40-Thu 02:40" in _hm(windows)
    options = hdo.pre_options(_fixture("pre_index.html"))
    assert options["485"].startswith("485")


def test_plan_prefers_latest_windows() -> None:
    day = date(2026, 9, 30)
    w = lambda a, b: (datetime.combine(day, datetime.strptime(a, "%H:%M").time(), PRAGUE),  # noqa: E731
                      datetime.combine(day, datetime.strptime(b, "%H:%M").time(), PRAGUE))
    windows = [w("12:00", "15:00"), w("15:40", "19:00")]
    now = datetime(2026, 9, 30, 13, 0, tzinfo=PRAGUE)
    plan, ok = hdo.plan_windows(windows, now, timedelta(hours=4))
    assert ok and [f"{a:%H:%M}-{b:%H:%M}" for a, b in plan] == ["14:20-15:00", "15:40-19:00"]
    plan, ok = hdo.plan_windows(windows, now, timedelta(hours=9))
    assert not ok


async def test_egd_config_flow(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(hdo.EGD_REGION_URL, text=_fixture("egd_region.json"))
    aioclient_mock.get(hdo.EGD_TIMES_URL, text=_fixture("egd_casy.json"))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"grid_power": "sensor.grid", "battery_power": "sensor.batt", "battery_soc": "sensor.soc"},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"hdo_source": "egd"})
    assert result["step_id"] == "hdo_egd"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"hdo_egd_psc": "373 71", "hdo_egd_code": "A9B9DP9"}
    )
    assert result["errors"] == {"hdo_egd_code": "egd_code_not_found"}
    with patch("custom_components.fve_optimizer.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"hdo_egd_psc": "373 71", "hdo_egd_code": "A1B4DP04"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["hdo_egd_region"] == "ZAPAD"
    assert result["data"]["hdo_egd_psc"] == "37371"
    with patch("custom_components.fve_optimizer.async_unload_entry", return_value=True):
        await hass.config_entries.async_remove(result["result"].entry_id)


async def test_egd_schedule_drives_deadline_plan(hass: HomeAssistant, aioclient_mock, freezer) -> None:
    """EG.D NT 14:00–18:00: heat as late as possible, not in the high tariff."""
    await hass.config.async_set_time_zone("Europe/Prague")
    aioclient_mock.get(hdo.EGD_TIMES_URL, text=_fixture("egd_casy.json"))
    rec = Recorder(hass)
    boiler = {
        **BOILER,
        "temperature_sensor": "sensor.water",
        "deadline_enabled": True,
        "deadline_time": "19:00:00",
        "deadline_temperature": 50.0,
        "deadline_hdo_only": True,
        "deadline_earliest": "12:00:00",
        "tank_volume_l": 160.0,
        "deadline_safety_factor": 1.2,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FVE Optimizer",
        data={**MAIN, "hdo_source": "egd", "hdo_egd_region": "ZAPAD", "hdo_egd_code": "A1B4DP04"},
        subentries_data=[
            ConfigSubentryData(data=boiler, subentry_type="switched", title="Bojler", unique_id=None)
        ],
    )
    # 40 → 50 °C: 1861 Wh / 2 kW × 1.2 = 67 min → plan 16:53–18:00 (NT ends at 18:00).
    freezer.move_to(datetime(2026, 9, 30, 15, 0, tzinfo=PRAGUE))
    _states(hass, grid=500, batt=0, soc=95, switch__boiler="off", sensor__water="40")
    coordinator = await _setup(hass, entry)
    subentry_id = next(iter(entry.subentries))
    data = coordinator.data.devices[subentry_id]
    assert data["deadline_plan"] == ["16:53-18:00"]
    assert data["reason"] == "waiting_for_hdo"
    assert hass.states.get("binary_sensor.fve_optimizer_hdo_low_tariff").state == "on"
    assert hass.states.get("binary_sensor.fve_optimizer_hdo_low_tariff").attributes["today"] == [
        "02:00-06:00",
        "14:00-18:00",
    ]
    assert ("turn_on", "switch.boiler", None) not in rec.calls

    freezer.move_to(datetime(2026, 9, 30, 17, 0, tzinfo=PRAGUE))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_on", "switch.boiler", None) in rec.calls
    assert coordinator.data.devices[subentry_id]["reason"] == "deadline_heating"

    # 18:10 – high tariff, not there yet (45 °C) → stop and wait; no NT until the deadline.
    freezer.move_to(datetime(2026, 9, 30, 18, 10, tzinfo=PRAGUE))
    hass.states.async_set("sensor.water", "45")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("turn_off", "switch.boiler", None) in rec.calls
    data = coordinator.data.devices[subentry_id]
    assert data["deadline_at_risk"] is True


async def test_manual_schedule(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    freezer.move_to(datetime(2026, 10, 3, 10, 0, tzinfo=PRAGUE))  # Saturday
    _states(hass, grid=0, batt=0, soc=95)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FVE Optimizer",
        data={**MAIN, "hdo_source": "manual", "hdo_manual_workday": "00:00-06:00; 13:00-15:00",
              "hdo_manual_weekend": "08:00-12:00"},
    )
    await _setup(hass, entry)
    state = hass.states.get("binary_sensor.fve_optimizer_hdo_low_tariff")
    assert state.state == "on"
    assert state.attributes["today"] == ["08:00-12:00"]
    assert state.attributes["tomorrow"] == ["08:00-12:00"]


async def test_egd_offline_uses_cached_windows(hass: HomeAssistant, aioclient_mock, freezer, hass_storage) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    aioclient_mock.get(hdo.EGD_TIMES_URL, status=503)
    freezer.move_to(datetime(2026, 9, 30, 15, 0, tzinfo=PRAGUE))
    _states(hass, grid=0, batt=0, soc=95)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FVE Optimizer",
        data={**MAIN, "hdo_source": "egd", "hdo_egd_region": "ZAPAD", "hdo_egd_code": "A1B4DP04"},
    )
    start = datetime(2026, 9, 30, 14, 0, tzinfo=PRAGUE)
    hass_storage[f"fve_optimizer.hdo.{entry.entry_id}"] = {
        "version": 1,
        "key": f"fve_optimizer.hdo.{entry.entry_id}",
        "data": {
            "key": "egd|ZAPAD|A1B4DP04|None|None",
            "windows": [(start.isoformat(), (start + timedelta(hours=4)).isoformat())],
        },
    }
    await _setup(hass, entry)
    state = hass.states.get("binary_sensor.fve_optimizer_hdo_low_tariff")
    assert state.state == "on"
    assert state.attributes["error"]


async def test_tariff_data_for_card(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    freezer.move_to(datetime(2026, 10, 2, 10, 30, tzinfo=PRAGUE))  # Friday, VT
    _states(hass, grid=0, batt=0, soc=95)
    entry = MockConfigEntry(
        domain=DOMAIN, title="FVE Optimizer",
        data={**MAIN, "hdo_source": "manual", "hdo_manual_workday": "00:00-09:00; 13:00-16:00",
              "price_vt": 3.4, "price_nt": 2.1},
    )
    coordinator = await _setup(hass, entry)
    data = coordinator.data.live_data
    assert data["price_vt"] == 3.4 and data["price_nt"] == 2.1
    assert data["hdo"] is False
    assert data["hdo_window"] is None
    assert data["hdo_next_window"][0].startswith("2026-10-02T13:00")
    freezer.move_to(datetime(2026, 10, 2, 14, 0, tzinfo=PRAGUE))
    await coordinator.async_refresh()
    data = coordinator.data.live_data
    assert data["hdo"] is True
    assert data["hdo_window"][1].startswith("2026-10-02T16:00")
