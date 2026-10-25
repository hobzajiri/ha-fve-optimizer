"""Calendar schedule parsing and apply rules."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from custom_components.fve_optimizer.devices import SwitchedDevice
from custom_components.fve_optimizer.schedule import ParsedEvent, apply_schedule, parse_summary

PRAGUE = ZoneInfo("Europe/Prague")


def test_parse_summary_variants() -> None:
    start = datetime(2026, 10, 6, 10, 0, tzinfo=PRAGUE)
    end = datetime(2026, 10, 6, 18, 0, tzinfo=PRAGUE)
    heat = parse_summary("Bojler: 55°C", start, end)
    assert heat and heat.kind == "order_temp" and heat.value == 55.0 and heat.name == "Bojler"
    soc = parse_summary("EcoVolter: 80%", start, end)
    assert soc and soc.kind == "order_soc" and soc.value == 80.0
    cap = parse_summary("Bojler: max 45°C", start, end)
    assert cap and cap.kind == "max_temp" and cap.value == 45.0
    away = parse_summary("EcoVolter: away", start, end)
    assert away and away.kind == "away" and away.value is None
    assert parse_summary("random note", start, end) is None


def _boiler(name: str = "Bojler") -> SwitchedDevice:
    boiler = object.__new__(SwitchedDevice)
    boiler.config = {"name": name, "temperature_sensor": "sensor.t"}
    boiler._heat_order = None
    boiler._order_completed = None
    boiler._calendar_order_done = None
    boiler._max_temp_override = None
    boiler._temperature = None
    return boiler


def test_apply_schedule_manual_beats_calendar() -> None:
    now = datetime(2026, 10, 6, 12, 0, tzinfo=PRAGUE)
    end = now + timedelta(hours=6)
    boiler = _boiler()
    boiler._heat_order = {
        "temp": 60.0,
        "deadline": (now + timedelta(hours=2)).isoformat(),
        "source": "manual",
    }
    events = [
        ParsedEvent("Bojler", "order_temp", 55.0, now - timedelta(hours=1), end),
        ParsedEvent("Bojler", "max_temp", 45.0, now - timedelta(hours=1), end),
    ]
    changed = apply_schedule({"b1": boiler}, events, now)
    assert boiler._heat_order["source"] == "manual"
    assert boiler._heat_order["temp"] == 60.0
    assert boiler._max_temp_override == 45.0
    assert changed is True


async def test_fetch_events_failure_returns_none() -> None:
    """Outage must not look like an empty calendar (would clear active schedule)."""
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.fve_optimizer.schedule import async_fetch_events

    hass = MagicMock()
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("calendar down"))
    now = datetime(2026, 10, 6, 12, 0, tzinfo=PRAGUE)
    assert await async_fetch_events(hass, "calendar.plan", now) is None


def test_apply_schedule_sets_calendar_heat_order() -> None:
    now = datetime(2026, 10, 6, 12, 0, tzinfo=PRAGUE)
    end = now + timedelta(hours=6)
    boiler = _boiler()
    events = [ParsedEvent("Bojler", "order_temp", 55.0, now - timedelta(hours=1), end)]
    assert apply_schedule({"b1": boiler}, events, now) is True
    assert boiler._heat_order == {
        "temp": 55.0,
        "deadline": end.isoformat(),
        "source": "calendar",
    }


def test_calendar_heat_order_not_reapplied_after_complete() -> None:
    """Once met, the same calendar event must not recreate the order until it ends."""
    now = datetime(2026, 10, 6, 12, 0, tzinfo=PRAGUE)
    end = now + timedelta(hours=6)
    boiler = _boiler()
    events = [ParsedEvent("Bojler", "order_temp", 55.0, now - timedelta(hours=1), end)]
    apply_schedule({"b1": boiler}, events, now)
    assert boiler.complete_heat_order() is not None
    assert boiler._heat_order is None
    assert boiler._calendar_order_done is not None

    assert apply_schedule({"b1": boiler}, events, now) is False
    assert boiler._heat_order is None

    # After the event ends, the satisfied marker clears so a later occurrence can apply.
    later = end + timedelta(minutes=1)
    assert apply_schedule({"b1": boiler}, events, later) is True
    assert boiler._calendar_order_done is None


def test_manual_heat_complete_suppresses_active_calendar_event() -> None:
    """After a manual order reaches the calendar target, sync must not re-apply it."""
    now = datetime(2026, 10, 6, 12, 0, tzinfo=PRAGUE)
    end = now + timedelta(hours=6)
    boiler = _boiler()
    boiler._temperature = 56.0
    events = [ParsedEvent("Bojler", "order_temp", 55.0, now - timedelta(hours=1), end)]
    # Simulate: manual order just completed, no active order left.
    boiler._heat_order = None
    boiler._calendar_order_done = None
    assert apply_schedule({"b1": boiler}, events, now) is True
    assert boiler._heat_order is None
    assert boiler._calendar_order_done == {
        "temp": 55.0,
        "deadline": end.isoformat(),
    }
    # Second sync stays quiet (no restart / no extra completed edge).
    assert apply_schedule({"b1": boiler}, events, now) is False


def test_unmet_calendar_heat_order_kept_after_event_end() -> None:
    """Missed calendar deadline must keep the order for catch-up after event end."""
    now = datetime(2026, 10, 6, 12, 0, tzinfo=PRAGUE)
    end = now + timedelta(hours=6)
    boiler = _boiler()
    events = [ParsedEvent("Bojler", "order_temp", 55.0, now - timedelta(hours=1), end)]
    apply_schedule({"b1": boiler}, events, now)
    assert boiler._heat_order is not None

    later = end + timedelta(minutes=1)
    assert apply_schedule({"b1": boiler}, events, later) is False
    assert boiler._heat_order == {
        "temp": 55.0,
        "deadline": end.isoformat(),
        "source": "calendar",
    }


def test_calendar_heat_order_not_reapplied_after_user_clear() -> None:
    """Clearing on the card must stick while the calendar event is still active."""
    now = datetime(2026, 10, 6, 12, 0, tzinfo=PRAGUE)
    end = now + timedelta(hours=6)
    boiler = _boiler()
    events = [ParsedEvent("Bojler", "order_temp", 55.0, now - timedelta(hours=1), end)]
    apply_schedule({"b1": boiler}, events, now)
    assert boiler._heat_order is not None
    boiler.clear_heat_order()
    assert boiler._calendar_order_done is not None
    assert apply_schedule({"b1": boiler}, events, now) is False
    assert boiler._heat_order is None


def _ev_device(name: str = "EcoVolter") -> object:
    from custom_components.fve_optimizer.devices import EvChargerDevice

    ev = object.__new__(EvChargerDevice)
    ev.config = {"name": name}
    ev._charge_order = None
    ev._order_completed = None
    ev._calendar_order_done = None
    ev._calendar_away_done = None
    ev._boost = None
    ev._away = None
    ev._ev_soc = 40.0
    ev.battery_lend_kwh = 0.0
    ev.away_prefer = False
    ev.away_car_budget_kwh = 0.0
    return ev


def test_calendar_away_applies_upcoming_event_for_prep() -> None:
    """Away event must be synced before start so leave_at is still in the future."""
    now = datetime(2026, 10, 6, 10, 0, tzinfo=PRAGUE)
    start = now + timedelta(hours=5)
    end = start + timedelta(hours=2)
    ev = _ev_device()
    events = [ParsedEvent("EcoVolter", "away", None, start, end)]
    assert apply_schedule({"e1": ev}, events, now) is True
    assert ev._away is not None
    assert ev._away["leave_at"] == start.isoformat()
    assert ev._away["return_at"] == end.isoformat()
    assert ev._away["source"] == "calendar"


def test_calendar_away_not_reapplied_after_user_clear() -> None:
    """Clearing calendar away on the card must stick while the event is active."""
    now = datetime(2026, 10, 6, 10, 0, tzinfo=PRAGUE)
    start = now + timedelta(hours=5)
    end = start + timedelta(hours=2)
    ev = _ev_device()
    events = [ParsedEvent("EcoVolter", "away", None, start, end)]
    apply_schedule({"e1": ev}, events, now)
    assert ev._away is not None
    ev.clear_away()
    assert ev._calendar_away_done is not None
    assert apply_schedule({"e1": ev}, events, now) is False
    assert ev._away is None


def test_calendar_charge_order_does_not_kill_boost() -> None:
    """Active boost outranks calendar; after stop_boost the calendar order returns."""
    now = datetime(2026, 10, 6, 12, 0, tzinfo=PRAGUE)
    end = now + timedelta(hours=6)
    ev = _ev_device()
    ev._ev_soc = 50.0

    events = [ParsedEvent("EcoVolter", "order_soc", 80.0, now - timedelta(hours=1), end)]
    apply_schedule({"e1": ev}, events, now)
    assert ev._charge_order is not None
    ev.start_boost(70)
    assert ev._boost == {"soc": 70.0}
    assert ev._charge_order is None
    assert ev._calendar_order_done is None

    assert apply_schedule({"e1": ev}, events, now) is False
    assert ev._boost == {"soc": 70.0}
    assert ev._charge_order is None

    ev.stop_boost()
    assert apply_schedule({"e1": ev}, events, now) is True
    assert ev._charge_order == {
        "soc": 80.0,
        "deadline": end.isoformat(),
        "source": "calendar",
    }
