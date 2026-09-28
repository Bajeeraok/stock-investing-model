"""
Redis cache layer for non–signal-critical data.

Cached (when REDIS_URL or REDIS_PRIVATE_URL etc. is set):
  - dashboard: full dashboard JSON – TTL via DASHBOARD_CACHE_TTL_SECONDS
    (intraday ~2h; overnight until next 8:30 ET warm window);
    avoids re-run on retry/refresh; warm scripts can pre-populate
  - backtest, next_day_backtest (24h)
  - economic_calendar (6h)
  - price_target, price_target_consensus (6h)
  - insider_stats, financial_estimates, key_metrics (12h)
  - long_horizon_risk (24h)
  - target_bands (4–24h, move-dependent) – prior ST/MT/LT for optional trailing re-anchor
  - ticker_detail (5 min), edgar_insider_flow (24h)
  - thrive_phase2 (15 min) – GET /api/thrive-phase2
  - earnings_quality (14d; 1d when earnings ≤7 days away) – statements move quarterly
  - institutional_bundle (12h) – insider weighted, short float %, ownership %, 13F trend

Recommended TTL bands (override per env where noted):
  - Short (2–15 min): dashboard bundle, ticker_detail, thrive_phase2 – intraday-ish freshness
  - Medium (6h): economic calendar, price targets – daily decision support
  - Long (12–24h): fundamentals aggregates, insider batch, long_horizon_risk, backtest – slow-moving

Not cached (by design): live price, MAs, RSI, MACD, cross-asset (signal-critical).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

logger = logging.getLogger("signals.cache")

_redis_pool: Any = None
_redis_pool_lock = threading.Lock()

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
TTL_CONFIDENCE = 5 * 60  # 5 min – 7-layer confidence (shared by ticker detail + /confidence route)
TTL_EDGAR_INSIDER = 24 * 3600  # 24h – Form 4 insider flow (once-daily refresh)
TTL_NEWS_GENERAL = 3600  # 1h – FMP general news for pre-IPO keyword filter
TTL_EARNINGS_QUALITY = 14 * 24 * 3600  # 14d – statements/revisions move quarterly
TTL_EARNINGS_QUALITY_NEAR = 24 * 3600  # 1d – earnings nearby: re-fetch daily to catch new report
TTL_INSTITUTIONAL_BUNDLE = 12 * 3600  # 12h – 13F quarterly, short interest bi-weekly, insiders daily at most
TTL_PRICE_TARGET_SCENARIOS = 15 * 60  # 15 min – internal scenario-EV engine (HMM/ML-tilted); mode-independent


def _dashboard_ttl_seconds() -> int:
    """
    Full dashboard JSON in Redis.

    - Env DASHBOARD_CACHE_TTL_SECONDS overrides (60–20h).
    - Outside signal-warm window (after 16:00 ET / weekends): TTL until next 8:30 ET
      so overnight page loads keep serving the post-EOD snapshot.
    - Intraday: align with DASHBOARD_WARM_INTERVAL_MIN (default 2h on Railway).
    """
    raw = (os.environ.get("DASHBOARD_CACHE_TTL_SECONDS") or "").strip()
    if raw:
        try:
            return max(60, min(20 * 3600, int(raw)))
        except ValueError:
            pass
    try:
        from alerts.market_hours import is_signal_warm_window, seconds_until_next_signal_warm_open

        if not is_signal_warm_window():
            # Cap weekend so Redis key still refreshes Monday morning window
            return min(20 * 3600, max(6 * 3600, seconds_until_next_signal_warm_open()))
    except Exception:
        pass
    try:
        from api.market_scheduler import _dashboard_warm_interval_min

        return max(30 * 60, min(3 * 3600, _dashboard_warm_interval_min() * 60))
    except Exception:
        return 2 * 3600


TTL_THRIVE_PHASE2 = 15 * 60  # 15 min – intraday + FMP + composite gate (UI-friendly)


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


def _redis_socket_timeout() -> float:
    """Read timeout for Redis commands.

    EOD snapshots are multi‑MB JSON; a 3s socket_timeout causes
    ``Timeout reading from socket`` on Railway and leaves the UI on a
    stale ``eod:dates`` member (e.g. stuck on 2026-08-02). Override with
    ``REDIS_SOCKET_TIMEOUT`` (seconds).
    """
    raw = (os.environ.get("REDIS_SOCKET_TIMEOUT") or "").strip()
    if raw:
        try:
            return max(3.0, min(120.0, float(raw)))
        except ValueError:
            pass
    return 15.0


def _redis_connect_timeout() -> float:
    raw = (os.environ.get("REDIS_CONNECT_TIMEOUT") or "").strip()
    if raw:
        try:
            return max(1.0, min(30.0, float(raw)))
        except ValueError:
            pass
    return 5.0


def _try_connect(url: str):
    import redis
    r = redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=_redis_connect_timeout(),
        socket_timeout=_redis_socket_timeout(),
        retry_on_timeout=True,
    )
    r.ping()
    return r


def _redis_max_connections() -> int:
    raw = (os.environ.get("REDIS_MAX_CONNECTIONS") or "").strip()
    if raw:
        try:
            return max(4, min(128, int(raw)))
        except ValueError:
            pass
    return 32


def _reset_redis_pool() -> None:
    """Drop pooled connections (e.g. after connection errors)."""
    global _redis_pool
    with _redis_pool_lock:
        pool = _redis_pool
        _redis_pool = None
    if pool is not None:
        try:
            pool.disconnect(inuse_connections=True)
        except Exception:
            pass


def _get_redis_pool():
    """Shared ConnectionPool — one TCP destination, reused across all cache ops."""
    global _redis_pool
    if _redis_pool is not None:
        return _redis_pool
    with _redis_pool_lock:
        if _redis_pool is not None:
            return _redis_pool
        url, _src = _redis_url()
        if not url:
            return None
        import redis

        last_err = None
        for u in _redis_attempt_urls(url):
            try:
                pool = redis.ConnectionPool.from_url(
                    u,
                    decode_responses=True,
                    socket_connect_timeout=_redis_connect_timeout(),
                    socket_timeout=_redis_socket_timeout(),
                    retry_on_timeout=True,
                    max_connections=_redis_max_connections(),
                    health_check_interval=30,
                )
                redis.Redis(connection_pool=pool).ping()
                _redis_pool = pool
                return _redis_pool
            except Exception as e:
                last_err = e
                continue
        logger.debug("Redis pool not available: %s", last_err)
        return None


def close_redis_pool() -> None:
    """Release pooled Redis connections on app shutdown."""
    _reset_redis_pool()


def _is_redis_connection_error(exc: BaseException) -> bool:
    try:
        import redis

        return isinstance(exc, (redis.ConnectionError, redis.TimeoutError))
    except Exception:
        return False


def _redis_client():
    """Return a Redis client backed by the shared pool (no new TCP connect per call)."""
    pool = _get_redis_pool()
    if pool is None:
        return None
    import redis

    return redis.Redis(connection_pool=pool)


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
            client = _redis_client()
            if client is not None:
                try:
                    client.ping()
                    connected = True
                    used_scheme = _redis_scheme(url)
                except Exception as e:
                    last_exc = e
                    _reset_redis_pool()
            else:
                for u in _redis_attempt_urls(url):
                    try:
                        probe = _try_connect(u)
                        try:
                            probe.close()
                        except Exception:
                            pass
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


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively replace non-finite floats with None so json.dumps never raises."""
    import math
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _serialize(val: Any) -> str:
    if isinstance(val, (dict, list)):
        return json.dumps(_sanitize_for_json(val), default=str)
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
        if _is_redis_connection_error(e):
            _reset_redis_pool()
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
        if _is_redis_connection_error(e):
            _reset_redis_pool()
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
        if _is_redis_connection_error(e):
            _reset_redis_pool()
        logger.warning("Redis set persistent failed for %s: %s", key[:50], e)
        return False


