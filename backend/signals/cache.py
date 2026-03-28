"""
Redis cache layer for non–signal-critical data.

Cached (when REDIS_URL or REDIS_PRIVATE_URL etc. is set):
  - dashboard: full dashboard JSON (3 min) – avoids re-run on retry/refresh
  - backtest, next_day_backtest (24h)
  - economic_calendar (6h)
  - price_target, price_target_consensus (6h)
  - insider_stats, financial_estimates, key_metrics (12h)
  - long_horizon_risk (24h)
  - target_bands (4–24h, move-dependent) – prior ST/MT/LT for optional trailing re-anchor
  - ticker_detail (5 min), edgar_insider_flow (12h)

Not cached (by design): live price, MAs, RSI, MACD, cross-asset (signal-critical).
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
TTL_TARGET_BANDS = 24 * 3600  # Default max TTL (quiet days); add_target_bands uses shorter TTL on big move days
TTL_NEXT_DAY_BACKTEST = 24 * 3600  # 24h – next-day bias state stats
TTL_LONG_HORIZON_RISK = 24 * 3600  # 24h – max drawdown, stress bear (monthly data)
TTL_TICKER_DETAIL = 5 * 60  # 5 min – full ticker detail (many fetches; repeat views)
TTL_EDGAR_INSIDER = 12 * 3600  # 12h – Form 4 insider flow (SEC EDGAR)
TTL_DASHBOARD = 3 * 60  # 3 min – full dashboard JSON (avoids re-running on retry/refresh)


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


def _redis_scheme(url: str | None) -> str | None:
    if not url:
        return None
    if "://" in url:
        return url.split("://", 1)[0].lower()
    return None


def _redis_attempt_urls(url: str) -> list[str]:
    """
    Return a list of URLs to attempt, including safe scheme fallback.
    Some managed Redis providers require TLS (`rediss://`) even when a `redis://`
    URL is provided (or vice versa).
    """
    out = [url]
    if url.startswith("redis://"):
        out.append("rediss://" + url[len("redis://"):])
    elif url.startswith("rediss://"):
        out.append("redis://" + url[len("rediss://"):])
    return out


def _try_connect(url: str):
    import redis
    r = redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
        retry_on_timeout=False,
    )
    r.ping()
    return r


def _redis_client():
    """Lazy Redis connection. Returns None if Redis unavailable or disabled."""
    try:
        url, _src = _redis_url()
        if not url:
            return None
        last_err = None
        for u in _redis_attempt_urls(url):
            try:
                return _try_connect(u)
            except Exception as e:
                last_err = e
                continue
        logger.debug("Redis not available: %s", last_err)
        return None
    except Exception as e:
        logger.debug("Redis not available: %s", e)
        return None


def redis_status() -> dict:
    """Return Redis connection status for dashboard. Does not raise."""
    try:
        url, src = _redis_url()
        configured = bool(url)
        scheme = _redis_scheme(url)
        connected = False
        error = None
        used_scheme = scheme

        if configured and url:
            last_exc: Exception | None = None
            for u in _redis_attempt_urls(url):
                try:
                    _ = _try_connect(u)
                    connected = True
                    used_scheme = _redis_scheme(u)
                    last_exc = None
                    break
                except Exception as e:
                    last_exc = e
            if not connected and last_exc is not None:
                error = f"{type(last_exc).__name__}: {str(last_exc)[:180]}"

        return {
            "configured": configured,
            "connected": connected,
            "source": src,
            "scheme": used_scheme,
            "error": error if (configured and not connected) else None,
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


def _set_persistent(key: str, value: Any) -> bool:
    """Set in Redis with no TTL (persistent). Returns True on success."""
    r = _redis_client()
    if r is None:
        return False
    try:
        r.set(key, _serialize(value))
        return True
    except Exception as e:
        logger.warning("Redis set persistent failed for %s: %s", key[:50], e)
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
    """Last computed target bands for optional ST trailing re-anchor."""
    key = cache_key("target_bands", ticker)
    return get_cached(key)


def set_cached_bands(ticker: str, bands: dict, ttl_seconds: int | None = None) -> bool:
    """ttl_seconds defaults to TTL_TARGET_BANDS (24h). Callers may pass a shorter TTL after large daily moves."""
    key = cache_key("target_bands", ticker)
    ttl = int(ttl_seconds) if ttl_seconds is not None else TTL_TARGET_BANDS
    return set_cached(key, bands, ttl)


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


def get_cached_dashboard() -> dict | None:
    """Return cached full dashboard payload if present and Redis available. TTL 3 min."""
    key = cache_key("dashboard", "default")
    hit = get_cached(key)
    if hit is not None and isinstance(hit, dict) and hit.get("config") is not None:
        return hit
    return None


def set_cached_dashboard(payload: dict) -> bool:
    """Store full dashboard payload in Redis. TTL 3 min."""
    key = cache_key("dashboard", "default")
    return set_cached(key, payload, TTL_DASHBOARD)


# ─── EOD snapshots (persistent; no TTL) ─────────────────────────────────────
# Store in Redis so EOD survives restarts when no persistent volume (Railway/Docker).
# Read path: Redis first, then file. Write path: both Redis and file when possible.

EOD_KEY_PREFIX = "eod:snapshot:"
EOD_DATES_SET = "eod:dates"


def set_eod_snapshot_redis(date_str: str, payload: dict) -> bool:
    """Store EOD snapshot in Redis (no TTL). Returns True on success."""
    r = _redis_client()
    if r is None:
        return False
    try:
        key = EOD_KEY_PREFIX + date_str
        r.set(key, _serialize(payload))
        r.sadd(EOD_DATES_SET, date_str)
        return True
    except Exception as e:
        logger.warning("Redis EOD set failed for %s: %s", date_str, e)
        return False


def get_eod_snapshot_redis(date_str: str) -> dict | None:
    """Load EOD snapshot from Redis. Returns None on miss or error."""
    key = EOD_KEY_PREFIX + date_str
    return get_cached(key)


def list_eod_dates_redis() -> list[str]:
    """List EOD snapshot dates stored in Redis, sorted descending."""
    r = _redis_client()
    if r is None:
        return []
    try:
        members = r.smembers(EOD_DATES_SET)
        return sorted((m for m in members if isinstance(m, str)), reverse=True)
    except Exception as e:
        logger.debug("Redis EOD list failed: %s", e)
        return []


def delete_eod_snapshot_redis(date_str: str) -> bool:
    """Remove one EOD snapshot from Redis (e.g. when pruning old snapshots). Returns True on success."""
    r = _redis_client()
    if r is None:
        return False
    try:
        r.delete(EOD_KEY_PREFIX + date_str)
        r.srem(EOD_DATES_SET, date_str)
        return True
    except Exception as e:
        logger.debug("Redis EOD delete failed for %s: %s", date_str, e)
        return False
