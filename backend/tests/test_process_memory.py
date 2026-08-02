"""Tests for in-process memory hygiene."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest


def test_ohlcv_cache_evicts_expired_entries():
    from signals import fetcher

    fetcher._ohlcv_store.clear()
    old_ts = time.monotonic() - 9999
    fetcher._ohlcv_store["stale:SPY:5y"] = fetcher._CacheEntry(value="series", ts=old_ts)
    fetcher._ohlcv_store["fresh:QQQ:5y"] = fetcher._CacheEntry(value="series2", ts=time.monotonic())

    stats = fetcher.prune_ohlcv_cache()

    assert "stale:SPY:5y" not in fetcher._ohlcv_store
    assert "fresh:QQQ:5y" in fetcher._ohlcv_store
    assert stats["expired_removed"] >= 1


def test_ohlcv_cache_lru_cap():
    from signals import fetcher

    fetcher._ohlcv_store.clear()
    with patch.object(fetcher, "_ohlcv_cache_max_entries", return_value=3):
        now = time.monotonic()
        for i in range(5):
            fetcher._ohlcv_store[f"k{i}"] = fetcher._CacheEntry(value=i, ts=now + i * 0.001)
        fetcher.prune_ohlcv_cache()
        assert len(fetcher._ohlcv_store) <= 3


def test_hmm_model_cache_trim():
    from signals import hmm_regime

    hmm_regime._MODEL_MEMORY_CACHE.clear()
    for i in range(10):
        hmm_regime._store_hmm_in_cache(f"T{i}", object())
    with patch.object(hmm_regime, "_hmm_cache_max", return_value=4):
        hmm_regime._MODEL_MEMORY_CACHE.clear()
        for i in range(10):
            hmm_regime._store_hmm_in_cache(f"T{i}", object())
        assert len(hmm_regime._MODEL_MEMORY_CACHE) == 4


def test_release_process_caches_returns_stats():
    from signals.process_memory import release_process_caches

    stats = release_process_caches(aggressive=False)
    assert "ohlcv" in stats
    assert "info" in stats
    assert "gc_collected" in stats


def test_process_rss_snapshot_keys():
    from signals.process_memory import process_rss_snapshot

    snap = process_rss_snapshot()
    assert "rss_mb" in snap
    assert "rss_mb_peak" in snap


def test_release_process_caches_aggressive_clears_yfinance():
    from signals.process_memory import release_process_caches

    stats = release_process_caches(aggressive=True)
    assert "yfinance" in stats
    assert "rss_mb" in stats or "rss_mb_after" in stats


def test_info_cache_evicts_expired_and_caps():
    from signals import fetcher

    fetcher._info_store.clear()
    old_ts = time.monotonic() - 9999
    fetcher._info_store["info:OLD"] = fetcher._CacheEntry(value={"x": 1}, ts=old_ts)
    fetcher._info_store["info:NEW"] = fetcher._CacheEntry(value={"y": 2}, ts=time.monotonic())

    stats = fetcher.prune_info_cache()
    assert "info:OLD" not in fetcher._info_store
    assert "info:NEW" in fetcher._info_store
    assert stats["expired_removed"] >= 1


def test_info_cache_get_deletes_expired():
    from signals import fetcher

    fetcher._info_store.clear()
    fetcher._info_store["info:STALE"] = fetcher._CacheEntry(value={"a": 1}, ts=time.monotonic() - 9999)
    hit, _ = fetcher._info_cache_get("info:STALE")
    assert hit is False
    assert "info:STALE" not in fetcher._info_store


def test_fmp_ohlcv_uses_shared_cache():
    from unittest.mock import patch

    import pandas as pd

    from signals import fetcher, providers

    fetcher._ohlcv_store.clear()
    idx = pd.date_range("2020-01-01", periods=120, freq="B")
    df = pd.DataFrame({"adjClose": range(120), "volume": range(120)}, index=idx)
    cfg = {"data": {"fmp_api_key": "test-key"}}

    with patch.object(providers, "_load_fmp_historical_df", return_value=df) as mock_load:
        c1, v1 = providers.fetch_ohlcv_close_and_volume("AAPL", "5y", cfg)
        c2, v2 = providers.fetch_ohlcv_close_and_volume("AAPL", "5y", cfg)
        assert c1 is not None and c2 is not None
        assert mock_load.call_count == 1
