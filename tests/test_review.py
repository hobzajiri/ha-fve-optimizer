"""Daily AI review via the AI Task service."""

from __future__ import annotations

from datetime import datetime
import json
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.fve_optimizer.review import (
    DECISION_LOG_FOR_AI,
    _clamp_score,
    _limit_delay_delta,
    _switching_stats,
    parse_proposals,
)
from .test_dispatcher import BOILER, Recorder, _setup, _states
from .test_features import _entry

PRAGUE = ZoneInfo("Europe/Prague")


def test_switching_stats_ignores_non_integration_for_gap() -> None:
    stats = _switching_stats([
        "10:00 on (integrace)",
        "10:05 off (mimo integraci)",
        "10:06 on (mimo integraci)",
        "10:07 off (mimo integraci)",
        "11:00 on (integrace)",
        "11:30 off (integrace)",
    ])
    assert stats["total"] == 6
    assert stats["integration_count"] == 3
    assert stats["by_source"]["mimo integraci"] == 3
    # Hour 10 has only 1 integration event; hour 11 has 2 – external spam ignored.
    assert stats["max_per_hour"] == 2
    assert stats["min_gap_min"] == 30  # 10:00 → 11:00 → 11:30; min of 60 and 30
    assert stats["short_cycles"] == 0


def test_switching_stats_detects_short_cycles() -> None:
    stats = _switching_stats([
        "12:00 on (integrace)",
        "12:03 off (integrace)",
        "12:05 on (integrace)",  # on→off→on in 5 min
        "14:00 off (integrace)",
        "14:20 on (integrace)",
        "15:00 off (integrace)",  # long cycle – not short
    ])
    assert stats["short_cycles"] == 1
    assert stats["integration_count"] == 6


def test_clamp_score() -> None:
    assert _clamp_score(7) == 7
    assert _clamp_score(0) == 1
    assert _clamp_score(15) == 10
    assert _clamp_score("3.6") == 4


def _fake_ai(hass: HomeAssistant, answer: dict | None = None, fail: bool = False) -> list[ServiceCall]:
    calls: list[ServiceCall] = []

    async def generate(call: ServiceCall):
        calls.append(call)
        if fail:
            raise RuntimeError("quota exceeded")
        structure = call.data.get("structure") or {}
        if answer is not None:
            data = answer
        elif "answer" in structure:
            data = {"answer": "Delay neprodlužuj – sepnutí integrace je v normě."}
        elif "expectations" in structure:
            data = {
                "summary": "Dnes ~12 kWh, baterie se nabije, bojler stihne termín.",
                "expectations": "- výroba 12 kWh\n- baterie do cíle\n- bojler ze slunce",
                "risks": "Žádné",
            }
        elif "battery_expected_soc" in structure:
            data = {
                "summary": "Baterie se dnes nabije k cíli, bojler stihne termín ze slunce.",
                "battery_expected_soc": 92,
                "battery_note": "Do večera ~92 % při stávající predikci.",
                "devices": "- bojler: stihne 55 °C\n- auto: bez termínu",
                "risks": "Žádné",
            }
        else:
            data = {
                "score": 7, "summary": "Přebytky využity dobře.", "good": "- bojler ze slunce",
                "problems": "- bojler 6× vypnut",
                "suggestions": "Bojler – off_delay_s: z 60 na 180 – mraky",
                "proposals": json.dumps([{
                    "target": "Bojler",
                    "key": "off_delay_s",
                    "from": 60,
                    "to": 180,
                    "reason": "mraky",
                }], ensure_ascii=False),
                "outlook": "- Bojler do 19:00 zvládne v NT\n- Auto bez rizika",
            }
        return {"conversation_id": "x", "data": data}

    hass.services.async_register("ai_task", "generate_data", generate, supports_response=SupportsResponse.ONLY)
    return calls


