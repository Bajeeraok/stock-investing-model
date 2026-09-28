"""
Institutional-style proxies: FMP insider list (role/size weighted), short float, holder trend.
Free fallbacks: Yahoo institutional_holders + SEC EDGAR 13F-HR (no FMP Ultimate required).
Complements SEC Form 4 flow in edgar_insider — not real-time options flow.
"""
from __future__ import annotations

import logging
from typing import Any

from signals.fmp_client import (
    fetch_institutional_holder_summary,
    fetch_insider_trading_list,
    fetch_short_float_summary,
)
from signals.institutional_conviction import compute_institutional_conviction_filter

logger = logging.getLogger(__name__)

_ROLE_WEIGHTS = (
    ("Chief Executive Officer", 1.0),
    ("Chief Financial Officer", 0.9),
    ("President", 0.8),
    ("Director", 0.5),
    ("VP", 0.3),
)


def _role_weight(reporting_name: str) -> float:
    name = (reporting_name or "").strip()
    for key, w in _ROLE_WEIGHTS:
        if key in name:
            return w
    return 0.2


_OPEN_MARKET_BUY_CODES = {"p-purchase"}
_OPEN_MARKET_SELL_CODES = {"s-sale"}
# Excluded on purpose, not just unmatched: A-Award (RSU/option grants), M-Exempt (derivative
# exercise), F-InKind/F-Tax (tax withholding), G-Gift, C-Conversion. These are compensation or
# administrative mechanics an insider doesn't choose in the way a discretionary market buy/sell
# is chosen — counting them as "conviction" is exactly the noise problem that made this signal
# unreliable (confirmed live: a typical AAPL 20-row window was 8 S-Sale / 6 M-Exempt / 3 F-InKind
# / 1 A-Award — most rows were never real signal to begin with).


def _tx_is_buy(action: str) -> bool:
    return (action or "").strip().lower() in _OPEN_MARKET_BUY_CODES


def _tx_is_sell(action: str) -> bool:
    return (action or "").strip().lower() in _OPEN_MARKET_SELL_CODES


def get_weighted_insider_signal(config: dict, ticker: str, limit: int = 20) -> dict[str, Any]:
    """Role/size-weighted net signal from open-market Form 4 transactions only (P-Purchase /
    S-Sale) — grants, option exercises, tax withholding, and gifts are fetched but excluded
    from scoring since they don't reflect a discretionary buy/sell decision.
    """
    rows, err = fetch_insider_trading_list(config, ticker, limit=limit)
    if err or not rows:
        return {"signal": 0.0, "buy_score": 0.0, "sell_score": 0.0, "n": 0, "error": err}

    buy_score = 0.0
    sell_score = 0.0
    open_market_n = 0
    for tx in rows[:limit]:
        role = tx.get("reportingName") or tx.get("reportingCik") or ""
        action = tx.get("transactionType") or tx.get("type") or ""
        is_buy = _tx_is_buy(action)
        is_sell = _tx_is_sell(action)
        if not is_buy and not is_sell:
            continue
        open_market_n += 1
        try:
            shares = float(tx.get("securitiesTransacted") or 0)
            price = float(tx.get("price") or 0)
            # Dollar value when both fields are present (FMP's search feed carries shares
            # transacted + fill price, not a pre-computed dollar amount); "value" is kept as
            # a fallback for any other insider-trading shape that already supplies it.
            value = abs(shares * price) if shares and price else abs(float(tx.get("value") or 0))
        except (TypeError, ValueError):
            value = 0.0
        w = _role_weight(str(role))
        size_w = min(value / 1_000_000.0, 5.0) if value else 0.1
        if is_buy:
            buy_score += w * size_w
        else:
            sell_score += w * size_w

    net = buy_score - sell_score
    signal = max(-100.0, min(100.0, net * 10.0))
    return {
        "signal": round(signal, 2),
        "buy_score": round(buy_score, 2),
        "sell_score": round(sell_score, 2),
        "n": open_market_n,
        "n_fetched": len(rows[:limit]),
    }


