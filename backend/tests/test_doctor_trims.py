from portfolio.doctor import allocation_recommendations


def _report():
    rows = [
        {"ticker": "NVDA", "account": "IRA", "value": 15.0, "score": 4, "is_trim_candidate": False},
        {"ticker": "NVDA", "account": "Taxable", "value": 10.0, "score": 4, "is_trim_candidate": False},
        {"ticker": "SHOP", "account": "IRA", "value": 5.0, "score": 20, "is_trim_candidate": True, "trim_risk_reasons": ["extended"]},
        {"ticker": "META", "account": "IRA", "value": 70.0 - 0.0, "score": 18, "is_trim_candidate": False},
    ]
    return {"total_value": 100.0, "per_holding": rows}


def test_one_row_per_ticker_and_avoid_alone_not_trimmed():
    rep = _report()
    rep["per_holding"][3]["value"] = 10.0
    rep["total_value"] = 40.0
    out = allocation_recommendations(rep, [], [], {"risk_appetite": "aggressive"})
    tickers = [t["ticker"] for t in out["trim"]]
    assert tickers.count("NVDA") == 1
    nvda = next(t for t in out["trim"] if t["ticker"] == "NVDA")
    assert nvda["over_limit"] and nvda["risk_reasons"] == []
    assert nvda["accounts"] == ["IRA", "Taxable"]
    assert "META" not in tickers
    assert next(t for t in out["trim"] if t["ticker"] == "SHOP")["risk_reasons"] == ["extended"]


def test_profile_cap_changes_over_limit_trim():
    rep = {"total_value": 100.0, "per_holding": [
        {"ticker": "NVDA", "value": 22.0, "score": 50, "is_trim_candidate": False},
        {"ticker": "SPY", "value": 78.0, "score": 50, "is_trim_candidate": False},
    ]}
    cons = allocation_recommendations(rep, [], [], {"risk_appetite": "conservative"})
    aggr = allocation_recommendations(rep, [], [], {"risk_appetite": "aggressive"})
    nv = next(t for t in cons["trim"] if t["ticker"] == "NVDA")
    assert nv["suggest_trim_pct"] == 7.0
    assert "NVDA" not in [t["ticker"] for t in aggr["trim"]]
