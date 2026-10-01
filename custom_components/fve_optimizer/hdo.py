"""HDO (low tariff) schedules from Czech distributors, a calendar, an entity or manual times.

Every source returns concrete low-tariff windows (start, end) for the next days,
so the dispatcher knows both the current tariff and the upcoming windows.

* EG.D  – public JSON (hdo.distribuce24.cz), selected by PSČ + HDO code
* PRE   – public schedule page (predistribuce.cz), selected by "povel"
* calendar – any HA calendar with NT events (e.g. the ČEZ Distribuce integration;
  ČEZ's anonymous API is behind a captcha since 2026)
* entity – on/off entity (HDO receiver, schedule helper); current state only
* manual – fixed times for workdays and weekends
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import html
import logging
import re
from typing import Any

import aiohttp

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

HDO_NONE = "none"
HDO_EGD = "egd"
HDO_PRE = "pre"
HDO_CALENDAR = "calendar"
HDO_ENTITY = "entity"
HDO_MANUAL = "manual"
HDO_SOURCES = [HDO_NONE, HDO_EGD, HDO_PRE, HDO_CALENDAR, HDO_ENTITY, HDO_MANUAL]

EGD_REGION_URL = "https://hdo.distribuce24.cz/region"
EGD_TIMES_URL = "https://hdo.distribuce24.cz/casy"
PRE_URL = "https://www.predistribuce.cz/cs/potrebuji-zaridit/zakaznici/stav-hdo/"

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)
REFRESH_INTERVAL = timedelta(hours=6)
DAYS_AHEAD = 2  # today + tomorrow + day after

Window = tuple[datetime, datetime]

_RANGE_RE = re.compile(r"(\d{1,2}):(\d{2})(?::\d{2})?\s*[-–—]\s*(\d{1,2}):(\d{2})(?::\d{2})?")
_EGD_CODE_RE = re.compile(r"^\s*A\s*(\d+)\s*B\s*(\d+)\s*D?P\s*(\d+)\s*$", re.IGNORECASE)
_PRE_ROW_RE = re.compile(
    r"<tr>\s*<td>.*?(\d{1,2})\.(\d{1,2})\.\s*</td>\s*<td>(.*?)</td>", re.DOTALL
)
_PRE_OPTION_RE = re.compile(r'<option value="([A-Za-z0-9_]{1,10})"[^>]*>(.*?)</option>', re.DOTALL)


class HdoError(Exception):
    """Schedule could not be loaded or the configuration does not match."""


# -- helpers --------------------------------------------------------------------


def _easter_sunday(year: int) -> date:
    """Gregorian Easter (anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def czech_holidays(year: int) -> set[date]:
    """Public holidays in the Czech Republic."""
    fixed = [(1, 1), (5, 1), (5, 8), (7, 5), (7, 6), (9, 28), (10, 28), (11, 17), (12, 24), (12, 25), (12, 26)]
    easter = _easter_sunday(year)
    return {date(year, m, d) for m, d in fixed} | {
        easter - timedelta(days=2),  # Good Friday
        easter + timedelta(days=1),  # Easter Monday
    }


def schedule_weekday(day: date) -> int:
    """ISO weekday used for tariff tables; public holidays count as Sunday."""
    return 7 if day in czech_holidays(day.year) else day.isoweekday()


def parse_ranges(text: str) -> list[tuple[time, time | None]]:
    """Parse '00:00-06:00; 14:00-17:00' → [(start, end)], end None = midnight."""
    ranges: list[tuple[time, time | None]] = []
    for h1, m1, h2, m2 in _RANGE_RE.findall(text or ""):
        start = time(int(h1) % 24, int(m1))
        end = None if int(h2) >= 24 else time(int(h2), int(m2))
        ranges.append((start, end))
    return ranges


def _windows_for_day(day: date, ranges: list[tuple[time, time | None]], tz) -> list[Window]:
    result = []
    for start, end in ranges:
        begin = datetime.combine(day, start, tzinfo=tz)
        finish = (
            datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz)
            if end is None or end <= start
            else datetime.combine(day, end, tzinfo=tz)
        )
        result.append((begin, finish))
    return result


def merge_windows(windows: list[Window]) -> list[Window]:
    """Sort and merge overlapping / touching windows."""
    merged: list[Window] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _days(today: date) -> list[date]:
    return [today + timedelta(days=i) for i in range(DAYS_AHEAD + 1)]


