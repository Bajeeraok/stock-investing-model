"""Tests for on-view number-guarded catalyst LLM wraps."""
from __future__ import annotations

import json

from signals.catalyst_llm_wrap import (
    CatalystWrapEngine,
    catalyst_headline_hash,
    guard_text,
    wrap_catalyst_cards,
)
from signals.narrative_waterfall import example_packet_amzn


def _card(**kwargs) -> dict:
    base = {
        "name": "earnings beat",
        "event_type": "EARNINGS_BEAT",
        "direction": "unlocks",
        "mechanism": "NVDA earnings beat expectations: revenue surpasses $40B",
        "watch": "gap hold vs fade next session",
        "horizon": "days",
        "source": "reuters.com",
        "age_label": "3h ago",
        "headline_count": 2,
        "draft_note": "NVDA · earnings beat (unlocks) — NVDA earnings beat. Advisory only — does not change bands or gates.",
    }
    base.update(kwargs)
    return base


class TestHeadlineHash:
    def test_stable_and_changes_with_title(self):
        a = catalyst_headline_hash([_card()])
        b = catalyst_headline_hash([_card()])
        assert a == b
        assert len(a) == 16
        c = catalyst_headline_hash([_card(mechanism="Different headline about NVDA earnings beat")])
        assert c != a


class TestGuard:
    def test_rejects_invented_price(self):
        allowed = {272.27, 272, 40.0, 40}
        assert guard_text("Print held vs $272.27", allowed) == []
        assert guard_text("Buy the dip at $999.99", allowed)


class TestWrapCatalystCards:
    def test_skipped_without_llm(self):
        out = wrap_catalyst_cards(
            [_card()], ticker="NVDA", asof="2026-08-18",
            packet=example_packet_amzn(), llm=None,
            engine=CatalystWrapEngine(None),
        )
        assert out["wrap_status"] == "skipped"
        assert "wrap" not in out["cards"][0]
        assert out["cards"][0]["direction"] == "unlocks"

    def test_wraps_and_caches_packet_numbers(self):
        calls = {"n": 0}

        def llm(system: str, user: str) -> str:
            calls["n"] += 1
            return json.dumps({
                "cards": [{
                    "event_type": "EARNINGS_BEAT",
                    "wrap": "Print held versus the $272.27 spot — wait on your plan, not a chase.",
                    "watch": "gap hold versus the $232.76 stop",
                }],
            })

        engine = CatalystWrapEngine(llm)
        pkt = example_packet_amzn()
        cards = [_card()]
        first = wrap_catalyst_cards(
            cards, ticker="NVDA", asof="2026-08-18", mode="swing",
            packet=pkt, llm=llm, engine=engine,
        )
        assert first["wrap_status"] == "ok"
        assert first["cards"][0]["wrap"].startswith("Print held")
        assert first["cards"][0]["direction"] == "unlocks"
        assert "$272.27" in first["cards"][0]["draft_note"]
        assert "does not change bands" in first["cards"][0]["draft_note"].lower()

        second = wrap_catalyst_cards(
            cards, ticker="NVDA", asof="2026-08-18", mode="swing",
            packet=pkt, llm=llm, engine=engine,
        )
        assert second["wrap_status"] == "cached"
        assert calls["n"] == 1

    def test_invented_price_falls_back(self):
        def llm(system: str, user: str) -> str:
            return json.dumps({
                "cards": [{
                    "event_type": "EARNINGS_BEAT",
                    "wrap": "Chase the breakout at $999.99",
                    "watch": "",
                }],
            })

        out = wrap_catalyst_cards(
            [_card()], ticker="NVDA", asof="2026-08-18",
            packet=example_packet_amzn(), llm=llm,
            engine=CatalystWrapEngine(llm, max_retries=1),
        )
        assert out["wrap_status"] == "fallback"
        assert "wrap" not in out["cards"][0]
        assert out["cards"][0]["mechanism"].startswith("NVDA earnings beat")

    def test_ignores_unknown_event_type_and_strips_fences(self):
        def llm(system: str, user: str) -> str:
            return (
                "```json\n"
                + json.dumps({
                    "cards": [
                        {"event_type": "MADE_UP", "wrap": "Ignore me.", "watch": ""},
                        {
                            "event_type": "EARNINGS_BEAT",
                            "wrap": "Qualitative follow-through vs your existing plan.",
                            "watch": "",
                        },
                    ],
                })
                + "\n```"
            )

        out = wrap_catalyst_cards(
            [_card()], ticker="NVDA", asof="2026-08-18",
            packet=example_packet_amzn(), llm=llm,
            engine=CatalystWrapEngine(llm),
        )
        assert out["wrap_status"] == "ok"
        assert out["cards"][0]["wrap"].startswith("Qualitative")
        assert len(out["cards"]) == 1
