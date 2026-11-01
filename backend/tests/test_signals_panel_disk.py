import signals.cache as cache


def test_signals_panel_falls_back_to_disk_when_redis_misses(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_signals_panel_disk_path", lambda: tmp_path / "cache" / "signals_panel.json")
    store: dict = {}
    monkeypatch.setattr(cache, "set_cached", lambda k, v, ttl=None: store.__setitem__(k, v) or True)
    monkeypatch.setattr(cache, "get_cached", lambda k: store.get(k))

    assert cache.set_signals_panel([{"ticker": "AAPL", "investor_summary": {"x": 1}}], as_of="2026-10-30")
    store.clear()  # Redis key expired over the weekend

    hit = cache.get_signals_panel()
    assert hit["signals"] == [{"ticker": "AAPL"}]
    assert store[cache.SIGNALS_PANEL_KEY]["as_of"] == "2026-10-30"  # re-seeded


def test_signals_panel_ttl_covers_weekend():
    assert cache.SIGNALS_PANEL_TTL >= 3 * 86400
    assert cache.UNIVERSE_SIGNALS_TTL >= 3 * 86400
