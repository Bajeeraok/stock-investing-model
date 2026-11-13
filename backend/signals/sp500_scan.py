"""Nightly S&P 500 + major ETF scan for the investor rulebook. Price-only rules; watch list only, never a signal."""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CACHE_KEY = "sp500_scan:latest"
CACHE_TTL = 5 * 86400
SCAN_ETFS = (
    "SPY", "QQQ", "IWM", "DIA", "MDY", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC",
    "SMH", "SOXX", "IGV", "XBI", "KRE", "ITB", "GLD", "SLV", "TLT", "IEF", "HYG", "EFA", "EEM", "VNQ", "ARKK",
)
PRICE_RULES = ("trend_template", "below_200d", "overextended", "distribution")
LEADERS_N = 25


def universe() -> tuple[list[str], dict[str, str]]:
    from signals.alpha.universe import load_membership, members_on, sector_map

    m = load_membership()
    names = [t.replace(".", "-") for t in members_on(m, pd.Timestamp.today().normalize())]
    sectors = {k.replace(".", "-"): v for k, v in sector_map(m).items()}
    for e in SCAN_ETFS:
        sectors.setdefault(e, "ETF")
    return sorted(set(names) | set(SCAN_ETFS)), sectors


def _rsi(close: pd.Series, n: int = 14) -> float | None:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up.iloc[-1] / dn.iloc[-1] if dn.iloc[-1] else np.inf
    v = 100 - 100 / (1 + rs)
    return round(float(v), 1) if np.isfinite(v) else None


def row_from_bars(ticker: str, df: pd.DataFrame, sector: str | None = None) -> dict[str, Any] | None:
    df = df.dropna(subset=["Close"])
    if len(df) < 210:
        return None
    c, v = df["Close"], df.get("Volume")
    px = float(c.iloc[-1])
    hi = float(c.tail(252).max())
    row: dict[str, Any] = {
        "ticker": ticker,
        "sector": sector,
        "price": round(px, 2),
        "change_pct": round((px / float(c.iloc[-2]) - 1) * 100, 2),
        "ma50": round(float(c.tail(50).mean()), 2),
        "ma200": round(float(c.tail(200).mean()), 2),
        "rsi": _rsi(c),
        "high_52w": round(hi, 2),
        "drawdown_52w": round((px / hi - 1) * 100, 1),
        "ret_6m": round((px / float(c.iloc[-127]) - 1) * 100, 1),
        "mom_12_1": round((float(c.iloc[-22]) / float(c.iloc[0]) - 1) * 100, 1),
    }
    if v is not None and float(v.tail(21).iloc[:-1].mean() or 0) > 0:
        row["volume_ratio"] = round(float(v.iloc[-1]) / float(v.tail(21).iloc[:-1].mean()), 2)
    return row


def build_payload(rows: list[dict[str, Any]], as_of: str) -> dict[str, Any]:
    from signals.investor_rules import RULES

    checks = {r["id"]: r["check"] for r in RULES if r["id"] in PRICE_RULES}
    spy = next((r for r in rows if r["ticker"] == "SPY"), None)
    hits: dict[str, list[dict[str, str]]] = {k: [] for k in PRICE_RULES}
    for r in rows:
        if spy:
            r["rs_6m_vs_spy"] = round(r["ret_6m"] - spy["ret_6m"], 1)
        for rid, fn in checks.items():
            d = fn(r)
            if d:
                hits[rid].append({"ticker": r["ticker"], "detail": d})
    trend_ok = {h["ticker"] for h in hits["trend_template"]}
    stocks = [r for r in rows if r.get("sector") != "ETF" and r["ticker"] in trend_ok]
    leaders = sorted(stocks, key=lambda r: r["mom_12_1"], reverse=True)[:LEADERS_N]
    by_sector: dict[str, int] = {}
    for r in leaders:
        by_sector[r.get("sector") or "Other"] = by_sector.get(r.get("sector") or "Other", 0) + 1
    return {
        "as_of": as_of,
        "n_scanned": len(rows),
        "rule_hits": {k: {"count": len(v), "hits": sorted(v, key=lambda h: h["ticker"])} for k, v in hits.items()},
        "leaders": [
            {k: r.get(k) for k in ("ticker", "sector", "price", "mom_12_1", "rs_6m_vs_spy", "drawdown_52w", "rsi")}
            for r in leaders
        ],
        "leader_sectors": by_sector,
        "note": "Watch list only. Momentum leaders = trend template + top 12-1 month return; not a buy signal until tracked vs SPY.",
    }


def run_scan() -> dict[str, Any]:
    import yfinance as yf

    from signals.cache import set_cached
    from signals.time_et import now_iso_et

    tickers, sectors = universe()
    rows: list[dict[str, Any]] = []
    for i in range(0, len(tickers), 100):
        chunk = tickers[i : i + 100]
        try:
            data = yf.download(chunk, period="13mo", group_by="ticker", auto_adjust=True, progress=False, threads=True)
        except Exception as e:
            logger.warning("sp500 scan chunk %s failed: %s", i, e)
            continue
        for t in chunk:
            try:
                r = row_from_bars(t, data[t], sectors.get(t))
            except Exception:
                r = None
            if r:
                rows.append(r)
    out = build_payload(rows, now_iso_et())
    set_cached(CACHE_KEY, out, CACHE_TTL)
    try:
        from config_loader import get_data_root

        (get_data_root() / "sp500_scan_latest.json").write_text(json.dumps(out))
    except Exception as e:
        logger.debug("sp500 scan disk write: %s", e)
    logger.info("[sp500-scan] %d of %d tickers scanned", len(rows), len(tickers))
    return out


def load_latest() -> dict[str, Any] | None:
    from signals.cache import get_cached

    hit = get_cached(CACHE_KEY)
    if isinstance(hit, dict):
        return hit
    try:
        from config_loader import get_data_root

        p = get_data_root() / "sp500_scan_latest.json"
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:
        return None