def delete_cached(key: str) -> bool:
    """Delete one Redis key. Returns True when deleted or already absent."""
    r = _redis_client()
    if r is None:
        return False
    try:
        r.delete(key)
        return True
    except Exception as e:
        if _is_redis_connection_error(e):
            _reset_redis_pool()
        logger.warning("Cache delete failed for %s: %s", key[:50], e)
        return False


def cache_key(prefix: str, *parts: str) -> str:
    """Build cache key: prefix:part1:part2..."""
    return ":".join([prefix] + [str(p).upper() for p in parts if p])


def cached_thrive_phase2(cache_parts: tuple[str, ...], fetch_fn, force_refresh: bool = False):
    """Cache GET /api/thrive-phase2 JSON. TTL 15m. Key thrive_phase2:v1:..."""
    key = cache_key("thrive_phase2", "v1", *cache_parts)
    if not force_refresh:
        hit = get_cached(key)
        if hit is not None:
            return hit
    out = fetch_fn()
    if out and not out.get("error"):
        set_cached(key, out, TTL_THRIVE_PHASE2)
    return out


def cached_backtest(ticker: str, period: str, fetch_fn, force_refresh: bool = False):
    """Cache backtest results. TTL 24h.

    force_refresh: skip Redis read and re-run fetch_fn (use after code changes or to bust stale cache).
    Still writes the new result to Redis on success.

    Key includes v3 — excess vs benchmark, live parity, walk-forward on API payload.
    """
    key = cache_key("backtest", "v3", ticker, period)
    if not force_refresh:
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


