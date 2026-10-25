"""
Cross-sectional feature panel for the pooled alpha model.

Every feature uses data up to and including the bar (no look-ahead). Features are
relative where possible — vs the benchmark, vs the sector ETF, and ranked across the
universe each day — so the model learns which stocks beat the market, not whether the
market went up.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from signals.alpha.labels import atr

SECTOR_ETF = {
    "Information Technology": "XLK",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

RANK_COLS = ("ret_20", "ret_60", "mom_12_1", "rel_ret_60", "vol_60", "dist_ma200", "rsi_14")


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def ticker_features(
    df: pd.DataFrame,
    bench_close: pd.Series,
    sector_close: pd.Series | None = None,
) -> pd.DataFrame:
    """Per-ticker features. ``df`` needs close/high/low/volume columns (lower-case)."""
    close = df["close"].astype(float)
    high = df.get("high", close).astype(float)
    low = df.get("low", close).astype(float)
    vol = df.get("volume", pd.Series(np.nan, index=df.index)).astype(float)
    b = bench_close.reindex(close.index).ffill()
    r1 = close.pct_change()
    b1 = b.pct_change()

    out = pd.DataFrame(index=close.index)
    for n in (5, 20, 60, 120):
        out[f"ret_{n}"] = close.pct_change(n)
    out["mom_12_1"] = close.shift(21) / close.shift(252) - 1
    out["rel_ret_20"] = out["ret_20"] - b.pct_change(20)
    out["rel_ret_60"] = out["ret_60"] - b.pct_change(60)
    out["rel_ret_120"] = out["ret_120"] - b.pct_change(120)
    if sector_close is not None:
        s = sector_close.reindex(close.index).ffill()
        out["sector_rel_20"] = out["ret_20"] - s.pct_change(20)
        out["sector_rel_60"] = out["ret_60"] - s.pct_change(60)
    out["vol_20"] = r1.rolling(20, min_periods=15).std() * np.sqrt(252)
    out["vol_60"] = r1.rolling(60, min_periods=40).std() * np.sqrt(252)
    out["vol_ratio"] = out["vol_20"] / out["vol_60"].replace(0, np.nan)
    out["atr_pct"] = atr(high, low, close) / close
    ma50 = close.rolling(50, min_periods=40).mean()
    ma200 = close.rolling(200, min_periods=150).mean()
    out["dist_ma50"] = close / ma50 - 1
    out["dist_ma200"] = close / ma200 - 1
    out["rsi_14"] = _rsi(close)
    out["drawdown_252"] = close / close.rolling(252, min_periods=120).max() - 1
    cov = r1.rolling(120, min_periods=80).cov(b1)
    out["beta_120"] = cov / b1.rolling(120, min_periods=80).var()
    out["resid_vol_60"] = (r1 - out["beta_120"] * b1).rolling(60, min_periods=40).std() * np.sqrt(252)
    lv = np.log1p(vol)
    out["volume_z_20"] = (lv - lv.rolling(20, min_periods=15).mean()) / lv.rolling(20, min_periods=15).std()
    out["log_dollar_vol_20"] = np.log1p((close * vol).rolling(20, min_periods=15).mean())
    return out.replace([np.inf, -np.inf], np.nan)


def market_features(bench: pd.DataFrame) -> pd.DataFrame:
    c = bench["close"].astype(float)
    r = c.pct_change()
    out = pd.DataFrame(index=c.index)
    out["mkt_ret_20"] = c.pct_change(20)
    out["mkt_dist_ma200"] = c / c.rolling(200, min_periods=150).mean() - 1
    out["mkt_vol_20"] = r.rolling(20, min_periods=15).std() * np.sqrt(252)
    out["mkt_drawdown_252"] = c / c.rolling(252, min_periods=120).max() - 1
    return out


def add_cross_sectional_ranks(panel: pd.DataFrame, cols=RANK_COLS) -> pd.DataFrame:
    """Percentile rank of each feature across tickers on the same date (0..1)."""
    g = panel.groupby(level="date")
    for c in cols:
        if c in panel.columns:
            panel[f"xs_rank_{c}"] = g[c].rank(pct=True)
    return panel


def build_panel(
    ohlcv: dict[str, pd.DataFrame],
    *,
    benchmark: str = "SPY",
    sector_of: dict[str, str] | None = None,
    extra_label_fn=None,
) -> pd.DataFrame:
    """
    Long panel indexed by (date, ticker). ``extra_label_fn(ticker, df, bench_close)`` may
    return a DataFrame of label columns aligned to df.index to join (kept out of features).
    """
    bench = ohlcv[benchmark]
    bclose = bench["close"].astype(float)
    mkt = market_features(bench)
    frames = []
    for tk, df in ohlcv.items():
        if tk == benchmark or tk in SECTOR_ETF.values() or df is None or len(df) < 260:
            continue
        etf = SECTOR_ETF.get((sector_of or {}).get(tk, ""))
        sclose = ohlcv[etf]["close"] if etf and etf in ohlcv else None
        f = ticker_features(df, bclose, sclose).join(mkt, how="left")
        if extra_label_fn is not None:
            f = f.join(extra_label_fn(tk, df, bclose), how="left")
        f["ticker"] = tk
        f.index.name = "date"
        frames.append(f.reset_index())
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True).set_index(["date", "ticker"]).sort_index()
    return add_cross_sectional_ranks(panel)
