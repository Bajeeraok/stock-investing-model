"""
News layer weight adjustment when HMM regime certainty is extreme.

Used by confidence_engine when ``confidence.extreme_regime_news.mode`` is ``taper``.
"""
from __future__ import annotations

REGIME_CERTAINTY_THRESHOLD = 0.90
NEWS_WEIGHT_FLOOR = 0.05
# Reference defaults for tests / documentation (engine passes actual profile weights)
NEWS_WEIGHT_STANDARD = 0.10
REGIME_WEIGHT_STANDARD = 0.15


def compute_news_weight(
    hmm_bull_probability: float | None,
    hmm_bear_probability: float | None,
    *,
    news_weight_standard: float = NEWS_WEIGHT_STANDARD,
    regime_weight_standard: float = REGIME_WEIGHT_STANDARD,
    certainty_threshold: float = REGIME_CERTAINTY_THRESHOLD,
    news_weight_floor: float = NEWS_WEIGHT_FLOOR,
) -> tuple[float, float, str]:
    """
    When max(bull, bear) >= threshold, taper news weight toward ``news_weight_floor``
    and add the delta to regime weight (sum of those two preserved).
    """
    if hmm_bull_probability is None and hmm_bear_probability is None:
        return news_weight_standard, regime_weight_standard, "no regime data"

    bull = hmm_bull_probability if hmm_bull_probability is not None else (
        1.0 - hmm_bear_probability if hmm_bear_probability is not None else 0.5
    )
    bear = hmm_bear_probability if hmm_bear_probability is not None else (1.0 - bull)

    regime_certainty = max(bull, bear)

    if regime_certainty < certainty_threshold:
        return news_weight_standard, regime_weight_standard, "regime not certain"

    if certainty_threshold >= 1.0:
        taper_factor = 0.0
    else:
        taper_factor = 1.0 - (regime_certainty - certainty_threshold) / (
            1.0 - certainty_threshold
        )
    taper_factor = max(0.0, min(1.0, taper_factor))
    adjusted_news = round(
        news_weight_floor + (news_weight_standard - news_weight_floor) * taper_factor,
        4,
    )
    delta = round(news_weight_standard - adjusted_news, 4)
    adjusted_regime = round(regime_weight_standard + delta, 4)

    direction = "bear" if bear > bull else "bull"
    reason = (
        f"HMM {direction} certainty {regime_certainty*100:.0f}% "
        f"≥ {certainty_threshold*100:.0f}% threshold — "
        f"news weight tapered {news_weight_standard*100:.0f}% → "
        f"{adjusted_news*100:.1f}%, "
        f"delta +{delta*100:.1f}% redistributed to regime"
    )

    return adjusted_news, adjusted_regime, reason


def apply_weight_cap_to_layer_config(
    layer_weights: dict[str, float],
    hmm_bull_probability: float | None,
    hmm_bear_probability: float | None,
    *,
    certainty_threshold: float = REGIME_CERTAINTY_THRESHOLD,
    news_weight_floor: float = 0.05,
) -> tuple[dict[str, float], str]:
    adjusted = dict(layer_weights)

    news_key = _find_key(adjusted, ["news_sentiment", "nlp_sentiment", "news"])
    regime_key = _find_key(adjusted, ["hmm_regime", "regime_hmm", "regime"])

    if news_key is None or regime_key is None:
        return adjusted, "news or regime key not found in layer config"

    new_news, new_regime, reason = compute_news_weight(
        hmm_bull_probability=hmm_bull_probability,
        hmm_bear_probability=hmm_bear_probability,
        news_weight_standard=adjusted[news_key],
        regime_weight_standard=adjusted[regime_key],
        certainty_threshold=certainty_threshold,
        news_weight_floor=news_weight_floor,
    )

    adjusted[news_key] = new_news
    adjusted[regime_key] = new_regime
    return adjusted, reason


def _find_key(d: dict, candidates: list[str]) -> str | None:
    for k in candidates:
        if k in d:
            return k
    for k in d:
        kl = k.lower()
        if any(c.lower() in kl for c in candidates):
            return k
    return None
