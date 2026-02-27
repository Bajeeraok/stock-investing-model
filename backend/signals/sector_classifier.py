"""
Sector-aware classification for composite score weight tuning.

What predicts a GLD bottom is fundamentally different from TSLA:
  - momentum_growth (NVDA, TSLA, QQQ):  trend + MACD momentum; RSI can stay elevated long
  - safe_haven      (GLD, SLV, TLT):    RSI oversold is the dominant buy signal; MA stacks unreliable
  - broad_market    (SPY, IWM, large-cap blend): balanced; global regime matters most
  - cyclical        (XLE, XLF, energy): trend confirmation critical; RSI oversold = value trap

classify_ticker() uses beta vs SPY + GLD correlation (dynamic), with a hardcoded fast-path
for known tickers. get_sector_weights() returns composite_score weight overrides.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Known-ticker fast path (avoids fetching SPY/GLD just to classify common names)
# ---------------------------------------------------------------------------
_KNOWN_SECTORS: dict[str, str] = {
    # momentum_growth: high-beta, momentum/tech-driven
    "NVDA": "momentum_growth", "TSLA": "momentum_growth", "AMD": "momentum_growth",
    "META": "momentum_growth", "SHOP": "momentum_growth", "CRWD": "momentum_growth",
    "PANW": "momentum_growth", "MRVL": "momentum_growth", "AVGO": "momentum_growth",
    "NFLX": "momentum_growth", "CRSP": "momentum_growth", "ASAN": "momentum_growth",
    "TTD": "momentum_growth",  "PLTR": "momentum_growth", "SE":   "momentum_growth",
    "BABA": "momentum_growth", "CRWV": "momentum_growth",
    # safe_haven: gold, silver, bonds, utilities
    "GLD": "safe_haven", "SLV": "safe_haven", "IAU": "safe_haven",
    "TLT": "safe_haven", "IEF": "safe_haven", "BND": "safe_haven",
    "XLU": "safe_haven", "XLP": "safe_haven", "VNQ": "safe_haven",
    # broad_market: index ETFs and large-cap blend
    "SPY": "broad_market", "QQQ": "broad_market", "IWM": "broad_market",
    "DIA": "broad_market", "VOO": "broad_market", "VTI": "broad_market",
    "AAPL": "broad_market", "MSFT": "broad_market", "GOOGL": "broad_market",
    "AMZN": "broad_market", "LLY":  "broad_market", "ABBV": "broad_market",
    "COST": "broad_market", "WMT":  "broad_market", "UNH":  "broad_market",
    "CRM":  "broad_market", "INTC": "broad_market", "QCOM": "broad_market",
    # cyclical: energy, financials, industrials — regime & trend confirmation critical
    "XLE": "cyclical", "XLF": "cyclical", "XLI": "cyclical", "XLB": "cyclical",
    "OIH": "cyclical", "HAL": "cyclical",
    "JPM": "cyclical", "BLK": "cyclical", "V":   "cyclical", "MA":  "cyclical",
}

# ---------------------------------------------------------------------------
# Weight profiles — must sum to 1.0 (trend + rsi + macd)
# Passed directly to composite_score(weights=...)
# ---------------------------------------------------------------------------
SECTOR_WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    # Momentum stocks trend hard; MACD crossovers are meaningful entry signals.
    # RSI stays overbought 70+ for months during runs → downweight it.
    "momentum_growth": {"trend": 0.60, "rsi": 0.15, "macd": 0.25},

    # Safe havens mean-revert; RSI oversold < 30 is the strongest buy signal.
    # MA stacks are less useful (GLD trends against equities unpredictably).
    "safe_haven":      {"trend": 0.30, "rsi": 0.55, "macd": 0.15},

    # Index ETFs: balanced default, regime overlay handles the rest.
    "broad_market":    {"trend": 0.50, "rsi": 0.30, "macd": 0.20},

    # Cyclicals need confirmed trend breakouts; RSI oversold in downtrends = value trap.
    # MACD divergence is a useful early rotation signal.
    "cyclical":        {"trend": 0.55, "rsi": 0.20, "macd": 0.25},
}

# Additive score bias after computing composite (keeps scale 0-100).
# Cyclicals: harder hurdle (-5) → fewer but higher-conviction signals.
# Safe havens: slight boost (+3) → RSI oversold signals tend to be reliable.
SECTOR_SCORE_BIAS: dict[str, float] = {
    "momentum_growth": 0.0,
    "safe_haven":      +3.0,
    "broad_market":    0.0,
    "cyclical":        -5.0,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_ticker(
    ticker: str,
    close: pd.Series | None = None,
    spy_close: pd.Series | None = None,
    gld_close: pd.Series | None = None,
) -> str:
    """
    Return sector cluster for ticker: 'momentum_growth' | 'safe_haven' | 'broad_market' | 'cyclical'.

    Fast path: checks _KNOWN_SECTORS first (no data needed).
    Dynamic path: computes 1y beta vs SPY and 1y correlation vs GLD from provided series.
    Fallback: 'broad_market'.
    """
    upper = ticker.upper().split(".")[0]
    if upper in _KNOWN_SECTORS:
        return _KNOWN_SECTORS[upper]

    if close is not None and len(close) >= 126:
        beta = _compute_beta(close, spy_close)
        corr_gld = _compute_correlation(close, gld_close)
        return _classify_from_stats(beta, corr_gld)

    return "broad_market"


def get_sector_weights(
    ticker: str,
    close: pd.Series | None = None,
    spy_close: pd.Series | None = None,
    gld_close: pd.Series | None = None,
) -> dict[str, float]:
    """Return composite_score weight dict for the ticker's sector cluster."""
    sector = classify_ticker(ticker, close, spy_close, gld_close)
    return SECTOR_WEIGHT_PROFILES[sector].copy()


