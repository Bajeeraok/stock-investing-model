from signals.position_advice import build_position_advice, holding_from_report

REPORT = {
    "total_value": 100_000,
    "per_holding": [
        {"ticker": "NVDA", "quantity": 100, "value": 10_000, "account": "IRA"},
        {"ticker": "NVDA", "quantity": 150, "value": 15_000, "account": "Taxable"},
        {"ticker": "AAPL", "quantity": 10, "value": 2_000, "account": "IRA"},
    ],
}


def test_holding_sums_all_accounts():
    h = holding_from_report(REPORT, "nvda")
    assert h["shares"] == 250 and h["value"] == 25_000 and len(h["accounts"]) == 2


def test_over_cap_trim_and_no_add():
    a = build_position_advice(
        ticker="NVDA", price=100, total_value=100_000,
        holding=holding_from_report(REPORT, "NVDA"), risk_profile="moderate", entry_mode="full_go",
    )
    assert a["weight_pct"] == 25.0
    assert not a["buy"]["allowed"]
    trim = [o for o in a["sell"]["options"] if o["reason"] == "over_cap"][0]
    assert trim["shares"] == 51  # back to <=20% of the book
    assert a["sell"]["default"] == "HOLD"


def test_hard_lock_blocks_buy():
    a = build_position_advice(
        ticker="AAPL", price=200, total_value=100_000,
        holding=holding_from_report(REPORT, "AAPL"), entry_mode="hard_lock",
    )
    assert a["buy"]["shares"] == 0 and "locked" in a["buy"]["note"]


def test_full_go_risk_capped_tranches():
    a = build_position_advice(
        ticker="MSFT", price=100, total_value=100_000, holding=None, risk_profile="moderate",
        entry_mode="full_go", horizons={"medium": {"stop_loss": 90}},
    )
    # cap room $20k; 2% risk / 10% stop -> $20k; full room
    assert a["buy"]["shares"] == 200
    assert [t["shares"] for t in a["buy"]["tranches"]] == [80, 60, 60]
    assert a["sell"]["options"] == [] and a["sell"]["default"] is None


def test_starter_and_protect_mode():
    a = build_position_advice(
        ticker="AAPL", price=200, total_value=100_000,
        holding=holding_from_report(REPORT, "AAPL"), entry_mode="starter_only",
        protect_mode={"active": True, "suggested_position_pct": 50},
    )
    assert a["buy"]["shares"] == int((20_000 - 2_000) * 0.25 // 200)
    pm = [o for o in a["sell"]["options"] if o["reason"] == "protect_mode"][0]
    assert pm["shares"] == 5
