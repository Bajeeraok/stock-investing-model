import pandas as pd

from signals.best_setups import build_report, pick_outcome, setup_row


def _detail(ticker="AAA", price=100.0, entry_mode="full_go", rr=2.5, prob=60.0, band=(96.0, 99.0),
            target=120.0, stop=90.0, setup_status="ok"):
    return {
        "ticker": ticker,
        "current_price": price,
        "investor_summary": {
            "retail_action": {"entry_mode": entry_mode,
                              "display_by_mode": {"swing": {"gates_passed": 2, "gates_total": 4},
                                                  "owner": {"gates_passed": 2, "gates_total": 4}}},
            "horizons": {
                "medium": {"entry_zone": {"low": band[0], "high": band[1], "levels": [
                    {"role": "entry", "price": band[1], "target_first_pct": 40, "stop_first_pct": 45}]},
                    "target": target, "stop_loss": stop, "risk_reward_from_entry": rr,
                    "ml_prob": prob, "ml_scored": True, "setup_status": setup_status},
                "long": {"entry_zone": {"low": 80.0, "high": 85.0}, "target": 130.0, "stop_loss": 70.0,
                         "risk_reward_from_entry": 3.0, "ml_prob": 50.0, "ml_scored": True},
            },
        },
    }


def test_qualified_swing_row_and_edge():
    r = setup_row(_detail(), "swing")
    assert r["qualified"] and r["status"] == "Can add"
    mid = 97.5
    tgt, stp = (120 - mid) / mid * 100, (mid - 90) / mid * 100
    assert abs(r["edge_pct"] - round(0.6 * tgt - 0.4 * stp, 2)) < 0.01
    assert r["target_first_pct"] == 40


def test_blockers_hard_lock_low_rr_and_far_band():
    r = setup_row(_detail(entry_mode="hard_lock", rr=1.6), "swing")
    assert not r["qualified"]
    assert "entry gates" in r["blockers"] and "R:R under 2.0" in r["blockers"]
    owner = setup_row(_detail(), "owner")  # price 100 vs band top 85 → far above band
    assert "price above band" in owner["blockers"]


def test_ranking_and_next_up():
    rep = build_report([
        _detail("AAA", prob=70),
        _detail("BBB", prob=55),
        _detail("CCC", prob=70, entry_mode="hard_lock"),
        {"ticker": "BTC-USD", "current_price": 1.0},
    ])
    sw = rep["modes"]["swing"]
    assert [r["ticker"] for r in sw["picks"]] == ["AAA", "BBB"]
    assert [r["ticker"] for r in sw["next_up"]] == ["CCC"]


def test_pick_outcome_target_first():
    idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"])
    bars = pd.DataFrame({"close": [100, 104, 112, 121], "high": [101, 105, 113, 122],
                         "low": [99, 102, 110, 118]}, index=idx)
    pk = {"price": 100.0, "target": 120.0, "stop": 92.0}
    oc = pick_outcome(pk, "2026-01-02", bars, 63)
    assert oc["result"] == "target" and oc["return_pct"] == 20.0
    oc2 = pick_outcome({"price": 100.0, "target": 130.0, "stop": 103.0}, "2026-01-02", bars, 63)
    assert oc2["result"] == "stop"
