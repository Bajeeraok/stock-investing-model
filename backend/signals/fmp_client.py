"""
FMP (Financial Modeling Prep) API client.
Fetches economic calendar, treasury, price targets, insider stats.
Detects plan limits and returns status for UI display.
"""
from __future__ import annotations

import json as _json
import urllib.request
from datetime import date, timedelta
from typing import Any

BASE = "https://financialmodelingprep.com/stable"
# Legacy v3/v4 for some endpoints
BASE_V3 = "https://financialmodelingprep.com/api/v3"
BASE_V4 = "https://financialmodelingprep.com/api/v4"


# Feature -> minimum plan (for display when unavailable)
FMP_PLAN_MAP = {
    "economic_calendar": "Starter",
    "treasury_rates": "Basic",
    "price_target": "Starter",
    "insider_stats": "Starter",
    "analyst_grades": "Starter",
    "profile": "Basic",
    "key_metrics": "Basic",
    "institutional_13f": "Ultimate",
    "earnings_transcripts": "Ultimate",
    "etf_holdings": "Ultimate",
    "stock_news": "Starter",
}


def _request(url: str, api_key: str) -> tuple[Any | None, str | None]:
    """
    Make FMP request. Returns (data, error).
    error is set when: HTTP error, plan limit, or invalid response.
    """
    sep = "&" if "?" in url else "?"
    full_url = f"{url}{sep}apikey={api_key}"
    try:
        req = urllib.request.Request(full_url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            data = _json.loads(raw)
        if isinstance(data, dict) and data.get("Error"):
            return None, data.get("Error", "Unknown error")
        return data, None
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None, f"Plan limit (HTTP {e.code})"
        return None, str(e)
    except Exception as e:
        return None, str(e)


def get_api_key(config: dict) -> str | None:
    return config.get("data", {}).get("fmp_api_key") or config.get("fmp_api_key") or None


def fetch_batch_quote(config: dict, symbols: list[str]) -> tuple[dict[str, dict], str | None]:
    """
    Fetch quotes for multiple symbols in a single request.
    Returns (ticker -> {price, close, ...}, error). Use for latest price to stay under API limits.
    FMP endpoint: stable/batch-quote?symbols=AAPL,MSFT,...
    """
    api_key = get_api_key(config)
    if not api_key:
        return {}, "No FMP API key"
    if not symbols:
        return {}, None
    # Dedupe and limit; FMP may cap symbols per request
    seen: set[str] = set()
    unique = [s for s in symbols if s and s not in seen and not seen.add(s)]
    symbols_param = ",".join(unique[:200])  # cap to avoid URL/plan limits
    url = f"{BASE}/batch-quote?symbols={symbols_param}"
    data, err = _request(url, api_key)
    if err:
        return {}, err
    if not isinstance(data, list):
        return {}, "Unexpected batch-quote response"
    out: dict[str, dict] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        sym = row.get("symbol") or row.get("Symbol")
        if not sym:
            continue
        # Prefer 'price' or 'close' for latest
        price = row.get("price") if row.get("price") is not None else row.get("close")
        if price is None:
            price = row.get("last")
        try:
            out[sym] = {"price": float(price)} if price is not None else {}
        except (TypeError, ValueError):
            out[sym] = {}
    return out, None


def fetch_economic_calendar(config: dict, days: int = 7) -> tuple[list[dict], str | None]:
    """
    Economic calendar for next N days. Returns (events, error).
    Requires Starter+ plan.
    """
    api_key = get_api_key(config)
    if not api_key:
        return [], "No FMP API key"
    today = date.today()
    to_d = today + timedelta(days=days)
    url = f"{BASE}/economic-calendar?from={today}&to={to_d}"
    data, err = _request(url, api_key)
    if err:
        return [], err
    if isinstance(data, list):
        return data[:50], None
    return [], "Unexpected response"


def fetch_treasury_rates(config: dict) -> tuple[list[dict] | None, str | None]:
    """Latest treasury rates (10Y, etc.). Returns (rates, error)."""
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    url = f"{BASE}/treasury-rates"
    data, err = _request(url, api_key)
    if err:
        return None, err
    if isinstance(data, list) and data:
        return data, None
    if isinstance(data, dict):
        return [data], None
    return None, "No data"


def get_10y_rate(rates: list[dict] | None) -> float | None:
    """Extract 10Y treasury rate from FMP response."""
    if not rates or not isinstance(rates, list):
        return None
    r = rates[0] if isinstance(rates[0], dict) else None
    if not r:
        return None
    for key in ("10Y", "10 year", "10 Year", "tenYear", "10", "ten_year"):
        val = r.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None


def fetch_price_target(config: dict, ticker: str) -> tuple[dict | None, str | None]:
    """Analyst price target summary. Returns (summary, error). Requires Starter+."""
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    url = f"{BASE}/price-target-summary?symbol={ticker}"
    data, err = _request(url, api_key)
    if err:
        return None, err
    if isinstance(data, list) and data:
        return data[0], None
    if isinstance(data, dict):
        return data, None
    return None, "No data"


def fetch_price_target_consensus(config: dict, ticker: str) -> tuple[dict | None, str | None]:
    """Analyst consensus: high, low, median. For LT band blend."""
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    url = f"{BASE}/price-target-consensus?symbol={ticker}"
    data, err = _request(url, api_key)
    if err:
        return None, err
    if isinstance(data, list) and data:
        return data[0], None
    if isinstance(data, dict):
        return data, None
    return None, "No data"


def fetch_analyst_estimates_quarterly(
    config: dict, ticker: str, limit: int = 4
) -> tuple[list[dict] | None, str | None]:
    """Quarterly analyst EPS consensus rows (newest first). For revision momentum."""
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    sym = (ticker or "").upper().split("-")[0]
    if not sym:
        return None, "No ticker"
    url = f"{BASE}/analyst-estimates?symbol={sym}&period=quarter&limit={min(max(2, limit), 20)}"
    data, err = _request(url, api_key)
    if err:
        return None, err
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)], None
    return None, "No data"


