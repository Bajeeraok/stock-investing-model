"""
Causal composite score at a single bar (same semantics as backtest bucket assignment).

Shared by scripts/backtest_simple.py and signals/thrive_phase2/short_backtest.py so the
~21d Phase 2 gate uses the same model score as the main backtest, not an RSI proxy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from signals.indicators import composite_score
from signals.sector_classifier import get_sector_score_bias, get_sector_weights


def composite_bar_score_for_backtest(
    close: pd.Series,
    idx: int,
    ticker: str = "",
    config: dict | None = None,
) -> float | None:
    """
    Composite score for bar idx (causal: data only up to idx).

    When score.interpretation.apply_to_backtest_buckets is True and the rolling window is
    classified MEAN_REVERTING (ACF), uses (100 - raw score) so the score aligns with
    bucket semantics (dip-buy edge on MR tape).
    """
    subset = close.iloc[: idx + 1]
    if len(subset) < 50:
        return None
    if config is None:
        try:
            from config_loader import load_config

            config = load_config()
        except Exception:
            config = {}

    use_spec = bool(config.get("use_spec_regime_score", False))
    weights = get_sector_weights(ticker) if ticker else None
    sig = composite_score(
        subset,
        weights=weights,
        use_spec=use_spec,
        ticker=ticker or None,
        config=config,
    )
    raw = sig.get("composite_buy")
    if raw is None:
        return None
    bias = get_sector_score_bias(ticker) if ticker else 0.0
    score = float(np.clip(raw + bias, 0.0, 100.0))

    ic = ((config.get("score") or {}).get("interpretation") or {})
    if not ic.get("apply_to_backtest_buckets", True):
        return score

    if ic.get("backtest_force_invert_buckets", False):
        return float(np.clip(100.0 - score, 0.0, 100.0))

    try:
        from signals.score_interpretation import detect_interpretation_style

        style, _meta = detect_interpretation_style(
            subset,
            None,
            config,
            ticker=ticker,
            for_backtest_buckets=True,
        )
        if style == "MEAN_REVERTING":
            score = float(np.clip(100.0 - score, 0.0, 100.0))
    except Exception:
        pass
    return score
