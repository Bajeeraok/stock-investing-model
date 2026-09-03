"""Monte Carlo noise-injection stability check — validates the user's own proposed test:

'Inject +/-3% daily random price noise. A reliable blocking gate setup should stay
blocked under high noise conditions. If minor noise flips the gate from FAIL to PASS,
the HMM variance thresholds are too sensitive.'

Uses synthetic, deterministic trend series (clear bull / clear bear) so the test is
fast and reproducible, rather than depending on live market data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from signals.hmm_stability_check import inject_return_noise, run_noise_stability_trials


@pytest.fixture(autouse=True)
def _isolate_model_dir(tmp_path, monkeypatch):
    """Never write test fixtures' fitted models into the real data/models/ dir."""
    monkeypatch.setattr("signals.hmm_regime.MODELS_DIR", tmp_path)
    monkeypatch.setattr("signals.hmm_regime._MODEL_MEMORY_CACHE", {})


def _trend_series(n: int, daily_drift: float, start: float = 100.0, seed: int = 1) -> pd.Series:
    """Deterministic trend + a little real (non-injected) chop, so the HMM has a
    genuine, unambiguous regime to read — not a perfectly straight, unrealistic line.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    chop = rng.normal(0.0, 0.004, size=n)
    ret = daily_drift + chop
    ret[0] = 0.0
    close = start * np.cumprod(1.0 + ret)
    return pd.Series(close, index=idx)


def test_inject_return_noise_preserves_length_and_start():
    close = _trend_series(300, 0.001)
    noisy = inject_return_noise(close, 0.03, seed=5)
    assert len(noisy) == len(close)
    assert noisy.iloc[0] == pytest.approx(close.iloc[0])


def test_inject_return_noise_is_reproducible_per_seed():
    close = _trend_series(300, 0.001)
    a = inject_return_noise(close, 0.03, seed=5)
    b = inject_return_noise(close, 0.03, seed=5)
    c = inject_return_noise(close, 0.03, seed=6)
    pd.testing.assert_series_equal(a, b)
    assert not a.equals(c)


@pytest.mark.parametrize(
    "daily_drift,seed",
    [
        (-0.0035, 2),   # sustained decline
        (0.0018, 3),    # sustained advance
    ],
)
def test_regime_gate_stable_under_noise(daily_drift, seed):
    """Whatever the baseline regime read is (bull or bear), it should not flip across
    the gate threshold on realistic +/-3% daily noise alone — the exact property the
    user asked to validate. This intentionally does not assert *which* regime the
    baseline resolves to (that's the separate, already-tracked RECENT_BARS/trend-decay
    question) — only that the read is stable under noise, which is this test's job.
    """
    close = _trend_series(400, daily_drift, seed=seed)
    result = run_noise_stability_trials(
        f"TESTHMM_{seed}", close, noise_pct=0.03, n_trials=15, seed_base=100 * seed
    )
    assert result["ok"] is True
    assert result["gate_flip_rate"] is not None
    assert result["gate_flip_rate"] <= 0.2, (
        f"Gate flipped in {result['gate_flip_count']}/{result['n_trials_completed']} "
        f"noisy trials — HMM is too sensitive to daily noise: {result}"
    )