def cached_general_news(fetch_fn):
    """Cache FMP general-latest feed. TTL 1h."""
    key = cache_key("general_news", "latest")
    hit = get_cached(key)
    if hit is not None:
        return hit
    out = fetch_fn()
    if out is not None and isinstance(out, list):
        set_cached(key, out, TTL_NEWS_GENERAL)
    return out


def cached_stock_news_articles(ticker: str, fetch_fn):
    """Cache raw stock news articles per ticker. TTL 1h."""
    key = cache_key("stock_news_articles", ticker.upper())
    hit = get_cached(key)
    if hit is not None:
        return hit
    out = fetch_fn()
    if out is not None and isinstance(out, list):
        set_cached(key, out, TTL_NEWS_GENERAL)
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


def cached_price_target_scenarios(ticker: str, regime: str, fetch_fn):
    """Cache run_price_targets() scenario list. TTL 15 min.

    Keyed by ticker + regime bucket only (not mode/persona) — the scenario
    math (HMM tilt, ML-probability adjustment, short-interest squeeze) is
    identical across scout/swing/owner, so callers that vary by mode (e.g.
    the trade-narrative endpoint) should share one cache entry per ticker
    instead of recomputing on every persona switch.
    """
    key = cache_key("price_target_scenarios", ticker, regime)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out = fetch_fn()
    if out is not None:
        set_cached(key, out, TTL_PRICE_TARGET_SCENARIOS)
    return out


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


def cached_grades_consensus(ticker: str, fetch_fn):
    """Cache FMP grades-consensus (buy/hold/sell counts). TTL 12h."""
    key = cache_key("grades_consensus", ticker)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out, _ = fetch_fn()
    if out is not None:
        set_cached(key, out, TTL_FUNDAMENTALS)
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


def cached_fundamentals_info(ticker: str, fetch_fn) -> dict | None:
    """Cache signals.fetcher.build_fundamentals_info()'s (info, fmp_km) tuple. TTL 12h.

    build_fundamentals_info() makes 3 uncached FMP calls internally (profile, key-metrics-ttm,
    analyst-estimates) every time it's invoked — including a duplicate of the analyst-estimates
    fetch scripts/run_daily.py already makes via cached_financial_estimates(). Wrapping the whole
    call here (rather than caching each inner fetch separately) keeps signals/fetcher.py's other
    caller (_institutional_conviction_context, which passes different args) unaffected.
    """
    key = cache_key("fundamentals_info", ticker)
    hit = get_cached(key)
    if hit is not None and isinstance(hit, dict):
        return hit
    info, fmp_km = fetch_fn()
    out = {"info": info, "fmp_km": fmp_km}
    if info:
        set_cached(key, out, TTL_FUNDAMENTALS)
    return out


