"""Tests for behavior.push_digest — fingerprint dedupe + titles."""
from __future__ import annotations

from behavior import push_digest as pd


def test_build_push_title_story_and_trim():
    title = pd.build_push_title(
        [{"ticker": "AAPL", "story_change": "Regime UP → NEUTRAL"}],
        ["TSLA", "META"],
    )
    assert "2 story" in title or "1 story" in title
    assert "trim" in title.lower()


def test_fingerprint_dedupe_skips_second_send(tmp_path, monkeypatch):
    state = tmp_path / "push_digest_state.json"
    monkeypatch.setattr(pd, "_state_path", lambda: state)

    sent: list[tuple[str, str]] = []

    def fake_broadcast(title, body, url="/"):
        sent.append((title, body))
        return {"sent": 1, "total": 1}

    monkeypatch.setattr("api.routers.push.broadcast_web_push", fake_broadcast)

    config = {"alerts": {"web_push_enabled": True}}
    sc = [{"ticker": "SPY", "story_change": "Regime flip"}]
    first = pd.maybe_broadcast_retail_push(config, story_changes=sc, trim_tickers=["XYZ"])
    second = pd.maybe_broadcast_retail_push(config, story_changes=sc, trim_tickers=["XYZ"])

    assert first.get("ok") is True
    assert second.get("skipped") is True
    assert second.get("reason") == "duplicate_digest"
    assert len(sent) == 1


def test_empty_digest_skipped():
    out = pd.maybe_broadcast_retail_push({"alerts": {}}, story_changes=[], trim_tickers=[])
    assert out["skipped"] is True
    assert out["reason"] == "empty_digest"
