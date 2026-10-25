"""
Daily point-in-time snapshot of FMP analyst consensus (quarterly EPS/revenue estimates,
price targets, rating counts) into the PIT store as ``fmp_estimates``.

FMP only serves *current* consensus, so estimate-revision signals can only be backtested
from vintages we save ourselves. Run after EOD; one vintage per market date.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)
DATASET = "fmp_estimates"


def _num(row: dict, *keys: str) -> float | None:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def flatten(quarters: list[dict] | None, pt: dict | None, grades: dict | None, as_of: str) -> dict[str, Any]:
    """Next two fiscal quarters (period end > as_of) + price-target + rating-count columns."""
    out: dict[str, Any] = {}
    fut = sorted(
        (r for r in (quarters or []) if str(r.get("date") or "") > as_of),
        key=lambda r: str(r.get("date")),
    )
    for i, r in enumerate(fut[:2], start=1):
        out[f"q{i}_period"] = r.get("date")
        out[f"q{i}_eps_avg"] = _num(r, "epsAvg", "estimatedEpsAvg")
        out[f"q{i}_eps_high"] = _num(r, "epsHigh", "estimatedEpsHigh")
        out[f"q{i}_eps_low"] = _num(r, "epsLow", "estimatedEpsLow")
        out[f"q{i}_rev_avg"] = _num(r, "revenueAvg", "estimatedRevenueAvg")
        out[f"q{i}_n_eps"] = _num(r, "numAnalystsEps", "numberAnalystEstimatedEps")
    pt = pt or {}
    out["pt_consensus"] = _num(pt, "targetConsensus", "consensus")
    out["pt_median"] = _num(pt, "targetMedian", "median", "medianPriceTarget")
    out["pt_high"] = _num(pt, "targetHigh", "high")
    out["pt_low"] = _num(pt, "targetLow", "low")
    g = grades or {}
    for k in ("strongBuy", "buy", "hold", "sell", "strongSell"):
        out[f"grades_{k}"] = _num(g, k)
    return out


def _one(config: dict, ticker: str, as_of: str) -> dict[str, Any] | None:
    from signals import fmp_client as fmp

    q, _ = fmp.fetch_analyst_estimates_quarterly(config, ticker, limit=12)
    pt, _ = fmp.fetch_price_target_consensus(config, ticker)
    gr, _ = fmp.fetch_grades_consensus(config, ticker)
    if not q and not pt and not gr:
        return None
    row = flatten(q, pt, gr, as_of)
    row["ticker"] = ticker
    return row


def snapshot_universe(config: dict) -> list[str]:
    tickers: set[str] = set()
    try:
        from signals.alpha.universe import load_membership, members_on

        tickers |= set(members_on(load_membership(), pd.Timestamp.today().normalize()))
    except Exception:
        logger.warning("[estimates] S&P 500 membership unavailable; using watchlist only")
    tickers |= {str(t).upper() for t in (config.get("watchlist") or []) if t}
    return sorted(t for t in tickers if t and not t.startswith("^"))


def run(config: dict, as_of: str | None = None, store_root: str | Path | None = None, workers: int = 4) -> dict:
    from config_loader import get_data_root
    from signals.alpha.pit_store import PITStore
    from signals.fmp_client import get_api_key

    if not get_api_key(config):
        return {"status": "skipped", "reason": "no FMP API key"}
    as_of = str(pd.Timestamp(as_of or pd.Timestamp.today()).date())
    store = PITStore(store_root or Path(get_data_root()) / "alpha" / "pit_store")
    if store._path(DATASET, as_of).exists():
        return {"status": "exists", "as_of": as_of}
    tickers = snapshot_universe(config)
    with ThreadPoolExecutor(workers) as ex:
        rows = [r for r in ex.map(lambda t: _one(config, t, as_of), tickers) if r]
    if not rows:
        return {"status": "empty", "as_of": as_of, "requested": len(tickers)}
    p = store.append(DATASET, pd.DataFrame(rows).set_index("ticker"), as_of)
    return {"status": "ok", "as_of": as_of, "rows": len(rows), "requested": len(tickers), "path": str(p)}
