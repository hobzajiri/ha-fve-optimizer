"""Notifications, domain events, and review notify gating."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.core import Event, HomeAssistant

from custom_components.fve_optimizer.notify import (
    EVENT_CHARGE_ORDER,
    EVENT_FAILSAFE,
    EVENT_FAILSAFE_CLEARED,
    EVENT_REVIEW_DONE,
    notify_service_name,
    review_should_notify,
)
from custom_components.fve_optimizer.const import DOMAIN

from .test_dispatcher import BOILER, Recorder, _setup, _states
from .test_features import _entry, _ev, _ev_states
from .test_review import _fake_ai

PRAGUE = ZoneInfo("Europe/Prague")
TIMEOUT = {"night_target": False, "input_timeout_s": 300, "persistent_notification": True}


def test_review_should_notify_threshold() -> None:
    assert review_should_notify({"score": 5, "suggestions": "Žádné"}, 7)
    assert not review_should_notify({"score": 9, "suggestions": "Žádné"}, 7)
    assert review_should_notify({"score": 9, "suggestions": "Bojler – delay: 60→180"}, 7)
    assert not review_should_notify({"score": 9, "suggestions": "none"}, 7)


def test_notify_service_name_normalizes() -> None:
    assert notify_service_name({"notify_service": "mobile_app_pixel"}) == "mobile_app_pixel"
    assert notify_service_name({"notify_service": "notify.telegram"}) == "telegram"
    assert notify_service_name({}) is None
    assert notify_service_name({"notify_service": "  "}) is None


async def test_failsafe_fires_event_and_persistent(hass: HomeAssistant, freezer) -> None:
    events: list[Event] = []
    hass.bus.async_listen(f"{DOMAIN}_{EVENT_FAILSAFE}", events.append)
    hass.bus.async_listen(f"{DOMAIN}_{EVENT_FAILSAFE_CLEARED}", events.append)
    Recorder(hass)
    _states(hass, grid=-3000, batt=0, soc=95, limit="10000", switch__boiler="on")
    coordinator = await _setup(hass, _entry(TIMEOUT, ("switched", BOILER)))

    freezer.tick(520)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.reason == "failsafe"
    assert any(e.event_type.endswith(EVENT_FAILSAFE) for e in events)
    assert events[0].data["entry_id"] == coordinator.config_entry.entry_id

    for entity_id, value in (("sensor.grid", "-3000"), ("sensor.batt", "0"), ("sensor.soc", "95")):
        hass.states.async_set(entity_id, value, force_update=True)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert any(e.event_type.endswith(EVENT_FAILSAFE_CLEARED) for e in events)


async def test_review_fires_event(hass: HomeAssistant) -> None:
    events: list[Event] = []
    hass.bus.async_listen(f"{DOMAIN}_{EVENT_REVIEW_DONE}", events.append)
    Recorder(hass)
    _fake_ai(hass)
    _states(hass, grid=-3000, batt=0, soc=95, switch__boiler="off")
    await _setup(
        hass,
        _entry(
            {
                "ai_task_entity": "ai_task.test",
                "notify_on_review": True,
                "notify_review_max_score": 10,
                "persistent_notification": True,
            },
            ("switched", BOILER),
        ),
    )
    await hass.services.async_call("fve_optimizer", "run_review", {}, blocking=True, return_response=True)
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["score"] == 7
    assert "suggestions" in events[0].data


async def test_charge_order_fires_event(hass: HomeAssistant, freezer) -> None:
    events: list[Event] = []
    hass.bus.async_listen(f"{DOMAIN}_{EVENT_CHARGE_ORDER}", events.append)
    await hass.config.async_set_time_zone("Europe/Prague")
    Recorder(hass)
    freezer.move_to(datetime(2026, 10, 1, 12, 0, tzinfo=PRAGUE))
    _ev_states(hass, "50")
    coordinator = await _setup(
        hass,
        _entry({"notify_on_order": True}, ("ev_charger", _ev(ev_deadline_hdo_only=False))),
    )
    device_id = next(iter(coordinator.devices))
    await hass.services.async_call(
        "fve_optimizer",
        "set_ev_charge_order",
        {"target_soc": 90, "deadline": "2026-10-01 20:00:00", "device_id": device_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["action"] == "set"
    assert events[0].data["soc"] == 90

    # Reaching target SoC auto-completes the order with the same event family.
    hass.states.async_set("sensor.car_soc", "91")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.devices[device_id].charge_order is None
    completed = [e for e in events if e.data.get("action") == "completed"]
    assert len(completed) == 1
    assert completed[0].data["soc"] == 90
    assert completed[0].data["device_id"] == device_id
