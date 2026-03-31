"""
Trade roadmap consistency validator & deterministic fixes (RC-1 … RC-5).

Used by api.ticker_detail after building buy/sell roadmap stages. Logging is left to
callers; this module does not call logging.basicConfig on import.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────


@dataclass
class PriceZone:
    low: float
    high: float

    def midpoint(self) -> float:
        return (self.low + self.high) / 2

    def is_single_point(
        self,
        ref_price: float | None = None,
        atr: float | None = None,
    ) -> bool:
        """Degenerate band: tiny $ span, or tiny vs price %, or vs ATR."""
        span = abs(self.high - self.low)
        if ref_price is not None and ref_price > 0:
            if span < max(0.01, 0.0001 * ref_price):
                return True
        if atr is not None and atr > 0 and span < 0.05 * atr:
            return True
        return span < 0.01

    def is_above(self, price: float) -> bool:
        return self.low > price

    def is_below(self, price: float) -> bool:
        return self.high < price


@dataclass
class BuyTier:
    label: str
    action: str
    zone: PriceZone
    condition: str
    conviction: str
    size_pct: int


@dataclass
class SellTier:
    label: str
    action: str
    zone: Optional[PriceZone]
    condition: str
    action_pct: Optional[int] = None


@dataclass
class RoadmapInput:
    ticker: str
    current_price: float
    fair_value: float
    regime_bull_pct: float
    ma50: float
    ma200: float
    week52_low: float
    week52_high: float
    atr: float
    scenario_target: float
    buy_tiers: list[BuyTier] = field(default_factory=list)
    sell_tiers: list[SellTier] = field(default_factory=list)


def _sell_action_from_stage(stage: dict[str, Any]) -> str:
    parts = [stage.get("when_to_sell"), stage.get("action")]
    return " ".join(p for p in parts if p).strip()


def trade_roadmap_stages_to_input(
    ticker: str,
    *,
    current_price: float,
    fair_value: float,
    regime_bull_pct: float,
    ma50: float,
    ma200: float,
    week52_low: float,
    week52_high: float,
    atr: float,
    scenario_target: float,
    buy_stages: list[dict[str, Any]],
    sell_stages: list[dict[str, Any]],
) -> RoadmapInput:
    """Map API-shaped buy/sell stage dicts into RoadmapInput."""
    buy_tiers: list[BuyTier] = []
    for st in buy_stages:
        lo = st.get("price_zone_low")
        hi = st.get("price_zone_high")
        if lo is None and hi is None:
            z = PriceZone(0.0, 0.0)
        else:
            z = PriceZone(float(lo or 0.0), float(hi or lo or 0.0))
        buy_tiers.append(
            BuyTier(
                label=str(st.get("label") or ""),
                action=str(st.get("when_to_act") or ""),
                zone=z,
                condition=str(st.get("condition") or ""),
                conviction=str(st.get("conviction") or ""),
                size_pct=int(st.get("position_pct") or 0),
            )
        )

    sell_tiers: list[SellTier] = []
    for st in sell_stages:
        lo, hi = st.get("price_zone_low"), st.get("price_zone_high")
        zone: Optional[PriceZone]
        if lo is None and hi is None:
            zone = None
        else:
            zone = PriceZone(float(lo or 0.0), float(hi or lo or 0.0))
        sell_tiers.append(
            SellTier(
                label=str(st.get("label") or ""),
                action=_sell_action_from_stage(st),
                zone=zone,
                condition=str(st.get("condition") or ""),
                action_pct=None,
            )
        )

    return RoadmapInput(
        ticker=ticker,
        current_price=current_price,
        fair_value=fair_value,
        regime_bull_pct=regime_bull_pct,
        ma50=ma50,
        ma200=ma200,
        week52_low=week52_low,
        week52_high=week52_high,
        atr=atr,
        scenario_target=scenario_target,
        buy_tiers=buy_tiers,
        sell_tiers=sell_tiers,
    )


def _canonical_full_target_tier(sell_tiers: list[SellTier]) -> SellTier | None:
    """When multiple 'full target' tiers exist, use the highest band (by zone.high)."""
    fts = [t for t in sell_tiers if "full" in t.action.lower() and t.zone is not None]
    if not fts:
        return None
    return max(fts, key=lambda t: (t.zone.high if t.zone else 0.0, t.zone.midpoint() if t.zone else 0.0))


def apply_fixed_zones_to_buy_stages(
    buy_stages: list[dict[str, Any]],
    buy_tiers: list[BuyTier],
) -> None:
    """Write BuyTier.zone back to buy_stages (same order)."""
    for st, bt in zip(buy_stages, buy_tiers):
        st["price_zone_low"] = round(bt.zone.low, 2)
        st["price_zone_high"] = round(bt.zone.high, 2)


def apply_fixed_zones_to_sell_stages(
    sell_stages: list[dict[str, Any]],
    sell_tiers: list[SellTier],
) -> None:
    for st, se in zip(sell_stages, sell_tiers):
        if se.zone is None:
            st["price_zone_low"] = None
            st["price_zone_high"] = None
        else:
            st["price_zone_low"] = round(se.zone.low, 2)
            st["price_zone_high"] = round(se.zone.high, 2)


# ──────────────────────────────────────────────
# Validators
# ──────────────────────────────────────────────


class RoadmapValidator:
    """
    Validates a RoadmapInput for internal consistency.
    Returns list of (issue_code, description, severity) tuples.
    """

    def validate(self, r: RoadmapInput) -> list[tuple[str, str, str]]:
        issues: list[tuple[str, str, str]] = []
        issues += self._check_target_consistency(r)
        issues += self._check_fv_sell_zones(r)
        issues += self._check_single_point_zones(r)
        issues += self._check_tail_risk_zone(r)
        issues += self._check_buy_zone_continuity(r)
        return issues

    def _check_target_consistency(self, r: RoadmapInput) -> list[tuple[str, str, str]]:
        issues: list[tuple[str, str, str]] = []
        ft = _canonical_full_target_tier(r.sell_tiers)
        if ft is None or ft.zone is None:
            return issues

        sell_full_mid = ft.zone.midpoint()
        if sell_full_mid <= 0:
            return issues
        delta_pct = abs(r.scenario_target - sell_full_mid) / sell_full_mid * 100

        if delta_pct > 3:
            issues.append(
                (
                    "RC-1",
                    f"Buy summary target ${r.scenario_target:.2f} diverges "
                    f"{delta_pct:.1f}% from sell full-target midpoint "
                    f"${sell_full_mid:.2f}. Both should derive from the same "
                    f"scenario_target value.",
                    "HIGH",
                )
            )
        return issues

    def _check_fv_sell_zones(self, r: RoadmapInput) -> list[tuple[str, str, str]]:
        issues: list[tuple[str, str, str]] = []
        for tier in r.sell_tiers:
            if tier.zone is None:
                continue
            if "partial" in tier.action.lower() or "trim" in tier.action.lower():
                if tier.zone.low < r.fair_value * 0.98:
                    issues.append(
                        (
                            "RC-2",
                            f"Sell tier '{tier.label} / {tier.action}' lower bound "
                            f"${tier.zone.low:.2f} is below fair value "
                            f"${r.fair_value:.2f}. Trim zones should start at or "
                            f"above fair value.",
                            "MEDIUM",
                        )
                    )
        return issues

    def _check_single_point_zones(self, r: RoadmapInput) -> list[tuple[str, str, str]]:
        issues: list[tuple[str, str, str]] = []
        for tier in r.buy_tiers:
            if tier.zone.is_single_point(ref_price=r.current_price, atr=r.atr):
                issues.append(
                    (
                        "RC-3",
                        f"Buy tier '{tier.label}' has single-point zone "
                        f"${tier.zone.low:.2f}–${tier.zone.high:.2f}. "
                        f"Should be a band derived from ATR.",
                        "MEDIUM",
                    )
                )
        for tier in r.sell_tiers:
            if tier.zone and tier.zone.is_single_point(ref_price=r.current_price, atr=r.atr):
                issues.append(
                    (
                        "RC-3",
                        f"Sell tier '{tier.label}' has single-point zone.",
                        "MEDIUM",
                    )
                )
        return issues

    def _check_tail_risk_zone(self, r: RoadmapInput) -> list[tuple[str, str, str]]:
        issues: list[tuple[str, str, str]] = []
        for tier in r.buy_tiers:
            tail_label = "tail" in tier.label.lower()
            tail_act = "black swan" in tier.action.lower() or "tail risk" in tier.action.lower()
            tail_cond = "black swan" in tier.condition.lower()
            if tail_label or tail_act or tail_cond:
                if tier.zone.is_above(r.current_price):
                    issues.append(
                        (
                            "RC-4",
                            f"Tail risk buy zone ${tier.zone.low:.2f}–"
                            f"${tier.zone.high:.2f} is ABOVE current price "
                            f"${r.current_price:.2f}. Tail risk zones must be "
                            f"below current price.",
                            "HIGH",
                        )
                    )
        return issues

    def _check_buy_zone_continuity(self, r: RoadmapInput) -> list[tuple[str, str, str]]:
        issues: list[tuple[str, str, str]] = []
        actionable = [
            t
            for t in r.buy_tiers
            if t.action not in ("Watch only",) and t.size_pct > 0
        ]
        for i in range(1, len(actionable)):
            prev = actionable[i - 1]
            curr = actionable[i]
            ph, ch = prev.zone.high, curr.zone.high
            if ph is None or ph <= 0:
                issues.append(
                    (
                        "RC-5",
                        f"Buy tier '{prev.label}' has invalid upper bound for continuity check.",
                        "LOW",
                    )
                )
                continue
            jump_pct = (ch - ph) / ph * 100
            if jump_pct > 20:
                issues.append(
                    (
                        "RC-5",
                        f"Buy zone upper bound jumps {jump_pct:.1f}% between "
                        f"'{prev.label}' (${ph:.2f}) and "
                        f"'{curr.label}' (${ch:.2f}). "
                        f"Add an intermediate tier or add a condition note explaining "
                        f"the wider zone.",
                        "LOW",
                    )
                )
        return issues


# ──────────────────────────────────────────────
# Auto-fixers
# ──────────────────────────────────────────────


class RoadmapFixer:
    """
    Applies deterministic fixes to a RoadmapInput in-place.
    Each fix is idempotent and logs what changed.
    """

    def fix_all(self, r: RoadmapInput) -> RoadmapInput:
        self._fix_target_consistency(r)
        self._fix_fv_sell_zones(r)
        self._fix_single_point_zones(r)
        self._fix_tail_risk_zone(r)
        return r

    def _fix_target_consistency(self, r: RoadmapInput) -> None:
        ft = _canonical_full_target_tier(r.sell_tiers)
        if ft is None or ft.zone is None:
            log.warning("RC-1: No full target sell tier found — cannot fix.")
            return

        sell_mid = ft.zone.midpoint()
        if sell_mid <= 0:
            return
        if abs(r.scenario_target - sell_mid) / sell_mid > 0.03:
            log.info(
                "RC-1 FIX [%s]: scenario_target $%.2f → $%.2f (aligned to sell full-target band)",
                r.ticker,
                r.scenario_target,
                sell_mid,
            )
            r.scenario_target = round(sell_mid, 2)

    def _fix_fv_sell_zones(self, r: RoadmapInput) -> None:
        fv = r.fair_value
        for tier in r.sell_tiers:
            if tier.zone is None:
                continue
            if "partial" in tier.action.lower() or "trim" in tier.action.lower():
                if tier.zone.low < fv * 0.98:
                    old_low = tier.zone.low
                    original_width = tier.zone.high - old_low
                    tier.zone.low = round(fv, 2)
                    tier.zone.high = round(fv + original_width, 2)
                    log.info(
                        "RC-2 FIX [%s] '%s': zone.low $%.2f → $%.2f (floored at fair value, width preserved)",
                        r.ticker,
                        tier.label,
                        old_low,
                        tier.zone.low,
                    )

    def _fix_single_point_zones(self, r: RoadmapInput) -> None:
        half_band = round(r.atr * 0.5, 2)
        for tier in r.buy_tiers:
            if tier.zone.is_single_point(ref_price=r.current_price, atr=r.atr):
                mid = (tier.zone.low + tier.zone.high) / 2
                tier.zone.low = round(mid - half_band, 2)
                tier.zone.high = round(mid + half_band, 2)
                log.info(
                    "RC-3 FIX [%s] buy '%s': expanded to $%.2f–$%.2f (±0.5 ATR)",
                    r.ticker,
                    tier.label,
                    tier.zone.low,
                    tier.zone.high,
                )
        for tier in r.sell_tiers:
            if tier.zone and tier.zone.is_single_point(ref_price=r.current_price, atr=r.atr):
                mid = (tier.zone.low + tier.zone.high) / 2
                tier.zone.low = round(mid - half_band, 2)
                tier.zone.high = round(mid + half_band, 2)
                log.info("RC-3 FIX [%s] sell '%s': single-point expanded", r.ticker, tier.label)

    def _fix_tail_risk_zone(self, r: RoadmapInput) -> None:
        for tier in r.buy_tiers:
            tail_label = "tail" in tier.label.lower()
            tail_act = "black swan" in tier.action.lower() or "tail risk" in tier.action.lower()
            tail_cond = "black swan" in tier.condition.lower()
            if not (tail_label or tail_act or tail_cond):
                continue
            if tier.zone.is_above(r.current_price):
                correct_high = round(r.current_price - r.atr, 2)
                correct_low = round(r.current_price - 3 * r.atr, 2)
                log.info(
                    "RC-4 FIX [%s] tail risk zone: $%.2f–$%.2f → $%.2f–$%.2f",
                    r.ticker,
                    tier.zone.low,
                    tier.zone.high,
                    correct_low,
                    correct_high,
                )
                tier.zone.low = correct_low
                tier.zone.high = correct_high


# ──────────────────────────────────────────────
# Serialization helpers
# ──────────────────────────────────────────────


def issues_to_json(issues: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    return [
        {"code": c, "description": d, "severity": s}
        for c, d, s in issues
    ]


def print_validation_report(ticker: str, issues: list[tuple[str, str, str]]) -> None:
    """CLI-friendly report (ASCII; safe on all consoles)."""
    root_causes = {
        "RC-1": "scenario_target computed before sell tiers finalized — "
        "two code paths set target independently",
        "RC-2": "sell zone generator not anchored to fair_value — "
        "uses raw scenario multiplier without FV floor",
        "RC-3": "current-price snapshot passed as low=high — "
        "ATR band expansion never applied for 'Today' row",
        "RC-4": "tail risk zone uses week52_low anchor which can be > "
        "current_price in a sharp drawdown — sign logic inverted",
        "RC-5": "buy tier upper bounds set independently per horizon — "
        "no cross-tier continuity check at generation time",
    }

    print(f"\n{'=' * 60}")
    print(f"  ROADMAP VALIDATION REPORT — {ticker}")
    print(f"{'=' * 60}")

    if not issues:
        print("  OK — No issues found.")
        return

    for code, desc, severity in issues:
        mark = "[HIGH]" if severity == "HIGH" else "[MED ]" if severity == "MEDIUM" else "[LOW ]"
        print(f"\n  {mark} [{severity}] {code}")
        print(f"     Issue    : {desc}")
        print(f"     Root cause: {root_causes.get(code, 'See code')}")

    print(f"\n  Total issues: {len(issues)}")
    print(f"{'=' * 60}\n")


def apply_roadmap_consistency(
    ticker: str,
    buy_stages: list[dict[str, Any]],
    sell_stages: list[dict[str, Any]],
    *,
    current_price: float,
    fair_value: float,
    regime_bull_pct: float,
    ma50: float,
    ma200: float,
    week52_low: float,
    week52_high: float,
    atr: float,
    scenario_target: float,
    apply_fixes: bool = True,
) -> dict[str, Any]:
    """
    Validate and optionally fix roadmap stages in place.

    Returns metadata dict: issues_before, issues_after, fixes_applied, scenario_target.
    """
    inp = trade_roadmap_stages_to_input(
        ticker,
        current_price=current_price,
        fair_value=fair_value,
        regime_bull_pct=regime_bull_pct,
        ma50=ma50,
        ma200=ma200,
        week52_low=week52_low,
        week52_high=week52_high,
        atr=atr,
        scenario_target=scenario_target,
        buy_stages=buy_stages,
        sell_stages=sell_stages,
    )
    validator = RoadmapValidator()
    before = validator.validate(inp)
    scenario_aligned = scenario_target
    st0 = float(scenario_target)

    if not apply_fixes:
        return {
            "issues": issues_to_json(before),
            "issues_before_fix": issues_to_json(before),
            "fixes_applied": False,
            "roadmap_auto_adjusted": False,
            "scenario_target": round(scenario_aligned, 2),
            "scenario_target_aligned": len([x for x in before if x[0] == "RC-1"]) == 0,
        }

    fixer = RoadmapFixer()
    fixer.fix_all(inp)
    apply_fixed_zones_to_buy_stages(buy_stages, inp.buy_tiers)
    apply_fixed_zones_to_sell_stages(sell_stages, inp.sell_tiers)
    after = validator.validate(inp)
    scenario_aligned = inp.scenario_target

    jb, ja = issues_to_json(before), issues_to_json(after)
    data_changed = jb != ja or abs(st0 - float(scenario_aligned)) > 1e-6

    return {
        "issues": ja,
        "issues_before_fix": jb,
        "fixes_applied": len(before) > len(after) or before != after,
        "roadmap_auto_adjusted": bool(data_changed),
        "scenario_target": round(float(scenario_aligned), 2),
        "scenario_target_aligned": len([x for x in after if x[0] == "RC-1"]) == 0,
    }