async def _fetch(hass: HomeAssistant, method: str, url: str, **kwargs: Any) -> aiohttp.ClientResponse:
    session = async_get_clientsession(hass)
    try:
        resp = await session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        resp.raise_for_status()
    except (aiohttp.ClientError, TimeoutError) as err:
        raise HdoError(f"{url}: {err}") from err
    return resp


# -- EG.D -----------------------------------------------------------------------


def parse_egd_code(code: str) -> dict[str, str]:
    """'A1B4DP5' → classic A/B/DP code, anything else → command code (e.g. 405, Cd56)."""
    if m := _EGD_CODE_RE.match(code):
        return {"A": m.group(1), "B": m.group(2), "DP": m.group(3)}
    return {"kodHdo_A": code.strip()}


def _egd_record_matches(record: dict[str, Any], code: dict[str, str]) -> bool:
    if "kodHdo_A" in code:
        return record.get("kodHdo_A", "").lower() == code["kodHdo_A"].lower()
    return (
        record.get("A") == code["A"]
        and record.get("B") == code["B"]
        and record.get("DP", "").lstrip("0") == code["DP"].lstrip("0")
    )


def egd_matching(records: list[dict[str, Any]], region: str | None, code: str) -> list[dict[str, Any]]:
    """Records for the code, preferring the PSČ region.

    Classic A/B/DP codes exist in every region, so they need the region.
    Command codes (405, Cd56 for smart meters…) fall back to any region.
    """
    parsed = parse_egd_code(code)
    candidates = [r for r in records if _egd_record_matches(r, parsed)]
    in_region = [r for r in candidates if r.get("region") == region]
    if in_region or "kodHdo_A" not in parsed:
        return in_region
    return candidates


def _egd_valid_on(record: dict[str, Any], day: date) -> bool:
    od, do = record.get("od", {}), record.get("do", {})
    try:
        start_md = (int(od["mesic"]), int(od["den"]))
        end_md = (int(do["mesic"]), int(do["den"]))
        start_year, end_year = int(od["rok"]), int(do["rok"])
    except (KeyError, ValueError):
        return False
    if start_year == 9999:  # yearly recurring season, may wrap over new year
        md = (day.month, day.day)
        if start_md <= end_md:
            return start_md <= md <= end_md
        return md >= start_md or md <= end_md
    try:
        start = date(start_year, *start_md)
        end = date(min(end_year, 9998), *end_md) if end_year != 9999 else date.max
    except ValueError:
        return False
    return start <= day <= end


def egd_windows(records: list[dict[str, Any]], region: str | None, code: str, today: date, tz) -> list[Window]:
    """Low-tariff windows for today and the next days from the EG.D table."""
    matching = egd_matching(records, region, code)
    if not matching:
        raise HdoError(f"EG.D: no schedule for code {code!r} in region {region!r}")
    windows: list[Window] = []
    for day in _days(today):
        weekday = schedule_weekday(day)
        for record in matching:
            if not _egd_valid_on(record, day):
                continue
            for tariff in record.get("sazby", []):
                for entry in tariff.get("dny", []):
                    if entry.get("denVTydnu") != weekday:
                        continue
                    ranges = parse_ranges(
                        "; ".join(f"{c['od']}-{c['do']}" for c in entry.get("casy", []))
                    )
                    windows.extend(_windows_for_day(day, ranges, tz))
    return merge_windows(windows)


async def async_egd_region(hass: HomeAssistant, psc: str) -> str:
    """Resolve the EG.D HDO region for a postal code."""
    resp = await _fetch(hass, "GET", EGD_REGION_URL)
    data = await resp.json(content_type=None)
    psc = psc.replace(" ", "")
    for row in data:
        if str(row.get("PSC")) == psc:
            return str(row["Region"])
    raise HdoError(f"EG.D: unknown PSČ {psc}")


async def async_egd_records(hass: HomeAssistant) -> list[dict[str, Any]]:
    resp = await _fetch(hass, "GET", EGD_TIMES_URL)
    return await resp.json(content_type=None)


# -- PRE ------------------------------------------------------------------------


