"""
Redis cache layer for non–signal-critical data.
Cache policy: backtest, economic calendar, fundamentals, price targets, insider stats.
No cache: price, MAs, RSI, MACD, cross-asset.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("signals.cache")

# TTLs in seconds
TTL_BACKTEST = 24 * 3600
TTL_ECONOMIC_CALENDAR = 6 * 3600
TTL_FUNDAMENTALS = 12 * 3600
TTL_PRICE_TARGET = 6 * 3600
TTL_INSIDER_STATS = 12 * 3600
TTL_TARGET_BANDS = 7 * 24 * 3600  # 7 days – previous bands for trailing re-anchor
TTL_NEXT_DAY_BACKTEST = 24 * 3600  # 24h – next-day bias state stats
TTL_LONG_HORIZON_RISK = 24 * 3600  # 24h – max drawdown, stress bear (monthly data)
TTL_TICKER_DETAIL = 5 * 60  # 5 min – full ticker detail (many fetches; repeat views)
TTL_EDGAR_INSIDER = 12 * 3600  # 12h – Form 4 insider flow (SEC EDGAR)


def _redis_url() -> tuple[str | None, str | None]:
    """
    Return (url, source_env_var) for Redis.

    Railway/managed services may expose multiple env vars; we standardize on REDIS_URL
    but accept common alternatives so "configured" works out of the box.
    """
    candidates = (
        "REDIS_URL",
        "REDIS_PRIVATE_URL",
        "REDIS_TLS_URL",
        "UPSTASH_REDIS_URL",
        "UPSTASH_REDIS_TLS_URL",
    )
    for name in candidates:
        raw = os.environ.get(name, "")
        url = (raw or "").strip()
        if url and url.lower() not in ("", "0", "false", "none"):
            return url, name
    return None, None


def _redis_client():
    """Lazy Redis connection. Returns None if Redis unavailable or disabled."""
    try:
        url, _src = _redis_url()
        if not url:
            return None
        import redis
        r = redis.from_url(url, decode_responses=True, socket_connect_timeout=3)
        r.ping()
        return r
    except Exception as e:
        logger.debug("Redis not available: %s", e)
        return None


def redis_status() -> dict:
    """Return Redis connection status for dashboard. Does not raise."""
    try:
        url, src = _redis_url()
        configured = bool(url)
        # Provide non-sensitive diagnostics (never return the URL itself)
        scheme = None
        if url and "://" in url:
            scheme = url.split("://", 1)[0].lower()
        err = None
        connected = False
        try:
            r = _redis_client()
            connected = r is not None
        except Exception as e:
            err = str(e)[:160]
            connected = False
        return {
            "configured": configured,
            "connected": connected,
            "source": src,
            "scheme": scheme,
            "error": err if (configured and not connected) else None,
        }
    except Exception as e:
        logger.debug("redis_status: %s", e)
        return {"configured": False, "connected": False, "source": None, "scheme": None, "error": None}


def _serialize(val: Any) -> str:
    if isinstance(val, (dict, list)):
        return json.dumps(val, default=str)
    return str(val)


def _deserialize(raw: str, as_json: bool = True) -> Any:
    if raw is None:
        return None
    if as_json:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def get_cached(key: str, as_json: bool = True) -> Any | None:
    """Get from Redis. Returns None on miss or Redis unavailable."""
    r = _redis_client()
    if r is None:
        return None
    try:
        raw = r.get(key)
        return _deserialize(raw, as_json) if raw is not None else None
    except Exception as e:
        logger.warning("Cache get failed for %s: %s", key[:50], e)
        return None


def set_cached(key: str, value: Any, ttl_seconds: int) -> bool:
    """Set in Redis. Returns True on success."""
    r = _redis_client()
    if r is None:
        return False
    try:
        r.set(key, _serialize(value), ex=ttl_seconds)
        return True
    except Exception as e:
        logger.warning("Cache set failed for %s: %s", key[:50], e)
        return False


def cache_key(prefix: str, *parts: str) -> str:
    """Build cache key: prefix:part1:part2..."""
    return ":".join([prefix] + [str(p).upper() for p in parts if p])


def cached_backtest(ticker: str, period: str, fetch_fn):
    """Cache backtest results. TTL 24h."""
    key = cache_key("backtest", ticker, period)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out = fetch_fn()
    if out and not out.get("error"):
        set_cached(key, out, TTL_BACKTEST)
    return out


def cached_economic_calendar(days: int, fetch_fn):
    """Cache economic calendar. TTL 6h."""
    key = cache_key("economic_calendar", str(days))
    hit = get_cached(key)
    if hit is not None:
        return hit
    out = fetch_fn()
    if out is not None and isinstance(out, list):
        set_cached(key, out, TTL_ECONOMIC_CALENDAR)
    return out


def cached_price_target(ticker: str, fetch_fn):
    """Cache FMP price target. TTL 6h."""
    key = cache_key("price_target", ticker)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out, _ = fetch_fn()
    if out is not None:
        set_cached(key, out, TTL_PRICE_TARGET)
        return out
    return None


def cached_insider_stats(ticker: str, fetch_fn):
    """Cache FMP insider stats. TTL 12h."""
    key = cache_key("insider_stats", ticker)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out, _ = fetch_fn()
    if out is not None:
        set_cached(key, out, TTL_INSIDER_STATS)
        return out
    return None


def cached_financial_estimates(ticker: str, fetch_fn):
    """Cache FMP analyst estimates (forward EPS). TTL 12h."""
    key = cache_key("financial_estimates", ticker)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out, _ = fetch_fn()
    if out is not None:
        set_cached(key, out, TTL_FUNDAMENTALS)
        return out
    return None


def cached_price_target_consensus(ticker: str, fetch_fn):
    """Cache FMP price target consensus (high/low/median). TTL 6h."""
    key = cache_key("price_target_consensus", ticker)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out, _ = fetch_fn()
    if out is not None:
        set_cached(key, out, TTL_PRICE_TARGET)
        return out
    return None


def cached_key_metrics(ticker: str, fetch_fn) -> dict | None:
    """Cache FMP key-metrics-ttm (forwardPE, roe, operatingMargin, debtToEquity). TTL 12h."""
    key = cache_key("key_metrics", ticker)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out, _ = fetch_fn()
    if out is not None:
        set_cached(key, out, TTL_FUNDAMENTALS)
        return out
    return None


def cached_long_horizon_risk(ticker: str, period: str, fetch_fn) -> dict | None:
    """Cache long-horizon risk (max drawdown, stress bear). TTL 24h."""
    key = cache_key("long_horizon_risk", ticker, period)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out = fetch_fn()
    if out is not None:
        set_cached(key, out, TTL_LONG_HORIZON_RISK)
    return out


def get_cached_bands(ticker: str) -> dict | None:
    """Get last computed target bands for ticker (for trailing re-anchor)."""
    key = cache_key("target_bands", ticker)
    return get_cached(key)


def set_cached_bands(ticker: str, bands: dict) -> bool:
    """Store target bands for ticker. Used when price hits levels to re-anchor."""
    key = cache_key("target_bands", ticker)
    return set_cached(key, bands, TTL_TARGET_BANDS)


def cached_ticker_detail(ticker: str, config_hash: str, fetch_fn):
    """Cache full ticker detail response. TTL 5 min. config_hash = hash of relevant config (period)."""
    key = cache_key("ticker_detail", ticker, config_hash)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out = fetch_fn()
    if out is not None and isinstance(out, dict) and out.get("ticker"):
        set_cached(key, out, TTL_TICKER_DETAIL)
    return out


def cached_next_day_backtest(ticker: str, fetch_fn):
    """Cache next-day bias backtest (state_stats). TTL 24h."""
    key = cache_key("next_day_backtest", ticker)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out = fetch_fn()
    if out and not out.get("error"):
        set_cached(key, out, TTL_NEXT_DAY_BACKTEST)
    return out


def cached_edgar_insider_flow(tickers: list[str], fetch_fn):
    """Cache SEC EDGAR insider flow (Form 4) by watchlist. TTL 12h."""
    import hashlib
    tag = ",".join(sorted(t.strip().upper() for t in tickers if t)[:80])
    key = cache_key("edgar_insider", hashlib.md5(tag.encode()).hexdigest()[:16])
    hit = get_cached(key)
    if hit is not None and isinstance(hit, dict):
        return hit
    out = fetch_fn()
    if out and isinstance(out, dict):
        set_cached(key, out, TTL_EDGAR_INSIDER)
    return out
