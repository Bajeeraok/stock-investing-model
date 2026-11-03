from signals.ticker_consistency_audit import audit_ticker_detail, summarize


def _detail(**over):
    d = {
        "ticker": "TEST",
        "current_price": 100.0,
        "low_52w": 80.0,
        "high_52w": 120.0,
        "gates_passed": 2,
        "model_confidence_pct": 50.0,
        "investor_summary": {
            "fair_value": 120.0,
            "model_confidence_pct": 50.0,
            "retail_action": {
                "entry_mode": "hard_lock",
                "go_no_go": "no_go",
                "max_sizing_pct": 0,
                "assessment_pct": 20.0,
                "gates": [{"id": "valuation", "pass": True}, {"id": "regime", "pass": True}, {"id": "ml", "pass": False}],
            },
            "horizons": {
                "short": {"entry_zone": {"low": 97.0, "high": 100.0}, "stop_loss": 94.0, "target": 105.0, "verdict": "HOLD"},
                "medium": {"entry_zone": {"low": 92.0, "high": 99.0}, "stop_loss": 88.0, "target": 112.0, "verdict": "HOLD"},
                "long": {"entry_zone": {"low": 85.0, "high": 95.0}, "stop_loss": 75.0, "target": 130.0, "verdict": "HOLD"},
            },
        },
    }
    d.update(over)
    return d


def _rules(findings):
    return {f["rule"] for f in findings}


def test_clean_detail_has_no_findings():
    assert audit_ticker_detail(_detail()) == []


def test_catches_list_vs_detail_and_gate_count():
    f = audit_ticker_detail(_detail(gates_passed=4), {"entry_mode": "full_go"})
    assert {"list_vs_detail_entry_mode", "gate_count_mismatch"} <= _rules(f)


def test_catches_band_and_target_problems():
    d = _detail()
    hz = d["investor_summary"]["horizons"]
    hz["medium"]["entry_zone"] = {"low": 80.0, "high": 104.0}
    hz["short"]["target"] = 95.0
    rules = _rules(audit_ticker_detail(d))
    assert {"band_above_price", "band_too_wide", "target_below_price"} <= rules


def test_buy_verdict_while_locked_and_nan():
    d = _detail(dividend_yield=float("nan"))
    d["investor_summary"]["horizons"]["long"]["verdict"] = "BUY"
    rules = _rules(audit_ticker_detail(d))
    assert {"buy_verdict_while_locked", "non_finite_values"} <= rules


def test_summary_counts():
    f = audit_ticker_detail(_detail(gates_passed=4))
    s = summarize(f, ["TEST"])
    assert s["counts"]["info"] == 1 and s["by_rule"][0]["rule"] == "gate_count_mismatch"


# ── edge cases: missing / malformed data must never crash the checker ──────────
import math
from datetime import date

from signals.ticker_consistency_audit import audit_track_record, rule_earnings_calendar, _Collector


def test_empty_and_error_details_do_not_crash():
    assert {f["rule"] for f in audit_ticker_detail({})} == {"price_missing"}
    assert _rules(audit_ticker_detail({"ticker": "X", "error": "boom"})) == {"detail_error"}
    d = _detail(investor_summary=None, position_advice=None, earnings="n/a", confidence=None)
    assert "rule_crashed" not in _rules(audit_ticker_detail(d))


def test_zero_and_string_values_are_handled():
    d = _detail(current_price=0, score="abc", beta=None)
    rules = _rules(audit_ticker_detail(d))
    assert "rule_crashed" not in rules and "price_missing" in rules


# ── negative cases: each contradiction is caught ─────────────────────────────
def test_ranges_and_indicators():
    d = _detail(score=140, rsi=-1, low_52w=130.0, high_52w=90.0, ma200=0, beta=9, daily_move_pct=80)
    rules = _rules(audit_ticker_detail(d))
    assert {"value_out_of_range", "range_52w_inverted", "indicator_non_positive", "beta_implausible",
            "daily_move_implausible"} <= rules


def test_entry_state_contradictions():
    d = _detail()
    ra = d["investor_summary"]["retail_action"]
    ra.update(entry_mode="full_go", go_no_go="go", action_title="No new entries", gates_locked_count=3)
    rules = _rules(audit_ticker_detail(d))
    assert {"full_go_with_failing_gate", "headline_vs_entry_mode", "locked_count_mismatch"} <= rules
    d2 = _detail()
    d2["investor_summary"]["overall_verdict"] = "BUY"
    for g in d2["investor_summary"]["retail_action"]["gates"]:
        g["pass"] = True
    d2["gates_passed"] = 3
    rules2 = _rules(audit_ticker_detail(d2))
    assert {"overall_buy_while_locked", "locked_with_all_gates_passing"} <= rules2


