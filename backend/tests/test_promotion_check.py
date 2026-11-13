import numpy as np

from signals.statistical_validation import (
    deflated_sharpe_ratio,
    newey_west_t_stat,
    probability_of_backtest_overfitting,
    promotion_check,
)


def test_strong_edge_passes_and_noise_fails():
    rng = np.random.default_rng(0)
    strong = rng.normal(1.0, 2.0, 400)
    noise = rng.normal(0.0, 2.0, 400)
    assert promotion_check(list(strong), n_trials=10)["passes"]
    r = promotion_check(list(noise), n_trials=10)
    assert not r["passes"] and r["fails"]


def test_costs_and_small_samples_block():
    r = promotion_check([0.08] * 10 + [0.12] * 10, n_trials=1, cost_bps=10)
    assert not r["passes"] and any("cases" in f for f in r["fails"])


def test_more_trials_lower_dsr():
    x = np.random.default_rng(1).normal(0.15, 1.0, 250)
    assert deflated_sharpe_ratio(x, 1)["dsr"] > deflated_sharpe_ratio(x, 200)["dsr"]


def test_overlap_shrinks_t():
    x = np.repeat(np.random.default_rng(2).normal(0.2, 1.0, 100), 5)  # 5-bar overlapping copies
    assert newey_west_t_stat(x, lags=4) < newey_west_t_stat(x, lags=0)


def test_pbo_high_for_pure_noise_low_for_real_edge():
    pbos = [probability_of_backtest_overfitting(np.random.default_rng(s).normal(0, 1, (320, 20)), n_splits=8) for s in range(12)]
    assert 0.35 < float(np.mean(pbos)) < 0.65  # noise: the in-sample winner is a coin flip out of sample
    noise = np.random.default_rng(3).normal(0, 1, (320, 20))
    edge = noise.copy()
    edge[:, 0] += 0.5
    assert probability_of_backtest_overfitting(edge, n_splits=8) < 0.1
