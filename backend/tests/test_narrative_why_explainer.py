"""Tests for the Why-panel plain-English explainer — a second, guarded LLM call
(separate from the top-summary trading note) that translates gate checks, execution
targets, and gate-linked catalysts into plain prose. Same number/jargon guard
infrastructure as the existing Layer 3 narrative, own cache namespace and own
structural contract (free prose, not the note's rigid 3-bullet format).
"""

from __future__ import annotations

from signals.narrative_waterfall import (
    NarrativeEngine,
    build_model_checks,
    build_summary,
    build_why_explainer_prompt,
    derive_action_contract,
    derive_catalysts,
    example_packet_amzn,
    guard_zone_claim,
    render_retail_scan,
    why_explainer_structure_errors,
)

GOOD_EXPLAINER = (
    "AMZN clears comfortably on valuation, sitting well below where the model thinks fair "
    "value should be. The market has not yet confirmed a broad bull phase for this stock "
    "specifically, and short-term momentum is still choppy, so the plan calls for a smaller "
    "starter position rather than full size for now. The buy zone reflects where that discount "
    "is deep enough to matter, the target is the level where the plan pays off, and the exit "
    "level is where the setup would be considered broken."
)


def _packet_bits():
    p = example_packet_amzn()
    contract = derive_action_contract(p)
    cats = derive_catalysts(p)
    mc = build_model_checks(p, cats)
    return p, contract, cats, mc


class TestStructureErrors:
    def test_rejects_empty(self):
        assert why_explainer_structure_errors("") == ["empty response"]

    def test_rejects_too_short(self):
        errs = why_explainer_structure_errors("Valuation is fine but momentum is weak.")
        assert any("word count" in e for e in errs)

    def test_rejects_too_long(self):
        errs = why_explainer_structure_errors("word " * 250)
        assert any("word count" in e for e in errs)

    def test_rejects_bullets(self):
        errs = why_explainer_structure_errors("- " + GOOD_EXPLAINER)
        assert any("bullets" in e for e in errs)

    def test_accepts_normal_paragraph(self):
        assert why_explainer_structure_errors(GOOD_EXPLAINER) == []


class TestBuildWhyExplainerPrompt:
    def test_includes_model_checks_and_action_contract(self):
        p, contract, cats, mc = _packet_bits()
        prompt = build_why_explainer_prompt(p, contract, mc, cats)
        assert "MODEL_CHECKS" in prompt
        assert "ACTION_CONTRACT" in prompt
        assert "PACKET" in prompt

    def test_includes_retail_scan_zone_fact(self):
        """RETAIL_SCAN carries the deterministic INSIDE/ABOVE/BELOW zone line — without
        it the model has to infer spot-vs-band position itself and gets it wrong (the
        bug this whole module is guarding against, see guard_zone_claim below)."""
        p, contract, cats, mc = _packet_bits()
        scan = render_retail_scan(p, contract, cats)
        prompt = build_why_explainer_prompt(p, contract, mc, cats, retail_scan=scan)
        assert "RETAIL_SCAN" in prompt
        assert "INSIDE" in prompt or "ABOVE" in prompt or "BELOW" in prompt


class TestGuardZoneClaim:
    def test_flags_pullback_claim_when_spot_already_inside_zone(self):
        p = example_packet_amzn()
        p.spot = 250.0  # entry_band is Band(245.14, 257.52) — spot sits inside it
        text = "Wait for price to pull back into the buy zone before adding size."
        assert guard_zone_claim(text, p) != []

    def test_allows_pullback_claim_when_spot_is_actually_above_zone(self):
        p = example_packet_amzn()  # default spot=272.27 is above entry_band.hi=257.52
        text = "Wait for price to pull back into the buy zone before adding size."
        assert guard_zone_claim(text, p) == []

    def test_allows_normal_text_when_spot_is_inside_zone(self):
        p = example_packet_amzn()
        p.spot = 250.0
        assert guard_zone_claim(GOOD_EXPLAINER, p) == []


