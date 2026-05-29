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