def fetch_analyst_estimates(config: dict, ticker: str) -> tuple[dict | None, str | None]:
    """
    Forward analyst EPS/Revenue consensus from FMP analyst-estimates endpoint.

    Returns a normalised dict with:
        eps_avg        — consensus forward EPS (mean of analyst estimates)
        eps_high       — most optimistic analyst EPS estimate
        eps_low        — most pessimistic analyst EPS estimate
        eps_dispersion — (high - low) / avg; >0.20 = high analyst disagreement
        analyst_count  — number of analysts contributing EPS estimates
        rev_avg        — consensus forward revenue (USD)
        certainty      — 0-1 score: 1 = tight consensus, 0 = wide disagreement
        eps_fwd        — alias for eps_avg (backward-compat)
    """
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    url = f"{BASE}/analyst-estimates?symbol={ticker}&period=annual&page=0&limit=2"
    data, err = _request(url, api_key)
    if err:
        return None, err

    item = None
    if isinstance(data, list) and data:
        item = data[0] if isinstance(data[0], dict) else None
    elif isinstance(data, dict):
        item = data
    if not item:
        return None, "No analyst estimate data"

    def _f(keys: list[str]) -> float | None:
        for k in keys:
            v = item.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return None

    def _i(keys: list[str]) -> int | None:
        for k in keys:
            v = item.get(k)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
        return None

    eps_avg  = _f(["estimatedEpsAvg", "epsEstimate", "estimatedEps", "eps"])
    eps_high = _f(["estimatedEpsHigh"])
    eps_low  = _f(["estimatedEpsLow"])
    rev_avg  = _f(["estimatedRevenueAvg", "estimatedRevenue", "revenueEstimate"])
    n_eps    = _i(["numberAnalystEstimatedEps", "numberOfAnalysts", "numAnalysts"])
    n_rev    = _i(["numberAnalystsEstimatedRevenue"])
    analyst_count = n_eps or n_rev

    if eps_avg is None:
        return None, "No EPS estimate in response"

    # Dispersion: (high - low) / avg — measures analyst disagreement
    eps_dispersion = None
    if eps_high is not None and eps_low is not None and eps_avg != 0:
        eps_dispersion = round(abs(eps_high - eps_low) / abs(eps_avg), 4)

    # Certainty score 0-1: tight consensus = 1, wide = 0
    # Dispersion < 0.10 = high certainty, > 0.40 = very uncertain
    certainty = None
    if eps_dispersion is not None:
        certainty = round(max(0.0, min(1.0, 1.0 - eps_dispersion / 0.40)), 3)

    return {
        "eps_avg":        round(eps_avg, 4),
        "eps_high":       round(eps_high, 4) if eps_high is not None else None,
        "eps_low":        round(eps_low,  4) if eps_low  is not None else None,
        "eps_dispersion": eps_dispersion,
        "analyst_count":  analyst_count,
        "rev_avg":        round(rev_avg, 0) if rev_avg is not None else None,
        "certainty":      certainty,
        "eps_fwd":        round(eps_avg, 4),   # backward-compat alias
    }, None


