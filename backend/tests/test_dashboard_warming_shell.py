"""Cold-start warming shell (no 503 while first compute runs)."""
from __future__ import annotations

from api.dashboard_shell import build_warming_shell


def test_build_warming_shell_minimal():
    shell = build_warming_shell({"watchlist": ["SPY", "QQQ"], "opportunities_bundle_enabled": False})
    assert shell["warming"] is True
    assert shell["stale"] is True
    assert shell["refresh_status"] == "running"
    assert shell["signals"] == []
    assert shell["portfolio"]["total_value"] == 0
    assert shell["opportunities_bundle_enabled"] is False
    assert shell["opportunities_deferred"] is False