def cached_quarterly_income(ticker: str, fetch_fn) -> list | None:
    """Cache signals.fv_eps_history.fetch_quarterly_income()'s raw FMP rows. TTL 24h —
    quarterly financials change at most once a quarter. Used by signals/eps_normalization.py;
    a separate cache namespace from cached_eps_history_counts (which caches derived quarter
    counts, not the raw rows the EPS-normalization adjustment needs).
    """
    key = cache_key("quarterly_income", ticker)
    hit = get_cached(key)
    if hit is not None and isinstance(hit, list):
        return hit
    out = fetch_fn()
    if out is not None and isinstance(out, list):
        set_cached(key, out, 24 * 3600)
    return out


def cached_eps_history_counts(ticker: str, fetch_fn) -> dict | None:
    """Cache signals.fv_eps_history.get_eps_history_counts(). TTL 24h — quarterly EPS
    history changes at most once a quarter, so a same-day re-run should never re-hit FMP.
    """
    key = cache_key("eps_history_counts", ticker)
    hit = get_cached(key)
    if hit is not None and isinstance(hit, dict):
        return hit
    out = fetch_fn()
    if out is not None and isinstance(out, dict):
        set_cached(key, out, 24 * 3600)
    return out


def cached_earnings_quality(
    ticker: str,
    fetch_fn,
    days_to_earnings: int | None = None,
    near_earnings_days: int = 7,
) -> dict | None:
    """Cache earnings-quality analysis per ticker.

    TTL 14d normally; 1d when earnings are within `near_earnings_days` so the
    post-report statements and EPS revisions are picked up quickly.
    """
    key = cache_key("earnings_quality", "v1", ticker)
    hit = get_cached(key)
    if hit is not None and isinstance(hit, dict):
        return hit
    out = fetch_fn()
    if out is not None and isinstance(out, dict) and not out.get("error"):
        near = days_to_earnings is not None and days_to_earnings <= near_earnings_days
        ttl = TTL_EARNINGS_QUALITY_NEAR if near else TTL_EARNINGS_QUALITY
        set_cached(key, out, ttl)
    return out


def cached_institutional_bundle(ticker: str, fetch_fn) -> dict | None:
    """Cache institutional bundle (insider weighted, short float %, ownership %, 13F trend). TTL 12h.

    Underlying sources move slowly: 13F quarterly, FINRA short interest bi-weekly,
    Form 4 insiders at most daily. Bundles where every section errored are not cached.
    """
    key = cache_key("institutional_bundle", "v1", ticker)
    hit = get_cached(key)
    if hit is not None and isinstance(hit, dict):
        return hit
    out = fetch_fn()
    if out is not None and isinstance(out, dict) and out.get("ticker"):
        sections = (
            out.get("insider_weighted"),
            out.get("short_interest"),
            out.get("institutional_ownership"),
            out.get("institutional_trend"),
            out.get("edgar_13f"),
        )
        any_ok = any(
            isinstance(s, dict) and not s.get("error") for s in sections
        )
        if any_ok:
            set_cached(key, out, TTL_INSTITUTIONAL_BUNDLE)
    return out


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


TTL_OHLCV_DEFAULT = 900  # 15 min default — see get_cached_ohlcv() for why this must stay short


def _ohlcv_redis_ttl() -> int:
    """Override via OHLCV_REDIS_TTL_SECONDS (60-3600s, same bounds as the in-process OHLCV cache)."""
    raw = (os.environ.get("OHLCV_REDIS_TTL_SECONDS") or "").strip()
    if raw:
        try:
            return max(60, min(3600, int(raw)))
        except ValueError:
            pass
    return TTL_OHLCV_DEFAULT


def get_cached_ohlcv(key: str) -> Any | None:
    """
    Cross-process OHLCV cache — dedupes 5y history fetches (FMP/yfinance) across the
    backend's worker processes and survives a mid-cycle restart. Deliberately short TTL:
    the most recent bar is today's still-forming session, which is signal-critical data
    ("not cached (by design)" per this module's own docstring) — this cache only removes
    *redundant* fetches within one signal-warm interval, not the refresh cadence itself.
    """
    return get_cached(cache_key("ohlcv", key))


def set_cached_ohlcv(key: str, value: Any) -> bool:
    return set_cached(cache_key("ohlcv", key), value, _ohlcv_redis_ttl())


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


