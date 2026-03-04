from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger("scanner.yahoo")


def _safe_float(x, default: float | None = None) -> float | None:
    try:
        f = float(x)
        if math.isnan(f):
            return default
        return f
    except Exception:
        return default


class _BatchCache:
    def __init__(self, ttl_sec: int):
        self.ttl = ttl_sec
        self.ts = 0.0
        self.value = None

    def get(self):
        if self.value is not None and (time.time() - self.ts) < self.ttl:
            return self.value
        return None

    def set(self, v):
        self.value = v
        self.ts = time.time()


class IVRankCache:
    """
    Daily cache of realized-vol proxy (21d rolling) per symbol, computed from 1y closes.
    Uses current ATM IV (percent) against the RV range for IV Rank.
    """

    def __init__(self):
        self._rv_by_symbol: dict[str, pd.Series] = {}
        self._fetched_at: float = 0.0
        self._ttl_sec: int = 24 * 3600

    def refresh(self, symbols: list[str]) -> None:
        if (time.time() - self._fetched_at) < self._ttl_sec and self._rv_by_symbol:
            return
        try:
            import yfinance as yf
            df = yf.download(
                tickers=" ".join(symbols),
                period="1y",
                interval="1d",
                progress=False,
                threads=True,
                auto_adjust=True,
                group_by="ticker",
            )
            rv_by: dict[str, pd.Series] = {}
            for sym in symbols:
                try:
                    c = None
                    if isinstance(df.columns, pd.MultiIndex):
                        if (sym, "Close") in df.columns:
                            c = df[(sym, "Close")]
                    else:
                        if "Close" in df.columns and len(symbols) == 1:
                            c = df["Close"]
                    if c is None:
                        continue
                    c = c.dropna()
                    if len(c) < 30:
                        continue
                    rets = c.pct_change().dropna()
                    rv = rets.rolling(window=21).std() * math.sqrt(252) * 100.0
                    rv = rv.dropna()
                    if len(rv) >= 10:
                        rv_by[sym] = rv
                except Exception:
                    continue
            if rv_by:
                self._rv_by_symbol = rv_by
                self._fetched_at = time.time()
                logger.info("[scanner] IV rank cache refreshed: %d symbols", len(rv_by))
        except Exception as e:
            logger.warning("[scanner] IV rank cache refresh failed: %s", e)

    def iv_rank(self, symbol: str, current_iv_pct: float) -> tuple[float, float]:
        rv = self._rv_by_symbol.get(symbol)
        if rv is None or rv.empty:
            return 50.0, 50.0
        lo = float(rv.min())
        hi = float(rv.max())
        rng = hi - lo
        if rng <= 1e-9:
            rank = 50.0
        else:
            rank = max(0.0, min(100.0, round(((current_iv_pct - lo) / rng) * 100.0, 1)))
        below = float((rv < current_iv_pct).mean() * 100.0)
        pct = max(0.0, min(100.0, round(below, 1)))
        return rank, pct


class EarningsCache:
    """
    Cache days-to-earnings, refreshed every 6 hours.
    Uses existing Thrive Alpha provider where possible.
    """

    def __init__(self):
        self._cache: dict[str, Optional[int]] = {}
        self._ts: dict[str, float] = {}
        self._ttl = 6 * 3600

    def days_to_earnings(self, symbol: str, config: dict | None = None) -> Optional[int]:
        now = time.time()
        if symbol in self._ts and (now - self._ts[symbol]) < self._ttl:
            return self._cache.get(symbol)
        days = None
        try:
            from signals.providers import get_next_earnings
            r = get_next_earnings(symbol, config or {})
            if r and r.get("days_until") is not None:
                days = int(r["days_until"])
        except Exception:
            days = None
        self._cache[symbol] = days
        self._ts[symbol] = now
        return days


@dataclass
class ChainMetrics:
    fetched_at: float
    expiry: str
    atm_iv_pct: float
    call_vol: int
    put_vol: int
    flow_ratio: float


