from __future__ import annotations

import time
import logging
import os
from dataclasses import dataclass
from typing import Optional

from scanner.engine import MarketSnapshot
from scanner.ticker_universe import TICKER_META, TIER1_SYMBOLS, ScanTier as Tier

logger = logging.getLogger("scanner.provider")


def get_support_level(symbol: str, price: float) -> Optional[float]:
    try:
        return round(price * 0.95, 2)
    except Exception:
        return None


@dataclass
class MacroSnapshot:
    vix: float
    es_change: float
    macro_flag: str


class MacroProvider:
    def __init__(self):
        self._cache: Optional[MacroSnapshot] = None
        self._cache_ts: float = 0.0

    def get(self) -> dict:
        if self._cache and (time.time() - self._cache_ts) < 300:
            return {"vix": self._cache.vix, "es_change": self._cache.es_change, "macro_flag": self._cache.macro_flag}
        vix = 18.0
        es_change = 0.0
        try:
            import yfinance as yf
            vix_t = yf.Ticker("^VIX")
            vix = float(vix_t.fast_info.get("last_price") or 18.0)
        except Exception:
            pass
        try:
            import yfinance as yf
            es = yf.Ticker("ES=F")
            inf = es.fast_info or {}
            prev_close = float(inf.get("previous_close") or inf.get("regular_market_previous_close") or 0.0)
            last = float(inf.get("last_price") or 0.0)
            if prev_close:
                es_change = round((last - prev_close) / prev_close * 100, 2)
        except Exception:
            pass

        risk = 0
        if vix > 25:
            risk += 3
        elif vix > 22:
            risk += 2
        elif vix > 20:
            risk += 1
        if es_change < -1.0:
            risk += 3
        elif es_change < -0.5:
            risk += 2
        elif es_change < -0.2:
            risk += 1
        elif es_change > 0.5:
            risk -= 1
        macro_flag = "RISK_OFF" if risk >= 4 else "RISK_ON" if risk <= -1 else "NEUTRAL"

        self._cache = MacroSnapshot(vix=vix, es_change=es_change, macro_flag=macro_flag)
        self._cache_ts = time.time()
        return {"vix": vix, "es_change": es_change, "macro_flag": macro_flag}


class MockDataProvider:
    MOCK_PRICES = {
        "AAPL": 172.5,
        "MSFT": 415.2,
        "NVDA": 847.2,
        "GOOGL": 155.3,
        "META": 505.8,
        "AMZN": 178.9,
        "TSLA": 185.4,
        "MSTR": 129.5,
        "MARA": 9.2,
        "RIOT": 8.4,
        "COIN": 198.3,
        "SMCI": 32.8,
        "QQQ": 445.6,
        "SPY": 512.3,
        "GLD": 188.5,
        "PLTR": 24.8,
        "NOW": 108.2,
        "CRWD": 345.8,
        "SNOW": 155.4,
        "AMD": 168.5,
    }

    SCENARIOS = {
        "NVDA": {"iv_rank": 87, "er_days": 2, "flow": 3.1, "regime": "BULLISH", "regime_conf": 78, "price_chg": 2.1},
        "MSTR": {"iv_rank": 82, "er_days": None, "flow": 2.8, "regime": "STRONGLY_BULLISH", "regime_conf": 85, "price_chg": 4.2},
        "COIN": {"iv_rank": 85, "er_days": None, "flow": 3.4, "regime": "STRONGLY_BULLISH", "regime_conf": 82, "price_chg": 5.1},
        "SNOW": {"iv_rank": 88, "er_days": 1, "flow": 2.6, "regime": "BULLISH", "regime_conf": 70, "price_chg": 1.8},
        "TSLA": {"iv_rank": 76, "er_days": None, "flow": 1.4, "regime": "BEARISH", "regime_conf": 61, "price_chg": -2.8},
        "PLTR": {"iv_rank": 75, "er_days": 6, "flow": 2.2, "regime": "STRONGLY_BULLISH", "regime_conf": 88, "price_chg": 3.8},
    }
    DEFAULT = {"iv_rank": 38, "er_days": None, "flow": 1.0, "regime": "NEUTRAL", "regime_conf": 50, "price_chg": 0.1}

    def get_snapshots(self, symbols: list[str], vix: float) -> list[MarketSnapshot]:
        out: list[MarketSnapshot] = []
        for sym in symbols:
            price = float(self.MOCK_PRICES.get(sym, 50.0))
            sc = self.SCENARIOS.get(sym, self.DEFAULT)
            meta = TICKER_META.get(sym)
            support = get_support_level(sym, price)
            out.append(
                MarketSnapshot(
                    symbol=sym,
                    price=price,
                    price_change_pct=float(sc["price_chg"]),
                    regime=str(sc["regime"]),
                    regime_confidence=float(sc["regime_conf"]),
                    iv_rank=float(sc["iv_rank"]),
                    iv_percentile=float(sc["iv_rank"]) + 3,
                    call_put_flow_ratio=float(sc["flow"]),
                    er_days_away=sc["er_days"],
                    vix=float(vix),
                    atr_pct=2.5,
                    support_level=support,
                    kelly_base=0.05,
                    in_watchlist=False,
                    scan_tier=(meta.tier if meta else Tier.TIER1_CORE),
                    sector=(meta.sector if meta else "Unknown"),
                )
            )
        return out


