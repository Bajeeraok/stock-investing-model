"""Opportunities bundle config gate."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_opportunities_bundle_disabled_skips_scan():
    from api.routers.dashboard import compute_opportunities_bundle

    with patch("api.routers.dashboard._load_config", return_value={"opportunities_bundle_enabled": False}):
        out = compute_opportunities_bundle()
    assert out is not None
    assert out["enabled"] is False
    assert out["opportunities"] == []
    assert out["portfolio_doctor_recommendations"] == {}


def test_opportunities_bundle_enabled_flag():
    from api.routers.dashboard import _opportunities_bundle_enabled

    assert _opportunities_bundle_enabled({"opportunities_bundle_enabled": False}) is False
    assert _opportunities_bundle_enabled({"opportunities_bundle_enabled": True}) is True
    assert _opportunities_bundle_enabled({}) is True
    assert _opportunities_bundle_enabled({"opportunities_bundle_enabled": "off"}) is False
