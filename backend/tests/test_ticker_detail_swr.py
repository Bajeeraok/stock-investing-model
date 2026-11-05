import time

import signals.cache as cache


def _mem(monkeypatch):
    store = {}
    monkeypatch.setattr(cache, "get_cached", lambda k, as_json=True: store.get(k))
    monkeypatch.setattr(cache, "set_cached", lambda k, v, ttl: store.__setitem__(k, v) or True)
    return store


def test_miss_without_last_builds_and_stores_both(monkeypatch):
    store = _mem(monkeypatch)
    out = cache.cached_ticker_detail("AAA", "2y", lambda: {"ticker": "AAA", "v": 1})
    assert out == {"ticker": "AAA", "v": 1}
    assert store[cache.cache_key("ticker_detail_last", "AAA", "2y")]["v"] == 1


def test_miss_serves_last_good_and_refreshes(monkeypatch):
    store = _mem(monkeypatch)
    store[cache.cache_key("ticker_detail_last", "BBB", "2y")] = {"ticker": "BBB", "v": 1}
    out = cache.cached_ticker_detail("BBB", "2y", lambda: {"ticker": "BBB", "v": 2})
    assert out["v"] == 1 and out["served_stale"] is True
    for _ in range(50):
        if cache.cache_key("ticker_detail", "BBB", "2y") in store:
            break
        time.sleep(0.02)
    assert store[cache.cache_key("ticker_detail", "BBB", "2y")]["v"] == 2


def test_allow_stale_false_always_builds(monkeypatch):
    store = _mem(monkeypatch)
    store[cache.cache_key("ticker_detail_last", "CCC", "2y")] = {"ticker": "CCC", "v": 1}
    out = cache.cached_ticker_detail("CCC", "2y", lambda: {"ticker": "CCC", "v": 2}, allow_stale=False)
    assert out == {"ticker": "CCC", "v": 2}


def test_refresh_skipped_when_rebuild_slots_full(monkeypatch):
    import threading

    store = _mem(monkeypatch)
    monkeypatch.setattr(cache, "_DETAIL_REFRESH_SLOTS", threading.BoundedSemaphore(1))
    cache._DETAIL_REFRESH_SLOTS.acquire()
    store[cache.cache_key("ticker_detail_last", "DDD", "2y")] = {"ticker": "DDD", "v": 1}
    out = cache.cached_ticker_detail("DDD", "2y", lambda: {"ticker": "DDD", "v": 2})
    assert out["served_stale"] is True
    time.sleep(0.1)
    assert cache.cache_key("ticker_detail", "DDD", "2y") not in store
    assert cache.cache_key("ticker_detail", "DDD", "2y") not in cache._DETAIL_REFRESHING