def get_short_interest_signal(config: dict, ticker: str) -> dict[str, Any]:
    row, err = fetch_short_float_summary(config, ticker)
    if err or not row:
        # Free fallback: FINRA bi-weekly via yfinance (no FMP subscription required)
        try:
            from signals.short_interest import fetch_short_interest

            si = fetch_short_interest(ticker)
            if si and si.get("short_pct") is not None:
                pct = float(si["short_pct"]) * 100.0
                risk = si.get("squeeze_risk") or "unknown"
                return {
                    "short_float_pct": round(pct, 2),
                    "signal": f"{str(risk).upper()} — {si.get('label', 'FINRA via Yahoo')}",
                    "source": "yfinance_finra",
                    "days_to_cover": si.get("days_to_cover"),
                    "trend": si.get("trend"),
                }
        except Exception as exc:
            logger.debug("short_interest yfinance fallback %s: %s", ticker, exc)
        return {"short_float_pct": None, "signal": "UNKNOWN", "error": err}

    sf = row.get("shortPercentOfFloat")
    if sf is None:
        sf = row.get("shortFloatPercent") or row.get("shortFloat")
    try:
        short_float = float(sf)
    except (TypeError, ValueError):
        return {"short_float_pct": None, "signal": "UNKNOWN", "raw": row}

    # FMP may return 0–1 or 0–100
    if short_float > 1.0:
        short_float = short_float / 100.0

    pct = short_float * 100.0
    if short_float > 0.20:
        label = "HIGH_SHORT — squeeze risk or justified caution"
    elif short_float > 0.10:
        label = "ELEVATED_SHORT — monitor"
    else:
        label = "LOW_SHORT — clean"

    return {"short_float_pct": round(pct, 2), "signal": label, "source": "fmp"}


_THIN_FLOAT_SHARES = 20_000_000
_LOW_FREE_FLOAT_PCT = 20.0


def get_liquidity_signal(config: dict, ticker: str) -> dict[str, Any]:
    """Real free-float liquidity flag (FMP /stable/shares-float) — a thin float means wider
    spreads and price that moves more on the same dollar volume, independent of anything the
    fair-value/technical signals already capture. Closes the open "liquidity flags for
    small/illiquid names" backlog item.
    """
    from signals.cache import cached_shares_float
    from signals.fmp_client import fetch_shares_float

    row = cached_shares_float(ticker, lambda: fetch_shares_float(config, ticker)[0])
    if not row:
        return {"flag": "UNKNOWN", "free_float_pct": None, "float_shares": None}

    free_float_pct = row.get("free_float_pct")
    float_shares = row.get("float_shares")
    thin_shares = float_shares is not None and float_shares < _THIN_FLOAT_SHARES
    low_pct = free_float_pct is not None and free_float_pct < _LOW_FREE_FLOAT_PCT
    if thin_shares or low_pct:
        flag = "THIN_FLOAT"
        label = (
            f"Thin float — {float_shares:,.0f} shares tradeable" if thin_shares
            else f"Low free float — {free_float_pct:.0f}% of shares outstanding"
        )
    else:
        flag = "NORMAL"
        label = "Float size within normal range"
    return {
        "flag": flag,
        "label": label,
        "free_float_pct": round(free_float_pct, 1) if free_float_pct is not None else None,
        "float_shares": int(float_shares) if float_shares is not None else None,
        "as_of": row.get("as_of"),
    }


def get_institutional_ownership(ticker: str) -> dict[str, Any]:
    """Institutional ownership % and top holders from Yahoo (13F-derived, delayed)."""
    try:
        from signals.yahoo_institutional import fetch_yahoo_institutional

        return fetch_yahoo_institutional(ticker)
    except Exception as exc:
        logger.debug("yahoo institutional %s: %s", ticker, exc)
        return {"error": str(exc), "source": "yfinance_delayed"}


def get_edgar_13f_holder_snapshot(
    ticker: str,
    config: dict | None = None,
    *,
    top_holders: list[dict] | None = None,
) -> dict[str, Any]:
    """Quarterly top-holder changes from SEC EDGAR 13F-HR via edgartools."""
    try:
        from signals.edgar_13f import fetch_edgar_13f_snapshot

        return fetch_edgar_13f_snapshot(
            ticker, config=config, top_holders=top_holders,
        )
    except Exception as exc:
        logger.debug("edgar 13f %s: %s", ticker, exc)
        return {"error": str(exc), "source": "sec_edgar_13f"}


