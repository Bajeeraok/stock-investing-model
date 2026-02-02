"""
2026 best tickers: forward-looking picks with confidence score.
Seeds from LT score, regime UP, sector strength; daily absorption via EOD.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config
from signals.fetcher import fetch_ohlcv_safe
from signals.indicators import multi_horizon_scores
from signals.regime import get_regime
from signals.providers import get_sector_and_industry


def get_best_picks_2026(config: dict, max_results: int = 20) -> list[dict]:
    """
    Rank tickers by LT score + regime + confidence. Exclude earnings within 2 weeks.
    Returns [{ticker, score, regime, confidence, reason}].
    """
    from signals.providers import get_next_earnings

    watchlist = config.get("watchlist", [])
    universe = config.get("opportunity_universe") or []
    tickers = list(dict.fromkeys([t.upper() for t in watchlist + universe]))[:80]

    up_min = config.get("regime", {}).get("up_min", 60)
    down_max = config.get("regime", {}).get("down_max", 40)
    period = config.get("data", {}).get("period", "2y") or "2y"

    picks = []
    for ticker in tickers:
        close = fetch_ohlcv_safe(ticker, period)
        if close is None or len(close) < 200:
            continue
        try:
            sig = multi_horizon_scores(close)
        except Exception:
            continue

        score = sig.get("composite_buy")
        regime = get_regime(score or 50, up_min, down_max)

        # Exclude earnings within 14 days
        earnings = get_next_earnings(ticker, config)
        if earnings and earnings.get("days_until") is not None:
            if 0 <= earnings["days_until"] <= 14:
                continue

        # Confidence: higher when regime UP, score stable, sector strong
        confidence = 50.0
        if regime == "UP":
            confidence += 15
        elif regime == "DOWN":
            confidence -= 20
        if score is not None:
            if score >= 70:
                confidence += 15
            elif score >= 55:
                confidence += 5
            elif score < 40:
                confidence -= 15
        # Sector strength (simplified: tech = +5)
        try:
            info = get_sector_and_industry(ticker) or {}
            sector = (info.get("sector") or "").lower()
            if "tech" in sector or "technology" in sector:
                confidence += 5
        except Exception:
            pass
        confidence = max(0, min(100, round(confidence, 1)))

        reason_parts = []
        if regime == "UP":
            reason_parts.append("regime UP")
        if score and score >= 70:
            reason_parts.append(f"score {score:.0f}")
        reason = "; ".join(reason_parts) or "momentum"

        picks.append({
            "ticker": ticker,
            "score": round(score, 1) if score is not None else None,
            "regime": regime,
            "confidence": confidence,
            "reason": reason,
            "close": sig.get("close"),
        })

    # Sort by confidence * (score/100), filter regime DOWN low
    def sort_key(p):
        s = p.get("score") or 50
        c = p.get("confidence") or 50
        return (c / 100) * (s / 100)

    picks.sort(key=sort_key, reverse=True)
    return picks[:max_results]