class YahooLiveProvider:
    """
    Live snapshots from Yahoo Finance.

    Key design: batch price/ohlc fetch, cache 1y RV series daily, cache option chain metrics 5–15 min.
    """

    def __init__(self):
        self.iv_cache = IVRankCache()
        self.earnings = EarningsCache()
        self._chain_cache: dict[str, ChainMetrics] = {}
        self._chain_ttl_sec = 10 * 60
        self._max_chain_fetch_per_scan = 12  # budget to avoid rate-limits

    def get_snapshots(self, symbols: list[str], *, config: dict | None = None) -> list[dict]:
        """
        Returns a list of dicts with keys matching what scanner adapter expects.
        """
        symbols = [s.upper() for s in symbols if s]
        if not symbols:
            return []

        self.iv_cache.refresh(symbols)

        price_pack = self._batch_prices(symbols)
        if not price_pack:
            return []

        # Only fetch chains when missing/stale and within budget
        to_fetch: list[str] = []
        now = time.time()
        for sym in symbols:
            cm = self._chain_cache.get(sym)
            if cm is None or (now - cm.fetched_at) > self._chain_ttl_sec:
                to_fetch.append(sym)
        to_fetch = to_fetch[: self._max_chain_fetch_per_scan]
        if to_fetch:
            self._refresh_chains(to_fetch)

        out: list[dict] = []
        for sym in symbols:
            p = price_pack.get(sym)
            if not p:
                continue
            price = float(p["price"])
            prev = float(p["prev"])
            pct_change = round(((price - prev) / prev * 100.0), 2) if prev else 0.0

            ma50 = p.get("ma50")
            ma200 = p.get("ma200")
            regime, reg_conf = self._ma_regime(price, ma50, ma200)

            atr_pct = p.get("atr_pct") or 2.5
            support = p.get("support")

            cm = self._chain_cache.get(sym)
            atm_iv_pct = cm.atm_iv_pct if cm else 30.0
            iv_rank, iv_pct = self.iv_cache.iv_rank(sym, float(atm_iv_pct))
            flow_ratio = cm.flow_ratio if cm else 1.0

            er_days = self.earnings.days_to_earnings(sym, config=config)

            out.append(
                {
                    "symbol": sym,
                    "price": round(price, 2),
                    "price_change_pct": pct_change,
                    "regime": regime,
                    "regime_confidence": reg_conf,
                    "iv_rank": iv_rank,
                    "iv_percentile": iv_pct,
                    "call_put_flow_ratio": float(flow_ratio),
                    "er_days_away": er_days,
                    "vix": float(p.get("vix") or 18.0),
                    "atr_pct": float(atr_pct),
                    "support_level": support,
                    "kelly_base": 0.05,
                    "scan_tier": p.get("tier"),
                    "sector": p.get("sector"),
                }
            )
        return out

    # ---------------- internal helpers ----------------

    def _batch_prices(self, symbols: list[str]) -> dict[str, dict]:
        """
        Batch download 1mo OHLC for ATR + MA regime, plus VIX (single ticker).
        """
        try:
            import yfinance as yf
            df = yf.download(
                tickers=" ".join(symbols),
                period="1mo",
                interval="1d",
                progress=False,
                threads=True,
                auto_adjust=True,
                group_by="ticker",
            )
            vix_df = yf.download("^VIX", period="5d", interval="1d", progress=False, threads=False, auto_adjust=True)
            vix = None
            try:
                if vix_df is not None and not vix_df.empty and "Close" in vix_df.columns:
                    close = vix_df["Close"]
                    if hasattr(close, "columns"):  # DataFrame
                        s = close.iloc[:, 0]
                    else:  # Series
                        s = close
                    vix = float(s.dropna().iloc[-1])
            except Exception:
                vix = None

            from scanner.ticker_universe import TICKER_META

            out: dict[str, dict] = {}
            for sym in symbols:
                try:
                    if isinstance(df.columns, pd.MultiIndex):
                        c = df[(sym, "Close")].dropna()
                        h = df[(sym, "High")].dropna()
                        l = df[(sym, "Low")].dropna()
                    else:
                        if len(symbols) != 1:
                            continue
                        c = df["Close"].dropna()
                        h = df["High"].dropna()
                        l = df["Low"].dropna()
                    if c.empty:
                        continue
                    price = float(c.iloc[-1])
                    prev = float(c.iloc[-2]) if len(c) >= 2 else price
                    ma50 = float(c.rolling(50, min_periods=20).mean().iloc[-1]) if len(c) >= 20 else None
                    ma200 = float(c.rolling(200, min_periods=60).mean().iloc[-1]) if len(c) >= 60 else None
                    atr_pct = self._atr_pct(h, l, c)
                    support = float(c.rolling(20, min_periods=10).min().iloc[-1]) if len(c) >= 10 else None
                    meta = TICKER_META.get(sym)
                    out[sym] = {
                        "price": price,
                        "prev": prev,
                        "ma50": ma50,
                        "ma200": ma200,
                        "atr_pct": atr_pct,
                        "support": support,
                        "tier": meta.tier if meta else None,
                        "sector": meta.sector if meta else "Unknown",
                        "vix": vix,
                    }
                except Exception:
                    continue
            return out
        except Exception as e:
            logger.warning("[scanner] batch price fetch failed: %s", e)
            return {}

    def _atr_pct(self, high: pd.Series, low: pd.Series, close: pd.Series) -> float:
        try:
            if len(close) < 15:
                return 2.5
            prev_c = close.shift(1)
            tr = pd.concat([(high - low).abs(), (high - prev_c).abs(), (low - prev_c).abs()], axis=1).max(axis=1)
            atr = tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
            last = float(close.iloc[-1])
            return round(float(atr) / last * 100.0, 2) if last else 2.5
        except Exception:
            return 2.5

    def _ma_regime(self, price: float, ma50: float | None, ma200: float | None) -> tuple[str, float]:
        """
        Map to scanner labels: STRONGLY_BULLISH/BULLISH/NEUTRAL/BEARISH/STRONGLY_BEARISH.
        """
        if ma50 is None or ma200 is None or ma50 <= 0 or ma200 <= 0:
            return "NEUTRAL", 55.0
        gap50 = (price - ma50) / ma50 * 100.0
        gap200 = (price - ma200) / ma200 * 100.0
        conf = min(95.0, max(40.0, 55.0 + abs(gap50) * 3.0 + abs(gap200) * 1.5))

        if price > ma50 > ma200 and gap50 > 1.0:
            return "STRONGLY_BULLISH", round(conf, 1)
        if price > ma50 and ma50 > ma200:
            return "BULLISH", round(conf, 1)
        if price < ma50 and ma50 < ma200 and gap50 < -1.0:
            return "STRONGLY_BEARISH", round(conf, 1)
        if price < ma50 and ma50 < ma200:
            return "BEARISH", round(conf, 1)
        return "NEUTRAL", round(conf, 1)

    def _refresh_chains(self, symbols: list[str]) -> None:
        """
        Refresh chain metrics for symbols (serial; yfinance can get flaky with too much concurrency).
        """
        try:
            import yfinance as yf
        except Exception as e:
            logger.warning("[scanner] yfinance missing: %s", e)
            return
        for sym in symbols:
            try:
                t = yf.Ticker(sym)
                spot = None
                try:
                    fi = getattr(t, "fast_info", None) or {}
                    spot = _safe_float(fi.get("last_price") or fi.get("regular_market_price") or fi.get("lastPrice"))
                except Exception:
                    spot = None
                expiries = list(getattr(t, "options", []) or [])
                if not expiries:
                    continue
                target = self._pick_expiry(expiries, min_days=5) or expiries[0]
                chain = t.option_chain(target)
                calls = getattr(chain, "calls", None)
                puts = getattr(chain, "puts", None)
                if calls is None or puts is None or calls.empty or puts.empty:
                    continue
                # ATM IV from nearest call+put strike
                atm_iv_pct = self._atm_iv_pct(calls, puts, spot=spot)
                call_vol = int(calls.get("volume", pd.Series(dtype=float)).fillna(0).sum())
                put_vol = int(puts.get("volume", pd.Series(dtype=float)).fillna(0).sum())
                flow = round(call_vol / put_vol, 2) if put_vol > 0 else (3.0 if call_vol > 0 else 1.0)
                self._chain_cache[sym] = ChainMetrics(
                    fetched_at=time.time(),
                    expiry=str(target),
                    atm_iv_pct=float(atm_iv_pct),
                    call_vol=call_vol,
                    put_vol=put_vol,
                    flow_ratio=float(flow),
                )
            except Exception as e:
                logger.debug("[scanner] chain fetch %s: %s", sym, e)

    def _pick_expiry(self, expiries: list[str], min_days: int) -> str | None:
        today = datetime.now().date()
        for exp in expiries:
            try:
                d = datetime.strptime(exp, "%Y-%m-%d").date()
                if (d - today).days >= min_days:
                    return exp
            except Exception:
                continue
        return None

    def _atm_iv_pct(self, calls: pd.DataFrame, puts: pd.DataFrame, *, spot: float | None) -> float:
        try:
            strikes = calls["strike"].astype(float)
            if strikes.empty:
                return 30.0
            mid = float(spot) if spot is not None else float(strikes.median())
            calls2 = calls.copy()
            calls2["dist"] = (calls2["strike"].astype(float) - mid).abs()
            atm_call = calls2.nsmallest(1, "dist").iloc[0]
            strike = float(atm_call["strike"])
            call_iv = _safe_float(atm_call.get("impliedVolatility"), 0.30) or 0.30
            puts2 = puts.copy()
            puts2["dist"] = (puts2["strike"].astype(float) - strike).abs()
            atm_put = puts2.nsmallest(1, "dist").iloc[0]
            put_iv = _safe_float(atm_put.get("impliedVolatility"), call_iv) or call_iv
            iv = (float(call_iv) + float(put_iv)) / 2.0
            return round(iv * 100.0, 2)
        except Exception:
            return 30.0