def cached_run_confidence(ticker: str, config_hash: str, fetch_fn):
    """Cache run_confidence() payload. TTL 5 min — avoids duplicate work in ticker detail + /confidence."""
    key = cache_key("confidence", ticker, config_hash)
    hit = get_cached(key)
    if hit is not None:
        return hit
    out = fetch_fn()
    if out is not None and isinstance(out, dict) and out.get("confidence") is not None:
        set_cached(key, out, TTL_CONFIDENCE)
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


def cached_edgar_insider_flow(tickers: list[str], fetch_fn, force_refresh: bool = False):
    """Cache SEC EDGAR insider flow (Form 4) by watchlist. TTL 24h (daily refresh)."""
    import hashlib
    tag = ",".join(sorted(t.strip().upper() for t in tickers if t)[:80])
    # v2: newest-first Form 4 sort + daily TTL (busts pre-fix Redis blobs stuck on June/July).
    key = cache_key("edgar_insider", "v2", hashlib.md5(tag.encode()).hexdigest()[:16])
    if not force_refresh:
        hit = get_cached(key)
        if hit is not None and isinstance(hit, dict):
            return hit
    out = fetch_fn()
    # Do not pin error payloads for a full day.
    if out and isinstance(out, dict) and not out.get("message"):
        set_cached(key, out, TTL_EDGAR_INSIDER)
    return out


def invalidate_edgar_insider_caches(tickers: list[str] | None = None) -> int:
    """Drop Form 4 flow cache (+ analysis slice/bundle) so the next load re-fetches EDGAR."""
    import hashlib
    n = 0
    if tickers:
        tag = ",".join(sorted(t.strip().upper() for t in tickers if t)[:80])
        key = cache_key("edgar_insider", "v2", hashlib.md5(tag.encode()).hexdigest()[:16])
        if delete_cached(key):
            n += 1
    else:
        r = _redis_client()
        if r is not None:
            try:
                for key in r.scan_iter(match="edgar_insider:*", count=100):
                    if delete_cached(key):
                        n += 1
            except Exception as e:
                logger.warning("invalidate_edgar_insider_caches scan failed: %s", e)
    if delete_cached("analysis:slice:insider_flow"):
        n += 1
    if delete_cached(ANALYSIS_BUNDLE_KEY):
        n += 1
    return n


def get_cached_dashboard() -> dict | None:
    """Return cached full dashboard payload if present and Redis available (TTL DASHBOARD_CACHE_TTL_SECONDS)."""
    key = cache_key("dashboard", "default")
    hit = get_cached(key)
    if hit is not None and isinstance(hit, dict) and hit.get("config") is not None:
        return hit
    return None


def get_last_dashboard_snapshot() -> dict | None:
    """Last good dashboard JSON (7d TTL) for stale-while-revalidate when fresh cache expired."""
    key = cache_key("dashboard", "last")
    hit = get_cached(key)
    if hit is not None and isinstance(hit, dict) and hit.get("config") is not None:
        return hit
    return None


DASHBOARD_FRESHNESS_META_KEY = "dashboard:freshness_meta"
DASHBOARD_FRESHNESS_META_TTL = 7 * 24 * 3600


def _persist_dashboard_freshness_meta(payload: dict) -> None:
    """Small Redis key so timestamps stay correct when the large dashboard blob is missing/evicted."""
    if not isinstance(payload, dict):
        return
    df = payload.get("data_freshness") if isinstance(payload.get("data_freshness"), dict) else {}
    meta = {
        "quotes_updated_at": df.get("quotes_updated_at"),
        "signals_updated_at": df.get("signals_updated_at"),
        "snapshot_updated_at": df.get("snapshot_updated_at"),
        "snapshot_updated_et": df.get("snapshot_updated_et"),
        "as_of_et": df.get("as_of_et"),
        "price_last_bar_date": df.get("price_last_bar_date"),
        "refresh_ts": payload.get("refresh_ts"),
        "as_of_date": payload.get("as_of_date"),
    }
    if not any(v is not None for v in meta.values()):
        return
    try:
        set_cached(DASHBOARD_FRESHNESS_META_KEY, meta, DASHBOARD_FRESHNESS_META_TTL)
    except Exception:
        pass


