"""Daily AI review via the AI Task service."""

from __future__ import annotations

from datetime import datetime
import json
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .test_dispatcher import BOILER, Recorder, _setup, _states
from .test_features import _entry

PRAGUE = ZoneInfo("Europe/Prague")


def _fake_ai(hass: HomeAssistant, answer: dict | None = None, fail: bool = False) -> list[ServiceCall]:
    calls: list[ServiceCall] = []

    async def generate(call: ServiceCall):
        calls.append(call)
        if fail:
            raise RuntimeError("quota exceeded")
        return {"conversation_id": "x", "data": answer or {
            "score": 7, "summary": "Přebytky využity dobře.", "good": "- bojler ze slunce",
            "problems": "- bojler 6× vypnut", "suggestions": "Bojler – zpoždění vypnutí: z 60 na 180 s – mraky",
        }}

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
    assert review["score"] == 7 and "zpoždění vypnutí" in review["suggestions"]
    # The AI got today's data and the structure.
    call = calls[0].data
    assert call["entity_id"] == "ai_task.test"
    assert set(call["structure"]) == {"score", "summary", "good", "problems", "suggestions"}
    data = json.loads(call["instructions"].split("Data dne:\n", 1)[1])
    assert "Bojler" in data["devices"] and "settings" in data and "decision_log" in data
    # Sensor + card data.
    sensor = [s for s in hass.states.async_all("sensor") if "suggestions" in s.attributes][0]
    assert sensor.state == "7"
    assert coordinator.data.live_data["review"]["score"] == 7
    buttons = hass.states.async_all("button")
    assert len(buttons) == 1


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
