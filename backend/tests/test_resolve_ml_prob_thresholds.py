from signals.regime import resolve_ml_prob_thresholds


def test_aliases_override():
    cfg = {
        "ml_strong_buy_prob": 0.55,
        "ml_buy_prob": 0.40,
        "ml_avoid_max_prob": 0.20,
        "strong_buy_ml": 0.60,
        "buy_ml": 0.41,
        "avoid_ml": 0.19,
    }
    a, b, c = resolve_ml_prob_thresholds(cfg)
    assert a == 0.60 and b == 0.41 and c == 0.19


def test_defaults_from_legacy_keys():
    cfg = {"ml_strong_buy_prob": 0.55, "ml_buy_prob": 0.40, "ml_avoid_max_prob": 0.20}
    assert resolve_ml_prob_thresholds(cfg) == (0.55, 0.40, 0.20)