def make_default_provider():
    macro = MacroProvider()
    mock = MockDataProvider()
    symbols = sorted(list(TIER1_SYMBOLS))
    yahoo_live = None

    def snapshots() -> list[MarketSnapshot]:
        m = macro.get()
        provider = os.getenv("SCANNER_PROVIDER", "yahoo").lower().strip()
        if provider in {"yahoo", "yfinance", "yf"}:
            try:
                from scanner.yahoo_live_provider import YahooLiveProvider
                from config_loader import load_config

                cfg = load_config()
                nonlocal yahoo_live
                if yahoo_live is None:
                    yahoo_live = YahooLiveProvider()
                raw = yahoo_live.get_snapshots(symbols, config=cfg)
                out: list[MarketSnapshot] = []
                for r in raw:
                    meta = TICKER_META.get(r["symbol"])
                    out.append(
                        MarketSnapshot(
                            symbol=r["symbol"],
                            price=float(r["price"]),
                            price_change_pct=float(r.get("price_change_pct") or 0.0),
                            regime=str(r.get("regime") or "NEUTRAL"),
                            regime_confidence=float(r.get("regime_confidence") or 55.0),
                            iv_rank=float(r.get("iv_rank") or 50.0),
                            iv_percentile=float(r.get("iv_percentile") or 50.0),
                            call_put_flow_ratio=float(r.get("call_put_flow_ratio") or 1.0),
                            er_days_away=r.get("er_days_away"),
                            vix=float(r.get("vix") or m.get("vix") or 18.0),
                            atr_pct=float(r.get("atr_pct") or 2.5),
                            support_level=r.get("support_level"),
                            kelly_base=float(r.get("kelly_base") or 0.05),
                            in_watchlist=False,
                            scan_tier=(meta.tier if meta else Tier.TIER1_CORE),
                            sector=(meta.sector if meta else "Unknown"),
                        )
                    )
                return out
            except Exception as e:
                logger.warning("[scanner] yahoo provider failed, falling back to mock: %s", e)
        return mock.get_snapshots(symbols, float(m.get("vix") or 18.0))

    def watchlist() -> set[str]:
        try:
            from config_loader import load_config
            cfg = load_config()
            wl = set(str(s).upper() for s in (cfg.get("watchlist") or []) if s)
            holdings = set()
            portfolios = cfg.get("portfolios") or {}
            if isinstance(portfolios, dict):
                for v in portfolios.values():
                    if isinstance(v, list):
                        for h in v:
                            if isinstance(h, dict) and h.get("ticker"):
                                holdings.add(str(h["ticker"]).upper())
                            elif isinstance(h, str):
                                holdings.add(h.upper())
            return wl | holdings
        except Exception:
            return {"NVDA", "QQQ", "MSTR"}

    def macro_provider() -> dict:
        m = macro.get()
        return {"vix": m.get("vix"), "es_change": m.get("es_change"), "macro_flag": m.get("macro_flag")}

    return snapshots, watchlist, macro_provider