async def test_review_on_request(hass: HomeAssistant) -> None:
    Recorder(hass)
    calls = _fake_ai(hass)
    _states(hass, grid=-3000, batt=0, soc=95, limit="10000", switch__boiler="off")
    coordinator = await _setup(hass, _entry({"ai_task_entity": "ai_task.test"}, ("switched", BOILER)))
    result = await hass.services.async_call("fve_optimizer", "run_review", {}, blocking=True, return_response=True)
    await hass.async_block_till_done()
    review = result["reviews"][0]
    assert review["score"] == 7 and "off_delay_s" in review["suggestions"]
    # The AI got today's data and the structure.
    call = calls[0].data
    assert call["entity_id"] == "ai_task.test"
    assert set(call["structure"]) == {
        "score", "summary", "good", "problems", "suggestions", "proposals", "outlook",
    }
    instructions = call["instructions"]
    assert "Známka 1–10" in instructions
    assert "morning_plan" in instructions
    assert "klíč_parametru" in instructions or "klíče parametrů" in instructions
    data = json.loads(instructions.split("Data dne:\n", 1)[1])
    assert "Bojler" in data["devices"] and "settings" in data and "decision_log" in data
    assert "scoring_hints" in data
    assert "morning_plan" in data
    assert "charge_forecast" in data
    assert "short_cycles" in data["devices"]["Bojler"]["switching"]
    hub = data["settings"]["FVE Optimizer"]
    assert "notify_on_review" not in hub
    assert "ai_review_enabled" not in hub
    assert "outlook" in data and "forecast" in data["outlook"]
    assert coordinator.data.live_data["outlook"]["battery"]["soc"] == 95
    assert review.get("outlook")
    assert review["proposals"][0]["key"] == "off_delay_s"
    assert review["proposals"][0]["status"] == "pending"
    sensor = [s for s in hass.states.async_all("sensor") if "suggestions" in s.attributes][0]
    assert sensor.state == "7"
    assert coordinator.data.live_data["review"]["score"] == 7
    buttons = hass.states.async_all("button")
    assert len(buttons) == 3  # review_now + morning_brief + charge_forecast


async def test_review_clamps_score(hass: HomeAssistant) -> None:
    Recorder(hass)
    _fake_ai(hass, answer={
        "score": 99, "summary": "x", "good": "-", "problems": "Žádné",
        "suggestions": "Žádné", "proposals": "[]", "outlook": "Žádné",
    })
    _states(hass, grid=0, batt=0, soc=95)
    await _setup(hass, _entry({"ai_task_entity": "ai_task.test"}))
    result = await hass.services.async_call("fve_optimizer", "run_review", {}, blocking=True, return_response=True)
    assert result["reviews"][0]["score"] == 10


