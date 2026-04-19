"""
signals/hmm_macro_features.py — optional rich HMM feature builder (macro-augmented).

PROBLEM:
    SPY HMM shows Bull 84% during a confirmed market downturn because
    the HMM is trained only on price returns. Price is still above MA200
    so the model reads Bull, ignoring macro deterioration.

FIX:
    Augment HMM observation matrix with macro features:
        - VIX level + VIX change (fear gauge)
        - 10-2 yield spread (recession signal)
        - SPY breadth: % stocks above MA200 (participation)
        - Put/call ratio 5d moving average (hedging demand)
        - Price vs MA200 gap % (already implicit, now explicit)

    For non-SPY tickers: beta-adjusted macro context is added
    but weighted lower than for SPY/QQQ.

INTEGRATION:
    Replace your current feature construction in hmm_regime.py or
    wherever you build the observation matrix for hmmlearn.
    Drop-in: call build_hmm_features(ticker, price_df) to get the
    augmented feature matrix instead of just return-based features.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ── Asset classification ───────────────────────────────────────────────────
BROAD_MARKET_ETFS  = {"SPY", "QQQ", "IWM", "DIA", "VTI", "VOO"}
SECTOR_ETFS        = {"XLK", "XLF", "XLE", "XLV", "XLI", "XLC", "XLY", "XLP"}
COMMODITY_ETFS     = {"GLD", "SLV", "USO", "GDX"}
BOND_ETFS          = {"TLT", "IEF", "HYG", "LQD", "AGG"}

# ── Feature weights by asset type ──────────────────────────────────────────
# Controls how much macro features influence the HMM vs price features
MACRO_WEIGHT = {
    "broad_market": 0.50,   # SPY — macro IS the signal
    "sector_etf":   0.35,   # sector ETFs — macro matters a lot
    "individual":   0.20,   # individual stocks — macro is context
    "commodity":    0.15,   # commodities — their own macro
    "bond":         0.25,   # bonds — rate-sensitive
}


def get_asset_type(ticker: str) -> str:
    t = ticker.upper()
    if t in BROAD_MARKET_ETFS:  return "broad_market"
    if t in SECTOR_ETFS:        return "sector_etf"
    if t in COMMODITY_ETFS:     return "commodity"
    if t in BOND_ETFS:          return "bond"
    return "individual"


def build_hmm_features(
    ticker: str,
    price_df: pd.DataFrame,
    include_macro: bool = True,
    lookback_days: int = 252,
) -> tuple[np.ndarray, list[str]]:
    """
    Build augmented HMM observation matrix for a ticker.

    Parameters
    ----------
    ticker      : str — e.g. "SPY", "NVDA"
    price_df    : pd.DataFrame with columns:
                  Close, Volume (required)
                  VIX, Yield10, Yield2, BreadthMA200, PCRatio (optional)
                  If macro columns missing, fetched from yfinance.
    include_macro : bool — set False to use price-only (legacy behavior)
    lookback_days : int — rows to use

    Returns
    -------
    (feature_matrix, feature_names)
    feature_matrix : np.ndarray shape (T, n_features) — ready for hmmlearn
    feature_names  : list[str] — for interpretability
    """
    df = price_df.copy().tail(lookback_days)
    if "Close" not in df.columns and "close" in df.columns:
        df = df.rename(columns={"close": "Close"})
    if "Volume" not in df.columns and "volume" in df.columns:
        df = df.rename(columns={"volume": "Volume"})
    if "Close" not in df.columns:
        raise ValueError("price_df must include Close or close")
    asset_type = get_asset_type(ticker)
    macro_w = MACRO_WEIGHT.get(asset_type, 0.20)

    features = {}

    # ── Core price features (always included) ─────────────────────────────
    close = df["Close"].astype(float)
    ret   = close.pct_change().fillna(0)

    # 1-day return
    features["ret_1d"] = ret

    # 5-day rolling return (weekly momentum)
    features["ret_5d"] = close.pct_change(5).fillna(0)

    # 20-day rolling return (monthly momentum)
    features["ret_20d"] = close.pct_change(20).fillna(0)

    # Realized volatility (20d annualized)
    features["vol_20d"] = ret.rolling(20).std().fillna(ret.std()) * np.sqrt(252)

    # Vol regime: vol_20d / vol_60d — detects vol expansion
    vol_60d = ret.rolling(60).std().fillna(ret.std()) * np.sqrt(252)
    features["vol_ratio"] = (features["vol_20d"] / vol_60d.replace(0, np.nan)).fillna(1.0)

    # Price vs MA200 gap
    ma200 = close.rolling(200, min_periods=50).mean()
    features["ma200_gap"] = ((close - ma200) / ma200.replace(0, np.nan)).fillna(0)

    # Price vs MA50 gap
    ma50 = close.rolling(50, min_periods=20).mean()
    features["ma50_gap"] = ((close - ma50) / ma50.replace(0, np.nan)).fillna(0)

    # Volume z-score (unusual volume = regime change signal)
    if "Volume" in df.columns:
        vol_mean = df["Volume"].rolling(20).mean()
        vol_std  = df["Volume"].rolling(20).std().replace(0, 1)
        features["volume_z"] = ((df["Volume"] - vol_mean) / vol_std).fillna(0)
    else:
        features["volume_z"] = pd.Series(0.0, index=df.index)

    if not include_macro or macro_w == 0:
        return _assemble(features, df.index), list(features.keys())

    # ── Macro features ────────────────────────────────────────────────────
    macro = _get_macro_features(df, ticker)

    # VIX level normalized (VIX > 20 = elevated, > 30 = fear)
    if "VIX" in macro:
        vix = macro["VIX"].reindex(df.index).ffill().fillna(20.0)
        features["vix_norm"]   = (vix / 30.0).clip(0, 2)       # normalized to fear threshold
        features["vix_chg_5d"] = vix.pct_change(5).fillna(0)   # VIX momentum

    # Yield curve slope (10y - 2y): inversion = recession risk
    if "Yield10" in macro and "Yield2" in macro:
        y10 = macro["Yield10"].reindex(df.index).ffill().fillna(4.0)
        y2  = macro["Yield2"].reindex(df.index).ffill().fillna(4.0)
        features["yield_slope"] = (y10 - y2) / 3.0   # normalize: ±3% is typical range

    # Breadth: % SPY stocks above MA200 (only meaningful for broad market)
    if "BreadthMA200" in macro and asset_type in ("broad_market", "sector_etf"):
        breadth = macro["BreadthMA200"].reindex(df.index).ffill().fillna(0.5)
        features["breadth"] = breadth   # already 0-1

    # Put/call ratio 5d MA: elevated = fear = potential contrarian buy
    if "PCRatio" in macro:
        pcr = macro["PCRatio"].reindex(df.index).ffill().fillna(1.0)
        features["pcr_5d_ma"] = pcr.rolling(5).mean().fillna(pcr)

    # ── Weight macro features by asset type ───────────────────────────────
    # Macro features get multiplied by macro_w so they don't dominate
    # price features for individual stocks but are significant for SPY
    macro_keys = ["vix_norm", "vix_chg_5d", "yield_slope", "breadth", "pcr_5d_ma"]
    for key in macro_keys:
        if key in features:
            features[key] = features[key] * macro_w * 2  # scale to similar range as price features

    return _assemble(features, df.index), list(features.keys())


def _assemble(features: dict, index: pd.Index) -> np.ndarray:
    """Stack features into observation matrix, handle NaN."""
    df = pd.DataFrame(features, index=index)
    df = df.ffill().fillna(0)
    arr = df.values.astype(float)
    # Clip extreme values to prevent HMM instability
    arr = np.clip(arr, -5, 5)
    return arr


def _get_macro_features(df: pd.DataFrame, ticker: str) -> dict:
    """
    Fetch or extract macro features.
    First checks if columns already exist in df (caller pre-fetched).
    Falls back to yfinance download for missing ones.
    """
    macro = {}
    start = df.index[0]
    end   = df.index[-1]

    # Use pre-fetched if available
    for col in ["VIX", "Yield10", "Yield2", "BreadthMA200", "PCRatio"]:
        if col in df.columns:
            macro[col] = df[col]

    # Fetch missing from yfinance
    missing = [c for c in ["VIX", "Yield10", "Yield2"] if c not in macro]
    if missing:
        try:
            import yfinance as yf
            import logging as _log
            _log.getLogger("yfinance").setLevel(_log.CRITICAL)

            symbol_map = {
                "VIX":     "^VIX",
                "Yield10": "^TNX",
                "Yield2":  "^IRX",  # 13-week proxy; use ^UST2Y if available
            }
            for key in missing:
                sym = symbol_map[key]
                try:
                    data = yf.download(
                        sym, start=start, end=end,
                        progress=False, auto_adjust=True, threads=False
                    )
                    if data is not None and len(data) > 10:
                        close_col = data["Close"] if "Close" in data else data.iloc[:, 0]
                        macro[key] = close_col.squeeze()
                        logger.debug(f"Fetched {key} ({sym}): {len(macro[key])} rows")
                except Exception as e:
                    logger.warning(f"Could not fetch {key}: {e}")
        except ImportError:
            logger.warning("yfinance not available for macro feature fetch")

    # BreadthMA200: approximate from SPY internals if not provided
    # True breadth requires constituent data (expensive). Use VIX proxy instead:
    # breadth ≈ 1 - (VIX - 12) / (80 - 12) clipped to [0,1]
    if "BreadthMA200" not in macro and "VIX" in macro:
        vix = macro["VIX"]
        macro["BreadthMA200"] = (1.0 - (vix - 12) / 68).clip(0, 1)
        logger.debug("BreadthMA200 approximated from VIX")

    return macro


# ── Convenience: drop-in replacement for legacy feature builder ───────────

def build_legacy_features(price_df: pd.DataFrame) -> np.ndarray:
    """
    Legacy price-only features for backward compatibility.
    Matches what the original HMM was trained on.
    """
    df = price_df.copy()
    close = df["Close"].astype(float)
    ret   = close.pct_change().fillna(0)
    vol   = ret.rolling(20).std().fillna(ret.std()) * np.sqrt(252)
    return np.column_stack([ret.values, vol.values])


# ── SPY-specific feature builder ──────────────────────────────────────────

def build_spy_features(
    spy_df: pd.DataFrame,
    lookback_days: int = 504,  # 2 years for better regime coverage
) -> tuple[np.ndarray, list[str]]:
    """
    SPY-specific feature set optimized for broad market regime detection.
    Always includes macro; uses longer lookback for regime stability.
    """
    return build_hmm_features(
        ticker="SPY",
        price_df=spy_df,
        include_macro=True,
        lookback_days=lookback_days,
    )
