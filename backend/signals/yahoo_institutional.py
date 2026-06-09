"""
Institutional ownership via Yahoo Finance (free, 13F-derived, quarterly lag).

Surfaces:
  - heldPercentInstitutions / major_holders breakdown
  - Top institutional holders with pctChange (QoQ from 13F filings)
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TTL_CACHE_SEC = 12 * 3600
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "institutional_cache"


def _cache_path(ticker: str) -> Path:
    return _CACHE_DIR / f"{ticker.upper()}.json"


def _read_cache(ticker: str) -> dict | None:
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(data.get("ts", 0)) > TTL_CACHE_SEC:
            return None
        return data.get("payload")
    except Exception:
        return None


def _write_cache(ticker: str, payload: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR.joinpath(f"{ticker.upper()}.json").write_text(
            json.dumps({"ts": time.time(), "payload": payload}, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.debug("institutional cache write failed %s: %s", ticker, exc)


def _parse_major_holders(df) -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {
        "insiders_pct": None,
        "institutions_pct": None,
        "institutions_float_pct": None,
        "institutions_count": None,
    }
    if df is None or getattr(df, "empty", True):
        return out
    try:
        for _, row in df.iterrows():
            label = str(row.iloc[0]).strip().lower()
            val = row.iloc[1]
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            if "insider" in label:
                out["insiders_pct"] = round(num * 100.0, 2) if num <= 1.0 else round(num, 2)
            elif "float" in label and "institution" in label:
                out["institutions_float_pct"] = round(num * 100.0, 2) if num <= 1.0 else round(num, 2)
            elif "institution" in label and "count" in label:
                out["institutions_count"] = int(num)
            elif "institution" in label:
                out["institutions_pct"] = round(num * 100.0, 2) if num <= 1.0 else round(num, 2)
    except Exception as exc:
        logger.debug("major_holders parse: %s", exc)
    return out


def _parse_institutional_holders(df) -> tuple[list[dict], str | None]:
    if df is None or getattr(df, "empty", True):
        return [], None
    holders: list[dict] = []
    as_of: str | None = None
    cols = {c.lower(): c for c in df.columns}
    date_col = cols.get("date reported") or cols.get("date_reported")
    holder_col = cols.get("holder")
    shares_col = cols.get("shares")
    pct_col = cols.get("pctheld") or cols.get("pct held") or cols.get("% out")
    change_col = cols.get("pctchange") or cols.get("pct change") or cols.get("% change")
    value_col = cols.get("value")
    for _, row in df.head(12).iterrows():
        holder = str(row.get(holder_col, "") if holder_col else row.iloc[1]).strip()
        reported = row.get(date_col) if date_col else None
        if reported is not None:
            as_of = str(reported)[:10]
        entry: dict[str, Any] = {"holder": holder}
        if shares_col and row.get(shares_col) is not None:
            try:
                entry["shares"] = int(float(row[shares_col]))
            except (TypeError, ValueError):
                pass
        if pct_col and row.get(pct_col) is not None:
            try:
                entry["pct_held"] = round(float(row[pct_col]) * 100.0, 2)
            except (TypeError, ValueError):
                pass
        if change_col and row.get(change_col) is not None:
            try:
                entry["pct_change_qoq"] = round(float(row[change_col]) * 100.0, 2)
            except (TypeError, ValueError):
                pass
        if value_col and row.get(value_col) is not None:
            try:
                entry["value_usd"] = int(float(row[value_col]))
            except (TypeError, ValueError):
                pass
        if holder:
            holders.append(entry)
    return holders, as_of


def _trend_from_holder_changes(holders: list[dict]) -> dict[str, Any]:
    changes = [h["pct_change_qoq"] for h in holders if h.get("pct_change_qoq") is not None]
    if not changes:
        return {"trend": "UNKNOWN", "pct_institutions_increasing": None, "total_institutions": len(holders)}
    increasing = sum(1 for c in changes if c > 0.5)
    decreasing = sum(1 for c in changes if c < -0.5)
    total = len(changes)
    pct_inc = increasing / total if total else 0.0
    if pct_inc > 0.55 and increasing > decreasing:
        trend = "ACCUMULATING"
    elif pct_inc < 0.45 and decreasing > increasing:
        trend = "DISTRIBUTING"
    else:
        trend = "NEUTRAL"
    return {
        "trend": trend,
        "pct_institutions_increasing": round(pct_inc, 3),
        "total_institutions": total,
        "increasing_count": increasing,
        "decreasing_count": decreasing,
    }


def fetch_yahoo_institutional(ticker: str, *, use_cache: bool = True) -> dict[str, Any]:
    """
    Fetch institutional ownership snapshot from Yahoo Finance (13F-derived, delayed).

    Returns institutional_pct, major_holders breakdown, top_holders, holder_trend, as_of.
    """
    sym = (ticker or "").upper().strip()
    if not sym:
        return {"error": "No ticker"}

    if use_cache:
        cached = _read_cache(sym)
        if cached:
            cached["from_cache"] = True
            return cached

    try:
        import yfinance as yf

        yt = yf.Ticker(sym)
        info = yt.info if isinstance(getattr(yt, "info", None), dict) else {}
        held = info.get("heldPercentInstitutions")
        inst_pct: float | None = None
        if held is not None:
            try:
                h = float(held)
                inst_pct = round(h * 100.0, 2) if h <= 1.0 else round(h, 2)
            except (TypeError, ValueError):
                pass

        major = _parse_major_holders(getattr(yt, "major_holders", None))
        if inst_pct is None and major.get("institutions_pct") is not None:
            inst_pct = float(major["institutions_pct"])

        top_holders, as_of = _parse_institutional_holders(getattr(yt, "institutional_holders", None))
        trend_block = _trend_from_holder_changes(top_holders)

        payload: dict[str, Any] = {
            "ticker": sym,
            "institutional_pct": inst_pct,
            "institutional_pct_label": f"{inst_pct:.1f}%" if inst_pct is not None else None,
            "source": "yfinance_delayed",
            "source_note": "Institutional % (Yahoo, delayed) — aggregated from quarterly 13F filings",
            "as_of": as_of,
            "major_holders": major,
            "top_holders": top_holders,
            "holder_trend": trend_block,
            "from_cache": False,
        }
        _write_cache(sym, payload)
        return payload
    except Exception as exc:
        logger.debug("yahoo institutional fetch failed %s: %s", sym, exc)
        return {"ticker": sym, "error": str(exc), "source": "yfinance_delayed"}
