"""Multi-day calibration diary: evidence gate and anti-oscillation cooldown."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.fve_optimizer.calibration import (
    COOLDOWN_DAYS,
    EVIDENCE_MIN_AGREE,
    CalibrationStore,
)
from custom_components.fve_optimizer.const import CONF_ON_DELAY, CONF_ON_MARGIN


def _day(d: date, *, short: int = 0, export: float = 0.0, unused: bool = False) -> dict:
    return {
        "date": d.isoformat(),
        "short_cycles": short,
        "export_kwh": export,
        "unused_export_risk": unused,
        "at_risk": [],
    }


def test_summary_empty():
    store = CalibrationStore()
    s = store.summary_for_ui()
    assert s["days_recorded"] == 0
    assert s["evidence_need"] == EVIDENCE_MIN_AGREE
    assert s["cooldown_days"] == COOLDOWN_DAYS
    assert s["recent"] == []


def test_candidates_need_multi_day_agreement():
    store = CalibrationStore()
    today = date(2026, 11, 16)
    # Only 2 hunting days → no candidate
    for i in range(2):
        store.record_day(_day(today - timedelta(days=2 - i), short=3))
    coord = MagicMock()
    device = SimpleNamespace(
        enabled=True,
        name="Bojler",
        config={CONF_ON_DELAY: 180, CONF_ON_MARGIN: 200},
    )
    coord.devices = {"d1": device}
    coord.conf = {}
    assert store.build_candidates(coord) == []

    # 3rd hunting day → longer on_delay
    store.record_day(_day(today, short=2))
    cands = store.build_candidates(coord)
    assert any(c["key"] == CONF_ON_DELAY and c["to"] > 180 for c in cands)
    assert all(c.get("source") == "calibration" for c in cands)


def test_cooldown_holds_opposite_ai_proposal():
    store = CalibrationStore()
    today = date(2026, 11, 16)
    store.record_change(
        day=(today - timedelta(days=1)).isoformat(),
        target="Bojler",
        key=CONF_ON_DELAY,
        from_val=120,
        to_val=180,
        status="applied",
        source="ai",
    )
    props = [
        {
            "id": "p1",
            "target": "Bojler",
            "key": CONF_ON_DELAY,
            "from": 180,
            "to": 120,
            "status": "pending",
            "reason": "AI chce zkrátit",
        }
    ]
    out = store.annotate_ai_proposals(props, today)
    assert out[0]["status"] == "held"
    assert "cooldown_opposite" in (out[0].get("error") or "")


def test_merge_adds_calibration_when_ai_silent():
    store = CalibrationStore()
    today = date(2026, 11, 16)
    for i in range(EVIDENCE_MIN_AGREE):
        store.record_day(
            _day(today - timedelta(days=EVIDENCE_MIN_AGREE - 1 - i), short=0, export=3.0, unused=True)
        )
    device = SimpleNamespace(
        enabled=True,
        name="Bojler",
        config={CONF_ON_DELAY: 180, CONF_ON_MARGIN: 200},
    )
    coord = MagicMock()
    coord.devices = {"d1": device}
    coord.conf = {}
    cands = store.build_candidates(coord)
    assert cands
    merged = store.merge_candidates([], cands, coord)
    assert any(m.get("source") == "calibration" for m in merged)
    assert any(m.get("subentry_id") == "d1" for m in merged)
