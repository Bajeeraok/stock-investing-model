"""
Regime (UP / NEUTRAL / DOWN) from composite score or MA-based (UP / UP-HV / DOWN / SIDE).
Global market regime: 5-level (STRONG_BULL, BULL, NEUTRAL, BEAR, STRONG_BEAR) from index vs MA200/MA50 + 12m momentum.
"""
from __future__ import annotations

# 5-level regime for finer granularity (Thrive Alpha Engine style)
GLOBAL_REGIMES = ("STRONG_BULL", "BULL", "NEUTRAL", "BEAR", "STRONG_BEAR")


def get_global_market_regime(close_index, min_days_confirm: int = 3) -> str:
    """
    5-level index-based market regime: STRONG_BULL, BULL, NEUTRAL, BEAR, STRONG_BEAR.
    Uses price vs MA200 (bull_threshold 1.05, bear_threshold 0.95), SMA50 vs MA200, and 12m momentum.
    """
    try:
        import pandas as pd
    except ImportError:
        return "NEUTRAL"
    if close_index is None or len(close_index) < 200:
        return "NEUTRAL"
    ma50 = close_index.rolling(50, min_periods=50).mean()
    ma200 = close_index.rolling(200, min_periods=200).mean()
    last_close = float(close_index.iloc[-1])
    last_ma50 = float(ma50.iloc[-1])
    last_ma200 = float(ma200.iloc[-1])
    if last_ma200 <= 0:
        return "NEUTRAL"

    # 12-month momentum (252 trading days)
    momentum_12m = 0.0
    if len(close_index) >= 252:
        price_12m_ago = float(close_index.iloc[-252])
        if price_12m_ago > 0:
            momentum_12m = (last_close / price_12m_ago) - 1.0

    # Require N consecutive days above/below MA200 for BULL/BEAR (else NEUTRAL)
    if min_days_confirm > 1:
        recent = close_index.iloc[-min_days_confirm:]
        ma_recent = ma200.iloc[-min_days_confirm:]
        above = (recent.values > ma_recent.values).all()
        below = (recent.values < ma_recent.values).all()
        if not above and not below:
            return "NEUTRAL"

    # 5-level classification
    if (last_close > last_ma200 * 1.05 and last_ma50 > last_ma200 and momentum_12m > 0.15):
        return "STRONG_BULL"
    if (last_close > last_ma200 and last_ma50 > last_ma200):
        return "BULL"
    if (last_close < last_ma200 * 0.95 and last_ma50 < last_ma200 and momentum_12m < -0.15):
        return "STRONG_BEAR"
    if (last_close < last_ma200 and last_ma50 < last_ma200):
        return "BEAR"
    return "NEUTRAL"


def get_regime_multiplier(regime: str, raw_score: float) -> tuple[float, str]:
    """
    Returns (multiplier, reason). In BEAR/STRONG_BEAR, high scores underperform → heavy suppression.
    """
    is_high_score = raw_score >= 50
    multiplier_map = {
        "STRONG_BULL": (1.20 if is_high_score else 0.50, "Strong bull: amplify high-confidence" if is_high_score else "Strong bull: fade low scores"),
        "BULL": (1.00 if is_high_score else 0.70, "Bull: use scores as-is" if is_high_score else "Bull: mild suppression of weak"),
        "NEUTRAL": (0.75, "Neutral: suppress all moderately"),
        "BEAR": (0.30 if is_high_score else 0.90, "BEAR: heavy suppression of high (mean-revert risk)" if is_high_score else "Bear: low scores relatively resilient"),
        "STRONG_BEAR": (0.10 if is_high_score else 0.60, "STRONG BEAR: near-zero on buys" if is_high_score else "Strong bear: only defensive"),
    }
    mult, reason = multiplier_map.get(regime, (0.75, "Unknown regime"))
    return mult, reason


def get_vix_multiplier(vix: float | None) -> tuple[float, str]:
    """VIX overlay: calm amplifies slightly, elevated+ suppresses."""
    if vix is None or vix <= 0:
        return 1.0, "VIX n/a: no adjustment"
    if vix < 15:
        return 1.10, f"VIX={vix:.1f} (calm): slight amplification"
    if vix < 20:
        return 1.00, f"VIX={vix:.1f} (normal): no adjustment"
    if vix < 25:
        return 0.80, f"VIX={vix:.1f} (elevated): mild suppression"
    if vix < 30:
        return 0.50, f"VIX={vix:.1f} (high): significant suppression"
    return 0.20, f"VIX={vix:.1f} (extreme): near-full suppression"


def get_vix_min_hit_rate(vix: float | None) -> float:
    """Higher VIX requires higher hit rate to trust ADD signals. Returns 0.0–1.0."""
    if vix is None or vix < 15:
        return 0.55
    if vix < 20:
        return 0.60
    if vix < 25:
        return 0.65
    if vix < 30:
        return 0.70
    return 0.80