class TestGenerateWhyExplainer:
    def test_skipped_without_llm(self):
        p, contract, cats, mc = _packet_bits()
        engine = NarrativeEngine(None)
        text, status = engine.generate_why_explainer(p, contract, mc, cats)
        assert status == "skipped"
        assert text == ""

    def test_ok_then_cached(self):
        p, contract, cats, mc = _packet_bits()
        engine = NarrativeEngine(lambda system, user: GOOD_EXPLAINER)
        first_text, first_status = engine.generate_why_explainer(p, contract, mc, cats)
        second_text, second_status = engine.generate_why_explainer(p, contract, mc, cats)
        assert first_status == "ok"
        assert first_text == GOOD_EXPLAINER
        assert second_status == "cached"
        assert second_text == GOOD_EXPLAINER

    def test_rejects_invented_number_then_retries_to_ok(self):
        calls = {"n": 0}

        def llm(system: str, user: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return (
                    "AMZN's buy zone sits near $999.99, a price that does not appear anywhere "
                    "in the packet, so this response is long enough to pass the word-count check "
                    "on its own while still citing a completely invented number that the guard "
                    "should catch and reject before it ever reaches a retail trader."
                )
            return GOOD_EXPLAINER

        p, contract, cats, mc = _packet_bits()
        engine = NarrativeEngine(llm)
        text, status = engine.generate_why_explainer(p, contract, mc, cats)
        assert status == "ok"
        assert text == GOOD_EXPLAINER
        assert calls["n"] == 2

    def test_rejects_pullback_claim_when_spot_already_inside_zone_then_retries_to_ok(self):
        """Regression for the reported bug: with spot inside the buy zone, the model
        defaulted to "wait for a pullback into the zone" — factually wrong, and not
        caught by the number/jargon/structure guards since it invents no bad number."""
        calls = {"n": 0}

        def llm(system: str, user: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return (
                    "Wait for AMZN's price to pull back into the buy zone before adding any "
                    "size here, since the plan only activates once that discount reappears "
                    "and the model's confidence checks line up behind the wait a bit longer."
                )
            return GOOD_EXPLAINER

        p = example_packet_amzn()
        p.spot = 250.0  # inside entry_band (245.14, 257.52)
        contract = derive_action_contract(p)
        cats = derive_catalysts(p)
        mc = build_model_checks(p, cats)
        engine = NarrativeEngine(llm)
        scan = render_retail_scan(p, contract, cats)
        text, status = engine.generate_why_explainer(p, contract, mc, cats, retail_scan=scan)
        assert status == "ok"
        assert text == GOOD_EXPLAINER
        assert calls["n"] == 2

    def test_rejects_banned_jargon_and_falls_back_after_retries(self):
        def llm(system: str, user: str) -> str:
            # "HMM" and "margin of safety" are both on the Layer-3 banned list — this
            # response also satisfies the word-count band so only the jargon guard fires.
            return (
                "AMZN's HMM regime read is bullish enough here, and the margin of safety on "
                "valuation is wide, but momentum and confidence both need to clear before this "
                "moves from a starter position to a full-size add across the whole entry plan."
            )

        p, contract, cats, mc = _packet_bits()
        engine = NarrativeEngine(llm)
        text, status = engine.generate_why_explainer(p, contract, mc, cats)
        assert status == "fallback"
        assert text == ""


class TestBuildSummaryIncludesWhyExplainer:
    def test_present_with_working_llm(self):
        p = example_packet_amzn()

        def llm(system: str, user: str) -> str:
            if "MODEL_CHECKS" in user:
                return GOOD_EXPLAINER
            # Top-summary trading note — exact 3-bullet/emoji format it validates for.
            return (
                "\U0001f6a6 ACTION: Wait for a better entry on AMZN before adding.\n"
                "⚠️ CATALYST & DRIVER: No fresh company catalyst is driving this move today.\n"
                "\U0001f3af BUY ZONE & STOP: Stay patient for the plan's entry band and respect the hard exit."
            )

        out = build_summary(p, llm=llm)
        assert out["why_explainer_status"] == "ok"
        assert out["why_explainer"] == GOOD_EXPLAINER

    def test_skipped_without_llm(self):
        p = example_packet_amzn()
        out = build_summary(p, llm=None)
        assert out["why_explainer_status"] == "skipped"
        assert out["why_explainer"] == ""
