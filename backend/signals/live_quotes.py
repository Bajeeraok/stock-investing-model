"""Live quote overlay — batch FMP or yfinance; keeps ohlcv_close for indicators."""
from __future__ import annotations

from typing import Any


def fetch_live_quotes(config: dict, tickers: list[str]) -> tuple[dict[str, float], str | None]:
    """Return {SYMBOL: price} and source label (fmp_batch | yfinance_latest)."""
    syms = [str(t).upper().strip() for t in tickers if t]
    if not syms:
        return {}, None
    out: dict[str, float] = {}
    try:
        from signals.fmp_client import fetch_batch_quote, get_fmp_api_key

        if get_fmp_api_key(config):
            batch, err = fetch_batch_quote(config, syms)
            if batch and not err:
                for sym, row in batch.items():
                    p = row.get("price") if isinstance(row, dict) else None
                    if p is not None:
                        try:
                            out[str(sym).upper()] = float(p)
                        except (TypeError, ValueError):
                            pass
                if out:
                    return out, "fmp_batch"
    except Exception:
        pass
    try:
        from signals.fetcher import fetch_yfinance_latest_prices

        missing = [s for s in syms if s not in out]
        if missing:
            yf = fetch_yfinance_latest_prices(missing)
            for k, v in (yf or {}).items():
                try:
                    out[str(k).upper()] = float(v)
                except (TypeError, ValueError):
                    pass
        if out:
            return out, "yfinance_latest"
    except Exception:
        pass
    return out, None


def overlay_live_price_fields(
    row: dict[str, Any],
    live: float,
    *,
    source: str,
) -> None:
    """Set display close + paper mark from live quote; preserve ohlcv_close."""
    if live <= 0:
        return
    prior = row.get("ohlcv_close")
    if prior is None and row.get("close") is not None:
        try:
            prior = float(row["close"])
            row["ohlcv_close"] = prior
        except (TypeError, ValueError):
            prior = None
    row["close"] = live
    row["live_price"] = live
    row["live_price_source"] = source
    row["paper_entry_price"] = live
    row["paper_entry_source"] = source
    ref = row.get("ohlcv_close")
    if ref is not None:
        try:
            ref_f = float(ref)
            if ref_f > 0:
                row["change_pct"] = round((live - ref_f) / ref_f * 100.0, 2)
        except (TypeError, ValueError):
            pass


def apply_live_quotes_to_results(
    results: list[dict],
    prices_by_ticker: dict[str, float] | None,
    *,
    source: str,
) -> None:
    if not prices_by_ticker:
        return
    for r in results or []:
        if not isinstance(r, dict) or r.get("error"):
            continue
        sym = str(r.get("ticker") or "").upper().strip()
        live = prices_by_ticker.get(sym)
        if live is None:
            continue
        try:
            overlay_live_price_fields(r, float(live), source=source)
        except (TypeError, ValueError):
            pass


def overlay_detail_current_price(detail: dict[str, Any], live: float, *, source: str) -> None:
    """Refresh header price on cached ticker detail without full recompute."""
    if live <= 0 or not isinstance(detail, dict):
        return
    prior = detail.get("ohlcv_close") or detail.get("current_price")
    if detail.get("current_price") is not None and detail.get("ohlcv_close") is None:
        try:
            detail["ohlcv_close"] = float(detail["current_price"])
            prior = detail["ohlcv_close"]
        except (TypeError, ValueError):
            pass
    detail["current_price"] = live
    detail["live_price"] = live
    detail["live_price_source"] = source
    if prior is not None:
        try:
            p0 = float(prior)
            if p0 > 0:
                detail["daily_move_pct"] = round((live - p0) / p0 * 100.0, 2)
        except (TypeError, ValueError):
            pass