def get_dashboard_freshness_meta() -> dict | None:
    hit = get_cached(DASHBOARD_FRESHNESS_META_KEY)
    return hit if isinstance(hit, dict) else None


def set_cached_dashboard(payload: dict) -> bool:
    """Store full dashboard payload in Redis. TTL from _dashboard_ttl_seconds(). Also keeps 7d last snapshot."""
    _persist_dashboard_freshness_meta(payload)
    key = cache_key("dashboard", "default")
    ok = set_cached(key, payload, _dashboard_ttl_seconds())
    last_key = cache_key("dashboard", "last")
    set_cached(last_key, payload, 7 * 24 * 3600)
    if ok:
        _notify_dashboard_ws(payload)
    return ok


def _notify_dashboard_ws(payload: dict) -> None:
    try:
        from api.dashboard_hub import notify_dashboard_updated_sync

        df = payload.get("data_freshness") if isinstance(payload.get("data_freshness"), dict) else {}
        kind = str(payload.get("warm_kind") or "full")
        notify_dashboard_updated_sync(
            kind,
            refresh_ts=payload.get("refresh_ts"),
            quotes_updated_at=df.get("quotes_updated_at"),
            signals_updated_at=df.get("signals_updated_at"),
            as_of_date=payload.get("as_of_date"),
        )
    except Exception:
        pass


def merge_dashboard_cache_updates(updates: dict) -> bool:
    """Merge keys into the latest dashboard snapshot (fresh or last)."""
    payload = get_cached_dashboard() or get_last_dashboard_snapshot()
    if not payload or not isinstance(payload, dict):
        return False
    merged = dict(payload)
    merged.update(updates)
    return set_cached_dashboard(merged)


# Dedicated compact signal-universe key — written after every dashboard run.
# Much smaller than the full dashboard payload so it survives Redis memory pressure.
UNIVERSE_SIGNALS_KEY = "dashboard:universe_signals"
UNIVERSE_SIGNALS_TTL = 25 * 3600  # 25 hours — survives overnight + weekend

# Signals-panel key: full signal rows with heavy nested objects stripped.
# Written after every dashboard run so /api/dashboard/signals-panel always has data.
SIGNALS_PANEL_KEY = "dashboard:signals_panel"
SIGNALS_PANEL_TTL = 25 * 3600  # 25 hours

_SIGNALS_PANEL_STRIP = frozenset({"investor_summary", "horizons_detail", "valuation_deck"})


_UNIVERSE_KEEP_KEYS = frozenset({
    "ticker", "close", "change_pct", "composite_buy", "composite_score",
    "rsi", "rsi14", "regime", "signal", "entry_mode", "go_no_go",
    "retail_status", "model_confidence_pct", "confidence_mid",
    "sector", "market_cap_bucket", "price_change_pct", "gates_total", "error",
    "gates_passed", "gate_cleared", "gates_frozen",
})

EOD_UNIVERSE_PANEL_KEY = "dashboard:eod_universe_panel"
EOD_UNIVERSE_PANEL_TTL = 5 * 60  # 5 min — shaped rows for Signal Universe table


def get_eod_universe_panel() -> dict | None:
    """Pre-shaped Signal Universe payload (avoids re-scanning all EOD snapshots per request)."""
    return get_cached(EOD_UNIVERSE_PANEL_KEY)


def set_eod_universe_panel(payload: dict) -> bool:
    return set_cached(EOD_UNIVERSE_PANEL_KEY, payload, EOD_UNIVERSE_PANEL_TTL)


