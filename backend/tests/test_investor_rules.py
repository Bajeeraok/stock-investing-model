from signals.investor_rules import RULES, evaluate_rules, market_inputs, rules_for_ticker

ROWS = [
    {"ticker": "SPY", "price": 700, "ma50": 720, "ma200": 710, "drawdown_52w": -12, "rsi": 40},
    {"ticker": "NVDA", "price": 160, "ma50": 190, "ma200": 200, "drawdown_52w": -32, "rsi": 25,
     "earnings_days_until": 4, "regime": "DOWN", "composite_buy": 20, "volume_ratio": 2.0, "change_pct": -3.0},
    {"ticker": "AAPL", "price": 300, "ma50": 260, "ma200": 230, "drawdown_52w": -2, "rsi": 78,
     "fair_value": 240, "fair_value_method": "peg_blend", "gate_cleared": True, "gates_total": 5,
     "retail_status": {"gates": [{"id": "valuation", "pass": False}]}},
    {"ticker": "BAC", "price": 80, "ma50": 50, "ma200": 45, "fair_value": 60,
     "fair_value_method": "Analyst median — model FV unavailable (BANK)"},
]


def _by_id(out):
    return {r["id"]: {h["ticker"] for h in r["hits"]} for r in out["rules"]}


def test_ticker_and_market_hits():
    m = market_inputs(ROWS, {"vix": 32.0, "yield_curve_2s10s": -0.2, "hy_oas_bp": 3.4})
    hits = _by_id(evaluate_rules(ROWS, m, today="2026-11-12"))
    assert {"NVDA", "SPY"} <= hits["below_200d"] and "AAPL" not in hits["below_200d"]
    assert "NVDA" in hits["falling_knife"] and "NVDA" in hits["earnings_binary"] and "NVDA" in hits["distribution"]
    assert {"AAPL", "BAC"} <= hits["overextended"]
    assert hits["rich_vs_value"] == {"AAPL"}  # Wall St fallback FV never counts as the model's value
    assert hits["fat_pitch"] == {"AAPL"} and "AAPL" in hits["trend_template"]
    assert hits["fear_buy"] == {"MARKET"} and hits["spy_below_200d"] == {"MARKET"} and hits["yield_curve"] == {"MARKET"}
    assert hits["credit_stress"] == set() and hits["complacency"] == set()


def test_first_seen_marks_new_then_resets():
    seen: dict[str, str] = {}
    out1 = evaluate_rules(ROWS, {}, first_seen=seen, today="2026-11-11")
    assert out1["new_total"] > 0 and seen["below_200d:NVDA"] == "2026-11-11"
    out2 = evaluate_rules(ROWS, {}, first_seen=seen, today="2026-11-12")
    assert out2["new_total"] == 0
    evaluate_rules([r for r in ROWS if r["ticker"] != "NVDA"], {}, first_seen=seen, today="2026-11-13")
    assert "below_200d:NVDA" not in seen
    hits = rules_for_ticker(out2, "nvda")
    assert hits and all(h["new"] is False for h in hits)


def test_every_rule_is_described():
    for r in RULES:
        assert r["applied"] in ("in_model", "highlight", "habit") and r["who"] and r["rule"] and r["how"]
        assert ("check" in r or "market_check" in r) == (r["applied"] != "habit" and r["id"] not in ("stop_first", "position_cap"))
