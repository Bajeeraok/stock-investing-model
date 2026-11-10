"""Core principle scorecard: losses small and rare, gains bigger."""
from datetime import date

from signals.forward_tracking_metrics import build_loss_scorecard, build_loss_scorecards
from signals.ticker_consistency_audit import audit_track_record


def _r(sig, ret, h=20, v="v2", dd=None):
    return {"horizon_days": h, "our_signal": sig, "actual_return_pct": ret, "forward_status": "complete",
            "data_quality": "ok", "model_version": v, "max_drawdown_pct": dd}


def test_buys_and_exits_split_hold_ignored():
    rows = [_r("HOLD/ADD", 4.0, dd=-1.0), _r("HOLD/ADD", -2.0, dd=-3.0), _r("HOLD", -9.0),
            _r("CONSIDER TRIM", -3.0), _r("AVOID", 1.0)]
    sc = build_loss_scorecard(rows, 20)
    b, e = sc["buys"], sc["exits"]
    assert b["n"] == 2 and b["avg_pnl_pct"] == 1.0 and b["loss_rate_pct"] == 50.0
    assert b["worst_loss_pct"] == -2.0 and b["worst_dip_pct"] == -3.0 and b["gain_loss_ratio"] == 2.0
    assert e == {"n": 2, "losses_avoided_n": 1, "avg_drop_avoided_pct": 3.0, "missed_gain_n": 1,
                 "avg_missed_gain_pct": 1.0, "net_saved_pct": 1.0}
    assert sc["buys_status"] == "too_few" and sc["exits_status"] == "too_few"


def test_status_needs_min_n():
    losing = [_r("ADD", -1.0)] * 6 + [_r("ADD", 0.5)] * 4
    assert build_loss_scorecard(losing, 20)["buys_status"] == "losing"
    weak = [_r("ADD", 2.0)] * 7 + [_r("ADD", -3.0)] * 3
    assert build_loss_scorecard(weak, 20)["buys_status"] == "weak"
    ok = [_r("ADD", 3.0)] * 7 + [_r("ADD", -1.0)] * 3
    assert build_loss_scorecard(ok, 20)["buys_status"] == "ok"
    costing = [_r("TRIM", 2.0)] * 10
    assert build_loss_scorecard(costing, 20)["exits_status"] == "costing"
    assert build_loss_scorecard([_r("HOLD", 1.0)], 20) is None


def test_scorecards_split_current_and_all():
    rows = [_r("ADD", 1.0, v="v1"), _r("ADD", 2.0, v="v2"), _r("ADD", 1.0, h=5, v="v2")]
    sc = build_loss_scorecards(rows, "v2")
    assert sc["20"]["all"]["buys"]["n"] == 2 and sc["20"]["current"]["buys"]["n"] == 1
    assert sc["5"]["current"]["buys"]["n"] == 1
    assert build_loss_scorecards([_r("HOLD", 1.0)], "v2") is None


def test_audit_flags_losing_buys_and_costly_exits():
    rows = [_r("ADD", -1.0)] * 10 + [_r("TRIM", 2.0)] * 10
    tr = {"available": True, "loss_scorecard": build_loss_scorecards(rows, "v2")}
    rules = {f["rule"] for f in audit_track_record(tr, "X", today=date(2026, 11, 3))}
    assert {"buy_calls_losing_money", "exit_calls_costing_money"} <= rules
    good = [_r("ADD", 3.0)] * 10
    tr = {"available": True, "loss_scorecard": build_loss_scorecards(good, "v2")}
    assert audit_track_record(tr, "X", today=date(2026, 11, 3)) == []
