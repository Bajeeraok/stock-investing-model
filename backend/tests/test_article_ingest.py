"""Tests for POST /api/ingest/article — the bookmarklet clip endpoint."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from signals import manual_catalysts as mc


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "_path", lambda: tmp_path / "manual_catalysts.json")
    return TestClient(app)


def _post_raw(client: TestClient, payload: dict):
    """Mirrors the bookmarklet: raw text/plain body, not FastAPI's JSON body parsing."""
    return client.post(
        "/api/ingest/article",
        content=json.dumps(payload),
        headers={"Content-Type": "text/plain"},
    )


def test_ingest_stores_article_and_returns_ok(client):
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ARTICLE_INGEST_SECRET", None)
        res = _post_raw(client, {"ticker": "amzn", "title": "Test title", "text": "Test body text."})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["ticker"] == "AMZN"

    cards = mc.manual_cards_for_ticker("AMZN")
    assert len(cards) == 1


def test_ingest_rejects_missing_fields(client):
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ARTICLE_INGEST_SECRET", None)
        res = _post_raw(client, {"ticker": "AMZN", "title": "", "text": ""})
    assert res.status_code == 400


def test_ingest_requires_correct_secret_when_configured(client):
    with patch.dict(os.environ, {"ARTICLE_INGEST_SECRET": "s3cr3t"}, clear=False):
        bad = _post_raw(client, {"ticker": "AMZN", "title": "t", "text": "b", "secret": "wrong"})
        assert bad.status_code == 403

        ok = _post_raw(client, {"ticker": "AMZN", "title": "t", "text": "b", "secret": "s3cr3t"})
        assert ok.status_code == 200


def test_ingest_rejects_non_json_body(client):
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ARTICLE_INGEST_SECRET", None)
        res = client.post(
            "/api/ingest/article",
            content="not json",
            headers={"Content-Type": "text/plain"},
        )
    assert res.status_code == 400
