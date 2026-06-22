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
    assert "gc_collected" in stats