def test_position_advice_contradictions():
    d = _detail(position_advice={
        "price": 100.0, "entry_mode": "hard_lock", "held": False, "shares": 10, "value": 1000,
        "portfolio_value": 10000, "weight_pct": 25.0, "cap_pct": 20,
        "buy": {"allowed": False, "shares": 5, "tranches": [1]},
        "sell": {"options": [{"shares": 50}]},
    })
    rules = _rules(audit_ticker_detail(d))
    assert {"held_flag_mismatch", "weight_mismatch", "buy_disallowed_but_sized", "sell_shares_invalid",
            "sell_without_holding"} <= rules


def test_levels_quality():
    d = _detail()
    d["investor_summary"]["horizons"]["medium"]["entry_zone"]["levels"] = [
        {"price": 98.0, "role": "entry", "touch_pct": 40, "window_sessions": 63, "touch_history_years": 10, "touch_sample_n": 2000},
        {"price": 98.0, "role": "entry", "touch_pct": 40, "window_sessions": 63, "touch_history_years": 10, "touch_sample_n": 2000},
        {"price": 93.0, "role": "entry", "touch_pct": 70, "window_sessions": 20, "touch_history_years": 12, "touch_sample_n": 50},
    ]
    rules = _rules(audit_ticker_detail(d))
    assert {"duplicate_levels", "touch_odds_not_monotonic", "touch_window_mismatch", "touch_history_invalid",
            "touch_sample_small"} <= rules


def test_stop_target_math_and_fair_value():
    d = _detail()
    hz = d["investor_summary"]["horizons"]["medium"]
    hz.update(stop_loss_pct=-3.0, target_pct=20.0, risk_reward=5.0)
    d["investor_summary"]["fair_value"] = -5
    rules = _rules(audit_ticker_detail(d))
    assert {"stop_pct_mismatch", "target_pct_mismatch", "rr_mismatch", "fair_value_invalid"} <= rules


def test_earnings_calendar():
    c = _Collector("X")
    rule_earnings_calendar({"earnings": {"date": "2027-01-28", "days_until": 10}}, c, None, today=date(2026, 11, 3))
    assert {f["rule"] for f in c.findings} == {"earnings_days_mismatch"}
    c2 = _Collector("X")
    rule_earnings_calendar({"earnings": {"date": "2027-01-28", "days_until": 86}}, c2, None, today=date(2026, 11, 3))
    assert c2.findings == []


# ── Track tab ────────────────────────────────────────────────────────────────
def _track():
    return {
        "available": True,
        "eod_date_last": "2026-11-02",
        "daily_calls": [
            {"date": "2026-10-30", "next_date": "2026-11-02", "signal": "HOLD", "close": 100.0, "next_close": 95.0,
             "return_pct": -5.0, "right": None, "gates_passed": 4, "gates_total": 4},
            {"date": "2026-10-29", "next_date": "2026-10-30", "signal": "ADD", "close": 98.0, "next_close": 100.0,
             "return_pct": 2.04, "right": True, "gates_passed": 4, "gates_total": 4},
        ],
        "by_horizon": {"1": {"calls_n": 1, "calls_right_pct": 100.0, "n_observations": 2}},
        "latest_model_daily": {"model_cum_pct": -3.0, "hold_cum_pct": -3.0, "spy_cum_pct": -1.0,
                               "model_vs_hold_pct": 0.0, "model_vs_spy_pct": -2.0, "days_reduced": 0},
        "daily_trades": [{"date": "2026-10-21", "signal": "STARTER:BUY", "model_price": 100, "target": 105, "stop": 92}],
    }


def test_clean_track_has_no_findings():
    assert audit_track_record(_track(), "X", today=date(2026, 11, 3)) == []


def test_track_catches_hold_scoring_and_bad_math():
    tr = _track()
    tr["daily_calls"][0]["right"] = False
    tr["daily_calls"][1]["right"] = False
    tr["daily_calls"][1]["return_pct"] = 9.0
    tr["by_horizon"]["1"] = {"calls_n": 0, "calls_right_pct": 25.0, "n_observations": 4}
    tr["latest_model_daily"]["model_vs_spy_pct"] = 5.0
    tr["latest_model_daily"]["model_cum_pct"] = -1.0
    tr["daily_trades"][0]["stop"] = 101
    rules = {f["rule"] for f in audit_track_record(tr, "X", today=date(2026, 11, 20))}
    assert {"track_hold_scored", "track_right_wrong_direction", "track_return_math", "track_pct_without_calls",
            "track_vs_spy_math", "track_vs_hold_math", "track_model_differs_without_trims", "track_stale",
            "trade_levels_invalid"} <= rules


def test_track_unavailable_is_silent():
    assert audit_track_record({"available": False}, "X") == []
    assert audit_track_record(None, "X") == []
