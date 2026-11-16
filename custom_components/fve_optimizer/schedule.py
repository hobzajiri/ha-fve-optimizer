"""Sync one-shot orders / away / max-temp caps from a per-device HA calendar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Nameless (per-device calendar): "55°C" / "80%" / "max 45°C" / "away"
# Legacy hub style still accepted: "Bojler: 55°C" → strip name, parse rest.
_ORDER_TEMP = re.compile(
    r"^\s*(?P<temp>\d+(?:[.,]\d+)?)\s*°?\s*[Cc]\s*$",
    re.UNICODE,
)
_ORDER_SOC = re.compile(
    r"^\s*(?P<soc>\d+(?:[.,]\d+)?)\s*%\s*$",
    re.UNICODE,
)
_MAX_TEMP = re.compile(
    r"^\s*max\s*(?P<temp>\d+(?:[.,]\d+)?)\s*°?\s*[Cc]\s*$",
    re.IGNORECASE | re.UNICODE,
)
_AWAY = re.compile(r"^\s*away\s*$", re.IGNORECASE | re.UNICODE)
_LEGACY_PREFIX = re.compile(r"^\s*(?P<name>.+?)\s*:\s*(?P<rest>.+?)\s*$", re.UNICODE)


@dataclass(frozen=True)
class ParsedEvent:
    """One calendar event interpreted as a device directive."""

    kind: str  # order_temp | order_soc | max_temp | away
    value: float | None
    start: datetime
    end: datetime
    name: str | None = None  # set only for legacy "Name: …" summaries


def _norm_name(name: str) -> str:
    return " ".join(str(name).casefold().split())


def _parse_body(
    text: str, start: datetime, end: datetime, *, name: str | None = None
) -> ParsedEvent | None:
    if m := _MAX_TEMP.match(text):
        return ParsedEvent(
            kind="max_temp",
            value=float(m.group("temp").replace(",", ".")),
            start=start,
            end=end,
            name=name,
        )
    if _AWAY.match(text):
        return ParsedEvent(kind="away", value=None, start=start, end=end, name=name)
    if m := _ORDER_TEMP.match(text):
        return ParsedEvent(
            kind="order_temp",
            value=float(m.group("temp").replace(",", ".")),
            start=start,
            end=end,
            name=name,
        )
    if m := _ORDER_SOC.match(text):
        return ParsedEvent(
            kind="order_soc",
            value=float(m.group("soc").replace(",", ".")),
            start=start,
            end=end,
            name=name,
        )
    return None


def parse_summary(summary: str, start: datetime, end: datetime) -> ParsedEvent | None:
    """Parse an event summary into a device directive, or None if unrecognized."""
    text = (summary or "").strip()
    if not text or end <= start:
        return None
    # Prefer nameless body; if that fails, strip a legacy "Name: …" prefix.
    if item := _parse_body(text, start, end):
        return item
    if m := _LEGACY_PREFIX.match(text):
        return _parse_body(
            m.group("rest").strip(),
            start,
            end,
            name=m.group("name").strip(),
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


def parse_events(
    raw_events: list[dict[str, Any]],
    now: datetime,
    *,
    log_unparsed_for: str | None = None,
) -> list[ParsedEvent]:
    """Convert HA calendar event dicts into parsed directives."""
    parsed: list[ParsedEvent] = []
    unparsed: list[str] = []
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
        summary = str(event.get("summary") or "").strip()
        item = parse_summary(summary, start, end)
        if item is not None:
            parsed.append(item)
        elif summary:
            unparsed.append(summary)
    if log_unparsed_for and unparsed:
        shown = ", ".join(unparsed[:5])
        extra = f" (+{len(unparsed) - 5} more)" if len(unparsed) > 5 else ""
        _LOGGER.warning(
            "Schedule calendar for %s: unrecognized event(s): %s%s",
            log_unparsed_for,
            shown,
            extra,
        )
    return parsed


def _events_for_device(device: Any, events: list[ParsedEvent]) -> list[ParsedEvent]:
    """Keep nameless events; legacy named events only if the name matches."""
    device_key = _norm_name(device.name)
    out: list[ParsedEvent] = []
    for ev in events:
        if not ev.name or _norm_name(ev.name) == device_key:
            out.append(ev)
    return out


def apply_schedule_for_device(
    device: Any, events: list[ParsedEvent], now: datetime
) -> bool:
    """Apply calendar directives onto one device. Returns True if state changed.

    Manual orders / away always win. Calendar fills gaps and clears its own
    leftovers when the matching event disappears.
    """
    from .devices import EvChargerDevice, SwitchedDevice  # noqa: PLC0415

    events = _events_for_device(device, events)
    best_order: ParsedEvent | None = None
    best_max: ParsedEvent | None = None
    best_away: ParsedEvent | None = None
    for ev in events:
        if ev.kind in ("order_temp", "order_soc") and ev.end > now:
            if best_order is None or ev.end < best_order.end:
                best_order = ev
        elif ev.kind == "max_temp" and ev.start <= now < ev.end:
            if best_max is None or (
                ev.value is not None
                and (best_max.value is None or ev.value < best_max.value)
            ):
                best_max = ev
        elif ev.kind == "away" and ev.end > now:
            # Upcoming or in-progress: leave_at = start so pre-departure planning
            # runs before the event (away_pending requires now < leave_at).
            if best_away is None or ev.start < best_away.start:
                best_away = ev

    changed = False
    if isinstance(device, SwitchedDevice):
        if (
            best_order
            and best_order.kind == "order_temp"
            and device.config.get("temperature_sensor")
        ):
            before = device.heat_order
            before_done = device._calendar_order_done
            device.set_calendar_heat_order(float(best_order.value or 0), best_order.end)
            if (
                device.heat_order != before
                or device._calendar_order_done != before_done
            ):
                changed = True
        elif device.release_calendar_order_event():
            # Event ended/removed: unmet calendar order kept for catch-up;
            # done marker cleared so a later occurrence can apply.
            changed = True

        wanted = (
            float(best_max.value) if best_max and best_max.value is not None else None
        )
        if device._max_temp_override != wanted:
            device.set_max_temp_override(wanted)
            changed = True

    elif isinstance(device, EvChargerDevice):
        if best_order and best_order.kind == "order_soc":
            before = device.charge_order
            before_done = device._calendar_order_done
            device.set_calendar_charge_order(float(best_order.value or 0), best_order.end)
            if (
                device.charge_order != before
                or device._calendar_order_done != before_done
            ):
                changed = True
        elif device.release_calendar_order_event():
            changed = True

        if best_away:
            before = device.away
            before_done = device._calendar_away_done
            device.set_calendar_away(best_away.start, best_away.end)
            if device.away != before or device._calendar_away_done != before_done:
                changed = True
        else:
            before = device.away
            before_done = device._calendar_away_done
            device.clear_calendar_away()
            if device.away != before or device._calendar_away_done != before_done:
                changed = True

    return changed


def apply_schedule(
    devices: dict[str, Any], events: list[ParsedEvent], now: datetime
) -> bool:
    """Apply the same event list to each device (per-device calendars / tests)."""
    changed = False
    for device in devices.values():
        if apply_schedule_for_device(device, events, now):
            changed = True
    return changed
