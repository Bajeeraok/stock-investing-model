"""Tests for signals.post_earnings_transition module."""
from __future__ import annotations

import pytest

from signals.post_earnings_transition import (
    PostEarningsSignal,
    compute_post_earnings_signal,
    _infer_direction,
    _build_note,
)


class TestInferDirection:
    def test_beat_positive_reaction(self):
        assert _infer_direction("beat", 5.0, 10.0) == "bullish"

    def test_beat_negative_reaction_sharp(self):
        assert _infer_direction("beat", -7.0, 10.0) == "bearish"

    def test_beat_flat_reaction(self):
        assert _infer_direction("beat", -1.0, 10.0) == "neutral"

    def test_miss_negative_reaction(self):
        assert _infer_direction("miss", -5.0, -10.0) == "bearish"

    def test_miss_strong_rally(self):
        assert _infer_direction("miss", 8.0, -10.0) == "bullish"

    def test_inline_flat(self):
        assert _infer_direction("inline", 0.5, 0.0) == "neutral"

    def test_inline_positive(self):
        assert _infer_direction("inline", 3.0, 0.0) == "bullish"


class TestBuildNote:
    def test_beat_note_contains_ticker(self):
        note = _build_note("NVDA", "beat", 15.0, 8.5, 2.5, 1, "bullish")
        assert "NVDA" in note
        assert "beat" in note.lower()
        assert "+15.0%" in note
        assert "+8.5%" in note

    def test_miss_note(self):
        note = _build_note("AAPL", "miss", -12.0, -5.3, 1.8, 2, "bearish")
        assert "AAPL" in note
        assert "miss" in note.lower()
        assert "negative" in note.lower()

    def test_inline_note(self):
        note = _build_note("MSFT", "inline", 0.5, 0.2, 1.1, 3, "neutral")
        assert "inline" in note.lower()
        assert "muted" in note.lower()


class TestComputePostEarningsSignal:
    def test_no_context(self):
        result = compute_post_earnings_signal("AAPL", {})
        assert not result.active

    def test_too_old(self):
        ctx = {
            "days_since_earnings": 10,
            "most_recent_earnings_date": "2026-05-01",
            "post_earnings_return_pct": 5.0,
            "post_earnings_volume_ratio": 2.0,
        }
        result = compute_post_earnings_signal("AAPL", {}, earnings_context=ctx)
        assert not result.active

    def test_recent_with_price_reaction(self):
        ctx = {
            "days_since_earnings": 2,
            "most_recent_earnings_date": "2026-05-09",
            "post_earnings_return_pct": 8.5,
            "post_earnings_volume_ratio": 2.3,
        }
        result = compute_post_earnings_signal("NVDA", {}, earnings_context=ctx)
        assert result.active
        assert result.beat_or_miss == "beat"
        assert result.signal_direction == "bullish"
        assert result.transition_note is not None
        assert "NVDA" in result.transition_note

    def test_miss_from_price_reaction(self):
        ctx = {
            "days_since_earnings": 1,
            "most_recent_earnings_date": "2026-05-10",
            "post_earnings_return_pct": -6.0,
            "post_earnings_volume_ratio": 3.0,
        }
        result = compute_post_earnings_signal("TEST", {}, earnings_context=ctx)
        assert result.active
        assert result.beat_or_miss == "miss"
        assert result.signal_direction == "bearish"

    def test_inline_from_flat_reaction(self):
        ctx = {
            "days_since_earnings": 3,
            "most_recent_earnings_date": "2026-05-08",
            "post_earnings_return_pct": 0.5,
            "post_earnings_volume_ratio": 1.2,
        }
        result = compute_post_earnings_signal("MSFT", {}, earnings_context=ctx)
        assert result.active
        assert result.beat_or_miss == "inline"
