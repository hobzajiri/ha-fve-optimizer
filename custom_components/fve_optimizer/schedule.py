"""Sync one-shot orders / away / max-temp caps from a Home Assistant calendar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# "Bojler: 55°C" / "EcoVolter: 80%" / "Bojler: max 45°C" / "EcoVolter: away"
_ORDER_TEMP = re.compile(
    r"^\s*(?P<name>.+?)\s*:\s*(?P<temp>\d+(?:[.,]\d+)?)\s*°?\s*[Cc]\s*$",
    re.UNICODE,
)
_ORDER_SOC = re.compile(
    r"^\s*(?P<name>.+?)\s*:\s*(?P<soc>\d+(?:[.,]\d+)?)\s*%\s*$",
    re.UNICODE,
)
_MAX_TEMP = re.compile(
    r"^\s*(?P<name>.+?)\s*:\s*max\s*(?P<temp>\d+(?:[.,]\d+)?)\s*°?\s*[Cc]\s*$",
    re.IGNORECASE | re.UNICODE,
)
_AWAY = re.compile(
    r"^\s*(?P<name>.+?)\s*:\s*away\s*$",
    re.IGNORECASE | re.UNICODE,
)


@dataclass(frozen=True)
class ParsedEvent:
    """One calendar event interpreted for a named device."""

    name: str
    kind: str  # order_temp | order_soc | max_temp | away
    value: float | None
    start: datetime
    end: datetime


def _norm_name(name: str) -> str:
    return " ".join(str(name).casefold().split())


def parse_summary(summary: str, start: datetime, end: datetime) -> ParsedEvent | None:
    """Parse an event summary into a device directive, or None if unrecognized."""
    text = (summary or "").strip()
    if not text or end <= start:
        return None
    if m := _MAX_TEMP.match(text):
        return ParsedEvent(
            name=m.group("name").strip(),
            kind="max_temp",
            value=float(m.group("temp").replace(",", ".")),
            start=start,
            end=end,
        )
    if m := _AWAY.match(text):
        return ParsedEvent(
            name=m.group("name").strip(),
            kind="away",
            value=None,
            start=start,
            end=end,
        )
    if m := _ORDER_TEMP.match(text):
        return ParsedEvent(
            name=m.group("name").strip(),
            kind="order_temp",
            value=float(m.group("temp").replace(",", ".")),
            start=start,
            end=end,
        )
    if m := _ORDER_SOC.match(text):
        return ParsedEvent(
            name=m.group("name").strip(),
            kind="order_soc",
            value=float(m.group("soc").replace(",", ".")),
            start=start,
            end=end,
        )
    return None


async def async_fetch_events(
    hass: HomeAssistant, entity_id: str, now: datetime
) -> list[dict[str, Any]] | None:
    """Load calendar events covering roughly the next week.

    Returns ``None`` when the calendar call fails so callers can keep the last
    applied schedule instead of treating the outage as an empty calendar.
    """
    try:
        response = await hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": entity_id,
                "start_date_time": (now - timedelta(hours=1)).isoformat(),
                "duration": {"hours": 24 * 8},
            },
            blocking=True,
            return_response=True,
        )
    except Exception:  # noqa: BLE001 – calendar optional / may be unavailable
        _LOGGER.exception("Schedule calendar %s: get_events failed", entity_id)
        return None
    return list((response or {}).get(entity_id, {}).get("events", []) or [])


def parse_events(raw_events: list[dict[str, Any]], now: datetime) -> list[ParsedEvent]:
    """Convert HA calendar event dicts into parsed directives."""
    parsed: list[ParsedEvent] = []
    for event in raw_events:
        start = dt_util.parse_datetime(str(event.get("start") or ""))
        end = dt_util.parse_datetime(str(event.get("end") or ""))
        if start is None or end is None:
            continue
        start = dt_util.as_local(start)
        end = dt_util.as_local(end)
        if start.tzinfo is None:
            start = start.replace(tzinfo=now.tzinfo)
        if end.tzinfo is None:
            end = end.replace(tzinfo=now.tzinfo)
        item = parse_summary(str(event.get("summary") or ""), start, end)
        if item is not None:
            parsed.append(item)
    return parsed


def apply_schedule(devices: dict[str, Any], events: list[ParsedEvent], now: datetime) -> bool:
    """Apply calendar directives onto devices. Returns True if state should be saved.

    Manual orders / away always win. Calendar fills gaps and clears its own
    leftovers when the matching event disappears.
    """
    from .devices import EvChargerDevice, SwitchedDevice  # noqa: PLC0415

    by_name: dict[str, list[Any]] = {}
    for device in devices.values():
        by_name.setdefault(_norm_name(device.name), []).append(device)

    changed = False

    # Prefer the soonest unmet order / lowest active max / soonest away per device.
    best_order: dict[str, ParsedEvent] = {}
    best_max: dict[str, ParsedEvent] = {}
    best_away: dict[str, ParsedEvent] = {}
    for ev in events:
        key = _norm_name(ev.name)
        if ev.kind in ("order_temp", "order_soc") and ev.end > now:
            prev = best_order.get(key)
            if prev is None or ev.end < prev.end:
                best_order[key] = ev
        elif ev.kind == "max_temp" and ev.start <= now < ev.end:
            prev = best_max.get(key)
            if prev is None or (
                ev.value is not None and (prev.value is None or ev.value < prev.value)
            ):
                best_max[key] = ev
        elif ev.kind == "away" and ev.end > now:
            # Upcoming or in-progress: leave_at = start so pre-departure planning
            # runs before the event (away_pending requires now < leave_at).
            prev = best_away.get(key)
            if prev is None or ev.start < prev.start:
                best_away[key] = ev

    for device in devices.values():
        n = _norm_name(device.name)
        if isinstance(device, SwitchedDevice):
            order_ev = best_order.get(n)
            if order_ev and order_ev.kind == "order_temp" and device.config.get(
                "temperature_sensor"
            ):
                before = device.heat_order
                before_done = device._calendar_order_done
                device.set_calendar_heat_order(float(order_ev.value or 0), order_ev.end)
                if (
                    device.heat_order != before
                    or device._calendar_order_done != before_done
                ):
                    changed = True
            elif device.release_calendar_order_event():
                # Event ended/removed: unmet calendar order kept for catch-up;
                # done marker cleared so a later occurrence can apply.
                changed = True

            max_ev = best_max.get(n)
            wanted = float(max_ev.value) if max_ev and max_ev.value is not None else None
            if device._max_temp_override != wanted:
                device.set_max_temp_override(wanted)
                changed = True

        elif isinstance(device, EvChargerDevice):
            order_ev = best_order.get(n)
            if order_ev and order_ev.kind == "order_soc":
                before = device.charge_order
                before_done = device._calendar_order_done
                device.set_calendar_charge_order(float(order_ev.value or 0), order_ev.end)
                if (
                    device.charge_order != before
                    or device._calendar_order_done != before_done
                ):
                    changed = True
            elif device.release_calendar_order_event():
                changed = True

            away_ev = best_away.get(n)
            if away_ev:
                before = device.away
                before_done = device._calendar_away_done
                device.set_calendar_away(away_ev.start, away_ev.end)
                if device.away != before or device._calendar_away_done != before_done:
                    changed = True
            else:
                before = device.away
                before_done = device._calendar_away_done
                device.clear_calendar_away()
                if device.away != before or device._calendar_away_done != before_done:
                    changed = True

    return changed