def pre_windows(page: str, today: date, tz) -> list[Window]:
    """Parse the PRE schedule table ('30.09.' | '00:00-02:40, 03:20-07:20, …')."""
    windows: list[Window] = []
    for day_s, month_s, times in _PRE_ROW_RE.findall(page):
        day_n, month_n = int(day_s), int(month_s)
        year = today.year + (1 if month_n < today.month - 6 else 0)
        try:
            day = date(year, month_n, day_n)
        except ValueError:
            continue
        windows.extend(_windows_for_day(day, parse_ranges(html.unescape(times)), tz))
    if not windows:
        raise HdoError("PRE: schedule table not found")
    return merge_windows(windows)


def pre_options(page: str) -> dict[str, str]:
    """Available commands from the PRE form: {povel: label}."""
    return {
        value: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", label))).strip()
        for value, label in _PRE_OPTION_RE.findall(page)
    }


async def async_pre_page(hass: HomeAssistant, povel: str | None = None, today: date | None = None) -> str:
    params: dict[str, Any] = {}
    if povel:
        today = today or dt_util.now().date()
        last = today + timedelta(days=DAYS_AHEAD)
        params = {
            "povel": povel,
            "den_od": today.day, "mesic_od": today.month, "rok_od": today.year,
            "den_do": last.day, "mesic_do": last.month, "rok_do": last.year,
        }
    resp = await _fetch(hass, "GET", PRE_URL, params=params, headers={"User-Agent": "Mozilla/5.0"})
    return await resp.text()


# -- manager --------------------------------------------------------------------


@dataclass
class HdoSettings:
    source: str = HDO_NONE
    entity_id: str | None = None
    egd_psc: str | None = None
    egd_region: str | None = None
    egd_code: str | None = None
    pre_povel: str | None = None
    manual_workday: str = ""
    manual_weekend: str = ""


