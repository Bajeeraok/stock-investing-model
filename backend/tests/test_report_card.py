from signals.report_card import build_report_card


def _rec(d, tk, sig, ret, h=20, spy=1.0, v="2026.10.2"):
    return {
        "as_of_date": d, "ticker": tk, "our_signal": sig, "actual_return_pct": ret, "horizon_days": h,
        "model_version": v, "forward_status": "complete", "benchmark_return_pct": spy,
        "close_at_signal": 100.0, "close_at_forward": 100.0 + ret,
    }


def test_trim_before_drop_is_positive_edge_and_clustered_by_day():
    recs = [_rec("2026-10-01", "AAA", "CONSIDER TRIM", -10), _rec("2026-10-01", "BBB", "HOLD", 5),
            _rec("2026-10-02", "AAA", "HOLD", 2), _rec("2026-10-01", "AAA", "CONSIDER TRIM", -1, h=1)]
    rc = build_report_card(recs, "2026.10.2", min_days=2)
    assert rc["trading_days_scored"] == 2 and rc["calls_scored"] == 3
    assert rc["edge_vs_hold_20d"]["mean"] == 1.225
    assert rc["directional_hit_rate"]["calls"] == 1 and rc["directional_hit_rate"]["hit_pct"] == 100.0
    assert rc["calls"][0]["return_20d_pct"] == -10 and rc["calls"][0]["right_20d"] is True
    assert rc["public"] is False


def test_publish_gate_needs_days_and_months():
    recs = [_rec(f"2026-10-{d:02d}", "AAA", "HOLD", 1) for d in range(1, 11)]
    rc = build_report_card(recs, "2026.10.2")
    assert not rc["ready_to_publish"]
    assert [c["ok"] for c in rc["publish_checks"]] == [False, False, False]
    assert build_report_card([_rec("2026-10-01", "A", "HOLD", 1, v="old")], "2026.10.2")["calls_scored"] == 0


def test_weekly_draft_mentions_trims():
    recs = [_rec("2026-10-01", "AAA", "CONSIDER TRIM", -2, h=1), _rec("2026-10-01", "BBB", "HOLD", 1, h=1)]
    draft = build_report_card(recs, "2026.10.2")["weekly_draft"]
    assert "Trim calls: AAA" in draft and "not investment advice" in draft
