"""Multi-day calibration diary: stabilize tunables without day-to-day oscillation.

Collects daily metrics, tracks applied proposals, and only surfaces a change when
several recent days agree on the same direction. After an apply, the opposite
direction is blocked for a cooldown window.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .const import (
    CONF_DEADLINE_SAFETY,
    CONF_HOUSE_AVG_POWER_W,
    CONF_NIGHT_POWER_W,
    CONF_OFF_DELAY,
    CONF_ON_DELAY,
    CONF_ON_MARGIN,
)

# How many finished days to keep.
DIARY_DAYS = 14
# Sliding window for “days agree”.
EVIDENCE_WINDOW = 5
EVIDENCE_MIN_AGREE = 3
# After apply/dismiss, block opposite nudges for this many days.
COOLDOWN_DAYS = 5

# Keys we try to stabilize (hub or per-device).
STABLE_KEYS = frozenset(
    {
        CONF_ON_DELAY,
        CONF_OFF_DELAY,
        CONF_ON_MARGIN,
        CONF_DEADLINE_SAFETY,
        CONF_NIGHT_POWER_W,
        CONF_HOUSE_AVG_POWER_W,
    }
)


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _direction(from_val: Any, to_val: Any) -> str | None:
    try:
        a = float(from_val)
        b = float(to_val)
    except (TypeError, ValueError):
        return None
    if abs(a - b) < 1e-9:
        return None
    return "up" if b > a else "down"


def _change_key(target: str, key: str) -> str:
    return f"{target}|{key}"


class CalibrationStore:
    """Persistent calibration state hung off the coordinator."""

    def __init__(self) -> None:
        self.days: list[dict[str, Any]] = []  # oldest → newest
        self.changes: list[dict[str, Any]] = []  # applied/dismissed, newest last

    def load(self, raw: dict[str, Any] | None) -> None:
        raw = raw or {}
        self.days = list(raw.get("days") or [])[-DIARY_DAYS:]
        self.changes = list(raw.get("changes") or [])[-50:]

    def dump(self) -> dict[str, Any]:
        return {"days": self.days[-DIARY_DAYS:], "changes": self.changes[-50:]}

    def record_day(self, entry: dict[str, Any]) -> None:
        """Upsert one finished day's metrics (by date)."""
        day = str(entry.get("date") or "")
        if not day:
            return
        self.days = [d for d in self.days if d.get("date") != day]
        self.days.append(entry)
        self.days = self.days[-DIARY_DAYS:]

    def record_change(
        self,
        *,
        day: str,
        target: str,
        key: str,
        from_val: Any,
        to_val: Any,
        status: str,
        source: str = "ai",
    ) -> None:
        if key not in STABLE_KEYS:
            return
        self.changes.append(
            {
                "date": day,
                "target": target,
                "key": key,
                "from": from_val,
                "to": to_val,
                "direction": _direction(from_val, to_val),
                "status": status,
                "source": source,
            }
        )
        self.changes = self.changes[-50:]

    def attach_score(self, day: str, score: int) -> None:
        for entry in reversed(self.days):
            if entry.get("date") == day:
                entry["score"] = score
                return

    def last_change(self, target: str, key: str) -> dict[str, Any] | None:
        needle = _change_key(target, key)
        for row in reversed(self.changes):
            if _change_key(str(row.get("target")), str(row.get("key"))) == needle:
                if row.get("status") in ("applied", "dismissed"):
                    return row
        return None

    def in_cooldown(self, target: str, key: str, today: date) -> dict[str, Any] | None:
        last = self.last_change(target, key)
        if not last:
            return None
        last_day = _parse_day(last.get("date"))
        if last_day is None:
            return None
        if (today - last_day).days < COOLDOWN_DAYS:
            return last
        return None

    def recent_days(self, n: int = EVIDENCE_WINDOW) -> list[dict[str, Any]]:
        return self.days[-n:]

    def build_candidates(self, coordinator: Any) -> list[dict[str, Any]]:
        """Local proposals when ≥ EVIDENCE_MIN_AGREE days push the same way."""
        today = datetime.now().astimezone().date()
        window = self.recent_days()
        if len(window) < EVIDENCE_MIN_AGREE:
            return []

        short = sum(1 for d in window if int(d.get("short_cycles") or 0) > 0)
        calm_export = sum(
            1
            for d in window
            if int(d.get("short_cycles") or 0) == 0
            and (
                bool(d.get("unused_export_risk"))
                or float(d.get("export_kwh") or 0) >= 2.0
            )
        )
        at_risk = sum(1 for d in window if d.get("at_risk"))

        out: list[dict[str, Any]] = []

        def hub_num(key: str) -> float:
            return float(coordinator.conf.get(key) or 0)

        # Hunting → longer delays (hub devices inherit; propose hub-level only if
        # we have no device context — propose for each switched/ev with delays).
        if short >= EVIDENCE_MIN_AGREE:
            for sid, device in coordinator.devices.items():
                if not device.enabled:
                    continue
                for key in (CONF_ON_DELAY, CONF_OFF_DELAY):
                    if key not in device.config:
                        continue
                    cur = float(device.config.get(key) or 0)
                    nxt = min(cur * 1.5 if cur > 0 else 120.0, 900.0)
                    nxt = round(nxt / 30) * 30
                    if nxt <= cur + 1:
                        continue
                    out.append(
                        self._candidate(
                            target=device.name,
                            key=key,
                            from_val=cur,
                            to_val=float(nxt),
                            reason=(
                                f"kalibrace: hunting {short}/{len(window)} dní "
                                f"(short_cycles) → delší {key}"
                            ),
                            evidence=f"{short}/{len(window)} dní hunting",
                            today=today,
                        )
                    )

        # Calm + unused export → shorter on_delay / lower on_margin
        if calm_export >= EVIDENCE_MIN_AGREE:
            for sid, device in coordinator.devices.items():
                if not device.enabled:
                    continue
                if CONF_ON_DELAY in device.config:
                    cur = float(device.config.get(CONF_ON_DELAY) or 0)
                    if cur >= 90:
                        nxt = max(60.0, round((cur * 0.75) / 30) * 30)
                        if nxt < cur - 1:
                            out.append(
                                self._candidate(
                                    target=device.name,
                                    key=CONF_ON_DELAY,
                                    from_val=cur,
                                    to_val=nxt,
                                    reason=(
                                        f"kalibrace: {calm_export}/{len(window)} dní "
                                        f"klid + nevyužitý přetok → kratší on_delay_s"
                                    ),
                                    evidence=f"{calm_export}/{len(window)} dní export bez hunting",
                                    today=today,
                                )
                            )
                if CONF_ON_MARGIN in device.config:
                    cur = float(device.config.get(CONF_ON_MARGIN) or 0)
                    if cur >= 150:
                        nxt = max(50.0, round((cur - 50) / 10) * 10)
                        if nxt < cur - 1:
                            out.append(
                                self._candidate(
                                    target=device.name,
                                    key=CONF_ON_MARGIN,
                                    from_val=cur,
                                    to_val=nxt,
                                    reason=(
                                        f"kalibrace: {calm_export}/{len(window)} dní "
                                        f"nevyužitý přetok → nižší on_margin_w"
                                    ),
                                    evidence=f"{calm_export}/{len(window)} dní export",
                                    today=today,
                                )
                            )

        # Chronic at_risk → lower deadline_safety_factor on boilers
        if at_risk >= EVIDENCE_MIN_AGREE:
            for device in coordinator.devices.values():
                if not device.enabled or CONF_DEADLINE_SAFETY not in device.config:
                    continue
                if not device.config.get("deadline_enabled"):
                    continue
                cur = float(device.config.get(CONF_DEADLINE_SAFETY) or 1.2)
                if cur <= 1.0:
                    continue
                nxt = round(max(0.9, cur - 0.1) * 20) / 20
                if nxt < cur - 0.01:
                    out.append(
                        self._candidate(
                            target=device.name,
                            key=CONF_DEADLINE_SAFETY,
                            from_val=cur,
                            to_val=nxt,
                            reason=(
                                f"kalibrace: at_risk {at_risk}/{len(window)} dní → "
                                f"nižší deadline_safety_factor"
                            ),
                            evidence=f"{at_risk}/{len(window)} dní nestíhá",
                            today=today,
                        )
                    )

        # Night power: if diary has night_kwh estimate consistently above/below setting
        night_samples = [
            float(d["night_kwh_est"])
            for d in window
            if d.get("night_kwh_est") is not None
        ]
        if len(night_samples) >= EVIDENCE_MIN_AGREE:
            avg = sum(night_samples) / len(night_samples)
            cur = hub_num(CONF_NIGHT_POWER_W)
            # night_kwh_est is kWh for the no-PV window; convert rough W:
            # use coordinator night hours if present on last day
            hours = float(window[-1].get("night_hours") or 14) or 14.0
            implied_w = (avg / hours) * 1000
            if implied_w > cur * 1.2 and cur > 0:
                nxt = min(round(implied_w / 50) * 50, cur * 1.5)
                out.append(
                    self._candidate(
                        target="hub",
                        key=CONF_NIGHT_POWER_W,
                        from_val=cur,
                        to_val=float(nxt),
                        reason=(
                            f"kalibrace: noční spotřeba ~{implied_w:.0f} W "
                            f"({len(night_samples)} dní) > nastavení"
                        ),
                        evidence=f"noc ~{implied_w:.0f} W vs {cur:g} W",
                        today=today,
                    )
                )
            elif implied_w < cur * 0.75 and cur >= 200:
                nxt = max(100.0, round(implied_w / 50) * 50)
                if nxt < cur - 1:
                    out.append(
                        self._candidate(
                            target="hub",
                            key=CONF_NIGHT_POWER_W,
                            from_val=cur,
                            to_val=float(nxt),
                            reason=(
                                f"kalibrace: noční spotřeba ~{implied_w:.0f} W "
                                f"({len(night_samples)} dní) < nastavení"
                            ),
                            evidence=f"noc ~{implied_w:.0f} W vs {cur:g} W",
                            today=today,
                        )
                    )

        # Drop cooldown / opposite conflicts
        filtered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for cand in out:
            ck = _change_key(str(cand["target"]), str(cand["key"]))
            if ck in seen:
                continue
            blocked = self._block_reason(cand, today)
            if blocked:
                cand = {**cand, "status": "held", "error": blocked}
            else:
                cand = {**cand, "status": "pending"}
            seen.add(ck)
            filtered.append(cand)
        return filtered

    def _candidate(
        self,
        *,
        target: str,
        key: str,
        from_val: float,
        to_val: float,
        reason: str,
        evidence: str,
        today: date,
    ) -> dict[str, Any]:
        return {
            "id": f"cal-{target}-{key}-{to_val}",
            "target": target,
            "key": key,
            "from": from_val,
            "to": to_val,
            "reason": reason,
            "evidence": evidence,
            "source": "calibration",
            "direction": _direction(from_val, to_val),
        }

    def _block_reason(self, cand: dict[str, Any], today: date) -> str | None:
        target = str(cand.get("target"))
        key = str(cand.get("key"))
        direction = cand.get("direction")
        last = self.in_cooldown(target, key, today)
        if not last:
            return None
        last_dir = last.get("direction")
        last_status = last.get("status")
        if last_status == "dismissed":
            return f"cooldown_dismissed_{COOLDOWN_DAYS}d"
        if last_dir and direction and last_dir != direction:
            return f"cooldown_opposite_{COOLDOWN_DAYS}d"
        if last_dir and direction and last_dir == direction:
            # Same direction during cooldown: still hold to let outcome settle
            return f"cooldown_same_{COOLDOWN_DAYS}d"
        return f"cooldown_{COOLDOWN_DAYS}d"

    def annotate_ai_proposals(
        self, proposals: list[dict[str, Any]], today: date | None = None
    ) -> list[dict[str, Any]]:
        """Mark AI proposals that would oscillate; attach evidence when possible."""
        today = today or datetime.now().astimezone().date()
        window = self.recent_days()
        out: list[dict[str, Any]] = []
        for prop in proposals:
            key = str(prop.get("key") or "")
            target = str(prop.get("target") or "")
            if key not in STABLE_KEYS:
                out.append(prop)
                continue
            direction = _direction(prop.get("from"), prop.get("to"))
            prop = {**prop, "direction": direction, "source": prop.get("source") or "ai"}
            blocked = None
            last = self.in_cooldown(target, key, today)
            if last and prop.get("status") == "pending":
                last_dir = last.get("direction")
                if last.get("status") == "dismissed":
                    blocked = f"cooldown_dismissed_{COOLDOWN_DAYS}d"
                elif last_dir and direction and last_dir != direction:
                    blocked = f"cooldown_opposite_{COOLDOWN_DAYS}d"
                elif last_dir and direction and last_dir == direction:
                    blocked = f"cooldown_same_{COOLDOWN_DAYS}d"
            if blocked:
                prop["status"] = "held"
                prop["error"] = blocked
                prop["reason"] = (
                    f"{prop.get('reason') or ''} · držení: počkej na ustálení "
                    f"({COOLDOWN_DAYS} dní od poslední změny)"
                ).strip(" ·")
            elif window and not prop.get("evidence"):
                short = sum(1 for d in window if int(d.get("short_cycles") or 0) > 0)
                export_days = sum(
                    1 for d in window if float(d.get("export_kwh") or 0) >= 1.0
                )
                prop["evidence"] = (
                    f"okno {len(window)} dní: hunting {short}, export≥1 kWh {export_days}"
                )
            out.append(prop)
        return out

    def merge_candidates(
        self,
        ai_proposals: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        coordinator: Any,
    ) -> list[dict[str, Any]]:
        """Prefer pending AI proposals; add calibration candidates for missing keys."""
        seen = {
            _change_key(str(p.get("target")), str(p.get("key")))
            for p in ai_proposals
            if p.get("status") in ("pending", "held")
        }
        by_name = {d.name: sid for sid, d in coordinator.devices.items()}
        merged = list(ai_proposals)
        for cand in candidates:
            ck = _change_key(str(cand.get("target")), str(cand.get("key")))
            if ck in seen:
                continue
            target = str(cand.get("target"))
            if target == "hub":
                cand = {**cand, "scope": "hub", "subentry_id": None}
            elif target in by_name:
                cand = {**cand, "scope": "device", "subentry_id": by_name[target]}
            else:
                cand = {**cand, "status": "invalid", "error": "unknown_target"}
            merged.append(cand)
            seen.add(ck)
        return merged

    def summary_for_ui(self) -> dict[str, Any]:
        window = self.recent_days()
        holds = [
            c
            for c in self.changes[-10:]
            if c.get("status") in ("applied", "dismissed")
        ]
        return {
            "days_recorded": len(self.days),
            "window_days": len(window),
            "evidence_need": EVIDENCE_MIN_AGREE,
            "cooldown_days": COOLDOWN_DAYS,
            "recent": [
                {
                    "date": d.get("date"),
                    "export_kwh": d.get("export_kwh"),
                    "short_cycles": d.get("short_cycles"),
                    "at_risk": bool(d.get("at_risk")),
                    "score": d.get("score"),
                }
                for d in window
            ],
            "last_changes": holds[-5:],
        }
