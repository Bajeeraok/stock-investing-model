"""
Scenario integrity — post-process price-target scenarios before UI/EV.

Enforces:
  1. Exclusive probabilities that sum to 1.0 (honest EV)
  2. Base Case is modal: P(base) >= P(bull) and P(base) >= P(bear)
  3. Bull "regime upgrade" trigger cross-checked against live HMM
  4. Specific-event copy (SI thresholds, 13G filings) fact-checked or rephrased
"""
from __future__ import annotations

from typing import Any


REGIME_GATE_PCT = 60.0  # same bar as Market Weather gate
# Short interest below this → squeeze scenario is not a factual setup for this name
SQUEEZE_MIN_SI_PCT = 0.10  # 10% of float


def _sf(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _find(scenarios: list[dict[str, Any]], scenario_type: str) -> dict[str, Any] | None:
    for s in scenarios:
        if s.get("scenario_type") == scenario_type:
            return s
        if scenario_type == "base" and s.get("is_base"):
            return s
    return None


def sanitize_event_triggers(
    scenarios: list[dict[str, Any]],
    short_interest: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Drop or rewrite scenarios that assert false ticker-specific facts."""
    si = short_interest or {}
    si_pct = si.get("short_pct")
    try:
        si_pct_f = float(si_pct) if si_pct is not None else None
    except (TypeError, ValueError):
        si_pct_f = None
    risk = str(si.get("squeeze_risk") or "")

    out: list[dict[str, Any]] = []
    for s in scenarios:
        name = str(s.get("name") or "")
        s = dict(s)

        if "Squeeze" in name or "squeeze" in name.lower():
            # Need real elevated SI — MU-class mega-caps usually fail this gate.
            si_ok = (
                si_pct_f is not None
                and si_pct_f >= SQUEEZE_MIN_SI_PCT
                and risk in ("elevated", "high", "extreme")
            )
            if not si_ok:
                # Omit rather than ship a false ">20% short interest" claim.
                continue
            pct_disp = f"{si_pct_f * 100:.1f}%"
            s["trigger"] = f"Short interest {pct_disp} of float + positive catalyst"
            s["rationale"] = (
                f"Live short interest is {pct_disp} ({risk}). A positive catalyst can force "
                "covering — this is a conditional squeeze path, not a guaranteed outcome."
            )
            s["si_note"] = f"Live SI: {pct_disp} of float ({risk})"
            s["trigger_fact_checked"] = True

        if "Institutional Exit" in name:
            # Hypothetical risk class — never imply a filing already happened.
            s["trigger"] = "Large holder reduces position (13F/13G-class risk)"
            s["rationale"] = (
                "Hypothetical downside catalyst class: a major holder trimming could pressure "
                "a high-beta name. Not a claim that a 13G/D filing has occurred."
            )
            s["trigger_fact_checked"] = True

        out.append(s)
    return out


def cross_check_regime_triggers(
    scenarios: list[dict[str, Any]],
    hmm_probs: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Cap Bull Case probability when live HMM bull % is far below the weather gate.

    A 'Regime upgrade' scenario cannot honestly sit near 45% while the same card's
    Market Weather gate reads ~0% bull.
    """
    if not hmm_probs:
        return scenarios

    bull_f = hmm_probs.get("bull")
    if bull_f is None:
        return scenarios
    bull_f = _sf(bull_f)
    bull_pct = bull_f * 100.0 if bull_f <= 1.0 else bull_f

    out: list[dict[str, Any]] = []
    for s in scenarios:
        s = dict(s)
        if s.get("scenario_type") == "bull" or s.get("name") == "Bull Case":
            # Soft ceiling: upgrade odds scale with distance to the 60% gate.
            # At 0% bull → max ~8%; at 30% bull → max ~25%; at 60%+ → uncapped here.
            if bull_pct < REGIME_GATE_PCT:
                ceiling = max(0.08, min(0.35, 0.08 + (bull_pct / REGIME_GATE_PCT) * 0.27))
                old_p = _sf(s.get("probability"), 0.05)
                if old_p > ceiling:
                    s["probability"] = round(ceiling, 4)
                    s["regime_cross_checked"] = True
            note = (
                f"Live HMM bull {bull_pct:.0f}% (gate needs {REGIME_GATE_PCT:.0f}%) — "
                "upgrade path is conditional, not current tape"
            )
            # Keep trigger scannable; put the gate cross-check in macro_note.
            s["trigger"] = (
                f"Regime upgrade + ML confirmation "
                f"(live HMM {bull_pct:.0f}% bull — conditional)"
            )
            existing = s.get("macro_note") or ""
            s["macro_note"] = f"{existing} · {note}".strip(" ·") if existing else note
        out.append(s)
    return out


def enforce_base_modal(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hard constraint: P(base) >= P(bull), P(base) >= P(bear), and P(base) >= max(others).

    A 'base case' is the modal outcome — not a tail with less weight than bull
    or an asset-specific Fed/earnings path.
    """
    scenarios = [dict(s) for s in scenarios]
    base = _find(scenarios, "base")
    bull = _find(scenarios, "bull")
    bear = _find(scenarios, "bear")
    if base is None:
        return scenarios

    def _boost_base_over(other: dict[str, Any] | None) -> None:
        if other is None:
            return
        bp = _sf(base.get("probability"), 0.05)
        op = _sf(other.get("probability"), 0.05)
        if op > bp:
            excess = op - bp
            other["probability"] = round(bp, 4)
            base["probability"] = round(bp + excess, 4)
            base["modal_enforced"] = True
            other["modal_enforced"] = True

    _boost_base_over(bull)
    _boost_base_over(bear)

    # Absolute modal: no other scenario may outrank base.
    for s in scenarios:
        if s is base:
            continue
        _boost_base_over(s)

    return scenarios


def normalize_probabilities(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Force exclusive probabilities to sum to 1.0 (honest portfolio-weighted EV)."""
    if not scenarios:
        return scenarios
    scenarios = [dict(s) for s in scenarios]
    total = sum(max(0.0, _sf(s.get("probability"))) for s in scenarios)
    if total <= 0:
        share = 1.0 / len(scenarios)
        for s in scenarios:
            s["probability"] = round(share, 4)
        return scenarios

    for s in scenarios:
        s["probability"] = max(0.0, _sf(s.get("probability")) / total)

    # Fix rounding so displayed % sum to 100
    rounded = [round(s["probability"], 4) for s in scenarios]
    drift = round(1.0 - sum(rounded), 4)
    # Prefer parking residual on base case
    base_i = next((i for i, s in enumerate(scenarios) if s.get("scenario_type") == "base" or s.get("is_base")), 0)
    rounded[base_i] = round(rounded[base_i] + drift, 4)
    for s, p in zip(scenarios, rounded):
        s["probability"] = p
        s["prob_normalized"] = True

    return scenarios


def finalize_scenarios(
    scenarios: list[dict[str, Any]],
    *,
    hmm_probs: dict[str, Any] | None = None,
    short_interest: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Full integrity pipeline — call after build + valuation guards."""
    out = sanitize_event_triggers(scenarios, short_interest)
    out = cross_check_regime_triggers(out, hmm_probs)
    out = enforce_base_modal(out)
    out = normalize_probabilities(out)
    # Re-assert modal after renorm (renorm can reintroduce bull > base if bull was large)
    out = enforce_base_modal(out)
    out = normalize_probabilities(out)
    return out


def scenario_probability_sum(scenarios: list[dict[str, Any]]) -> float:
    return round(sum(_sf(s.get("probability")) for s in scenarios), 4)


def portfolio_ev_pct(scenarios: list[dict[str, Any]]) -> float | None:
    """Σ(p × r) with exclusive probs — do NOT divide by Σp again."""
    if not scenarios:
        return None
    total_p = sum(_sf(s.get("probability")) for s in scenarios)
    if total_p <= 0:
        return None
    # If somehow not normalized, weight-normalize once for safety
    ev = sum(_sf(s.get("return_pct")) * _sf(s.get("probability")) for s in scenarios)
    if abs(total_p - 1.0) > 0.02:
        ev = ev / total_p
    return round(ev, 1)