def get_sector_score_bias(ticker: str) -> float:
    """Additive post-score adjustment for the ticker's sector."""
    sector = _KNOWN_SECTORS.get(ticker.upper().split(".")[0], "broad_market")
    return SECTOR_SCORE_BIAS.get(sector, 0.0)


def sector_aware_composite_score(
    close: pd.Series,
    ticker: str,
    spy_close: pd.Series | None = None,
    gld_close: pd.Series | None = None,
    use_spec: bool = False,
    config: dict | None = None,
) -> dict:
    """
    Compute composite score using sector-appropriate weights.

    Wraps composite_score() selecting weights via classify_ticker().
    Adds 'sector' key to result so callers can see which profile was used.
    """
    from signals.indicators import composite_score

    sector = classify_ticker(ticker, close, spy_close, gld_close)
    weights = SECTOR_WEIGHT_PROFILES[sector]
    bias = SECTOR_SCORE_BIAS.get(sector, 0.0)

    result = composite_score(
        close, weights=weights, use_spec=use_spec, ticker=ticker, config=config
    )
    if "composite_buy" in result:
        adjusted = float(np.clip(result["composite_buy"] + bias, 0.0, 100.0))
        result = {**result, "composite_buy": round(adjusted, 1), "sector": sector}
    return result


def describe_sector(ticker: str) -> str:
    """Human-readable label for why a ticker's sector was chosen."""
    sector = _KNOWN_SECTORS.get(ticker.upper().split(".")[0], "broad_market")
    labels = {
        "momentum_growth": "Momentum/Growth (trend + MACD dominant; RSI less reliable)",
        "safe_haven":      "Safe Haven (RSI oversold dominant; MA stacks less reliable)",
        "broad_market":    "Broad Market (balanced weights; regime overlay key)",
        "cyclical":        "Cyclical (trend confirmation critical; RSI oversold = caution)",
    }
    return labels.get(sector, sector)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_from_stats(beta: float | None, corr_gld: float | None) -> str:
    if corr_gld is not None and corr_gld > 0.5:
        return "safe_haven"
    if beta is not None and beta < 0.5:
        return "safe_haven"
    if beta is not None and beta > 1.4:
        return "momentum_growth"
    if beta is not None and 0.7 <= beta <= 1.4:
        if corr_gld is not None and corr_gld < 0.1:
            return "cyclical"
    return "broad_market"


def _compute_beta(asset: pd.Series, benchmark: pd.Series | None) -> float | None:
    """1-year beta of asset vs benchmark using daily returns."""
    if benchmark is None or len(asset) < 63 or len(benchmark) < 63:
        return None
    aligned = pd.concat(
        [asset.rename("asset"), benchmark.rename("bm")], axis=1
    ).dropna()
    if len(aligned) < 63:
        return None
    rets = aligned.pct_change().dropna().tail(252)
    if len(rets) < 30:
        return None
    cov = rets["asset"].cov(rets["bm"])
    var = rets["bm"].var()
    return float(cov / var) if var != 0 else None


def _compute_correlation(asset: pd.Series, reference: pd.Series | None) -> float | None:
    """1-year correlation of daily returns between asset and reference."""
    if reference is None or len(asset) < 63 or len(reference) < 63:
        return None
    aligned = pd.concat(
        [asset.rename("asset"), reference.rename("ref")], axis=1
    ).dropna()
    if len(aligned) < 63:
        return None
    rets = aligned.pct_change().dropna().tail(252)
    if len(rets) < 30:
        return None
    return float(rets["asset"].corr(rets["ref"]))