class HdoSchedule:
    """Keeps the low-tariff windows fresh and answers 'is it NT now / when next'."""

    def __init__(self, hass: HomeAssistant, entry_id: str, settings: HdoSettings) -> None:
        self.hass = hass
        self.settings = settings
        self.windows: list[Window] = []
        self.last_update: datetime | None = None
        self.error: str | None = None
        self._next_refresh: datetime | None = None
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"fve_optimizer.hdo.{entry_id}")

    @property
    def enabled(self) -> bool:
        return self.settings.source != HDO_NONE

    @property
    def knows_future(self) -> bool:
        """Entity sources only know the current state, the rest know windows."""
        return self.settings.source not in (HDO_NONE, HDO_ENTITY)

    async def async_load(self) -> None:
        """Restore the last known windows (used while the distributor is offline)."""
        if not self.knows_future or self.settings.source == HDO_MANUAL:
            return
        stored = await self._store.async_load()
        if stored and stored.get("key") == self._settings_key():
            self.windows = [
                (dt_util.parse_datetime(a), dt_util.parse_datetime(b))  # type: ignore[misc]
                for a, b in stored.get("windows", [])
            ]

    def _settings_key(self) -> str:
        s = self.settings
        return f"{s.source}|{s.egd_region}|{s.egd_code}|{s.pre_povel}|{s.entity_id}"

    async def async_refresh(self, now: datetime | None = None, force: bool = False) -> None:
        """Reload windows when due (every few hours and after midnight)."""
        now = now or dt_util.now()
        if not self.knows_future:
            return
        if (
            not force
            and self._next_refresh is not None
            and now < self._next_refresh
            and self.last_update is not None
            and self.last_update.date() == now.date()
        ):
            return
        # Retry sooner after a failure, regular interval otherwise.
        self._next_refresh = now + timedelta(minutes=15)
        try:
            windows = await self._async_load_windows(now)
        except HdoError as err:
            self.error = str(err)
            _LOGGER.warning("HDO schedule not updated (%s), using last known windows", err)
            return
        except Exception as err:  # noqa: BLE001 - never break the dispatcher
            self.error = str(err)
            _LOGGER.exception("HDO schedule failed")
            return
        self.windows = windows
        self.last_update = now
        self.error = None
        self._next_refresh = now + REFRESH_INTERVAL
        if self.settings.source != HDO_MANUAL:
            await self._store.async_save(
                {
                    "key": self._settings_key(),
                    "windows": [(a.isoformat(), b.isoformat()) for a, b in windows],
                }
            )
        _LOGGER.debug("HDO windows: %s", [(a.isoformat(), b.isoformat()) for a, b in windows])

    async def _async_load_windows(self, now: datetime) -> list[Window]:
        s, today, tz = self.settings, now.date(), now.tzinfo
        if s.source == HDO_EGD:
            records = await async_egd_records(self.hass)
            return egd_windows(records, s.egd_region, s.egd_code or "", today, tz)
        if s.source == HDO_PRE:
            page = await async_pre_page(self.hass, s.pre_povel, today)
            return pre_windows(page, today, tz)
        if s.source == HDO_MANUAL:
            windows: list[Window] = []
            for day in _days(today):
                text = s.manual_weekend if schedule_weekday(day) >= 6 and s.manual_weekend else s.manual_workday
                windows.extend(_windows_for_day(day, parse_ranges(text), tz))
            return merge_windows(windows)
        if s.source == HDO_CALENDAR:
            return await self._async_calendar_windows(now)
        return []

    async def _async_calendar_windows(self, now: datetime) -> list[Window]:
        response = await self.hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": self.settings.entity_id,
                "start_date_time": (now - timedelta(hours=12)).isoformat(),
                "duration": {"hours": 24 * (DAYS_AHEAD + 1)},
            },
            blocking=True,
            return_response=True,
        )
        events = (response or {}).get(self.settings.entity_id, {}).get("events", [])
        windows: list[Window] = []
        for event in events:
            start = dt_util.parse_datetime(str(event.get("start")))
            end = dt_util.parse_datetime(str(event.get("end")))
            if start and end:
                windows.append((dt_util.as_local(start), dt_util.as_local(end)))
        return merge_windows(windows)

    # -- queries ------------------------------------------------------------------
    def is_active(self, now: datetime) -> bool | None:
        """True in low tariff, None when HDO is not configured / unknown."""
        if not self.enabled:
            return None
        if self.settings.source == HDO_ENTITY:
            state = self.hass.states.get(self.settings.entity_id or "")
            return None if state is None else state.state == STATE_ON
        if not self.windows:
            return None
        return any(start <= now < end for start, end in self.windows)

    def windows_between(self, start: datetime, end: datetime) -> list[Window] | None:
        """Known windows clipped to [start, end], None when the future is unknown."""
        if not self.knows_future or not self.windows:
            return None
        return [
            (max(a, start), min(b, end)) for a, b in self.windows if a < end and b > start
        ]

    def next_change(self, now: datetime) -> datetime | None:
        for start, end in self.windows:
            if start > now:
                return start
            if start <= now < end:
                return end
        return None

    def attributes(self, now: datetime) -> dict[str, Any]:
        def fmt(day: date) -> list[str]:
            return [
                f"{a.strftime('%H:%M')}-{'24:00' if b.date() > day else b.strftime('%H:%M')}"
                for a, b in self.windows
                if a.date() == day
            ]

        today = now.date()
        return {
            "source": self.settings.source,
            "today": fmt(today),
            "tomorrow": fmt(today + timedelta(days=1)),
            "next_change": (nc.isoformat() if (nc := self.next_change(now)) else None),
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "error": self.error,
        }


def plan_windows(
    windows: list[Window], now: datetime, needed: timedelta
) -> tuple[list[Window], bool]:
    """Pick the latest windows (before the deadline) that give ``needed`` time.

    ``windows`` are already clipped to [earliest, deadline]. Past parts are
    dropped. Returns (chosen windows, enough time available).
    """
    remaining = needed
    chosen: list[Window] = []
    for start, end in sorted(windows, reverse=True):
        start = max(start, now)
        if end <= start or remaining <= timedelta(0):
            continue
        length = end - start
        if length >= remaining:
            chosen.append((end - remaining, end))
            remaining = timedelta(0)
        else:
            chosen.append((start, end))
            remaining -= length
    return sorted(chosen), remaining <= timedelta(0)


def settings_from_conf(conf: dict[str, Any], get: Callable[[str], Any] | None = None) -> HdoSettings:
    get = get or conf.get
    # Entries from before the source selector only had an entity.
    source = get("hdo_source") or (HDO_ENTITY if get("hdo_entity") else HDO_NONE)
    return HdoSettings(
        source=source,
        entity_id=get("hdo_entity"),
        egd_psc=get("hdo_egd_psc"),
        egd_region=get("hdo_egd_region"),
        egd_code=get("hdo_egd_code"),
        pre_povel=get("hdo_pre_povel"),
        manual_workday=get("hdo_manual_workday") or "",
        manual_weekend=get("hdo_manual_weekend") or "",
    )
