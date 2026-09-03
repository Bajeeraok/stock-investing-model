"""Monte Carlo noise-injection stability check for the HMM regime gate.

Validates a specific claim: a blocking Market Weather gate should stay blocked (and a
clear pass should stay a pass) under realistic day-to-day price noise that doesn't
change the underlying trend. If small noise flips bull_probability across the
REGIME_GATE threshold, the HMM read is too sensitive to be a reliable trading gate.

Noise is injected at the return level (not the price level) and reconstructed into a
price path — this is "the same trend, noisier daily prints", not an independent random
walk. Because `_load_or_fit` only refits on a feature-dimension mismatch (see
hmm_regime._load_or_fit), calling get_hmm_regime() with a noisy-but-same-length series
reuses the cached/fitted model and only exercises predict_proba — isolating prediction
sensitivity from fitting noise, the same care taken when diagnosing the direction-blind
feature bug (see hmm_regime._signed_trend_feature).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from signals.hmm_regime import get_hmm_regime
from signals.retail_action_payload import REGIME_GATE


def inject_return_noise(close: pd.Series, noise_pct: float, seed: int) -> pd.Series:
    """Add i.i.d. Uniform(-noise_pct, +noise_pct) noise to daily returns, then
    reconstruct a price path anchored to the same starting price.
    """
    rng = np.random.default_rng(seed)
    ret = close.pct_change().fillna(0.0)
    eps = rng.uniform(-noise_pct, noise_pct, size=len(ret))
    noisy_ret = ret.values + eps
    noisy_ret[0] = 0.0  # first bar has no return to perturb
    noisy_close = float(close.iloc[0]) * np.cumprod(1.0 + noisy_ret)
    return pd.Series(noisy_close, index=close.index)


def run_noise_stability_trials(
    ticker: str,
    close: pd.Series,
    volume: pd.Series | None = None,
    *,
    noise_pct: float = 0.03,
    n_trials: int = 30,
    seed_base: int = 0,
    **hmm_kwargs,
) -> dict:
    """Run n_trials noisy variants through get_hmm_regime() and summarize stability.

    Returns a dict with the baseline (unperturbed) read, trial bull_probability stats,
    and gate_flip_rate — the fraction of trials whose regime_ok (bull % >= REGIME_GATE)
    disagrees with the baseline's regime_ok. A well-behaved gate should show a low
    flip_rate for a moderate noise_pct like 0.03 (±3%/day).
    """
    baseline = get_hmm_regime(ticker, close, volume, **hmm_kwargs)
    if baseline is None:
        return {"ok": False, "error": "baseline HMM read failed"}

    baseline_bull_pct = float(baseline["bull_probability"]) * 100.0
    baseline_gate_ok = baseline_bull_pct >= REGIME_GATE

    trial_bull_pcts: list[float] = []
    flips = 0
    for i in range(n_trials):
        noisy_close = inject_return_noise(close, noise_pct, seed=seed_base + i)
        result = get_hmm_regime(ticker, noisy_close, volume, **hmm_kwargs)
        if result is None:
            continue
        bull_pct = float(result["bull_probability"]) * 100.0
        trial_bull_pcts.append(bull_pct)
        if (bull_pct >= REGIME_GATE) != baseline_gate_ok:
            flips += 1

    n_ok = len(trial_bull_pcts)
    arr = np.array(trial_bull_pcts) if n_ok else np.array([baseline_bull_pct])
    return {
        "ok": True,
        "ticker": ticker,
        "noise_pct": noise_pct,
        "n_trials": n_trials,
        "n_trials_completed": n_ok,
        "baseline_bull_pct": round(baseline_bull_pct, 2),
        "baseline_gate_ok": baseline_gate_ok,
        "trial_bull_pct_mean": round(float(arr.mean()), 2),
        "trial_bull_pct_std": round(float(arr.std()), 2),
        "trial_bull_pct_min": round(float(arr.min()), 2),
        "trial_bull_pct_max": round(float(arr.max()), 2),
        "gate_flip_count": flips,
        "gate_flip_rate": round(flips / n_ok, 3) if n_ok else None,
    }