def fetch_insider_stats(config: dict, ticker: str) -> tuple[dict | None, str | None]:
    """Insider trading statistics. Returns (stats, error). Requires Starter+."""
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    url = f"{BASE}/insider-trading/statistics?symbol={ticker}"
    data, err = _request(url, api_key)
    if err:
        return None, err
    if isinstance(data, dict):
        return data, None
    if isinstance(data, list) and data:
        return data[0] if isinstance(data[0], dict) else None, None
    return None, "No data"


def fetch_insider_trading_list(
    config: dict, ticker: str, limit: int = 20
) -> tuple[list[dict] | None, str | None]:
    """
    Recent insider transactions (stable insider-trading feed).
    Returns (rows, error). Used for role/size-weighted net signal.
    """
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    sym = (ticker or "").upper().split("-")[0]
    if not sym:
        return None, "No ticker"
    url = f"{BASE}/insider-trading?symbol={sym}&limit={min(max(1, limit), 100)}"
    data, err = _request(url, api_key)
    if err:
        return None, err
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)], None
    return None, "Unexpected insider-trading response"


def fetch_short_float_summary(config: dict, ticker: str) -> tuple[dict | None, str | None]:
    """
    Short interest / short percent of float (v4). Shape varies by plan.
    """
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    sym = (ticker or "").upper().split("-")[0]
    if not sym:
        return None, "No ticker"
    url = f"{BASE_V4}/short_float?symbol={sym}"
    data, err = _request(url, api_key)
    if err:
        url2 = f"{BASE_V4}/short-interest?symbol={sym}"
        data, err = _request(url2, api_key)
    if err:
        return None, err
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0], None
    if isinstance(data, dict):
        return data, None
    return None, "No data"


def fetch_institutional_holder_summary(config: dict, ticker: str) -> tuple[list[dict] | None, str | None]:
    """
    Institutional holders (v3). May require higher FMP tier — caller should handle errors.
    """
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    sym = (ticker or "").upper().split("-")[0]
    if not sym:
        return None, "No ticker"
    url = f"{BASE_V3}/institutional-holder/{sym}"
    data, err = _request(url, api_key)
    if err:
        return None, err
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)], None
    return None, "No data"


