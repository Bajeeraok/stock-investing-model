"""Live quote overlay — batch FMP or yfinance; keeps ohlcv_close for indicators."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any


def fetch_live_quotes(config: dict, tickers: list[str]) -> tuple[dict[str, float], str | None]:
    """Return {SYMBOL: price} and source label (fmp_batch | yfinance_latest)."""
    syms = [str(t).upper().strip() for t in tickers if t]
    if not syms:
        return {}, None
    out: dict[str, float] = {}
    # Respect use_fmp_batch_quote config flag (false on FMP Starter — batch endpoint needs Premium).
    # When false, skip FMP entirely to avoid stale EOD prices being returned as "live" data.
    use_fmp = config.get("data", {}).get("use_fmp_batch_quote", True)
    if use_fmp:
        try:
            from signals.fmp_client import fetch_batch_quote, get_api_key as get_fmp_api_key

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
    if detail.get("current_price") is not None and detail.get("ohlcv_close") is None:
        try:
            detail["ohlcv_close"] = float(detail["current_price"])
        except (TypeError, ValueError):
            pass
    detail["current_price"] = live
    detail["live_price"] = live
    detail["live_price_source"] = source
    detail["live_price_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    detail["daily_move_pct"] = _daily_move_vs_prior_session(detail, live)


def _prior_session_close(detail: dict[str, Any], now: datetime | None = None) -> float | None:
    """Close of the session before the one the live quote belongs to, taken from the build's price
    history. None when the build is too old to contain it (a stale page), so today's move is never
    measured from a close several days back."""
    from zoneinfo import ZoneInfo

    from signals.market_calendar import is_nyse_holiday

    hist = detail.get("price_history") or []
    if len(hist) < 2:
        return None
    try:
        last_d = date.fromisoformat(str(hist[-1]["date"])[:10])
        last_c, prev_c = float(hist[-1]["close"]), float(hist[-2]["close"])
    except (KeyError, TypeError, ValueError):
        return None
    now = now or datetime.now(ZoneInfo("America/New_York"))
    if str(detail.get("ticker") or "").upper().endswith("-USD"):
        session, before = now.date(), now.date() - timedelta(days=1)
    else:
        def _back(d: date) -> date:
            d -= timedelta(days=1)
            while d.weekday() >= 5 or is_nyse_holiday(d):
                d -= timedelta(days=1)
            return d

        session = now.date()
        if session.weekday() >= 5 or is_nyse_holiday(session) or (now.hour, now.minute) < (9, 30):
            session = _back(session)
        before = _back(session)
    if last_d == session:
        return prev_c if prev_c > 0 else None
    if last_d == before:
        return last_c if last_c > 0 else None
    return None


def _daily_move_vs_prior_session(detail: dict[str, Any], live: float, now: datetime | None = None) -> float | None:
    p0 = _prior_session_close(detail, now)
    return round((live - p0) / p0 * 100.0, 2) if p0 else None
