from signals.forward_tracking_metrics import aggregate_horizon_stats


def _row(sig, ret):
    return {"our_signal": sig, "actual_return_pct": ret}


def test_hold_is_not_scored_right_or_wrong():
    out = aggregate_horizon_stats([_row("HOLD", -6.4), _row("HOLD", -0.9), _row("HOLD", 1.1)], quality_only=False)
    assert out["calls_n"] == 0
    assert out["calls_right_pct"] is None


def test_add_and_trim_scored_by_direction():
    rows = [_row("HOLD/ADD", 2.0), _row("HOLD/ADD", -1.0), _row("CONSIDER TRIM", -3.0), _row("HOLD", -5.0)]
    out = aggregate_horizon_stats(rows, quality_only=False)
    assert out["calls_n"] == 3
    assert out["calls_right_pct"] == 66.7
