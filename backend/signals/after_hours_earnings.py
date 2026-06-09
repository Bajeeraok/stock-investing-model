"""
After-hours earnings snapshot: lightweight quote pass for tickers reporting today.

Gated by get_next_earnings(days_until == 0). Does not rerun full run_signals.
Writes data/after_hours_latest.json and merges into dashboard Redis cache.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("signals.after_hours_earnings")

_ETFS = frozenset({"SPY", "QQQ", "GLD", "SLV", "DIA", "IWM", "XLF", "XLK", "XLE", "XLV", "XLP", "XLY", "XLI", "XLB", "XLU"})


def _today_et() -> str:
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


def _holdings_from_config(config: dict) -> list:
    holdings: list = []
    portfolios = config.get("portfolios") or {}
    if portfolios and isinstance(portfolios, dict):
        for account_name, account_holdings in portfolios.items():
            if isinstance(account_holdings, list):
                for h in account_holdings:
                    entry = dict(h) if isinstance(h, dict) else {"ticker": h, "quantity": 1}
                    entry["account"] = account_name
                    holdings.append(entry)
    if not holdings:
        portfolio = config.get("portfolio", [])
        if isinstance(portfolio, list) and portfolio and isinstance(portfolio[0], dict):
            holdings = portfolio
        else:
            holdings = [{"ticker": t, "quantity": 1} for t in config.get("watchlist", [])]
    return holdings


def signal_universe_tickers(config: dict) -> list[str]:
    """Portfolio holdings ∪ watchlist (deduped, no ETFs for earnings)."""
    tickers: list[str] = []
    seen: set[str] = set()
    for t in config.get("watchlist") or []:
        if t and t not in seen:
            seen.add(t)
            tickers.append(t)
    for h in _holdings_from_config(config):
        t = h.get("ticker") if isinstance(h, dict) else h
        if t and t not in seen:
            seen.add(t)
            tickers.append(t)
    return [t for t in tickers if t.upper() not in _ETFS]


def tickers_reporting_today(config: dict, universe: list[str] | None = None) -> list[dict[str, Any]]:
    """Return [{ticker, earnings_date, days_until: 0}, ...] for names with earnings today (ET)."""
    from signals.providers import get_next_earnings

    syms = universe if universe is not None else signal_universe_tickers(config)
    out: list[dict[str, Any]] = []
    for ticker in syms:
        try:
            e = get_next_earnings(ticker, config)
            if not e or e.get("days_until") is None:
                continue
            if int(e["days_until"]) != 0:
                continue
            out.append({
                "ticker": ticker,
                "earnings_date": e.get("date"),
                "days_until": 0,
            })
        except Exception as exc:
            logger.debug("earnings today check %s: %s", ticker, exc)
    return out


def _prior_closes_from_dashboard_cache() -> dict[str, float]:
    try:
        from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot

        cached = get_cached_dashboard() or get_last_dashboard_snapshot()
        if not cached:
            return {}
        out: dict[str, float] = {}
        for r in cached.get("signals") or []:
            if not isinstance(r, dict) or r.get("error"):
                continue
            t = r.get("ticker")
            c = r.get("close")
            if t and c is not None:
                try:
                    out[str(t).upper()] = float(c)
                except (TypeError, ValueError):
                    pass
        return out
    except Exception as exc:
        logger.debug("prior closes from cache: %s", exc)
        return {}


def _fetch_live_prices(config: dict, tickers: list[str]) -> tuple[dict[str, float], str]:
    """ticker -> latest price; returns (prices, source label)."""
    if not tickers:
        return {}, "none"
    from signals.fmp_client import fetch_batch_quote, get_api_key as fmp_key
    from signals.fetcher import fetch_yfinance_latest_prices

    prices: dict[str, float] = {}
    source = "yfinance_latest"
    if fmp_key(config):
        batch, err = fetch_batch_quote(config, tickers)
        if not err and batch:
            for sym, row in batch.items():
                p = row.get("price") if isinstance(row, dict) else None
                if p is not None:
                    try:
                        prices[sym.upper()] = float(p)
                    except (TypeError, ValueError):
                        pass
            if prices:
                source = "fmp_batch"
    missing = [t for t in tickers if t.upper() not in prices]
    if missing:
        yf = fetch_yfinance_latest_prices(missing)
        for sym, p in (yf or {}).items():
            prices[sym.upper()] = float(p)
        if yf and not prices:
            source = "yfinance_latest"
        elif yf and source != "fmp_batch":
            source = "yfinance_latest"
        elif yf:
            source = "fmp_batch+yfinance"
    return prices, source


def _post_earnings_advisory(ticker: str, config: dict, change_pct: float, earnings_date: str | None) -> dict | None:
    try:
        from signals.post_earnings_transition import compute_post_earnings_signal

        ctx = {
            "most_recent_earnings_date": earnings_date or _today_et(),
            "days_since_earnings": 0,
            "post_earnings_return_pct": round(change_pct, 2),
            "post_earnings_volume_ratio": None,
        }
        pe = compute_post_earnings_signal(ticker, config, earnings_context=ctx)
        if not pe.active:
            return None
        return {
            "beat_or_miss": pe.beat_or_miss,
            "eps_surprise_pct": pe.eps_surprise_pct,
            "transition_note": pe.transition_note,
            "signal_direction": pe.signal_direction,
            "price_reaction_pct": pe.price_reaction_pct,
        }
    except Exception as exc:
        logger.debug("post-earnings advisory %s: %s", ticker, exc)
        return None


def run_after_hours_earnings_snapshot(*, slot: str = "6pm", config: dict | None = None) -> dict[str, Any]:
    """
    If any universe ticker has earnings today, fetch live marks vs last RTH close from cache.
    Persists JSON under DATA_ROOT and merges into dashboard Redis when available.
    """
    from config_loader import get_data_root, load_config

    config = config or load_config()
    session_date = _today_et()
    from signals.time_et import now_iso_et

    reporting = tickers_reporting_today(config)
    base: dict[str, Any] = {
        "as_of_et": now_iso_et(),
        "session_date_et": session_date,
        "slot": slot,
        "skipped": False,
        "tickers_scheduled": [r["ticker"] for r in reporting],
        "items": [],
        "disclaimer": (
            "After-hours mark vs last regular-session close from the prior dashboard run. "
            "Composite score and indicators are unchanged until the next full refresh."
        ),
    }

    if not reporting:
        base["skipped"] = True
        base["skip_reason"] = "no_earnings_today"
        logger.info("[after-hours] slot=%s skipped — no tickers with earnings today", slot)
        _persist_snapshot(base)
        return base

    tickers = [r["ticker"] for r in reporting]
    prior = _prior_closes_from_dashboard_cache()
    live, price_source = _fetch_live_prices(config, tickers)

    items: list[dict[str, Any]] = []
    for row in reporting:
        sym = row["ticker"]
        key = sym.upper()
        mark = live.get(key)
        prev = prior.get(key)
        change_pct = None
        if mark is not None and prev is not None and prev > 0:
            change_pct = round((mark - prev) / prev * 100.0, 2)
        item: dict[str, Any] = {
            "ticker": sym,
            "earnings_date": row.get("earnings_date") or session_date,
            "previous_close": prev,
            "mark_price": mark,
            "change_pct": change_pct,
            "price_source": price_source,
        }
        if change_pct is not None:
            adv = _post_earnings_advisory(sym, config, change_pct, item.get("earnings_date"))
            if adv:
                item["post_earnings"] = adv
        items.append(item)

    base["items"] = items
    base["price_source"] = price_source
    logger.info(
        "[after-hours] slot=%s ok tickers=%s with_marks=%d",
        slot,
        tickers,
        sum(1 for i in items if i.get("mark_price") is not None),
    )
    _persist_snapshot(base)
    try:
        from signals.cache import merge_dashboard_cache_updates

        merge_dashboard_cache_updates({"after_hours_earnings": base})
    except Exception as exc:
        logger.debug("[after-hours] cache merge skipped: %s", exc)
    return base


def _persist_snapshot(payload: dict[str, Any]) -> None:
    try:
        from config_loader import get_data_root

        path = get_data_root() / "after_hours_latest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("[after-hours] file write failed: %s", exc)


def load_after_hours_snapshot() -> dict[str, Any] | None:
    try:
        from config_loader import get_data_root

        path = get_data_root() / "after_hours_latest.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.debug("load after_hours snapshot: %s", exc)
        return None
