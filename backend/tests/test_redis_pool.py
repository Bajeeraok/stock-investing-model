"""Redis cache must reuse a connection pool (not open a new TCP socket per get/set)."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_pool():
    from signals import cache as cache_mod

    cache_mod.close_redis_pool()
    yield
    cache_mod.close_redis_pool()


def test_get_redis_pool_returns_cached_module_pool():
    from signals import cache as cache_mod

    sentinel = object()
    cache_mod._redis_pool = sentinel  # noqa: SLF001 — intentional test hook
    assert cache_mod._get_redis_pool() is sentinel


def test_close_redis_pool_clears_module_pool():
    from signals import cache as cache_mod

    cache_mod._redis_pool = object()  # noqa: SLF001
    cache_mod.close_redis_pool()
    assert cache_mod._redis_pool is None


def test_redis_client_returns_none_without_url(monkeypatch):
    from signals import cache as cache_mod

    monkeypatch.setattr(cache_mod, "_redis_url", lambda: (None, None))
    assert cache_mod._redis_client() is None
