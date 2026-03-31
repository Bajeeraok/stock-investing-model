"""~21 trading-day hit-rate gate on a simple daily proxy signal (replace with model score in prod)."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .intraday import YF_AVAILABLE

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None


class ShortTermBacktester:
    def __init__(self, min_hit_rate_1m: float = 0.65):
        self._min_hit = min_hit_rate_1m

    def _fetch_daily(self, ticker: str, years: int = 2) -> pd.DataFrame:
        if not YF_AVAILABLE or yf is None:
            return pd.DataFrame()
        try:
            t = yf.Ticker(ticker)
            df = t.history(period=f"{years}y", interval="1d")
            df.index = pd.to_datetime(df.index)
            return df
        except Exception as e:
            logger.warning("Backtest data fetch error: %s", e)
            return pd.DataFrame()

    def _compute_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["Close"]
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        ma_score = ((close - ma50) / ma50 * 100).clip(0, 40)
        rsi_score = rsi * 0.60
        return (ma_score + rsi_score).clip(0, 100)

    def _compute_atr_series(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["High"]
        low = df["Low"]
        close = df["Close"].shift(1)
        tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def run(
        self,
        ticker: str,
        years: int = 2,
        score_thresh: float = 70.0,
        horizon_days: int = 21,
    ) -> dict:
        df = self._fetch_daily(ticker, years)
        if df.empty or len(df) < 100:
            return {
                "ticker": ticker,
                "trusted": False,
                "reason": "Insufficient data",
                "hit_rate": None,
                "mean_return": None,
                "n_signals": 0,
            }

        signals = self._compute_signals(df)
        atr = self._compute_atr_series(df)
        close = df["Close"]

        results = []
        for i in range(len(df) - horizon_days - 1):
            score = signals.iloc[i]
            if score < score_thresh:
                continue
            entry = close.iloc[i]
            future = close.iloc[i + horizon_days]
            atr_val = atr.iloc[i]
            if pd.isna(atr_val) or atr_val <= 0:
                continue
            stop = entry - (atr_val * 1.5)
            window = close.iloc[i + 1 : i + horizon_days]
            hit_stop = bool((window < stop).any()) if len(window) else False

            if hit_stop:
                ret = (stop - entry) / entry
                hit = False
            else:
                ret = (future - entry) / entry
                hit = ret > 0

            results.append(
                {
                    "date": df.index[i],
                    "entry": entry,
                    "exit": future if not hit_stop else stop,
                    "return": ret,
                    "hit": hit,
                }
            )

        if not results:
            return {
                "ticker": ticker,
                "trusted": False,
                "reason": "No signals generated in period",
                "hit_rate": None,
                "mean_return": None,
                "n_signals": 0,
            }

        res_df = pd.DataFrame(results)
        hit_rate = float(res_df["hit"].mean())
        mean_ret = float(res_df["return"].mean())
        n = len(res_df)
        trusted = hit_rate >= self._min_hit and n >= 20

        res_df["year"] = pd.to_datetime(res_df["date"]).dt.year
        yearly = res_df.groupby("year").agg(
            hit_rate=("hit", "mean"),
            mean_return=("return", "mean"),
            n=("hit", "count"),
        ).round(4)

        return {
            "ticker": ticker,
            "trusted": trusted,
            "hit_rate": round(hit_rate, 4),
            "mean_return": round(mean_ret, 4),
            "n_signals": n,
            "min_required_hit_rate": self._min_hit,
            "yearly_breakdown": yearly.to_dict(orient="index"),
            "reason": (
                f"Hit rate {hit_rate:.1%} {'≥' if trusted else '<'} "
                f"threshold {self._min_hit:.0%} — "
                f"{'TRUSTED' if trusted else 'NOT TRUSTED'}"
            ),
        }