async def test_review_scheduled_once_a_day(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    calls = _fake_ai(hass)
    freezer.move_to(datetime(2026, 10, 2, 20, 59, 30, tzinfo=PRAGUE))
    _states(hass, grid=0, batt=0, soc=95)
    coordinator = await _setup(hass, _entry({"ai_task_entity": "ai_task.test", "ai_review_time": "21:00:00"}))
    freezer.move_to(datetime(2026, 10, 2, 21, 0, 0, tzinfo=PRAGUE))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(calls) == 1
    freezer.move_to(datetime(2026, 10, 2, 21, 0, 0, 500000, tzinfo=PRAGUE))
    await coordinator.async_scheduled_review(datetime(2026, 10, 2, 21, 0, tzinfo=PRAGUE))
    assert len(calls) == 1  # not twice the same day
    assert coordinator.reviews[0]["date"] == "2026-10-02"


async def test_review_failure_is_reported(hass: HomeAssistant) -> None:
    Recorder(hass)
    _fake_ai(hass, fail=True)
    _states(hass, grid=0, batt=0, soc=95)
    coordinator = await _setup(hass, _entry({"ai_task_entity": "ai_task.test"}))
    await coordinator.async_scheduled_review(datetime.now(PRAGUE).replace(hour=21, minute=0))
    try:
        await coordinator.async_run_review()
    except RuntimeError:
        pass
    assert "quota" in coordinator.review_error
    assert coordinator.reviews == []


async def test_no_review_entities_without_ai(hass: HomeAssistant) -> None:
    Recorder(hass)
    _states(hass, grid=0, batt=0, soc=95)
    await _setup(hass, _entry({}))
    assert hass.states.async_all("button") == []
    assert not [s for s in hass.states.async_all("sensor") if "suggestions" in s.attributes]


async def test_day_outlook_includes_deadline_plan(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    freezer.move_to(datetime(2026, 10, 2, 12, 0, tzinfo=PRAGUE))
    _states(hass, grid=-500, batt=2000, soc=40, switch__boiler="off", sensor__water="35")
    boiler = {
        **BOILER,
        "temperature_sensor": "sensor.water",
        "deadline_enabled": True,
        "deadline_time": "19:00:00",
        "deadline_temperature": 50.0,
        "deadline_hdo_only": False,
        "tank_volume_l": 120,
    }
    coordinator = await _setup(hass, _entry({"night_target": False}, ("switched", boiler)))
    outlook = coordinator.data.live_data["outlook"]
    assert outlook["battery"]["priority"] is True
    device = outlook["devices"][0]
    assert device["name"] == "Bojler"
    assert device["mode"] == "deadline"
    assert device["need_kwh"] > 0
    assert device["deadline_start"] or device["deadline"]


async def test_day_overview_counts_switching_and_grid(hass: HomeAssistant, freezer) -> None:
    Recorder(hass)
    _states(hass, grid=-3000, batt=0, soc=95, limit="10000", switch__boiler="off")
    coordinator = await _setup(hass, _entry({}, ("switched", BOILER)))
    for _ in range(4):
        freezer.tick(15)
        await coordinator.async_refresh()
    day = coordinator.today()
    sid = next(iter(coordinator.devices))
    assert day["switches"][sid][0].endswith(" on (integrace)")
    assert day["export_kwh"] > 0
    assert day["log"]


async def test_switch_sources_and_recommendation_outcomes(hass: HomeAssistant, freezer) -> None:
    Recorder(hass)
    calls = _fake_ai(hass)
    _states(hass, grid=-3000, batt=0, soc=95, limit="10000", switch__boiler="off")
    coordinator = await _setup(
        hass, _entry({"dry_run": True, "export_limit_control": False, "ai_task_entity": "ai_task.t"},
                     ("switched", BOILER))
    )
    sid = next(iter(coordinator.devices))
    assert coordinator.open_recommendations()  # boiler: turn on

    # 1) The user carries it out with the button.
    freezer.tick(15)
    await hass.services.async_call("fve_optimizer", "execute_recommendation", {"id": sid}, blocking=True)
    await hass.async_block_till_done()
    freezer.tick(15)
    await coordinator.async_refresh()
    day = coordinator.today()
    assert day["switches"][sid][-1].endswith("on (tlačítko Provést)")
    assert day["recommendations"][-1]["outcome"].startswith("provedeno tlačítkem")

    # 2) Surplus gone → recommendation "turn off"; the user switches it off by hand.
    hass.states.async_set("sensor.grid", "3000")
    for _ in range(2):
        freezer.tick(15)
        await coordinator.async_refresh()
    assert coordinator.open_recommendations()
    hass.states.async_set("switch.boiler", "off")
    hass.states.async_set("sensor.grid", "1000")
    freezer.tick(15)
    await coordinator.async_refresh()
    day = coordinator.today()
    assert day["switches"][sid][-1].endswith("off (mimo integraci)")
    assert day["recommendations"][-1]["outcome"].startswith("vyřešeno mimo integraci")
    assert day["plan_match"][sid][1] > 0

    # The AI gets all of it.
    await coordinator.async_run_review()
    data = json.loads(calls[0].data["instructions"].split("Data dne:\n", 1)[1])
    assert data["recommendations"]["finished"]
    assert data["devices"]["Bojler"]["plan_match_pct"] is not None
    assert any("mimo integraci" in s for s in data["devices"]["Bojler"]["switch_times"])
    switching = data["devices"]["Bojler"]["switching"]
    assert switching["total"] >= 2
    assert switching["by_source"]
    assert "short_cycles" in switching
    assert "Spínání – jen skutečná sepnutí" in calls[0].data["instructions"]
    assert data["scoring_hints"]["integration_switches"] >= 0


async def test_review_payload_trims_decision_log(hass: HomeAssistant) -> None:
    Recorder(hass)
    calls = _fake_ai(hass)
    _states(hass, grid=0, batt=0, soc=95)
    coordinator = await _setup(hass, _entry({"ai_task_entity": "ai_task.test"}))
    day = coordinator.today()
    day["log"] = [f"{i:02d}:00 entry" for i in range(DECISION_LOG_FOR_AI + 20)]
    await coordinator.async_run_review()
    data = json.loads(calls[0].data["instructions"].split("Data dne:\n", 1)[1])
    assert len(data["decision_log"]) == DECISION_LOG_FOR_AI
    assert data["decision_log"][0].endswith("entry")
    assert data["decision_log"][-1] == day["log"][-1]


async def test_ask_review_appends_discussion(hass: HomeAssistant) -> None:
    Recorder(hass)
    calls = _fake_ai(hass)
    _states(hass, grid=0, batt=0, soc=95)
    coordinator = await _setup(hass, _entry({"ai_task_entity": "ai_task.test"}))
    await coordinator.async_run_review()
    result = await hass.services.async_call(
        "fve_optimizer",
        "ask_review",
        {"question": "Proč prodlužovat off_delay_s?"},
        blocking=True,
        return_response=True,
    )
    turn = result["turns"][0]
    assert "Delay neprodlužuj" in turn["answer"]
    assert coordinator.reviews[0]["discussion"][-1]["question"] == "Proč prodlužovat off_delay_s?"
    assert coordinator.data.live_data["review"]["discussion"]
    assert "day_data" not in coordinator.data.live_data["review"]
    discuss_call = calls[1]
    assert "diskuse k hodnocení" in discuss_call.data["task_name"]
    payload = json.loads(discuss_call.data["instructions"].split("Kontext (JSON):\n", 1)[1])
    assert payload["question"].startswith("Proč")
    assert payload["review"]["score"] == 7
    assert "day_data" in payload


async def test_morning_brief_and_evening_payload(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    calls = _fake_ai(hass)
    freezer.move_to(datetime(2026, 10, 7, 7, 0, tzinfo=PRAGUE))
    _states(hass, grid=-500, batt=2000, soc=40)
    coordinator = await _setup(
        hass,
        _entry({
            "ai_task_entity": "ai_task.test",
            "ai_morning_time": "07:00:00",
            "ai_charge_forecast_enabled": False,
        }),
    )
    result = await hass.services.async_call(
        "fve_optimizer", "run_morning_brief", {}, blocking=True, return_response=True
    )
    plan = result["plans"][0]
    assert plan["summary"].startswith("Dnes")
    assert plan["snapshot"]["outlook"]["forecast"]
    assert coordinator.morning_plan["date"] == "2026-10-07"
    assert coordinator.data.live_data["morning_plan"]["summary"]
    assert "snapshot" not in coordinator.data.live_data["morning_plan"]
    assert "ranní předpoklad" in calls[0].data["task_name"]

    # Evening review gets the morning plan in day_data.
    await coordinator.async_run_review()
    review_call = calls[1]
    data = json.loads(review_call.data["instructions"].split("Data dne:\n", 1)[1])
    assert data["morning_plan"]["date"] == "2026-10-07"
    assert data["morning_plan"]["snapshot"]["outlook"]
    assert data["charge_forecast"] is None


async def test_morning_brief_scheduled_once_a_day(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    calls = _fake_ai(hass)
    freezer.move_to(datetime(2026, 10, 7, 6, 59, 30, tzinfo=PRAGUE))
    _states(hass, grid=0, batt=0, soc=50)
    coordinator = await _setup(
        hass,
        _entry({
            "ai_task_entity": "ai_task.test",
            "ai_morning_enabled": True,
            "ai_morning_time": "07:00:00",
            "ai_review_enabled": False,
            "ai_charge_forecast_enabled": False,
        }),
    )
    freezer.move_to(datetime(2026, 10, 7, 7, 0, 0, tzinfo=PRAGUE))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert coordinator.morning_plan["date"] == "2026-10-07"
    freezer.move_to(datetime(2026, 10, 7, 7, 0, 0, 500000, tzinfo=PRAGUE))
    await coordinator.async_scheduled_morning(datetime(2026, 10, 7, 7, 0, tzinfo=PRAGUE))
    assert len(calls) == 1  # not twice the same day


async def test_charge_forecast_service_and_day_data(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    calls = _fake_ai(hass)
    freezer.move_to(datetime(2026, 10, 7, 10, 0, tzinfo=PRAGUE))
    _states(hass, grid=-800, batt=1500, soc=55)
    coordinator = await _setup(
        hass,
        _entry({
            "ai_task_entity": "ai_task.test",
            "ai_charge_forecast_enabled": True,
        }),
    )
    morning_summary = "Ranní baseline – neměnit."
    coordinator.morning_plan = {
        "date": "2026-10-07",
        "at": "2026-10-07T07:00:00+02:00",
        "summary": morning_summary,
        "expectations": "- baterie",
        "risks": "Žádné",
        "snapshot": {"outlook": {"forecast": {"remaining_kwh": 10}}},
    }
    result = await hass.services.async_call(
        "fve_optimizer", "run_charge_forecast", {}, blocking=True, return_response=True
    )
    forecast = result["forecasts"][0]
    assert forecast["battery_expected_soc"] == 92
    assert "Baterie" in forecast["summary"]
    assert coordinator.charge_forecast["date"] == "2026-10-07"
    assert coordinator.data.live_data["charge_forecast"]["battery_expected_soc"] == 92
    assert "snapshot" not in coordinator.data.live_data["charge_forecast"]
    assert "předpověď nabití" in calls[0].data["task_name"]
    # Refresh must not overwrite morning_plan.
    assert coordinator.morning_plan["summary"] == morning_summary

    await coordinator.async_run_review()
    review_call = calls[1]
    data = json.loads(review_call.data["instructions"].split("Data dne:\n", 1)[1])
    assert data["charge_forecast"]["battery_expected_soc"] == 92
    assert data["morning_plan"]["summary"] == morning_summary


async def test_charge_forecast_schedule_every_3h(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    calls = _fake_ai(hass)
    freezer.move_to(datetime(2026, 10, 7, 9, 59, 30, tzinfo=PRAGUE))
    _states(hass, grid=-500, batt=1000, soc=60)
    coordinator = await _setup(
        hass,
        _entry({
            "ai_task_entity": "ai_task.test",
            "ai_morning_enabled": False,
            "ai_review_enabled": False,
            "ai_charge_forecast_enabled": True,
            "ai_morning_time": "07:00:00",
        }),
    )
    # 10:00 = 3 h after 07:00 → first mid-day slot
    freezer.move_to(datetime(2026, 10, 7, 10, 0, 0, tzinfo=PRAGUE))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert coordinator.charge_forecast["date"] == "2026-10-07"
    # Same minute again → skipped
    await coordinator.async_scheduled_charge_forecast(
        datetime(2026, 10, 7, 10, 0, tzinfo=PRAGUE)
    )
    assert len(calls) == 1
    # 11:00 is not a 3 h boundary
    freezer.move_to(datetime(2026, 10, 7, 11, 0, 0, tzinfo=PRAGUE))
    await coordinator.async_scheduled_charge_forecast(
        datetime(2026, 10, 7, 11, 0, tzinfo=PRAGUE)
    )
    assert len(calls) == 1
    # 13:00 = next 3 h slot
    freezer.move_to(datetime(2026, 10, 7, 13, 0, 0, tzinfo=PRAGUE))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(calls) == 2


async def test_ask_review_requires_prior_review(hass: HomeAssistant) -> None:
    Recorder(hass)
    _fake_ai(hass)
    _states(hass, grid=0, batt=0, soc=95)
    await _setup(hass, _entry({"ai_task_entity": "ai_task.test"}))
    try:
        await hass.services.async_call(
            "fve_optimizer", "ask_review", {"question": "Proč?"}, blocking=True
        )
        raise AssertionError("expected error")
    except Exception as err:  # noqa: BLE001 – HomeAssistantError wrapping
        assert "review" in str(err).lower() or "No review" in str(err)


def test_limit_delay_delta() -> None:
    assert _limit_delay_delta(60, 1000) == 360  # max(×3, +300) → 360
    assert _limit_delay_delta(200, 1000) == 600  # ×3
    assert _limit_delay_delta(600, 100) == 200  # min(/3, −300) as floor


async def test_parse_proposals_whitelist(hass: HomeAssistant) -> None:
    Recorder(hass)
    _fake_ai(hass)
    _states(hass, grid=0, batt=0, soc=95, switch__boiler="off")
    coordinator = await _setup(hass, _entry({"ai_task_entity": "ai_task.test"}, ("switched", BOILER)))
    parsed = parse_proposals(
        coordinator,
        [
            {"target": "Bojler", "key": "off_delay_s", "from": 60, "to": 180, "reason": "ok"},
            {"target": "Bojler", "key": "dry_run", "from": False, "to": True, "reason": "no"},
            {"target": "hub", "key": "reserve_w", "from": 100, "to": 150, "reason": "ok"},
            {"target": "Neexistuje", "key": "off_delay_s", "from": 60, "to": 90, "reason": "x"},
        ],
    )
    pending = [p for p in parsed if p["status"] == "pending"]
    invalid = [p for p in parsed if p["status"] == "invalid"]
    assert {p["key"] for p in pending} == {"off_delay_s", "reserve_w"}
    assert any(p["error"] == "key_not_allowed" for p in invalid)
    assert any(p["error"] == "unknown_target" for p in invalid)


async def test_apply_and_dismiss_ai_proposal(hass: HomeAssistant) -> None:
    Recorder(hass)
    events: list = []
    hass.bus.async_listen("fve_optimizer_proposal_applied", lambda e: events.append(e))
    _fake_ai(hass)
    _states(hass, grid=-3000, batt=0, soc=95, switch__boiler="off")
    coordinator = await _setup(hass, _entry({"ai_task_entity": "ai_task.test"}, ("switched", BOILER)))
    await coordinator.async_run_review()
    props = coordinator.reviews[0]["proposals"]
    pending = [p for p in props if p["status"] == "pending"]
    assert pending
    prop = pending[0]
    sid = prop["subentry_id"]
    before = coordinator.devices[sid].config.get("off_delay_s")
    morning = {"date": "2026-10-07", "summary": "baseline", "snapshot": {}}
    coordinator.morning_plan = morning

    result = await hass.services.async_call(
        "fve_optimizer",
        "apply_ai_proposal",
        {"id": prop["id"]},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    applied = result["proposals"][0]
    assert applied["status"] == "applied"
    assert coordinator.devices[sid].config.get("off_delay_s") == prop["to"]
    assert coordinator.devices[sid].config.get("off_delay_s") != before
    assert coordinator.morning_plan["summary"] == "baseline"
    assert events and events[0].data["key"] == "off_delay_s"

    # Second proposal path: dismiss without conf change
    coordinator.reviews[0]["proposals"].append({
        "id": "dismiss-me",
        "target": "hub",
        "key": "reserve_w",
        "scope": "hub",
        "subentry_id": None,
        "from": 100,
        "to": 200,
        "reason": "test",
        "status": "pending",
    })
    reserve_before = coordinator.conf.get("reserve_w")
    dismissed = await hass.services.async_call(
        "fve_optimizer",
        "dismiss_ai_proposal",
        {"id": "dismiss-me"},
        blocking=True,
        return_response=True,
    )
    assert dismissed["proposals"][0]["status"] == "dismissed"
    assert coordinator.conf.get("reserve_w") == reserve_before


async def test_apply_ai_proposal_requires_id(hass: HomeAssistant) -> None:
    Recorder(hass)
    _fake_ai(hass)
    _states(hass, grid=0, batt=0, soc=95)
    await _setup(hass, _entry({"ai_task_entity": "ai_task.test"}))
    try:
        await hass.services.async_call(
            "fve_optimizer", "apply_ai_proposal", {}, blocking=True
        )
        raise AssertionError("expected error")
    except Exception as err:  # noqa: BLE001
        assert "id" in str(err).lower() or "required" in str(err).lower()

    try:
        await hass.services.async_call(
            "fve_optimizer", "apply_ai_proposal", {"id": "missing"}, blocking=True
        )
        raise AssertionError("expected error")
    except Exception as err:  # noqa: BLE001
        assert "proposal" in str(err).lower() or "review" in str(err).lower()
