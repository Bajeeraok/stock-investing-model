"""Tactical velocity track: verdict rules + 5d outcome resolver."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from signals.signal_audit_outcomes import resolve_event_outcome
from signals.signal_audit_store import SignalAuditStore, row_to_signal_event
from signals.signal_audit_verdict import VERDICT_RULE_TACTICAL_5D, compute_tactical_verdict


def test_compute_tactical_verdict_t1_before_stop():
    v, rule = compute_tactical_verdict(
        {},
        return_horizon_pct=0.5,
        hit_t1=1,
        hit_stop=0,
    )
    assert v == "WIN"
    assert VERDICT_RULE_TACTICAL_5D in rule


def test_compute_tactical_verdict_stop_hit():
    v, rule = compute_tactical_verdict(
        {},
        return_horizon_pct=2.0,
        hit_t1=0,
        hit_stop=1,
    )
    assert v == "LOSS"
    assert "stop_hit" in rule


def test_compute_tactical_verdict_return_thresholds():
    v, _ = compute_tactical_verdict({}, return_horizon_pct=2.0, hit_t1=0, hit_stop=0, win_return_pct=1.5)
    assert v == "WIN"
    v, _ = compute_tactical_verdict({}, return_horizon_pct=-2.0, hit_t1=0, hit_stop=0, loss_return_pct=-1.5)
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
                "tactical_horizon_trading_days": 5,
                "use_intraday_touch": True,
            },
        },
    }


def test_resolve_tactical_velocity_5d_window(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    dates = [f"2026-01-{d:02d}" for d in range(1, 12)]
    for i, d in enumerate(dates):
        close = 100.0 + i
        _write_eod(tmp_path, d, "NVDA", close, high=close + 3, low=close - 1)

    store = SignalAuditStore(data_root=tmp_path)
    event = row_to_signal_event(
        {
            "ticker": "NVDA",
            "close": 100.0,
            "signal": "BUY",
            "gate_cleared": False,
            "gates_passed": 2,
            "velocity_triggered": True,
            "track": "velocity",
            "tactical_t1": 105.0,
            "tactical_t2": 110.0,
            "tactical_stop": 97.0,
            "horizon_trading_days": 5,
        },
        signal_date=dates[0],
        signal_ts="2026-01-01T16:00:00",
        run_id="r1",
        cohort_tag="test_cohort",
        market_cap_bucket="large_cap_tech",
        config_hash="abc",
        run_source="test",
    )
    assert event is not None
    assert event["horizon_trading_days"] == 5
    ok, _ = store.insert_event(event)
    assert ok
    ev = store.list_events_for_resolution(cohort_tag="test_cohort")[0]

    from signals.paper_trade_logger import PaperTradeLogger

    pt = PaperTradeLogger(data_root=tmp_path)
    outcome = resolve_event_outcome(
        ev,
        pt._list_eod_dates(),
        pt._load_snapshot,
        horizon_short=7,
        horizon_long=20,
        tactical_horizon=5,
    )
    assert outcome is not None
    assert outcome["path_days"] == 5
    assert VERDICT_RULE_TACTICAL_5D in outcome["verdict_rule"]
    assert outcome["notes"] == "tactical_5d_window"
