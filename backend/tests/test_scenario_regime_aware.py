import pytest

from signals.scenario_regime_aware import Scenario, adjust_scenario_probabilities


@pytest.fixture
def nvda_scenarios():
    return [
        Scenario("Bull Case", "bull_case", 0.34, 400.00, 112.6, "Bull"),
        Scenario("Base Case", "base_case", 0.14, 275.00, 46.2, "Base"),
        Scenario("Earnings Beat", "earnings_beat", 0.29, 214.48, 14.0, "Beat"),
        Scenario("Fed Rate Cut", "fed_rate_cut", 0.19, 212.60, 13.0, "Fed"),
        Scenario("Earnings Miss", "earnings_miss", 0.05, 188.14, 0.0, "Miss"),
        Scenario("Bear Case", "bear_case", 0.05, 170.32, -9.5, "Bear"),
    ]


def test_probabilities_sum_to_one(nvda_scenarios):
    adj, _ = adjust_scenario_probabilities(
        nvda_scenarios, hmm_bull_prob=0.01, hmm_bear_prob=0.00, hmm_trans_prob=0.99
    )
    total = sum(s.adjusted_probability for s in adj)
    assert abs(total - 1.0) < 0.001


def test_transition_regime_downweights_bull_vs_bull_regime(nvda_scenarios):
    adj_trans, _ = adjust_scenario_probabilities(
        nvda_scenarios, hmm_bull_prob=0.01, hmm_bear_prob=0.00, hmm_trans_prob=0.99
    )
    adj_bull, _ = adjust_scenario_probabilities(
        nvda_scenarios, hmm_bull_prob=0.85, hmm_bear_prob=0.05, hmm_trans_prob=0.10
    )
    t_bull = next(s for s in adj_trans if s.scenario_type == "bull_case")
    b_bull = next(s for s in adj_bull if s.scenario_type == "bull_case")
    assert t_bull.adjusted_probability < b_bull.adjusted_probability


def test_hmm_macro_features_smoke():
    import numpy as np
    import pandas as pd

    from signals.hmm_macro_features import build_hmm_features, get_asset_type

    assert get_asset_type("SPY") == "broad_market"
    n = 300
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    close = 100 * np.cumprod(1 + np.random.default_rng(0).normal(0.0003, 0.012, n))
    df = pd.DataFrame({"close": close, "volume": np.random.randint(1_000_000, 10_000_000, n)}, index=dates)
    mat, names = build_hmm_features("NVDA", df, include_macro=False)
    assert mat.ndim == 2
    assert "ma200_gap" in names
    assert not np.any(np.isnan(mat))
