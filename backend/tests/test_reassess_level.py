from signals.reassess_level import compute_reassess_level


def test_no_52w_low_in_primary_condition():
    r = compute_reassess_level(
        current_price=189.31,
        verdict="REDUCE",
        confidence_score=0.43,
        ml_probability=0.10,
        pattern_score=38.0,
        hmm_bull_prob=0.01,
        ma50=182.01,
        ma200=180.90,
        week52_high=207.02,
        week52_low=96.89,
    )
    assert "96.89" not in r.primary_condition
    assert r.to_dict()["display"]


def test_spy_price_level_not_below_spot_when_below_ma():
    r = compute_reassess_level(
        current_price=686.10,
        verdict="REDUCE",
        confidence_score=0.37,
        ml_probability=0.02,
        pattern_score=41.0,
        hmm_bull_prob=0.84,
        ma50=672.87,
        ma200=661.39,
        week52_high=693.60,
        week52_low=508.06,
    )
    if r.price_level is not None:
        assert r.price_level > r.current_price
