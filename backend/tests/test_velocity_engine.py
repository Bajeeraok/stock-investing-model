import pandas as pd

from signals.velocity_engine import attach_velocity_to_row, compute_velocity_fields


def _series(vals):
    return pd.Series(vals, dtype=float)


def test_velocity_triggered_on_rvol_and_bb_breakout():
    close = _series([100 + i * 0.5 for i in range(40)])
    # ramp volume on last bar
    vol = _series([1_000_000.0] * 39 + [3_000_000.0])
    out = compute_velocity_fields(close, vol, config={"velocity_tactical": {"rvol_min": 2.0, "bb_pct_b_min": 0.9, "min_velocity_score": 50}})
    assert out["rvol"] is not None
    assert out["rvol"] >= 2.0
    assert out["velocity_score"] >= 50
    assert out["velocity_triggered"] is True
    assert out["track"] == "velocity"


def test_accumulate_when_quiet():
    close = _series([50.0] * 40)
    vol = _series([500_000.0] * 40)
    out = compute_velocity_fields(close, vol)
    assert out["velocity_triggered"] is False
    assert out["track"] == "accumulate"


def test_attach_velocity_to_row():
    close = _series([100 + i * 0.4 for i in range(40)])
    vol = _series([1_000_000.0] * 39 + [2_500_000.0])
    row = {"ticker": "TEST"}
    attach_velocity_to_row(row, close=close, volume=vol, config={"velocity_tactical": {"min_velocity_score": 40}})
    assert "velocity_score" in row
    assert row.get("track") in ("velocity", "accumulate")


def test_velocity_context_only_when_not_actionable():
    from signals.hunter_panel import build_hunter_panel
    from signals.velocity_engine import (
        align_tactical_entry_with_one_answer,
        build_tactical_breakouts_from_results,
        build_tactical_ui_payload,
    )

    cfg = {"velocity_tactical": {"actionable": False}}
    row = {"ticker": "X", "velocity_triggered": True, "velocity_score": 90, "tactical_entry": 10.0,
           "tactical_t1": 11.0, "tactical_stop": 9.5, "tactical_rr": 2.0, "close": 10.0}
    p = build_tactical_ui_payload(row, config=cfg)
    assert p["actionable"] is False and p["velocity_triggered"] is True
    assert p["entry"] is None and p["target_1"] is None and p["stop"] is None and p["rr_ratio"] is None
    p = align_tactical_entry_with_one_answer(p, {"action_today": "enter_now", "verdict": "BUY"})
    assert p["entry_stance"] == "breakout_context" and "context only" in p["stance_note"]
    assert build_tactical_breakouts_from_results([row], config=cfg) == []
    panel = build_hunter_panel([row], portfolio_tickers=[], watchlist_tickers=[], signal_universe=[],
                               velocity_actionable=False)
    assert all(c.get("hunter_reason") != "velocity" for c in panel.get("candidates") or [])
    assert build_tactical_ui_payload(row, config={})["target_1"] == 11.0


def test_shipped_config_keeps_velocity_off():
    from config_loader import load_config
    from signals.velocity_engine import velocity_actionable

    cfg = load_config()
    assert velocity_actionable(cfg) is False
    assert cfg["velocity_tactical"]["log_paper_trades"] is False
    assert cfg["alerts"]["enable_tactical_velocity_alerts"] is False