def _trend_from_fmp_rows(rows: list[dict]) -> dict[str, Any]:
    increasing = 0
    for h in rows:
        ch = h.get("change") or h.get("changeInShares") or h.get("changeInHoldings")
        try:
            if ch is not None and float(ch) > 0:
                increasing += 1
        except (TypeError, ValueError):
            continue
    total = len(rows)
    pct_inc = increasing / total if total else 0.0
    trend = (
        "ACCUMULATING" if pct_inc > 0.60 else
        "DISTRIBUTING" if pct_inc < 0.40 else
        "NEUTRAL"
    )
    return {
        "pct_institutions_increasing": round(pct_inc, 3),
        "trend": trend,
        "total_institutions": total,
        "source": "fmp",
    }


def get_institutional_trend_proxy(
    config: dict,
    ticker: str,
    *,
    yahoo: dict[str, Any] | None = None,
    edgar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Holder trend: FMP institutional-holder feed when available, else Yahoo pctChange,
    else SEC EDGAR 13F sample comparison.
    """
    rows, err = fetch_institutional_holder_summary(config, ticker)
    if rows and len(rows) >= 2 and not err:
        out = _trend_from_fmp_rows(rows)
        out["error"] = None
        return out

    yahoo = yahoo if yahoo is not None else get_institutional_ownership(ticker)
    yahoo_trend = yahoo.get("holder_trend") or {}
    if yahoo_trend.get("trend") and yahoo_trend.get("trend") != "UNKNOWN":
        return {
            **yahoo_trend,
            "source": "yfinance_delayed",
            "as_of": yahoo.get("as_of"),
            "error": yahoo.get("error"),
        }

    edgar = edgar if edgar is not None else get_edgar_13f_holder_snapshot(ticker, config=config)
    if edgar.get("trend") and edgar.get("trend") != "UNKNOWN":
        return {
            "trend": edgar["trend"],
            "pct_institutions_increasing": edgar.get("pct_filings_increasing"),
            "total_institutions": edgar.get("filers_comparable") or edgar.get("filers_sampled"),
            "source": "sec_edgar_13f",
            "period_ending": edgar.get("period_ending"),
            "error": edgar.get("error"),
        }

    return {
        "trend": "UNKNOWN",
        "error": err or yahoo.get("error") or edgar.get("error"),
        "total_institutions": yahoo_trend.get("total_institutions", 0),
        "source": None,
    }


def build_institutional_bundle(config: dict, ticker: str, **conviction_kwargs: Any) -> dict[str, Any]:
    """Single-ticker snapshot for API / insights."""
    t = (ticker or "").upper().strip()
    yahoo = get_institutional_ownership(t)
    edgar = get_edgar_13f_holder_snapshot(t, config=config, top_holders=yahoo.get("top_holders"))
    trend = get_institutional_trend_proxy(config, t, yahoo=yahoo, edgar=edgar)
    partial = {
        "ticker": t,
        "institutional_ownership": {
            "institutional_pct": yahoo.get("institutional_pct"),
            "institutional_pct_label": yahoo.get("institutional_pct_label"),
            "source": yahoo.get("source", "yfinance_delayed"),
            "source_note": yahoo.get("source_note"),
            "as_of": yahoo.get("as_of"),
            "major_holders": yahoo.get("major_holders"),
            "top_holders": yahoo.get("top_holders"),
            "error": yahoo.get("error"),
        },
        "institutional_trend": trend,
        "edgar_13f": edgar,
    }
    conviction = compute_institutional_conviction_filter(
        partial,
        config=config,
        **conviction_kwargs,
    )
    return {
        "ticker": t,
        "insider_weighted": get_weighted_insider_signal(config, t),
        "short_interest": get_short_interest_signal(config, t),
        "liquidity": get_liquidity_signal(config, t),
        **partial,
        "conviction_filter": conviction,
    }