def _clipf(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _fmp_item_sentiment_raw(item: dict) -> float | None:
    """If FMP adds per-article scores, map to -1..1. Returns None if absent."""
    for key in (
        "sentimentScore",
        "sentiment_score",
        "sentiment",
        "overallSentimentScore",
        "overall_sentiment_score",
    ):
        v = item.get(key)
        if v is None:
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        # Heuristic: FMP might use 0-1, -1..1, or 0-100
        if -1.01 <= x <= 1.01:
            return _clipf(x, -1.0, 1.0)
        if 0.0 <= x <= 1.01:
            return float(x * 2.0 - 1.0)
        if 0.0 <= x <= 100.0:
            return _clipf((x - 50.0) / 50.0, -1.0, 1.0)
    return None


def _stock_news_summary_from_items(rows: list[dict], ticker: str, limit: int) -> dict:
    """
    Build FMP-style summary dict from stable or v3 news rows (raw JSON objects).
    """
    raw_items = [x for x in rows[:limit] if isinstance(x, dict)]
    if not raw_items:
        return {
            "ticker": ticker,
            "sentiment_score_avg": None,
            "sentiment_label": "Neutral",
            "sentiment_method": "none",
            "headline_count": 0,
            "headlines": [],
        }

    # Per-article API sentiment when present
    fmp_scores: list[float] = []
    for it in raw_items:
        r = _fmp_item_sentiment_raw(it)
        if r is not None:
            fmp_scores.append(r)

    if fmp_scores:
        import numpy as _np

        avg = float(_np.mean(_np.clip(_np.array(fmp_scores, dtype=float), -1.0, 1.0)))
        label = "Bullish" if avg > 0.15 else "Bearish" if avg < -0.15 else "Neutral"
        headlines = []
        for item in raw_items[:10]:
            title = (item.get("title") or item.get("headline") or "")[:120]
            headlines.append(
                {
                    "title": title,
                    "score": _fmp_item_sentiment_raw(item),
                    "label": "Neutral",
                }
            )
        return {
            "ticker": ticker,
            "sentiment_score_avg": round(avg, 4),
            "sentiment_label": label,
            "sentiment_method": "fmp_field",
            "headline_count": len(raw_items),
            "headlines": headlines,
        }

    # Keyword lexicon on title + text
    from signals.news_keyword_sentiment import aggregate_keyword_sentiment

    kw_avg, n_h, kw_hit = aggregate_keyword_sentiment(raw_items, ticker=ticker)
    headlines = []
    for item in raw_items[:10]:
        title = (item.get("title") or item.get("headline") or "")[:120]
        headlines.append({"title": title, "score": None, "label": "Neutral"})

    if kw_hit and kw_avg is not None:
        label = "Bullish" if kw_avg > 0.15 else "Bearish" if kw_avg < -0.15 else "Neutral"
        return {
            "ticker": ticker,
            "sentiment_score_avg": round(kw_avg, 4),
            "sentiment_label": label,
            "sentiment_method": "keyword",
            "headline_count": n_h,
            "headlines": headlines,
        }

    # Headlines only — no usable signal for this path; caller should try Alpha Vantage
    return {
        "ticker": ticker,
        "sentiment_score_avg": None,
        "sentiment_label": "Neutral",
        "sentiment_method": "none",
        "headline_count": len(raw_items),
        "headlines": headlines,
    }


def fetch_stock_news(config: dict, ticker: str, limit: int = 10) -> tuple[dict | None, str | None]:
    """
    Fetch recent stock news: prefer FMP stable ``/news/stock``, fall back to legacy v3 ``stock_news``.

    Returns summary:
      sentiment_score_avg — raw in [-1, 1] for ConfidenceEngine (mapped to 0..1 there)
      sentiment_method — "fmp_field" | "keyword" | "none" (caller may try Alpha Vantage)
      headline_count, headlines

    Rows usually have no ML sentiment field; we aggregate keyword scores from title + body.
    If API adds scores later, _fmp_item_sentiment_raw uses them first.
    """
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    sym = (ticker or "").upper().split("-")[0]
    if not sym:
        return None, "No ticker"
    lim = min(limit, 50)
    errs: list[str] = []

    # Primary: stable search stock news (documented path; v3 may be restricted on some plans)
    url_stable = f"{BASE}/news/stock?symbols={sym}"
    data_s, err_s = _request(url_stable, api_key)
    if not err_s and isinstance(data_s, list) and data_s:
        return _stock_news_summary_from_items(data_s, ticker, limit), None
    if err_s:
        errs.append(f"stable: {err_s}")

    # Fallback: legacy v3
    url_v3 = f"{BASE_V3}/stock_news?tickers={sym}&limit={lim}"
    data_v, err_v = _request(url_v3, api_key)
    if not err_v and isinstance(data_v, list) and data_v:
        return _stock_news_summary_from_items(data_v, ticker, limit), None
    if err_v:
        errs.append(f"v3: {err_v}")

    if errs:
        return None, "; ".join(errs)
    return None, "Empty stock news (stable and v3)"


def fetch_profile(config: dict, ticker: str) -> tuple[dict | None, str | None]:
    """
    Company profile: sector, industry, beta, mktCap, country.
    For LT score, fair PE style (quality growth vs mature), sector benchmark.
    """
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    url = f"{BASE_V3}/profile/{ticker}"
    data, err = _request(url, api_key)
    if err:
        return None, err
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0], None
    if isinstance(data, dict):
        return data, None
    return None, "No data"