def set_universe_signals(rows: list[dict], as_of: str | None = None) -> bool:
    """
    Store compact signal rows for the universe panel. TTL 25h.
    Only keeps the fields needed by _shape_universe_rows — strips heavy nested
    objects (investor_summary, horizons_detail, etc.) that contain inf/nan floats.
    """
    compact: list[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        row: dict = {k: v for k, v in r.items() if k in _UNIVERSE_KEEP_KEYS}
        # Keep retail_status but only the gates sub-key to minimise payload
        rs = r.get("retail_status")
        if isinstance(rs, dict):
            row["retail_status"] = {
                "entry_mode": rs.get("entry_mode"),
                "gates": rs.get("gates"),
                "go_no_go": rs.get("go_no_go"),
                "gates_locked_count": rs.get("gates_locked_count"),
            }
        try:
            from signals.tracking_gate import gate_snapshot_from_row

            snap = gate_snapshot_from_row(row)
            row["gates_passed"] = snap.get("gates_passed")
            row["gates_total"] = snap.get("gates_total")
            if snap.get("go_no_go"):
                row["go_no_go"] = snap.get("go_no_go")
        except Exception:
            pass
        compact.append(row)
    payload = {"rows": compact, "as_of": as_of}
    return set_cached(UNIVERSE_SIGNALS_KEY, payload, UNIVERSE_SIGNALS_TTL)


def get_universe_signals() -> dict | None:
    """Return {rows, as_of} from the universe signal cache, or None on miss."""
    return get_cached(UNIVERSE_SIGNALS_KEY)


def set_signals_panel(rows: list[dict], as_of: str | None = None) -> bool:
    """
    Store full signal rows (heavy keys stripped) for the signals-panel endpoint. TTL 25h.
    These are the complete signal rows minus investor_summary/horizons_detail/valuation_deck,
    suitable for direct use by the SignalsTable component.
    """
    slim: list[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        slim.append({k: v for k, v in r.items() if k not in _SIGNALS_PANEL_STRIP})
    payload = {"signals": slim, "as_of": as_of}
    return set_cached(SIGNALS_PANEL_KEY, payload, SIGNALS_PANEL_TTL)


def get_signals_panel() -> dict | None:
    """Return {signals, as_of} from the signals-panel cache, or None on miss."""
    return get_cached(SIGNALS_PANEL_KEY)


# Analysis tab bundle — separate from the large dashboard payload (paper trading is heavy).
ANALYSIS_BUNDLE_KEY = "dashboard:analysis_bundle"
ANALYSIS_BUNDLE_TTL = 6 * 3600  # 6 hours

_PAPER_TRADING_STRIP = frozenset({
    "backfill", "sync_targets", "mtm_history_sync", "mtm_history_log", "fill", "mtm",
})


def _slim_analysis_bundle(bundle: dict) -> dict:
    """Drop verbose paper-trading internals; keep summary/recent/equity_curve for UI."""
    out = dict(bundle)
    pt = out.get("paper_trading")
    if isinstance(pt, dict):
        slim_pt = {k: v for k, v in pt.items() if k not in _PAPER_TRADING_STRIP}
        out["paper_trading"] = slim_pt
    return _sanitize_for_json(out)


def set_analysis_bundle(bundle: dict, refresh_ts: str | None = None) -> bool:
    """Store Analysis tab payload in Redis. TTL 6h; keyed to dashboard refresh_ts."""
    payload = {"bundle": _slim_analysis_bundle(bundle), "refresh_ts": refresh_ts}
    ok = set_cached(ANALYSIS_BUNDLE_KEY, payload, ANALYSIS_BUNDLE_TTL)
    try:
        set_analysis_slices(bundle, refresh_ts=refresh_ts)
    except Exception:
        pass
    return ok


def get_analysis_bundle(*, refresh_ts: str | None = None) -> dict | None:
    """Return cached analysis bundle, or None on miss / refresh_ts mismatch."""
    cached = get_cached(ANALYSIS_BUNDLE_KEY)
    if not cached or not isinstance(cached, dict):
        return None
    cached_ts = cached.get("refresh_ts")
    if refresh_ts and cached_ts and cached_ts != refresh_ts:
        return None
    bundle = cached.get("bundle")
    return bundle if isinstance(bundle, dict) else None


# Per-section slices — smaller Redis keys so each Analysis panel can load independently.
_ANALYSIS_SLICE_KEYS = (
    "forward_tracking",
    "model_audit",
    "paper_trading",
    "insider_flow",
    "regime_validation",
    "confidence_calibration",
    "paper_vs_backtest_drift",
    "indicator_validation",
    "indicator_comparisons",
    "fmp_plan_status",
)


def set_analysis_slice(key: str, data: Any, refresh_ts: str | None = None) -> bool:
    """Write one Analysis section to Redis."""
    payload = {"data": _sanitize_for_json(data), "refresh_ts": refresh_ts}
    return set_cached(f"analysis:slice:{key}", payload, ANALYSIS_BUNDLE_TTL)


def set_analysis_slices(bundle: dict, refresh_ts: str | None = None) -> bool:
    """Write each Analysis section to its own Redis key (avoids one giant payload)."""
    ok = True
    for key in _ANALYSIS_SLICE_KEYS:
        if key not in bundle:
            continue
        ok = set_analysis_slice(key, bundle[key], refresh_ts=refresh_ts) and ok
    return ok


def get_analysis_slice(key: str, *, refresh_ts: str | None = None) -> Any | None:
    cached = get_cached(f"analysis:slice:{key}")
    if not cached or not isinstance(cached, dict) or "data" not in cached:
        return None
    cached_ts = cached.get("refresh_ts")
    if refresh_ts and cached_ts and cached_ts != refresh_ts:
        return None
    return cached.get("data")


_CORE_ANALYSIS_SLICES = ("forward_tracking", "model_audit", "paper_trading")


def assemble_analysis_slices(*, require_all: bool = False) -> dict | None:
    """Merge slice keys into one bundle dict. Core panels need only forward_tracking + model_audit + paper_trading."""
    keys = _ANALYSIS_SLICE_KEYS if require_all else _CORE_ANALYSIS_SLICES
    out: dict[str, Any] = {"analysis_deferred": False}
    refresh_ts = None
    for key in keys:
        cached = get_cached(f"analysis:slice:{key}")
        if not cached or not isinstance(cached, dict) or "data" not in cached:
            return None
        out[key] = cached["data"]
        if cached.get("refresh_ts"):
            refresh_ts = cached["refresh_ts"]
    if require_all:
        for key in _ANALYSIS_SLICE_KEYS:
            if key in out:
                continue
            cached = get_cached(f"analysis:slice:{key}")
            if cached and isinstance(cached, dict) and "data" in cached:
                out[key] = cached["data"]
    if refresh_ts:
        out["refresh_ts"] = refresh_ts
    return out


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
        if _is_redis_connection_error(e):
            _reset_redis_pool()
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
        if _is_redis_connection_error(e):
            _reset_redis_pool()
        logger.debug("Redis EOD list failed: %s", e)
        return []


def build_eod_snapshot_index() -> list[dict]:
    """Live Redis ∪ disk EOD date index (no blob reads).

    Dashboard Force refresh often reuses a cached ``eod_snapshots`` list baked
    into the last full compute — that list can stay stuck on an old max date
    (e.g. 2026-08-02) while ``GET /api/eod/status`` already sees today's file.
    Call this on every shell serve so the UI file list matches status.
    """
    by_date: dict[str, dict] = {}
    try:
        for date_str in list_eod_dates_redis() or []:
            if not date_str or len(date_str) < 10:
                continue
            by_date[date_str] = {
                "date": date_str,
                "size_bytes": 0,
                "run_date": None,
                "tickers_count": 0,
                "universe": None,
                "source": "redis",
            }
    except Exception as e:
        logger.debug("EOD Redis index failed: %s", e)

    try:
        from config_loader import get_data_root

        eod_dir = get_data_root() / "eod"
        if eod_dir.exists():
            for p in eod_dir.glob("*.json"):
                stem = p.stem
                if len(stem) != 10 or stem[4] != "-" or stem[7] != "-":
                    continue
                try:
                    size = p.stat().st_size
                except Exception:
                    size = 0
                prev = by_date.get(stem)
                if prev is None:
                    by_date[stem] = {
                        "date": stem,
                        "size_bytes": size,
                        "run_date": None,
                        "tickers_count": 0,
                        "universe": None,
                        "source": "disk",
                    }
                else:
                    prev["size_bytes"] = size or prev.get("size_bytes") or 0
                    if prev.get("source") == "redis":
                        prev["source"] = "redis+disk"
    except Exception as e:
        logger.debug("EOD disk index failed: %s", e)

    return sorted(by_date.values(), key=lambda x: x["date"], reverse=True)


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
        if _is_redis_connection_error(e):
            _reset_redis_pool()
        logger.debug("Redis EOD delete failed for %s: %s", date_str, e)
        return False
