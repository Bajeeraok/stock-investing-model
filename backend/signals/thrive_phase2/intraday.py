"""Intraday OHLCV via yfinance (1h / 15m)."""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .models import IntradayData

logger = logging.getLogger(__name__)

try:
    import yfinance as yf

    YF_AVAILABLE = True
except ImportError:
    yf = None
    YF_AVAILABLE = False


class IntradayFeed:
    """Pull intraday bars, compute ATR, VWAP, RSI, volume ratio, S/R."""

    def _compute_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        high = df["High"]
        low = df["Low"]
        close = df["Close"].shift(1)
        tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])

    def _compute_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        delta = df["Close"].diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])

    def _compute_vwap(self, df: pd.DataFrame) -> float:
        typical = (df["High"] + df["Low"] + df["Close"]) / 3
        vwap = (typical * df["Volume"]).cumsum() / df["Volume"].cumsum()
        return float(vwap.iloc[-1])

    def _compute_support_resistance(self, df: pd.DataFrame, lookback: int = 20) -> tuple[float, float]:
        recent = df.tail(lookback)
        resistance = float(recent["High"].max())
        support = float(recent["Low"].min())
        return support, resistance

    def fetch(
        self,
        ticker: str,
        interval: str = "1h",
        days: int = 5,
    ) -> Optional[IntradayData]:
        if not YF_AVAILABLE:
            logger.warning("yfinance not installed — intraday feed disabled")
            return None

        try:
            t = yf.Ticker(ticker)
            df = t.history(period=f"{days}d", interval=interval)

            if df.empty or len(df) < 20:
                logger.warning("Insufficient intraday data for %s", ticker)
                return None

            df.index = pd.to_datetime(df.index)

            atr = self._compute_atr(df)
            rsi = self._compute_rsi(df)
            vwap = self._compute_vwap(df)
            support, resistance = self._compute_support_resistance(df)
            ma20 = float(df["Close"].rolling(20).mean().iloc[-1])
            ma50_val = df["Close"].rolling(50).mean().iloc[-1]
            ma50 = float(ma50_val) if not np.isnan(ma50_val) else ma20
            current = float(df["Close"].iloc[-1])
            avg_vol = float(df["Volume"].rolling(20).mean().iloc[-1])
            curr_vol = float(df["Volume"].iloc[-1])
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

            return IntradayData(
                ticker=ticker,
                interval=interval,
                df=df,
                current_price=current,
                atr=atr,
                vwap=vwap,
                ma20=ma20,
                ma50=ma50,
                rsi=rsi,
                volume_ratio=vol_ratio,
                resistance=resistance,
                support=support,
            )
        except Exception as e:
            logger.warning("Intraday fetch error [%s]: %s", ticker, e)
            return None