def fetch_key_metrics_ttm(config: dict, ticker: str) -> tuple[dict | None, str | None]:
    """
    Key metrics TTM: trailingPE, forwardPE, roe, operatingMargin, netMargin, debtToEquity, etc.
    For LT quality/valuation score and fair PE range.
    """
    api_key = get_api_key(config)
    if not api_key:
        return None, "No FMP API key"
    url = f"{BASE_V3}/key-metrics-ttm/{ticker}"
    data, err = _request(url, api_key)
    if err:
        return None, err
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0], None
    if isinstance(data, dict):
        return data, None
    return None, "No data"


def fetch_historical_earning_dates(
    config: dict,
    ticker: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[str], str | None]:
    """
    Historical earnings-related dates for a US equity (FMP v3).

    Returns (YYYY-MM-DD strings sorted ascending, error). Empty list is valid (ETF / no data).

    Tries ``historical/earning_calendar`` first, then ``earnings_surprises`` for ``date`` fields
    (fallback is noisier). Used by ``backtest_earnings`` exclusion.
    """
    api_key = get_api_key(config)
    if not api_key:
        return [], "No FMP API key"
    sym = (ticker or "").upper().replace(".", "-").split("-")[0]
    if not sym:
        return [], "No ticker"
    from_d = (start_date or "2000-01-01")[:10]
    to_d = (end_date or "2035-12-31")[:10]
    url = f"{BASE_V3}/historical/earning_calendar/{sym}?from={from_d}&to={to_d}"
    data, err = _request(url, api_key)
    out_dates: list[str] = []
    if isinstance(data, list) and data:
        for row in data:
            if not isinstance(row, dict):
                continue
            ds = row.get("date") or row.get("earningDate")
            if ds:
                out_dates.append(str(ds)[:10])
    if not out_dates:
        url2 = f"{BASE_V3}/earnings-surprises/{sym}"
        data2, err2 = _request(url2, api_key)
        if isinstance(data2, list) and data2:
            for row in data2:
                if not isinstance(row, dict):
                    continue
                ds = row.get("date") or row.get("filingDate")
                if ds:
                    out_dates.append(str(ds)[:10])
        if err2 and not out_dates:
            err = err2
    uniq = sorted(set(out_dates))
    return uniq, err


def run_fmp_plan_check(config: dict) -> dict:
    """
    Probe FMP endpoints to see which features work.
    Returns: {
        "has_key": bool,
        "available": [{"feature": str, "plan": str}],
        "unavailable": [{"feature": str, "suggested_plan": str, "error": str}],
    }
    """
    api_key = get_api_key(config)
    result = {
        "has_key": bool(api_key),
        "available": [],
        "unavailable": [],
    }
    if not api_key:
        result["unavailable"] = [
            {"feature": "All FMP features", "suggested_plan": "Starter ($22/mo) or Ultimate ($149/mo)", "error": "Add fmp_api_key to config"},
        ]
        return result

    checks = [
        ("economic_calendar", lambda: fetch_economic_calendar(config, 1)),
        ("treasury_rates", lambda: fetch_treasury_rates(config)),
        ("price_target", lambda: fetch_price_target(config, "AAPL")),
        ("insider_stats", lambda: fetch_insider_stats(config, "AAPL")),
        ("stock_news", lambda: fetch_stock_news(config, "AAPL", 5)),
    ]
    for name, fn in checks:
        plan = FMP_PLAN_MAP.get(name, "?")
        try:
            out, err = fn()
            if err:
                result["unavailable"].append({
                    "feature": name.replace("_", " ").title(),
                    "suggested_plan": plan,
                    "error": err[:80] if err else "Unknown",
                })
            else:
                result["available"].append({"feature": name.replace("_", " ").title(), "plan": plan})
        except Exception as e:
            result["unavailable"].append({
                "feature": name.replace("_", " ").title(),
                "suggested_plan": plan,
                "error": str(e)[:80],
            })

    return result
