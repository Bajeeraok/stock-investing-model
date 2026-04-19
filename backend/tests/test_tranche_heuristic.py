"""Dynamic long-horizon T1/T2/T3 weights."""
from signals.tranche_heuristic import compute_long_horizon_tier_percentages


def test_tier_pcts_sum_to_100():
    r = compute_long_horizon_tier_percentages(
        current_price=100.0,
        ma200=100.0,
        atr=2.0,
        model_confidence_pct=50.0,
    )
    assert r["t1_pct"] + r["t2_pct"] + r["t3_pct"] == 100


def test_extended_reduces_front_load_increases_tail():
    low = compute_long_horizon_tier_percentages(
        current_price=100.0,
        ma200=100.0,
        atr=2.0,
        model_confidence_pct=60.0,
    )
    high = compute_long_horizon_tier_percentages(
        current_price=130.0,
        ma200=100.0,
        atr=5.0,
        model_confidence_pct=30.0,
    )
    assert high["t3_pct"] >= low["t3_pct"]
    assert high["stress01"] >= low["stress01"]
