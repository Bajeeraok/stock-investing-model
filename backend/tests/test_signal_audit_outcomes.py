"""Phase 2: signal audit outcome resolver + verdict rules."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from signals.signal_audit_outcomes import resolve_event_outcome, resolve_signal_audit_outcomes
from signals.signal_audit_store import SignalAuditStore, row_to_signal_event, compute_config_hash
from signals.signal_audit_verdict import classify_signal_side, compute_verdict


def test_classify_buy_and_caution():
    assert classify_signal_side("BUY", "WATCH", "go") == "buy"
    assert classify_signal_side("HOLD", "WATCH", "no_go") == "caution"


def test_verdict_buy_hit_target():
    v, rule = compute_verdict(
        {"ml_signal": "BUY", "go_no_go": "go"},
        return_30d_pct=1.0,
        hit_st_target=1,
        hit_stop_swing=0,
    )
    assert v == "WIN"
    assert "st_target" in rule


def test_verdict_caution_false_negative():
    v, _ = compute_verdict(
        {"ml_signal": "HOLD", "go_no_go": "no_go"},
        return_30d_pct=6.0,
        hit_st_target=None,
        hit_stop_swing=None,
    )
    assert v == "LOSS"


def _write_eod(tmp_path: Path, date: str, ticker: str, close: float, high: float | None = None, low: float | None = None):
    eod_dir = tmp_path / "eod"
    eod_dir.mkdir(parents=True, exist_ok=True)
    hi = high if high is not None else close * 1.01
    lo = low if low is not None else close * 0.99
    payload = {
        "snapshot_date": date,
        "run_results": [
            {"ticker": ticker, "close": close, "high": hi, "low": lo},
            {"ticker": "SPY", "close": 500.0, "high": 501.0, "low": 499.0},
        ],
    }
    (eod_dir / f"{date}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def audit_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    cohort_file = tmp_path / "cohort.yaml"
    cohort_file.write_text(
        "cohort_tag: test_cohort\ncategories:\n  etfs:\n    - SPY\n",
        encoding="utf-8",
    )
    return {
        "signal_audit": {
            "enabled": True,
            "cohort_file": str(cohort_file),
            "outcomes": {
                "enabled": True,
                "horizon_trading_days": [7, 20],
                "use_intraday_touch": True,
            },
        },
        "score": {"buy_min": 65, "sell_max": 35},
    }


def test_resolve_event_outcome_with_eod_chain(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    dates = [f"2026-01-{d:02d}" for d in range(1, 26)]
    price = 100.0
    for i, d in enumerate(dates):
        _write_eod(tmp_path, d, "SPY", price + i * 0.5, high=price + i * 0.5 + 2, low=price + i * 0.5 - 1)

    store = SignalAuditStore(data_root=tmp_path)
    event = row_to_signal_event(
        {
            "ticker": "SPY",
            "close": 100.0,
            "signal": "BUY",
            "go_no_go": True,
            "gate_cleared": True,
            "composite_buy": 70,
            "rsi": 50,
            "regime": "UP",
            "st_band": {"low": 95.0, "high": 110.0},
            "mt_band": {"low": 90.0, "high": 120.0},
            "lt_band": {"low": 85.0, "high": 130.0},
            "retail_status": {"go_no_go": "go", "gates": [{"id": "ml", "pass": True}]},
        },
        signal_date=dates[0],
        signal_ts="2026-01-01T16:00:00",
        run_id="r1",
        cohort_tag="test_cohort",
        market_cap_bucket="etfs",
        config_hash="abc",
        run_source="test",
    )
    ok, _ = store.insert_event(event)
    assert ok
    ev = store.list_events_for_resolution(cohort_tag="test_cohort")[0]

    from signals.paper_trade_logger import PaperTradeLogger

    pt = PaperTradeLogger(data_root=tmp_path)
    eod_dates = pt._list_eod_dates()
    outcome = resolve_event_outcome(
        ev,
        eod_dates,
        pt._load_snapshot,
        horizon_short=7,
        horizon_long=20,
    )
    assert outcome is not None
    assert outcome["return_30d_pct"] is not None
    assert outcome["verdict"] in ("WIN", "LOSS", "NEUTRAL")

    store.upsert_outcome(outcome)
    summary = store.outcome_summary(cohort_tag="test_cohort")
    assert summary["resolved_n"] == 1
    assert "actionable_slices" in summary
    assert "full_go" in summary["actionable_slices"]
    assert "by_gates_passed" in summary
