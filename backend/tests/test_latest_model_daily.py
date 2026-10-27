from signals.forward_tracking import build_latest_model_daily

V = "9.9.9"


def _rec(d0, d1, ret, sig="HOLD", v=V, tk="AAA", dq="ok", spy=0.5):
    stale = dq == "stale_session"
    return {
        "ticker": tk, "as_of_date": d0, "next_date": d1, "horizon_days": 1, "our_signal": sig,
        "actual_return_pct": None if stale else ret, "forward_status": "pending" if stale else "complete",
        "data_quality": dq, "benchmark_return_pct": None if stale else spy, "model_version": v,
    }


def test_skips_stale_start_and_scores_following_days():
    recs = [
        _rec("2026-10-23", "2026-10-24", None, v="old", dq="stale_session"),
        _rec("2026-10-24", "2026-10-26", None, dq="stale_session"),
        _rec("2026-10-26", "2026-10-27", 3.0),  # starts from a stale snapshot -> 2-day move, skipped
        _rec("2026-10-27", "2026-10-28", 2.0),
        _rec("2026-10-28", "2026-10-29", -4.0, sig="CONSIDER TRIM"),
        _rec("2026-10-28", "2026-11-03", 9.0),  # other horizon ignored
    ]
    recs[-1]["horizon_days"] = 5
    out = build_latest_model_daily(recs, V)
    assert out["days"] == 2
    assert out["first_date"] == "2026-10-27" and out["last_date"] == "2026-10-29"
    assert out["hold_cum_pct"] == round(100 * (1.02 * 0.96 - 1), 2)
    assert out["model_cum_pct"] == round(100 * (1.02 * 0.98 - 1), 2)
    assert out["model_vs_hold_pct"] > 0 and out["days_reduced"] == 1
    assert out["spy_cum_pct"] == round(100 * (1.005 ** 2 - 1), 2)
    assert "2026-10-26" in out["skipped_days"] and "2026-10-24" in out["skipped_days"]
    assert out["rows"][0]["date"] == "2026-10-28"


def test_pooled_equal_weight_and_version_filter():
    recs = [
        _rec("2026-10-27", "2026-10-28", 2.0, tk="AAA"),
        _rec("2026-10-27", "2026-10-28", -1.0, tk="BBB", sig="CONSIDER TRIM"),
        _rec("2026-10-27", "2026-10-28", 50.0, tk="CCC", v="old"),
    ]
    out = build_latest_model_daily(recs, V)
    row = out["rows"][0]
    assert row["tickers"] == 2 and row["hold_return_pct"] == 0.5 and row["model_return_pct"] == 0.75
    assert row["exposure"] == 0.75


def test_empty():
    out = build_latest_model_daily([], V)
    assert out["days"] == 0 and out["model_cum_pct"] is None and out["rows"] == []
