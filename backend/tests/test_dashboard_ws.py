"""Tests for dashboard WebSocket hub."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def test_ws_public_url_from_public_api_base():
    with patch.dict(os.environ, {"PUBLIC_API_BASE_URL": "https://api.example.com"}, clear=False):
        from api.dashboard_hub import ws_public_url

        assert ws_public_url() == "wss://api.example.com/api/dashboard/ws"


def test_ws_public_url_explicit_override():
    with patch.dict(
        os.environ,
        {
            "PUBLIC_API_BASE_URL": "https://api.example.com",
            "DASHBOARD_WS_PUBLIC_URL": "wss://custom.example/ws",
        },
        clear=False,
    ):
        from api.dashboard_hub import ws_public_url

        assert ws_public_url() == "wss://custom.example/ws"


def test_notify_dashboard_updated_sync_no_clients():
    from api.dashboard_hub import notify_dashboard_updated_sync

    notify_dashboard_updated_sync("full", refresh_ts="2026-08-02T12:00:00Z")


def test_dashboard_ws_config_endpoint():
    from fastapi.testclient import TestClient

    from api.main import app

    with patch.dict(os.environ, {"PUBLIC_API_BASE_URL": "https://backend.test"}, clear=False):
        client = TestClient(app)
        res = client.get("/api/dashboard/ws-config")
        assert res.status_code == 200
        body = res.json()
        assert body["enabled"] is True
        assert body["url"] == "wss://backend.test/api/dashboard/ws"
