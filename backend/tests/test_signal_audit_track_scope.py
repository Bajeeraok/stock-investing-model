"""Headline audit win rate excludes velocity tactical track."""
from __future__ import annotations

from signals.signal_audit_store import SignalAuditStore, row_to_signal_event


def _insert(store: SignalAuditStore, row: dict, *, track: str, ticker: str) -> int:
    row = dict(row)
    row["ticker"] = ticker
    row["track"] = track
    if track == "velocity":
        row["velocity_triggered"] = 1
    event = row_to_signal_event(
        row,
        signal_date="2026-06-01",
        signal_ts="2026-06-01T16:00:00Z",
        run_id=f"run-{ticker}-{track}",
        cohort_tag="track_test",
        market_cap_bucket="etfs",
        config_hash="h1",
        run_source="test",
    )
    ok, _ = store.insert_event(event)
    assert ok
    with store._connect() as conn:
        ev = conn.execute(
            "SELECT id, track FROM signal_events WHERE cohort_tag = ? AND ticker = ?",
            ("track_test", ticker.upper()),
        ).fetchone()
    assert ev is not None
    assert ev["track"] == track
    return int(ev["id"])


def test_outcome_summary_headline_excludes_velocity(tmp_path):
    store = SignalAuditStore(data_root=tmp_path)
    base = {
        "ticker": "SPY",
        "close": 500.0,
        "composite_buy": 72,
        "signal": "HOLD",
        "st_band": {"low": 480, "high": 520},
        "mt_band": {"low": 460, "high": 540},
        "retail_status": {
            "go_no_go": "no_go",
            "gates": [
                {"id": "valuation", "pass": False},
                {"id": "regime", "pass": True},
                {"id": "momentum", "pass": True},
                {"id": "ml", "pass": True},
            ],
            "gates_locked_count": 1,
        },
        "entry_mode": "hard_lock",
    }

    acc_id = _insert(store, base, track="accumulate", ticker="SPY")
    vel_id = _insert(store, base, track="velocity", ticker="QQQ")

    store.upsert_outcome({
        "signal_event_id": acc_id,
        "resolved_ts": "2026-06-22T00:00:00Z",
        "return_7d_pct": 2.0,
        "return_30d_pct": 5.0,
        "verdict": "WIN",
        "verdict_rule": "test",
        "hit_st_target": 0,
        "hit_stop_swing": 0,
    })
    store.upsert_outcome({
        "signal_event_id": vel_id,
        "resolved_ts": "2026-06-08T00:00:00Z",
        "return_7d_pct": -3.0,
        "return_30d_pct": -4.0,
        "verdict": "LOSS",
        "verdict_rule": "tactical_test",
        "hit_st_target": 0,
        "hit_stop_swing": 1,
    })

    summary = store.outcome_summary(cohort_tag="track_test")
    assert summary.get("track_scope") == "accumulate"
    assert summary.get("wins") == 1
    assert summary.get("losses") == 0
    assert summary.get("win_rate_pct") == 100.0
    assert summary.get("resolved_n_velocity") == 1
    assert summary.get("resolved_n_accumulate") == 1
    tac = summary.get("tactical_summary") or {}
    assert tac.get("losses") == 1
    assert tac.get("actionable_win_rate_pct") == 0.0
    assert summary.get("all_tracks_actionable_win_rate_pct") == 50.0