def get_regime_ma(
    price: float,
    ma50: float | None,
    ma200: float | None,
    vol_20: float | None,
    vol_70_pct: float | None,
) -> str:
    """
    MA-based regime from price vs MA50 vs MA200 and 20d volatility.
    Spec: price > MA50 > MA200 + vol <= p70 -> UP; vol > p70 -> UP-HV;
    price < MA50 < MA200 -> DOWN; else SIDE.
    """
    if ma200 is None or ma200 <= 0 or ma50 is None or ma50 <= 0:
        return "SIDE"
    if price > ma50 > ma200:
        if vol_20 is not None and vol_70_pct is not None and vol_20 > vol_70_pct:
            return "UP-HV"  # high-vol uptrend
        return "UP"
    if price < ma50 < ma200:
        return "DOWN"
    return "SIDE"


def _ma_regime_to_display(ma_regime: str) -> str:
    """Map MA regime to display regime (UP/NEUTRAL/DOWN) for backward compatibility."""
    if ma_regime in ("UP", "UP-HV"):
        return "UP"
    if ma_regime == "DOWN":
        return "DOWN"
    return "NEUTRAL"


def get_regime(composite_buy: float, up_min: float = 60, down_max: float = 40) -> str:
    """
    UP: composite_buy >= up_min
    DOWN: composite_buy <= down_max
    else NEUTRAL
    """
    if composite_buy >= up_min:
        return "UP"
    if composite_buy <= down_max:
        return "DOWN"
    return "NEUTRAL"


def get_score_label(score: float, market_regime: str | None) -> str:
    """
    Regime-aware interpretation of score buckets.
    BULL/STRONG_BULL: high scores = opportunities. BEAR/STRONG_BEAR/NEUTRAL: high scores = extended / mean-reversion risk.
    """
    is_bull = market_regime in ("BULL", "STRONG_BULL")
    if is_bull:
        if score >= 70:
            return "Strong opportunity"
        if score >= 50:
            return "Moderate opportunity"
        if score >= 30:
            return "Neutral / watchlist"
        return "Weak / avoid"
    # BEAR, STRONG_BEAR or NEUTRAL
    if score >= 70:
        return "Extended / high risk of pullback"
    if score >= 50:
        return "Neutral"
    if score >= 30:
        return "Mildly defensive"
    return "Oversold / speculative bounce"


def get_signal(composite_buy: float, buy_min: float = 70, sell_max: float = 30) -> str:
    """BUY / HOLD / SELL from composite and bands."""
    if composite_buy >= buy_min:
        return "BUY"
    if composite_buy <= sell_max:
        return "SELL"
    return "HOLD"


def resolve_ml_prob_thresholds(score_cfg: dict | None) -> tuple[float, float, float]:
    """Config aliases strong_buy_ml / buy_ml / avoid_ml override ml_*_prob."""
    sc = score_cfg or {}
    return (
        float(sc.get("strong_buy_ml", sc.get("ml_strong_buy_prob", 0.55))),
        float(sc.get("buy_ml", sc.get("ml_buy_prob", 0.40))),
        float(sc.get("avoid_ml", sc.get("ml_avoid_max_prob", 0.20))),
    )


def get_ml_aware_signal(
    confluence: float,
    ml_short_prob: float | None = None,
    buy_min: float = 65,
    sell_max: float = 35,
    ml_strong_buy_confluence: float = 72.0,
    ml_strong_buy_prob: float = 0.55,
    ml_buy_prob: float = 0.40,
    ml_avoid_max_prob: float = 0.20,
    interpretation_style: str = "TRENDING",
) -> str:
    """
    Multi-layer signal that requires BOTH technical (confluence) AND ML to agree
    before emitting BUY. Falls back to confluence-only when ML not yet trained.

    Tiers (when ML available, thresholds from config or defaults):
      STRONG BUY — confluence ≥ ml_strong_buy_confluence AND ML ≥ ml_strong_buy_prob
      BUY        — confluence ≥ buy_min AND ML ≥ ml_buy_prob
      WATCH      — confluence ≥ buy_min but ML < ml_buy_prob (technical good, ML cautious)
      HOLD       — neither extreme
      REDUCE     — confluence ≤ sell_max OR ML < ml_avoid_max_prob
      AVOID      — confluence ≤ sell_max AND ML < ml_avoid_max_prob

    Without ML: falls back to BUY/HOLD/SELL from confluence only.

    interpretation_style MEAN_REVERTING: use (100 - confluence) for threshold routing only —
    raw score in API unchanged; low momentum score maps to "buy the fear" path.
    """
    c = float(confluence)
    if interpretation_style == "MEAN_REVERTING":
        c = 100.0 - c

    if ml_short_prob is not None:
        if c >= ml_strong_buy_confluence and ml_short_prob >= ml_strong_buy_prob:
            return "STRONG BUY"
        if c >= buy_min and ml_short_prob >= ml_buy_prob:
            return "BUY"
        if c >= buy_min and ml_short_prob < ml_buy_prob:
            return "WATCH"
        if c <= sell_max and ml_short_prob < ml_avoid_max_prob:
            return "AVOID"
        if c <= sell_max or ml_short_prob < ml_avoid_max_prob:
            return "REDUCE"
        return "HOLD"

    # ── Fallback: confluence-only (no ML model yet) ───────────────────────
    if c >= 70:
        return "BUY"
    if c >= buy_min:
        return "BUY"
    if c <= sell_max:
        return "SELL"
    return "HOLD"
