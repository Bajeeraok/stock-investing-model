"""
Structured “reassess” guidance: signal-based triggers, not 52w-low price floors.

Use when copy might otherwise show a tail-risk level as if it were a re-entry trigger.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ReassessLevel:
    primary_condition: str
    primary_label: str
    price_level: Optional[float]
    price_label: Optional[str]
    current_price: float
    confidence_score: float
    verdict: str

    def to_display_string(self) -> str:
        parts = [self.primary_label]
        if self.price_level and self.price_level > self.current_price:
            pct = (self.price_level - self.current_price) / self.current_price * 100
            pl = self.price_label or "level"
            parts.append(f"or price recovers toward {pl} (${self.price_level:.2f}, +{pct:.1f}%)")
        return " · ".join(parts)

    def to_dict(self) -> dict:
        return {
            "primary_condition": self.primary_condition,
            "primary_label":     self.primary_label,
            "price_level":       round(self.price_level, 2) if self.price_level else None,
            "price_label":       self.price_label,
            "current_price":     self.current_price,
            "display":           self.to_display_string(),
        }


def compute_reassess_level(
    current_price: float,
    verdict: str,
    confidence_score: float,
    ml_probability: float | None,
    pattern_score: float | None,
    hmm_bull_prob: float | None,
    ma50: float | None = None,
    ma200: float | None = None,
    week52_high: float | None = None,
    week52_low: float | None = None,
    ml_threshold: float = 0.25,
    pattern_threshold: float = 50.0,
    regime_threshold: float = 0.40,
) -> ReassessLevel:
    conditions: list[str] = []
    price_level = None
    price_label = None

    ml_weak = ml_probability is not None and ml_probability < ml_threshold
    pattern_low = pattern_score is not None and pattern_score < pattern_threshold
    regime_bear = hmm_bull_prob is not None and hmm_bull_prob < regime_threshold

    if ml_weak:
        conditions.append(
            f"ML prob crosses {ml_threshold * 100:.0f}% "
            f"(currently {ml_probability * 100:.0f}%)"  # type: ignore[union-attr]
        )

    if pattern_low:
        conditions.append(
            f"Pattern score crosses {pattern_threshold:.0f} "
            f"(currently {pattern_score:.0f})"
        )

    if regime_bear:
        conditions.append(
            f"HMM regime improves above {regime_threshold * 100:.0f}% bull "
            f"(currently {hmm_bull_prob * 100:.0f}%)"  # type: ignore[union-attr]
        )

    if not conditions:
        conditions.append("Signals hold above current thresholds for 3+ days")

    primary_condition = " OR ".join(conditions)
    primary_label = _shorten_condition(conditions, verdict)

    candidates: list[tuple[float, str]] = []

    if ma50 and ma50 > current_price * 1.005:
        candidates.append((ma50, "MA50"))
    if ma200 and ma200 > current_price * 1.005:
        candidates.append((ma200, "MA200"))

    recovery_level = current_price * 1.03
    if not candidates:
        candidates.append((recovery_level, "3% recovery"))

    candidates_above = [(p, l) for p, l in candidates if p > current_price]
    if candidates_above:
        price_level, price_label = min(candidates_above, key=lambda x: x[0])

    return ReassessLevel(
        primary_condition=primary_condition,
        primary_label=primary_label,
        price_level=price_level,
        price_label=price_label,
        current_price=current_price,
        confidence_score=confidence_score,
        verdict=verdict,
    )


def _shorten_condition(conditions: list[str], verdict: str) -> str:
    if not conditions:
        return "Monitor signal improvement"

    parts: list[str] = []
    for c in conditions:
        if "ML prob" in c:
            parts.append("ML prob ≥ 25%")
        elif "Pattern score" in c:
            parts.append("Pattern ≥ 60")
        elif "HMM regime" in c:
            parts.append("Regime improves")
        elif "hold above" in c:
            parts.append("Signals sustain 3d+")
        else:
            parts.append(c[:40])

    action = "Re-evaluate when" if verdict in ("REDUCE", "WAIT") else "Add when"
    return f"{action}: {' or '.join(parts)}"

