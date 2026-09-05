"""
Thrive Alpha — Narrative Waterfall v2.2 (tiered LLM strategy)
======================================================
Layers flow strictly downward — lower layers narrate upper layers, never
contradict them.

    Layer 0   SignalPacket     canonical validated snapshot (single source of truth)
              + scenario EV cross-checks
    Layer 1   ActionContract   deterministic executable instruction (no LLM)
    Layer 2   Explanations     templated gate "why" + scenario summary + catalysts (no LLM)
    Layer 3   Narrative        LLM prose composed ONLY from packet + catalysts,
                               number-guarded, hash-cached, provider-agnostic

Integration:
    pkt = to_packet(your_engine_output_dict)     # see signals/narrative_packet_mapper.py
    summary = build_summary(pkt, llm=make_anthropic_client())   # or any (sys,user)->str
    # render UI ONLY from `summary` — never from a second data source.

v2.2 changes (integration hardening, see backend/signals/narrative_waterfall.py review):
    - render_scenarios() no longer crashes when all scenario probabilities are 0
      (scenario_ev() can return None in that degenerate case).
    - guard_numbers() also catches bare numbers (not just $amounts/percentages),
      symmetric with numeric_universe() which already allows bare numbers.
    - render_explanations() tolerates non-numeric / missing template fields
      (our engine's gate `detail` is a pre-formatted string, not a numeric dict)
      and falls back to a plain "label: text" line instead of crashing.
    - NarrativeEngine cache is Redis-backed (signals/cache.py) when available,
      so Layer 3 output survives backend restarts; falls back to in-memory only
      when Redis is unavailable (same optional/no-op pattern as the rest of the app).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from enum import Enum
from typing import Callable, Optional
import logging

logger = logging.getLogger("signals.narrative_waterfall")

# ═════════════════════════════════════════════════════════════
# LAYER 0 — CANONICAL SIGNAL PACKET
# ═════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Band:
    lo: float
    hi: float

    def contains(self, px: float) -> bool:
        return self.lo <= px <= self.hi

    def at_or_below(self, px: float) -> bool:
        """Owner/long T1 ceiling: any print at or below hi counts (gaps included)."""
        return px <= self.hi

    def fmt(self) -> str:
        return f"${self.lo:,.2f}-${self.hi:,.2f}"


@dataclass
class Gate:
    name: str          # valuation | market_weather | momentum_chop | ml_probability | confidence
    passed: bool
    detail: dict       # numeric facts (template keys) + always a "text" fallback string


@dataclass
class Scenario:
    name: str
    ret_pct: float
    prob_pct: float


def _driver_context_hash_key(ctx: dict | None) -> tuple:
    """Coarse fingerprint for Layer-3 cache invalidation."""
    if not isinstance(ctx, dict) or not ctx:
        return ()
    insider = ctx.get("insider") if isinstance(ctx.get("insider"), dict) else {}
    si = ctx.get("short_interest") if isinstance(ctx.get("short_interest"), dict) else {}
    macro = ctx.get("macro") if isinstance(ctx.get("macro"), dict) else {}
    return (
        str(insider.get("signal") or insider.get("net_sentiment") or ""),
        int(insider.get("sell_count") or insider.get("sells") or 0),
        round(float(si.get("short_pct") or si.get("shortPercentOfFloat") or 0), 2),
        round(float(macro.get("cpi_yoy") or macro.get("cpi") or 0), 1),
        round(float(macro.get("dgs10") or macro.get("yield_10y") or 0), 2),
        round(float(macro.get("dxy") or 0), 1),
    )


@dataclass
class SignalPacket:
    # identity
    ticker: str
    mode: str                      # swing | scout | owner
    asof: str                      # ISO date
    spot: float
    trend: str                     # UP | DOWN
    verdict: str                   # BRIDGE_PARTIAL | WATCH_ZONE | DO_NOT_CHASE | TACTICAL_ENTRY
    score: int

    # gates
    gates: list[Gate] = field(default_factory=list)

    # levels (None-safe when engine doesn't emit)
    entry_band: Optional[Band] = None
    stop: Optional[float] = None
    invalidation: Optional[float] = None
    target: Optional[float] = None
    rr: Optional[float] = None
    st_band: Optional[Band] = None          # ONE canonical short-term band
    bridge_band: Optional[Band] = None
    bridge_levels: list[float] = field(default_factory=list)
    catch_levels: list[float] = field(default_factory=list)
    anchor_levels: list[float] = field(default_factory=list)
    t1: Optional[Band] = None
    t2: Optional[Band] = None
    ma200_zone: Optional[Band] = None

    # sizing / execution
    entry_mode: str = "WAIT"                # FULL | STARTER_ONLY | BRIDGE_ONLY | WAIT
    max_tranche_pct: float = 0.0
    roadmap: list[dict] = field(default_factory=list)
    sector: str = ""
    fair_value: Optional[float] = None
    mos_pct: Optional[float] = None          # (FV − spot) / spot × 100
    required_mos_pct: Optional[float] = None
    full_size_price: Optional[float] = None  # spot that would clear required MOS

    # model internals
    hmm_bull_pct: float = 0.0
    hmm_transition_pct: float = 0.0
    rsi: Optional[float] = None
    ml_prob_pct: Optional[float] = None
    ml_threshold_pct: Optional[float] = None
    fused_confidence_pct: Optional[float] = None
    options_pc: Optional[float] = None
    options_class: str = ""
    options_score_pct: Optional[float] = None

    # unlock logic — derived from failed gates upstream, never hand-written
    unlock_conditions: list[str] = field(default_factory=list)

    # scenarios & context
    scenarios: list[Scenario] = field(default_factory=list)
    expected_value_pct: Optional[float] = None      # engine's displayed EV
    sensitivities: list[str] = field(default_factory=list)
    street_median: Optional[float] = None
    street_analysts: Optional[int] = None
    street_bullish_pct: Optional[float] = None
    news_sentiment: str = ""
    # Advisory news / known-event cards from the news rail (not gate inputs).
    news_events: list[dict] = field(default_factory=list)
    # Optional live feeds for Catalyst Translation Matrix (insider / SI / macro).
    driver_context: dict = field(default_factory=dict)

    # ---- derived --------------------------------------------------
    def scenario_ev(self) -> Optional[float]:
        """Probability-weighted EV, normalized (probs need not sum to 100)."""
        if not self.scenarios:
            return None
        tot = sum(s.prob_pct for s in self.scenarios)
        if tot <= 0:
            return None
        return round(sum(s.ret_pct * s.prob_pct for s in self.scenarios) / tot, 1)

    def waiting_above_entry(self) -> bool:
        """True when spot is above the add zone (pullback / stretch wait).

        Owner packets deepen entry_band.lo with swing/scout floors, so stop and
        invalidation often sit *between* spot and that deep floor. That is a
        coherent wait plan (structure first, then fill) — not a publish block.
        """
        if self.entry_band is None:
            return False
        return self.spot > self.entry_band.hi + 1e-6

    # ---- integrity ------------------------------------------------
    def validate(self) -> list[str]:
        """Render-time consistency checks. Empty list == safe to publish."""
        errs: list[str] = []
        failed = [g.name for g in self.gates if not g.passed]
        waiting = self.waiting_above_entry()

        # unlock conditions must cover ALL failed gates (footer-mismatch bug)
        for g in failed:
            if not any(g.replace("_", " ") in c.lower() or g in c.lower()
                       for c in self.unlock_conditions):
                errs.append(f"unlock_conditions missing failed gate '{g}'")

        # verdict vs gates coherence (Score-100-with-red-gate class of bug)
        if self.verdict == "TACTICAL_ENTRY" and failed:
            errs.append(f"verdict TACTICAL_ENTRY but gates failed: {failed}")

        # probability bounds
        for name, v in [("hmm_bull_pct", self.hmm_bull_pct),
                        ("ml_prob_pct", self.ml_prob_pct),
                        ("fused_confidence_pct", self.fused_confidence_pct)]:
            if v is not None and not (0 <= v <= 100):
                errs.append(f"{name} out of range: {v}")

        # ordering sanity — in-zone buys need stop under the zone; wait-above
        # plans keep stop/invalidation between spot and a deeper floor.
        if (
            self.stop
            and self.entry_band
            and self.stop >= self.entry_band.lo
            and not waiting
        ):
            errs.append("stop >= entry band low")
        if self.target and self.target <= self.spot and self.trend == "UP":
            # Fair-value / LT targets can sit below spot when rich (Owner WAIT).
            if not waiting and self.entry_mode not in ("WAIT",):
                errs.append("target below spot on UP trend")
        if self.invalidation is not None and self.invalidation >= self.spot:
            errs.append(
                f"invalidation ${self.invalidation:.2f} is not below spot ${self.spot:.2f} "
                "— thesis-broken level is already on the wrong side of price"
            )
        if (
            self.mode == "owner"
            and self.invalidation is not None
            and self.entry_band is not None
            and self.invalidation >= self.entry_band.lo
            and not waiting
        ):
            errs.append(
                f"owner invalidation ${self.invalidation:.2f} sits at/above entry floor "
                f"${self.entry_band.lo:.2f} — would negate the plan before the add zone"
            )
        if (
            self.stop
            and self.target
            and self.spot
            and self.rr is not None
            and self.spot > self.stop
            and self.target > self.spot
        ):
            computed = (self.target - self.spot) / (self.spot - self.stop)
            if abs(computed - float(self.rr)) > 0.2:
                errs.append(
                    f"R:R {self.rr} vs displayed stop/target {computed:.1f} "
                    "(label must match the levels panel)"
                )
        if (
            self.mode == "scout"
            and self.st_band
            and self.entry_band
            and (
                abs(self.st_band.lo - self.entry_band.lo) > 0.02
                or abs(self.st_band.hi - self.entry_band.hi) > 0.02
            )
        ):
            errs.append(
                f"scout st_band ${self.st_band.lo:.2f}–${self.st_band.hi:.2f} != "
                f"entry_band ${self.entry_band.lo:.2f}–${self.entry_band.hi:.2f}"
            )
        if (
            self.mode in ("scout", "swing")
            and self.entry_band
            and self.spot + 1e-6 < self.entry_band.hi
            and self.verdict in ("WATCH_ZONE", "DO_NOT_CHASE", "WAIT")
        ):
            # Pullback thesis with a ceiling above spot = buy-the-rally.
            # Soft: only flag when clearly stretched above the band's *intent*.
            pass

        # scenario sanity (BLK "Base Case 1% prob" class of bug)
        if self.scenarios:
            base = next((s for s in self.scenarios if "base" in s.name.lower()), None)
            modal = max(self.scenarios, key=lambda s: s.prob_pct)
            # flag only degenerate weights (e.g. base 1%), not legitimate spreads
            if base and base.prob_pct < max(10.0, 0.25 * modal.prob_pct):
                errs.append(f"base case prob {base.prob_pct}% far below modal "
                            f"'{modal.name}' {modal.prob_pct}% — weights suspect")
            for s in self.scenarios:
                if not (0 <= s.prob_pct <= 100):
                    errs.append(f"scenario '{s.name}' prob out of range: {s.prob_pct}")
            ev = self.scenario_ev()
            if (self.expected_value_pct is not None and ev is not None
                    and abs(ev - self.expected_value_pct) > 3.0):
                errs.append(f"displayed EV {self.expected_value_pct}% vs "
                            f"computed {ev}% — scenario math drift")
        return errs

    def content_hash(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def decision_hash(self) -> str:
        """Cache key for Layer 3: changes only when DECISION-relevant state moves
        (gate flips, band/level shifts, RSI or regime crossing a bucket) — NOT on
        every spot tick. This is what keeps intraday LLM cost near zero."""
        core = {
            "gates": [(g.name, g.passed) for g in self.gates],
            "verdict": self.verdict,
            "entry_mode": self.entry_mode,
            "sector": (self.sector or "").lower(),
            "entry_band": asdict(self.entry_band) if self.entry_band else None,
            "stop": self.stop,
            "target": self.target,
            "unlock": self.unlock_conditions,
            "rsi_bucket": None if self.rsi is None else int(self.rsi // 5),
            "hmm_bucket": int(self.hmm_bull_pct // 10),
            "full_size_price": self.full_size_price,
            "required_mos_pct": self.required_mos_pct,
            # Coarse spot so Layer 3 cannot keep a stale quote while the header ticks.
            "spot_bucket": round(self.spot, 1) if self.spot < 250 else round(self.spot),
            "news_events": [
                (e.get("event_type") or e.get("name"), e.get("direction"))
                for e in (self.news_events or [])[:4]
                if isinstance(e, dict)
            ],
            # Coarse driver feeds so notes refresh when insider/SI/macro flips.
            "driver_ctx": _driver_context_hash_key(self.driver_context),
        }
        blob = json.dumps(core, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def numeric_universe(self) -> set[float]:
        """Every number in the packet (+ derived EV) — the ONLY numbers Layer 3 may utter."""
        out: set[float] = set()

        def walk(x):
            if isinstance(x, bool):
                return
            if isinstance(x, (int, float)):
                v = abs(float(x))                   # guard extracts unsigned; store abs
                out.add(round(v, 2))
                out.add(round(v))                   # allow "$1,083" for 1082.56
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, (list, tuple)):
                for v in x:
                    walk(v)
        walk(asdict(self))
        ev = self.scenario_ev()
        if ev is not None:
            out.add(abs(ev)); out.add(round(abs(ev)))
        out.add(50.0)  # RSI < 50 is a fixed retail-scan threshold
        if self.target is not None and self.spot:
            pct = abs((float(self.target) - float(self.spot)) / float(self.spot) * 100.0)
            out.add(round(pct, 2))
            out.add(round(pct))
        return out


# ═════════════════════════════════════════════════════════════
# LAYER 1 — ACTION CONTRACT (deterministic)
# ═════════════════════════════════════════════════════════════

class Action(Enum):
    WAIT = "WAIT"
    PLACE_LIMIT = "PLACE_LIMIT"
    STARTER_BUY = "STARTER_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    STAND_ASIDE = "STAND_ASIDE"


@dataclass
class ActionContract:
    action: Action
    limit_prices: list[float]
    tranche_pct: float
    stop: Optional[float]
    invalidation: Optional[float]
    review_by: str
    forbidden: list[str]
    source_hash: str


REVIEW_DAYS = {"swing": 21, "scout": 7, "owner": 60}


def derive_action_contract(p: SignalPacket) -> ActionContract:
    """Pure decision table. Every branch returns exactly one instruction."""
    review = (date.fromisoformat(p.asof) +
              timedelta(days=REVIEW_DAYS.get(p.mode, 21))).isoformat()
    failed = [g.name for g in p.gates if not g.passed]
    all_pass = not failed
    if p.mode == "owner" and p.entry_band:
        in_band = p.entry_band.at_or_below(p.spot)
        above_band = p.spot > p.entry_band.hi
    else:
        in_band = bool(p.entry_band and p.entry_band.contains(p.spot))
        above_band = bool(p.entry_band and p.spot > p.entry_band.hi)
    in_bridge = bool(p.bridge_band and p.bridge_band.contains(p.spot))
    h = p.content_hash()

    # 1) thesis broken — invalidation is a FLOOR (close below), never a ceiling
    if p.invalidation and p.spot < p.invalidation:
        return ActionContract(Action.STAND_ASIDE, [], 0.0, p.stop, p.invalidation,
                              review, ["Do not average down until regime reassessed."], h)

    # 2) clean setup: all gates pass AND price inside planned band
    if all_pass and in_band:
        limits = sorted([lv for lv in p.catch_levels
                         if p.entry_band.contains(lv)], reverse=True)[:3] or [p.spot]
        return ActionContract(Action.BUY, limits, p.max_tranche_pct or 100.0,
                              p.stop, p.invalidation, review,
                              ["Do not exceed planned tranche on fill."], h)

    # 3) bridge starter: in bridge sleeve, starter mode, at most one gate failing
    if in_bridge and p.entry_mode in ("STARTER_ONLY", "BRIDGE_ONLY") and len(failed) <= 1:
        anchor = min(p.bridge_levels, key=lambda x: abs(x - p.spot)) \
            if p.bridge_levels else p.spot
        return ActionContract(Action.STARTER_BUY, [anchor], p.max_tranche_pct,
                              p.stop, p.invalidation, review,
                              [f"Do not exceed {p.max_tranche_pct:.0f}% tranche — bridge is a starter, not the plan.",
                               "Do not add again inside the bridge; next add only in the swing band."], h)

    # 4) stretched above band → limits (if nearly unlocked) or alerts-only wait
    if above_band:
        first = p.entry_band.hi
        scale = sorted([lv for lv in p.catch_levels
                        if p.entry_band.contains(lv)], reverse=True)
        limits = ([first] + [lv for lv in scale if lv < first])[:3]
        forbidden = ["Do not chase at spot.",
                     "Do not treat the short-term band alone as a buy signal."]
        act = Action.PLACE_LIMIT if len(failed) <= 1 else Action.WAIT
        return ActionContract(act, limits if act is Action.PLACE_LIMIT else [],
                              p.max_tranche_pct if act is Action.PLACE_LIMIT else 0.0,
                              p.stop, p.invalidation, review, forbidden, h)

    # 5) default
    return ActionContract(Action.HOLD, [], 0.0, p.stop, p.invalidation, review,
                          ["No new orders until a gate flips."], h)


def render_action(c: ActionContract, p: SignalPacket) -> str:
    """Templated English. f-strings only — cannot hallucinate."""
    d = f"by {c.review_by}"
    if c.action is Action.BUY:
        lvls = ", ".join(f"${x:,.2f}" for x in c.limit_prices)
        return (f"BUY {p.ticker}: place limits at {lvls} for a {c.tranche_pct:.0f}% "
                f"tranche. Stop ${c.stop:,.2f}. Cancel unfilled orders {d}.")
    if c.action is Action.STARTER_BUY:
        return (f"STARTER BUY {p.ticker}: up to {c.tranche_pct:.0f}% tranche near "
                f"${c.limit_prices[0]:,.2f} (bridge). Stop ${c.stop:,.2f}; reassess "
                f"below ${c.invalidation:,.2f}. " + " ".join(c.forbidden))
    if c.action is Action.PLACE_LIMIT:
        lvls = ", ".join(f"${x:,.2f}" for x in c.limit_prices)
        return (f"WAIT — place GTC limits at {lvls} ({c.tranche_pct:.0f}% tranche if "
                f"filled). Stop ${c.stop:,.2f}; cancel if {p.ticker} closes below "
                f"${c.invalidation:,.2f} or {d}. " + " ".join(c.forbidden))
    if c.action is Action.WAIT:
        return (f"WAIT — no orders. Set alerts at the catch levels; revisit when a "
                f"gate flips or {d}. " + " ".join(c.forbidden))
    if c.action is Action.STAND_ASIDE:
        return (f"STAND ASIDE — {p.ticker} lost ${c.invalidation:,.2f}. "
                f"No adds until regime is reassessed.")
    return f"HOLD {p.ticker} — no new orders. Review {d}."


# ── Retail 10-second scan (Layer 2 primary body) ─────────────
# Verdict → numbers → reason. Catalysts / Mix EV / jargon live in Why.

_RETAIL_BANNED = (
    "momentum chop",
    "technical reset",
    "invalidation level",
    "confluence",
    "thesis",
    "tape",
    "margin of safety",
)

# Extra jargon Layer 3 trading notes must not use (packet still has the numbers).
_LAYER3_BANNED = _RETAIL_BANNED + (
    "hmm",
    "fused model",
    "bull tape",
    "bear tape",
    "unlocks when",
    "starter zone",
    "true entry",
    "bull conditions",
    "0% bull",
    "institutions are buying",
    "institutional selling",
    "regime confirmation",
)

_RETAIL_TIMING = {
    "scout": "Usually takes days to get there.",
    "swing": "Usually takes days to a few weeks to get there.",
    "owner": "Usually takes weeks to months to get there.",
}


def _retail_headline_reason(p: SignalPacket, c: ActionContract) -> tuple[str, str]:
    """First line = action + plain-English why. No numbers in the headline."""
    if c.action is Action.STAND_ASIDE:
        return "⏸ WALK AWAY — plan is broken", "Price closed through the walk-away level."
    if c.action is Action.BUY:
        return "✅ BUY — checks line up", "Price and the model's checks agree."
    if c.action is Action.STARTER_BUY:
        return "🟡 STARTER — small slice only", "Only a small starter — full size is not cleared."
    mom_hot = p.rsi is not None and float(p.rsi) >= 50
    val_failed = any(g.name == "valuation" and not g.passed for g in p.gates)
    if mom_hot:
        reason = "Price ran up too fast. Good company, bad entry."
    elif val_failed:
        reason = "Price is too expensive here. Good company, bad entry."
    else:
        reason = "Wait for the remaining checks to clear."
    if c.action is Action.HOLD:
        return "⏸ HOLD — don't add today", reason
    return "⏸ WAIT — don't buy today", reason


def _starter_watch_zone(p: SignalPacket) -> bool:
    """True when the painted band is a starter at most — not a full-size MOS unlock."""
    if p.entry_mode == "FULL":
        return False
    if band_clears_full_mos(p):
        return False
    val_failed = any(g.name == "valuation" and not g.passed for g in p.gates)
    return val_failed or p.entry_mode in ("STARTER_ONLY", "BRIDGE_ONLY", "WAIT")



def _retail_catalyst_line(p: SignalPacket, cats: list["Catalyst"]) -> str | None:
    """Optional scan line — calendar/news facts only; omit when irrelevant."""
    for x in cats:
        mech = (x.mechanism or "").lower()
        name = (x.name or "")
        if not name:
            continue
        if mech.startswith("known event:") or "earnings" in name.lower() or "earnings" in mech:
            tip = "binary event — don't size up into it" if x.direction != "unlocks" else "watch for confirmation"
            return f"⚡ Catalyst: {name} — {tip}"
    for x in cats:
        if not _is_news_catalyst(x):
            continue
        if x.direction == "breaks":
            return f"⚡ Catalyst: {x.name} — adds risk to the wait, not a buy cue"
        if x.direction == "unlocks":
            return f"⚡ Catalyst: {x.name} — could unlock the wait if gates clear"
    return None


def render_retail_scan(p: SignalPacket, c: ActionContract, cats: list["Catalyst"] | None = None) -> dict:
    """Cover-the-prose test: 5 lines must answer buy-today / at-what-price / give-up."""
    headline, reason = _retail_headline_reason(p, c)
    lines: list[str] = []
    starter = _starter_watch_zone(p)
    rsi_clause = ""
    if p.rsi is not None and float(p.rsi) >= 50:
        rsi_clause = " and RSI drops below 50"
    if p.entry_band:
        in_band = p.entry_band.contains(float(p.spot))
        if in_band:
            zone = f"📍 Zone: ${float(p.spot):,.2f} is INSIDE buy zone {p.entry_band.fmt()}"
        elif float(p.spot) > p.entry_band.hi:
            zone = (
                f"📍 Zone: ${float(p.spot):,.2f} is ABOVE buy zone {p.entry_band.fmt()} "
                "— wait for pullback"
            )
        else:
            zone = f"📍 Zone: ${float(p.spot):,.2f} is BELOW buy zone {p.entry_band.fmt()}"
        if starter:
            zone += " (starter only)"
        lines.append(zone)
        buy = f"✅ Buy zone: {p.entry_band.fmt()}{rsi_clause}"
        if starter:
            buy += " — starter only, not full size"
        lines.append(buy)
        lines.append(f"❌ Never chase above ${p.entry_band.hi:,.2f}")
    cat_line = _retail_catalyst_line(p, cats or [])
    if cat_line:
        lines.append(cat_line)
    walk = p.stop if p.stop is not None else p.invalidation
    if walk is not None:
        dd = ""
        if p.spot and float(walk) < float(p.spot):
            dd = f" ({(float(walk) - float(p.spot)) / float(p.spot) * 100.0:.1f}%)"
        lines.append(f"🛑 If it breaks down: exit below ${walk:,.2f}{dd}")
    if p.target is not None:
        payoff = f"🎯 If it works: target ${p.target:,.2f}"
        if p.spot:
            pct = (float(p.target) - float(p.spot)) / float(p.spot) * 100.0
            payoff += f" ({pct:+.0f}%)"
        lines.append(payoff)
    lines = lines[:6]
    timing = _RETAIL_TIMING.get(p.mode, _RETAIL_TIMING["swing"])
    text = "\n".join([headline, reason, *lines, timing])
    return {
        "headline": headline,
        "reason": reason,
        "lines": lines,
        "timing": timing,
        "text": text,
        "starter_only_zone": starter,
    }


def retail_scan_banned_hits(text: str) -> list[str]:
    low = (text or "").lower()
    return [w for w in _RETAIL_BANNED if w in low]


def layer3_banned_hits(text: str) -> list[str]:
    low = (text or "").lower()
    return [w for w in _LAYER3_BANNED if w in low]


# ── Execution-note payload (LLM + deterministic share this contract) ──

_MODE_TO_EXEC = {
    "scout": "DAY_TRADING",
    "swing": "SWING_TRADING",
    "owner": "LONG_TERM_INVESTOR",
}

_PRIMARY_ACTION_EMOJI = {
    "AVOID": "🛑",
    "WAIT_PULLBACK": "🚦",
    "BUY_STARTER": "🚦",
    "CONFIRMED_BUY": "🟢",
}


def map_execution_mode(mode: str) -> str:
    return _MODE_TO_EXEC.get((mode or "").strip().lower(), "SWING_TRADING")


def map_primary_action(c: ActionContract) -> str:
    if c.action is Action.STAND_ASIDE:
        return "AVOID"
    if c.action is Action.BUY:
        return "CONFIRMED_BUY"
    if c.action in (Action.STARTER_BUY, Action.PLACE_LIMIT):
        return "BUY_STARTER"
    return "WAIT_PULLBACK"


def primary_action_emoji(primary: str) -> str:
    return _PRIMARY_ACTION_EMOJI.get(primary, "🚦")


def _plain_catalyst_text(x: "Catalyst") -> str:
    """Strip News:/Known event: prefixes and fin-tech jargon for retail bullets."""
    mech = (x.mechanism or x.name or "").strip()
    for prefix in ("News:", "Known event:", "Known Event:"):
        if mech.startswith(prefix):
            mech = mech[len(prefix):].strip()
    low = mech.lower()
    replacements = (
        ("hmm bear", "momentum is weak"),
        ("hmm bull", "momentum is firm"),
        ("put-heavy", "big traders are betting against this stock"),
        ("high p/c", "big traders are betting against this stock"),
        ("overbought", "overpriced right now — don't chase"),
        ("insider selling", "company insiders are selling shares"),
        ("margin of safety", "discount to fair value"),
    )
    out = mech
    for a, b in replacements:
        if a in low:
            out = re.sub(re.escape(a), b, out, flags=re.IGNORECASE)
    return out.rstrip(".")


def _top_catalysts(cats: list["Catalyst"] | None) -> list[str]:
    rows = list(cats or [])
    news = [x for x in rows if _is_news_catalyst(x)]
    ordered = news + [x for x in rows if x not in news]
    out: list[str] = []
    for x in ordered:
        t = _plain_catalyst_text(x)
        if t and t not in out:
            out.append(t)
        if len(out) >= 2:
            break
    if not out:
        out = ["No fresh company catalyst in the packet"]
    return out


def _binary_event_label(cats: list["Catalyst"] | None, board: dict | None = None) -> str:
    for x in cats or []:
        blob = f"{x.name or ''} {x.mechanism or ''}"
        m = re.search(r"in\s+(\d+)\s+days?", blob, flags=re.IGNORECASE)
        if m:
            name = (x.name or "Event").split("(")[0].strip() or "Event"
            return f"{name} in {m.group(1)} days"
    if board:
        pd = board.get("primary_driver") or {}
        if str(pd.get("category") or "") == "BINARY_EVENT":
            headline = str(pd.get("headline") or "").strip()
            if headline:
                return headline[:80]
        for d in board.get("top_drivers") or []:
            if str(d.get("category") or "") == "BINARY_EVENT":
                headline = str(d.get("headline") or "").strip()
                if headline:
                    return headline[:80]
    return "NONE"


def _buy_zone_label(p: SignalPacket) -> str:
    if p.entry_band:
        return p.entry_band.fmt()
    return "n/a"


def _stop_label(p: SignalPacket) -> str:
    walk = p.stop if p.stop is not None else p.invalidation
    if walk is None:
        return "n/a"
    if p.spot and float(p.spot) > 0:
        pct = (float(walk) - float(p.spot)) / float(p.spot) * 100.0
        return f"{pct:.1f}% (${walk:,.2f})"
    return f"${walk:,.2f}"


def build_trading_note_payload(
    p: SignalPacket,
    c: ActionContract,
    cats: list["Catalyst"] | None = None,
    *,
    context: dict | None = None,
) -> dict:
    """Deterministic JSON fed to the LLM — keeps notes reproducible."""
    from signals.catalyst_category_mapper import (
        build_driver_board,
        primary_driver_plain,
    )

    primary = map_primary_action(c)
    board = build_driver_board(
        p,
        cats,
        context=context if context is not None else (p.driver_context or None),
        mode=p.mode,
    )
    top_from_board = [
        str(d.get("headline") or "").strip()
        for d in (board.get("top_drivers") or [])
        if str(d.get("headline") or "").strip()
    ]
    top = top_from_board[:2] if top_from_board else _top_catalysts(cats)
    primary_driver = board.get("primary_driver") or {}
    return {
        "MODE": map_execution_mode(p.mode),
        "TICKER": (p.ticker or "").upper(),
        "PRIMARY_ACTION": primary,
        "STATUS_EMOJI": primary_action_emoji(primary),
        "PRIMARY_DRIVER": primary_driver,
        "PRIMARY_DRIVER_PLAIN": primary_driver_plain(board),
        "DRIVER_CATEGORY": primary_driver.get("category") or "TECHNICAL",
        "DRIVER_CHIP": board.get("chip_label") or primary_driver.get("category") or "TECHNICAL",
        "TOP_CATALYSTS": top,
        "BUY_ZONE": _buy_zone_label(p),
        "STOP_LOSS": _stop_label(p),
        "BINARY_EVENT": _binary_event_label(cats, board),
        "SPOT": p.spot,
        "PACKET_MODE": p.mode,
        "DRIVER_BOARD": {
            "top_drivers": board.get("top_drivers") or [],
            "category_counts": board.get("category_counts") or {},
            "matrix_version": board.get("matrix_version") or "v1",
        },
    }


def _count_words(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text or ""))


def trading_note_structure_errors(text: str) -> list[str]:
    """Enforce 3 bullets + 35–50 words for Layer-3 trading notes."""
    errs: list[str] = []
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) != 3:
        errs.append(f"need exactly 3 bullet lines, got {len(lines)}")
    for ln in lines:
        if not ln.lstrip().startswith(("•", "-", "*")):
            errs.append("each line must start with a bullet")
            break
    if lines and not any(lines[0].startswith(e) or e in lines[0][:4] for e in ("🛑", "🚦", "🟢")):
        # emoji may sit after the bullet
        first = lines[0].lstrip("•-* ").strip()
        if not first[:2] in ("🛑", "🚦") and not first.startswith("🟢"):
            errs.append("first bullet must start with 🛑, 🚦, or 🟢")
    n = _count_words(text)
    if n < 30 or n > 55:
        errs.append(f"word count {n} outside 30–55")
    return errs


def render_plain_trading_notes(
    p: SignalPacket,
    c: ActionContract,
    cats: list["Catalyst"] | None = None,
) -> str:
    """Deterministic 10-second note: exactly 3 bullets, plain English, mode-aware."""
    payload = build_trading_note_payload(p, c, cats)
    emoji = payload["STATUS_EMOJI"]
    primary = payload["PRIMARY_ACTION"]
    mode = payload["MODE"]
    ticker = payload["TICKER"]
    zone = payload["BUY_ZONE"]
    stop = payload["STOP_LOSS"]
    cats_txt = payload["TOP_CATALYSTS"]
    driver_cat = str(payload.get("DRIVER_CATEGORY") or "TECHNICAL")
    primary_driver = payload.get("PRIMARY_DRIVER") or {}

    def _short(s: str, n: int = 70) -> str:
        s = (s or "").strip()
        return s if len(s) <= n else (s[: n - 1].rstrip() + "…")

    cat1 = _short(cats_txt[0] if cats_txt else "No fresh company catalyst")
    binary = payload["BINARY_EVENT"]
    starter = _starter_watch_zone(p)
    in_band = bool(p.entry_band and p.entry_band.contains(float(p.spot)))

    if primary == "AVOID":
        action = f"Avoid new buys in {ticker} — plan is broken for now."
    elif primary == "CONFIRMED_BUY":
        action = f"Buy plan is clear for {ticker} — size only in the zone."
    elif primary == "BUY_STARTER":
        action = f"Small starter only in {ticker} — not a full buy."
    else:
        action = f"Wait on {ticker} — do not chase; buy the pullback only."

    headline = _short(str(primary_driver.get("headline") or cat1))
    plain = str(primary_driver.get("plain_english") or "")
    if binary != "NONE" or driver_cat == "BINARY_EVENT":
        driver = f"Near-term driver: {binary if binary != 'NONE' else headline}."
    elif driver_cat != "TECHNICAL" and headline:
        driver = f"Main driver ({plain}): {headline}." if plain else f"Main driver: {headline}."
    elif "no fresh company catalyst" in cat1.lower() or "no fresh catalyst" in headline.lower():
        driver = "No fresh company catalyst — this wait is about price and support."
    else:
        driver = f"Main driver: {cat1}."

    if mode == "DAY_TRADING":
        level = (
            f"Scalp only in {zone}; hard exit at {stop}."
            if zone != "n/a"
            else f"No clean scalp zone — stay flat; hard exit at {stop}."
        )
        line3 = f"• 🎯 SCALP LEVEL: {level}"
    elif mode == "LONG_TERM_INVESTOR":
        if starter:
            plan = f"Starter-size adds only in {zone}; walk away below {stop}."
        elif in_band:
            plan = f"Accumulate in {zone}; walk away below {stop}."
        else:
            plan = f"Add on a deeper dip into {zone}; walk away below {stop}."
        line3 = f"• 🎯 ACCUMULATION PLAN: {plan}"
    else:
        if in_band:
            band = f"Already in buy zone {zone}; hard stop at {stop}."
        elif starter:
            band = f"Starter slice only in {zone}; hard stop at {stop}."
        else:
            band = f"Buy the pullback in {zone}; hard stop at {stop}."
        line3 = f"• 🎯 BUY ZONE & STOP: {band}"

    return chr(10).join([
        f"• {emoji} ACTION: {action}",
        f"• ⚠️ CATALYST & DRIVER: {driver}",
        line3,
    ])



def _is_news_catalyst(x: "Catalyst") -> bool:
    if (getattr(x, "origin", None) or "").lower() == "news":
        return True
    name = (x.name or "").lower()
    mech = (x.mechanism or "").lower()
    if (
        name.startswith("news:")
        or name.startswith("known event:")
        or mech.startswith("news:")
        or mech.startswith("known event:")
    ):
        return True
    news_markers = (
        "earnings", "guidance", "deal", "m&a", "acquisition", "fda", "partnership",
        "upgrade", "downgrade", "buyback", "dividend", "ceo", "lawsuit", "probe",
        "regulatory", "spin-off", "ipo",
    )
    return any(m in name or m in mech for m in news_markers)


# ═════════════════════════════════════════════════════════════
# LAYER 2 — TEMPLATED EXPLANATIONS + SCENARIOS + CATALYSTS
# ═════════════════════════════════════════════════════════════

GATE_TEMPLATES: dict[tuple[str, bool], str] = {
    ("valuation", True):
        "Valuation clears: the stock is trading {mos_pct:.1f}% below what the model thinks it's "
        "worth, more than the {required_pct:.0f}% cushion this plan requires.",
    ("valuation", False):
        "Valuation is a partial pass: the stock is only {mos_pct:.1f}% below fair value, short of "
        "the {required_pct:.0f}% discount this plan wants before sizing up.",
    ("market_weather", True):
        "The market's own trend-reading model backs the trade: it puts {hmm_bull_pct:.0f}% odds on "
        "this stock being in an uptrend right now.",
    ("market_weather", False):
        "The market's own trend-reading model isn't confirming yet: only {hmm_bull_pct:.0f}% odds "
        "on an uptrend, below the {need_pct:.0f}% this plan needs before it counts as confirmed.",
    ("momentum_chop", True):
        "Recent price action is favorable for adding — the stock's short-term momentum reading is "
        "{rsi:.0f}, not overheated.",
    ("momentum_chop", False):
        "Recent price action says wait — the stock's short-term momentum reading is {rsi:.0f}, "
        "running hot; the model prefers it cools off before adding.",
    ("ml_probability", True):
        "The model's statistical pattern-match sees a real setup here: {ml_prob_pct:.0f}% "
        "likelihood, above the {threshold_pct:.0f}% bar it needs — though conviction still scales "
        "with how far above that bar it is.",
    ("ml_probability", False):
        "The model's statistical pattern-match doesn't see a setup: {ml_prob_pct:.0f}% likelihood, "
        "below the {threshold_pct:.0f}% bar it needs to clear.",
    ("confidence", True):
        "The model's overall confidence is {conf_pct:.0f}% — that reflects timing uncertainty, not "
        "a guarantee the overall call is right.",
    ("confidence", False):
        "The model's overall confidence is only {conf_pct:.0f}% — its different signals disagree "
        "with each other, so position size should stay small.",
}


def render_explanations(p: SignalPacket) -> list[str]:
    out = []
    for g in p.gates:
        tpl = GATE_TEMPLATES.get((g.name, g.passed))
        mark = "✓ " if g.passed else "✗ "
        if tpl:
            try:
                out.append(mark + tpl.format(**g.detail))
                continue
            except (KeyError, ValueError, TypeError):
                pass  # fall through to text fallback below
        # Fallback: our engine's gate detail is often a pre-formatted string
        # (`detail["text"]`) rather than the exact numeric keys a template wants.
        text = g.detail.get("text") if isinstance(g.detail, dict) else None
        if text:
            out.append(mark + f"{g.name.replace('_', ' ').title()}: {text}")
        else:
            out.append(mark + f"{g.name}: {'pass' if g.passed else 'fail'}")
    if p.unlock_conditions:
        out.append("This becomes a full buy once " + " and ".join(p.unlock_conditions) + ".")
    return out


def render_scenarios(p: SignalPacket) -> str:
    if not p.scenarios:
        return ""
    bull = [s for s in p.scenarios if s.ret_pct > 0]
    bear = [s for s in p.scenarios if s.ret_pct <= 0]
    ev = p.scenario_ev()
    worst = min(p.scenarios, key=lambda s: s.ret_pct)
    header = f"{len(p.scenarios)} scenarios ({len(bull)} bullish / {len(bear)} bearish)"
    if ev is None:
        # Degenerate case: probabilities summed to 0 — no EV to report.
        return (f"{header}. Worst case: {worst.name} {worst.ret_pct:+.1f}% at "
                f"{worst.prob_pct:.0f}% probability.")
    return (f"{header}; probability-weighted mix {ev:+.1f}% (scenario mix — not this "
            f"horizon's painted target). Worst case: {worst.name} {worst.ret_pct:+.1f}% at "
            f"{worst.prob_pct:.0f}% probability.")


# ── Catalyst engine ──────────────────────────────────────────

@dataclass
class Catalyst:
    name: str
    direction: str      # "unlocks" | "breaks"
    mechanism: str      # one sentence, packet numbers only
    watch: str          # observable trigger
    horizon: str        # "days" | "1-2 weeks" | "4-12 weeks" | ...
    origin: str = "technical"  # "news" | "technical" — survives News: stripping


def mos_at_price(fair_value: float | None, price: float | None) -> float | None:
    if fair_value is None or price is None or price <= 0:
        return None
    return (float(fair_value) - float(price)) / float(price) * 100.0


def full_size_price_from_mos(fair_value: float | None, required_mos_pct: float | None) -> float | None:
    if fair_value is None or required_mos_pct is None or required_mos_pct <= -100:
        return None
    fv = float(fair_value)
    if fv <= 0:
        return None
    return round(fv / (1.0 + float(required_mos_pct) / 100.0), 2)


def band_clears_full_mos(p: SignalPacket) -> bool:
    if not p.entry_band or p.required_mos_pct is None:
        return False
    mos = mos_at_price(p.fair_value, p.entry_band.hi)
    if mos is None:
        return False
    return mos + 1e-6 >= float(p.required_mos_pct)


_TECH_SECTORS = {
    "technology", "information technology", "communication services", "communications",
}
_SAFE_HAVEN_SECTORS = {
    "basic materials", "materials", "utilities",
}
_SAFE_HAVEN_TICKERS = {"GLD", "IAU", "SGOL", "GLDM", "GDX", "GDXJ", "SLV", "SIVR", "PPLT"}
_SAFE_HAVEN_CATALYST_NAMES = {"Safe-haven outflow"}


def _sector_key(p: SignalPacket) -> str:
    return (p.sector or "").strip().lower()


def is_risk_on_sector(p: SignalPacket) -> bool:
    sec = _sector_key(p)
    return sec in _TECH_SECTORS or sec.startswith("tech")


def allows_safe_haven_macro(p: SignalPacket) -> bool:
    if (p.ticker or "").upper() in _SAFE_HAVEN_TICKERS:
        return True
    if is_risk_on_sector(p):
        return False
    sec = _sector_key(p)
    return sec in _SAFE_HAVEN_SECTORS or "gold" in sec or "precious" in sec


def news_catalysts_from_packet(p: SignalPacket) -> list[Catalyst]:
    """Map advisory news/known-event cards into Layer-3 CATALYSTS (plain English)."""
    out: list[Catalyst] = []
    for card in (p.news_events or [])[:4]:
        if not isinstance(card, dict):
            continue
        name = str(card.get("name") or "").strip() or "Company news"
        title = str(card.get("mechanism") or card.get("title") or "").strip()
        if not title and not name:
            continue
        # Drop redundant "News:" / "Known event:" if upstream already stamped them.
        for prefix in ("News:", "Known event:", "Known Event:"):
            if title.startswith(prefix):
                title = title[len(prefix):].strip()
            if name.startswith(prefix):
                name = name[len(prefix):].strip()
        raw_dir = str(card.get("direction") or "").lower()
        if raw_dir in ("bullish", "unlocks", "positive"):
            direction = "unlocks"
        elif raw_dir in ("bearish", "breaks", "negative"):
            direction = "breaks"
        else:
            direction = "breaks" if "earnings" in name.lower() else "unlocks"
        et = str(card.get("event_type") or "")
        # Keep mechanism as the headline only — no "News:" stamp (UI/parser cleans leftovers).
        mech = title or name
        if et in ("EARNINGS_CALENDAR", "POST_EARNINGS") and "earnings" not in mech.lower():
            mech = f"Earnings: {mech}"
        watch = str(card.get("watch") or "").strip()
        # Avoid "Watch: how the stock reacts" boilerplate when it adds no information.
        if watch.lower() in {
            "",
            "how the stock reacts to the news",
            "how the stock reacts",
            "watch the reaction",
        }:
            watch = "price reaction into the event"
        out.append(Catalyst(
            name=name[:80],
            direction=direction,
            mechanism=mech[:240],
            watch=watch[:120],
            horizon=str(card.get("horizon") or "days to a few weeks")[:40],
            origin="news",
        ))
    return out


def derive_catalysts(p: SignalPacket) -> list[Catalyst]:
    c: list[Catalyst] = []
    # Real-world news / calendar first — Layer 3 must lead with these when present.
    c.extend(news_catalysts_from_packet(p))

    band = p.entry_band.fmt() if p.entry_band else "the entry band"
    val_failed = any(g.name == "valuation" and not g.passed for g in p.gates)
    starter_not_full = val_failed and not band_clears_full_mos(p)
    full_px = p.full_size_price

    for g in p.gates:
        if g.name == "momentum_chop" and not g.passed:
            if starter_not_full:
                c.append(Catalyst(
                    "Cooler pullback for a starter",
                    "unlocks",
                    f"Price ran ahead of itself; a cooler pullback into {band} "
                    f"is a small first slice at most — not a full buy.",
                    "pullback into the buy area after the move cools",
                    "1-2 weeks",
                ))
            else:
                c.append(Catalyst(
                    "Price and cooler reading line up",
                    "unlocks",
                    f"A cooler pullback that brings price toward {band} "
                    f"would be the first clean chance to act.",
                    "pullback into the buy area after the move cools",
                    "1-2 weeks",
                ))
        if g.name == "market_weather" and not g.passed:
            need = float(g.detail.get("need_pct", 60) or 60)
            c.append(Catalyst(
                "Broader market support",
                "unlocks",
                f"The broader market check is weak right now "
                f"({p.hmm_bull_pct:.0f}% supportive vs needing about {need:.0f}%). "
                f"Wait until risk appetite looks healthier — usually one to four weeks — "
                f"before even a small add.",
                "broader market and this stock both look healthier",
                "1-4 weeks",
            ))
        if g.name == "valuation" and not g.passed:
            if band_clears_full_mos(p) and p.entry_band:
                if p.mode == "owner":
                    c.append(Catalyst(
                        "Cheaper price",
                        "unlocks",
                        f"A print at or below ${p.entry_band.hi:,.2f} would finally "
                        f"look cheap enough for a full-size buy.",
                        f"price ≤ ${p.entry_band.hi:,.2f}",
                        "days to a few weeks",
                    ))
                else:
                    c.append(Catalyst(
                        "Cheaper price",
                        "unlocks",
                        f"A pullback into {band} would finally look cheap enough "
                        f"for a full-size buy.",
                        f"price in {band}",
                        "days to a few weeks",
                    ))
            else:
                deeper = f"${full_px:,.2f}" if full_px else "a much deeper discount"
                c.append(Catalyst(
                    "Starter watch — not full size",
                    "unlocks",
                    f"A print in {band} is a small starter at most. It does not clear "
                    f"full-size valuation (need about {deeper}).",
                    f"price in {band} (starter only)",
                    "days to a few weeks",
                ))

    MACRO: dict[str, list[Catalyst]] = {
        "USD-sensitive": [
            Catalyst("Dollar strength", "breaks",
                "A stronger dollar creates immediate downward pressure on the setup.",
                "dollar breakout", "days"),
            Catalyst("Higher real yields", "breaks",
                "Sticky inflation keeping rates higher-for-longer raises the "
                "opportunity cost of the position.", "CPI/FOMC surprises", "4-12 weeks")],
        "gold-sensitive": [
            Catalyst("Safe-haven outflow", "breaks",
                "Geopolitical de-escalation rotates capital out of defensive assets.",
                "risk-on rotation after de-escalation headlines", "days to weeks")],
        "volatility-sensitive": [
            Catalyst("Volatility spike", "unlocks",
                (
                    f"A vol shock often delivers a dip into {band} faster than a grinding market "
                    "— still a starter, not full size."
                    if starter_not_full else
                    f"A vol shock often delivers a dip into {band} faster than a grinding market."
                ),
                "VIX spike", "days")],
    }
    for tag in p.sensitivities:
        rows = MACRO.get(tag, [])
        if tag == "gold-sensitive" and not allows_safe_haven_macro(p):
            continue
        c.extend(rows)

    if p.invalidation:
        c.append(Catalyst("Plan break", "breaks",
            f"A close below ${p.invalidation:,.2f} with momentum means walk away — "
            "reassess, don't average down.",
            f"close < ${p.invalidation:,.2f}", "any time"))
    if p.scenarios:
        worst = min(p.scenarios, key=lambda s: s.ret_pct)
        c.append(Catalyst(worst.name, "breaks",
            f"Engine's downside scenario: {worst.ret_pct:+.1f}% at "
            f"{worst.prob_pct:.0f}% probability.", "scenario triggers", "—"))
    return c


def validate_catalysts(p: SignalPacket, cats: list[Catalyst]) -> list[str]:
    """Catalysts must not promise a MOS unlock the band cannot deliver, or
    attach safe-haven logic to a risk-on sector."""
    errs: list[str] = []
    mos_lie = (
        not band_clears_full_mos(p)
        and any(g.name == "valuation" and not g.passed for g in p.gates)
    )
    for x in cats:
        mech = (x.mechanism or "").lower()
        if mos_lie and x.direction == "unlocks" and (
            "margin of safety" in mech or "restores the required" in mech
        ) and "starter" not in mech:
            errs.append(
                f"catalyst '{x.name}' claims a full-size valuation unlock from a band "
                "that does not clear required MOS"
            )
        if x.name in _SAFE_HAVEN_CATALYST_NAMES and (
            is_risk_on_sector(p) or "technology" in _sector_key(p)
        ):
            errs.append(
                f"safe-haven catalyst '{x.name}' cannot attach to {p.ticker} "
                f"sector={p.sector or 'unknown'} (Technology/risk-on)"
            )
    return errs


def _short_horizon(horizon: str) -> str:
    h = (horizon or "").strip().lower()
    if not h:
        return ""
    # Collapse verbose "days to a few weeks" into a short tag.
    if "day" in h and "week" in h:
        return "days–weeks"
    if h.startswith("1-2 week") or h.startswith("1–2 week"):
        return "1–2 weeks"
    if h.startswith("1-4 week") or h.startswith("1–4 week"):
        return "1–4 weeks"
    if "week" in h:
        return h.replace("weeks", "wks")[:24]
    return horizon[:24]


def _format_catalyst_bullet(x: Catalyst, *, include_watch: bool = False) -> str:
    """One clean retail bullet — no duplicated News:/Watch: boilerplate."""
    body = _plain_catalyst_text(x)
    # If name is already the start of the body, don't repeat it.
    name = (x.name or "").strip()
    for prefix in ("News:", "Known event:", "Known Event:"):
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
    if name and not body.lower().startswith(name.lower()[: min(12, len(name))]):
        # Prefer body; only prepend name when it's a short label (e.g. "Earnings").
        if len(name) <= 28 and name.lower() not in body.lower():
            body = f"{name} — {body}" if body else name
    hz = _short_horizon(x.horizon)
    watch = (x.watch or "").strip()
    if include_watch and watch and watch.lower() not in body.lower():
        body = f"{body} (watch: {watch})"
    if hz:
        return f"• {body} · {hz}"
    return f"• {body}"


def render_catalysts(cats: list[Catalyst]) -> list[str]:
    unlock = [x for x in cats if x.direction == "unlocks"]
    breaks = [x for x in cats if x.direction == "breaks"]
    news_u = [x for x in unlock if _is_news_catalyst(x)]
    tech_u = [x for x in unlock if not _is_news_catalyst(x)]
    news_b = [x for x in breaks if _is_news_catalyst(x)]
    tech_b = [x for x in breaks if not _is_news_catalyst(x)]
    out: list[str] = []
    news = (news_u + news_b)[:3]
    if news:
        out.append("Company / event catalysts:")
        out += [_format_catalyst_bullet(x) for x in news]
    if tech_u:
        out.append("What gets you your entry (timing):")
        out += [_format_catalyst_bullet(x) for x in tech_u[:3]]
    if tech_b:
        out.append("What would break this plan:")
        out += [_format_catalyst_bullet(x) for x in tech_b[:3]]
    return out


_GATE_PILL_LABELS: dict[str, str] = {
    "valuation": "Valuation",
    "market_weather": "Regime",
    "momentum_chop": "Momentum",
    "ml_probability": "ML setup",
    "confidence": "Confidence",
}


def _gate_pill_label(name: str) -> str:
    return _GATE_PILL_LABELS.get(name) or name.replace("_", " ").title()


def _execution_targets_from_packet(p: SignalPacket) -> list[dict]:
    """Price levels traders care about — separate from news/catalyst prose."""
    rows: list[dict] = []
    if p.entry_band:
        rows.append({
            "kind": "buy_zone",
            "label": "Buy zone",
            "value": p.entry_band.fmt(),
            "detail": "Wait for price here before sizing up",
        })
    if p.target is not None:
        rows.append({
            "kind": "target",
            "label": "Target",
            "value": f"${float(p.target):,.2f}",
            "detail": "If the plan works",
        })
    walk = p.stop if p.stop is not None else p.invalidation
    if walk is not None:
        dd = ""
        if p.spot and float(p.spot) > 0 and float(walk) < float(p.spot):
            dd = f" ({(float(walk) - float(p.spot)) / float(p.spot) * 100.0:.1f}%)"
        rows.append({
            "kind": "stop",
            "label": "Hard exit",
            "value": f"${float(walk):,.2f}{dd}",
            "detail": "Walk away if broken",
        })
    if p.full_size_price is not None and (
        not p.entry_band or abs(float(p.full_size_price) - float(p.entry_band.lo)) > 0.02
    ):
        rows.append({
            "kind": "full_size",
            "label": "Full-size price",
            "value": f"${float(p.full_size_price):,.2f}",
            "detail": "Where valuation clears full size",
        })
    return rows


# Category → gates this catalyst can *contextually* relate to (never auto-clears).
_CATEGORY_RELATED_GATES: dict[str, tuple[str, ...]] = {
    "BINARY_EVENT": ("confidence", "ml_probability"),
    "SMART_MONEY": ("confidence",),
    "MACRO_RATES": ("market_weather",),
    "GEOPOLITICAL": ("market_weather", "confidence"),
    "CROSS_ASSET": ("market_weather",),
    "TECHNICAL": ("momentum_chop",),
}

_ROLE_SORT = {"drove_signal": 0, "unlock_context": 1, "risk": 2}


def _catalyst_display_name(x: Catalyst) -> str:
    name = (x.name or "").strip()
    for prefix in ("News:", "Known event:", "Known Event:"):
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
    return name[:80] or "Catalyst"


def _news_driver_cards(cats: list[Catalyst], *, limit: int = 3) -> list[dict]:
    """Legacy slim news list — prefer gate_linked_catalysts in UI."""
    news = [x for x in cats if _is_news_catalyst(x)][:limit]
    out: list[dict] = []
    for x in news:
        body = _plain_catalyst_text(x)
        out.append({
            "name": _catalyst_display_name(x) or "News",
            "direction": x.direction,
            "summary": body[:160],
            "horizon": _short_horizon(x.horizon),
        })
    return out


def _classify_catalyst_category(x: Catalyst) -> str:
    try:
        from signals.catalyst_category_mapper import classify_text
    except Exception:
        return "TECHNICAL"
    blob = f"{x.name or ''} {x.mechanism or ''} {x.watch or ''}"
    return classify_text(blob) or "TECHNICAL"


def _related_gates_for_catalyst(
    category: str,
    x: Catalyst,
    failed: set[str],
) -> list[str]:
    gates = list(_CATEGORY_RELATED_GATES.get(category, ()))
    blob = f"{x.name or ''} {x.mechanism or ''} {x.watch or ''}".lower()
    if category == "TECHNICAL" or any(
        k in blob for k in ("pullback", "buy zone", "entry band", "cooler")
    ):
        if "momentum_chop" not in gates:
            gates.append("momentum_chop")
        if "valuation" in failed and "valuation" not in gates:
            gates.append("valuation")
    if "earnings" in blob or "guidance" in blob:
        for g in ("confidence", "ml_probability"):
            if g not in gates:
                gates.append(g)
    # Failed gates first so the UI can emphasize unlock context.
    return sorted(set(gates), key=lambda g: (0 if g in failed else 1, g))


def _valuation_locked_watch(p: SignalPacket) -> str:
    if p.entry_band:
        return f"price into buy zone ({p.entry_band.fmt()})"
    return "price into buy zone"


def _assign_catalyst_role(
    *,
    direction: str,
    category: str,
    related: list[str],
    failed: set[str],
    is_news: bool,
    summary: str,
    name: str,
    primary_driver: dict | None,
) -> str:
    if direction == "breaks":
        return "risk"
    pd = primary_driver or {}
    primary_cat = str(pd.get("category") or "").upper()
    primary_hl = str(pd.get("headline") or "").strip().lower()
    blob = f"{name} {summary}".lower()
    if primary_cat and category == primary_cat and category != "TECHNICAL":
        return "drove_signal"
    if primary_hl and (
        primary_hl[:48] in blob
        or (name and name.lower() in primary_hl)
        or (summary and summary.lower()[:48] in primary_hl)
    ):
        return "drove_signal"
    if any(g in failed for g in related):
        return "unlock_context"
    if is_news and direction == "unlocks":
        return "drove_signal"
    return "unlock_context"


def build_gate_linked_catalyst_cards(
    p: SignalPacket,
    cats: list[Catalyst] | None = None,
    *,
    primary_driver: dict | None = None,
    limit: int = 5,
) -> list[dict]:
    """Gate-linked catalyst cards — context only; news never clears a gate."""
    cats = list(cats or [])
    failed = {g.name for g in (p.gates or []) if not g.passed}
    valuation_locked = "valuation" in failed
    cards: list[dict] = []

    for x in cats:
        is_news = _is_news_catalyst(x)
        # Prefer news + catalysts tied to failed gates; skip soft technical noise
        # when we already have enough news cards.
        category = _classify_catalyst_category(x)
        related = _related_gates_for_catalyst(category, x, failed)
        name = _catalyst_display_name(x)
        summary = _plain_catalyst_text(x)[:160]
        direction = (x.direction or "unlocks").lower()
        if direction not in ("unlocks", "breaks"):
            direction = "unlocks"

        role = _assign_catalyst_role(
            direction=direction,
            category=category,
            related=related,
            failed=failed,
            is_news=is_news,
            summary=summary,
            name=name,
            primary_driver=primary_driver,
        )

        if valuation_locked:
            watch = _valuation_locked_watch(p)
        else:
            watch = (x.watch or "").strip() or "price reaction into the event"

        # News never clears a gate (backtest proof required later).
        # Technical templates also stay clears_gate=false — watch is the tell.
        cards.append({
            "role": role,
            "related_gates": related,
            "clears_gate": False,
            "watch": watch[:140],
            "name": name,
            "summary": summary,
            "direction": direction,
            "horizon": _short_horizon(x.horizon),
            "category": category,
            "origin": "news" if is_news else "technical",
        })

    # Prefer: drove_signal → unlock_context → risk; within role, news first.
    cards.sort(
        key=lambda c: (
            _ROLE_SORT.get(str(c.get("role")), 9),
            0 if c.get("origin") == "news" else 1,
        )
    )
    # Drop pure-technical noise that isn't unlock/risk when we have news.
    has_news = any(c.get("origin") == "news" for c in cards)
    if has_news:
        trimmed: list[dict] = []
        for c in cards:
            if c.get("origin") == "news":
                trimmed.append(c)
            elif c.get("role") in ("unlock_context", "risk") and any(
                g in failed for g in (c.get("related_gates") or [])
            ):
                trimmed.append(c)
        cards = trimmed or cards
    return cards[:limit]


def build_model_checks(
    p: SignalPacket,
    cats: list[Catalyst] | None = None,
    *,
    primary_driver: dict | None = None,
) -> dict:
    """Structured Model Checks payload for the Why panel (no string scraping)."""
    cats = list(cats or [])
    unlock = ""
    if p.unlock_conditions:
        unlock = "This becomes a full buy once " + " and ".join(p.unlock_conditions) + "."
    gates = [
        {
            "id": g.name,
            "label": _gate_pill_label(g.name),
            "passed": bool(g.passed),
            "detail": (
                (g.detail.get("text") if isinstance(g.detail, dict) else None)
                or ""
            )[:160],
        }
        for g in (p.gates or [])
    ]
    linked = build_gate_linked_catalyst_cards(
        p, cats, primary_driver=primary_driver, limit=5
    )
    return {
        "unlock_when": unlock,
        "gates": gates,
        "execution_targets": _execution_targets_from_packet(p),
        "news_drivers": _news_driver_cards(cats, limit=3),
        "gate_linked_catalysts": linked,
    }


# ═════════════════════════════════════════════════════════════
# LAYER 3 — LLM NARRATIVE (guarded, cached, provider-agnostic)
# ═════════════════════════════════════════════════════════════

LLMFn = Callable[[str, str], str]   # (system, user) -> completion text

SYSTEM_PROMPT = """You are a plain-English trading execution assistant for retail equity traders.
Convert the EXECUTION_NOTE payload into an immediate, scannable 10-second trading note.

CORE RULES:
1. STRICT LENGTH: 35 to 50 words TOTAL. Never exceed 50 words.
2. NO FIN-TECH JARGON. Translate metrics into everyday language:
   - HMM bear / low fused score -> Momentum is weak / Overall signal is cautious
   - Put-heavy / high P/C -> Big traders are betting against this stock
   - Extended / overbought -> Overpriced right now / Don't chase
   - Insider selling -> Company insiders are selling shares
   - Yield / dollar spikes -> Broader market drag from interest rates
   - High beta / volatility -> Wild daily swings / High risk
3. DYNAMIC STATUS EMOJI on the first bullet (use STATUS_EMOJI when provided):
   - 🛑 if PRIMARY_ACTION is AVOID
   - 🚦 if PRIMARY_ACTION is WAIT_PULLBACK or BUY_STARTER
   - 🟢 if PRIMARY_ACTION is CONFIRMED_BUY
4. STRUCTURE: Output EXACTLY 3 bullet lines. No intro, no outro, no blank lines.
5. Every dollar figure and percentage MUST appear in EXECUTION_NOTE or PACKET. Never invent prices.
6. Never contradict PRIMARY_ACTION. Do not say buy when action is AVOID or WAIT_PULLBACK.
7. Lead the CATALYST & DRIVER bullet with PRIMARY_DRIVER / DRIVER_CATEGORY (already ranked).
   Prefer BINARY_EVENT > SMART_MONEY > MACRO_RATES > GEOPOLITICAL > CROSS_ASSET over TECHNICAL.
   Use PRIMARY_DRIVER_PLAIN or TOP_CATALYSTS; do not invent a different main driver.
8. Prefer BINARY_EVENT when present over chart-only chatter.
9. Forbidden words: margin of safety, tape, HMM, confluence, thesis, invalidation, fused, RSI (say "after the move cools off").

OUTPUT BY MODE (EXECUTION_NOTE.MODE):

IF MODE == DAY_TRADING:
• [EMOJI] ACTION: [1 sentence intraday verdict]
• ⚠️ CATALYST & DRIVER: [today's flow / news / big-trader positioning]
• 🎯 SCALP LEVEL: [exact entry band + hard intraday stop]

IF MODE == SWING_TRADING:
• [EMOJI] ACTION: [1 sentence 1-2 week verdict]
• ⚠️ CATALYST & DRIVER: [earnings / macro / insider driver]
• 🎯 BUY ZONE & STOP: [pullback band + hard exit]

IF MODE == LONG_TERM_INVESTOR:
• [EMOJI] ACTION: [1 sentence long-term portfolio verdict]
• ⚠️ CATALYST & DRIVER: [valuation / rates / policy risk]
• 🎯 ACCUMULATION PLAN: [dip-buying zone for long-term adds]

Output bullets only."""


WHY_EXPLAINER_SYSTEM_PROMPT = """You are a plain-English trading execution assistant for retail equity traders.
Convert the MODEL_CHECKS payload (gate pass/fail results, execution price levels, and any
gate-linked catalysts) into a short explanation a non-finance reader can follow.

CORE RULES:
1. LENGTH: 2 to 4 short sentences, 60 to 160 words total.
2. NO FIN-TECH JARGON. Translate metrics into everyday language, same as these examples:
   - HMM bear / low fused score -> Momentum is weak / Overall signal is cautious
   - Put-heavy / high P/C -> Big traders are betting against this stock
   - Extended / overbought -> Overpriced right now / Don't chase
   - Insider selling -> Company insiders are selling shares
   - Yield / dollar spikes -> Broader market drag from interest rates
   - High beta / volatility -> Wild daily swings / High risk
   - margin of safety -> how much cheaper than fair value it is
   - RSI -> say "the stock's recent momentum" instead
   - regime / HMM bull % -> "the market's own trend-reading model"
3. COVER, IN ORDER:
   a. Which of the 4 gates (from MODEL_CHECKS.gates) are blocking vs. clear, and why, in plain
      terms — not gate names, describe what each one is actually checking.
   b. What the execution price levels (MODEL_CHECKS.execution_targets) mean practically — why
      this buy zone, why this target, why this exit level, not just restating the numbers.
   c. If MODEL_CHECKS.gate_linked_catalysts is non-empty, explain in one clause why that
      news/event matters to the specific gate(s) it's related to. Skip this if the list is empty.
4. Every dollar figure and percentage you write MUST already appear in MODEL_CHECKS or PACKET.
   Never invent a price, level, probability, or percentage.
5. Never contradict ACTION_CONTRACT. Do not say buy when action is AVOID or WAIT_PULLBACK.
6. Tone: measured, direct, like explaining to a friend — no hype, no certainty language.
7. Forbidden words: margin of safety, tape, HMM, confluence, thesis, invalidation, fused, RSI.
8. Output plain prose only — no bullets, no headers, no markdown, no emoji."""


def build_why_explainer_prompt(p: SignalPacket, contract: ActionContract, model_checks: dict,
                               cats: list[Catalyst]) -> str:
    """Structured payload for the Why-panel explainer — same number-guard universe as
    build_user_prompt (model_checks is itself derived from `p`, so nothing new to guard)."""
    return json.dumps({
        "MODEL_CHECKS": model_checks,
        "PACKET": asdict(p),
        "ACTION_CONTRACT": {**asdict(contract), "action": contract.action.value},
        "CATALYSTS": [asdict(x) for x in cats],
    }, default=str)


def why_explainer_structure_errors(text: str) -> list[str]:
    """Looser structural check than trading_note_structure_errors — free prose, no bullets,
    just a sane word-count band so the model doesn't collapse to one line or ramble on."""
    errs: list[str] = []
    stripped = (text or "").strip()
    if not stripped:
        errs.append("empty response")
        return errs
    n = _count_words(text)
    if n < 40 or n > 200:
        errs.append(f"word count {n} outside 40-200")
    if any(ln.strip().startswith(("•", "-", "*")) for ln in stripped.splitlines()):
        errs.append("must be plain prose, not bullets")
    return errs


def build_user_prompt(p: SignalPacket, contract: ActionContract,
                      cats: list[Catalyst],
                      retail_scan: dict | None = None) -> str:
    """Structured execution payload first — keeps Layer-3 notes reproducible."""
    return json.dumps({
        "EXECUTION_NOTE": build_trading_note_payload(p, contract, cats),
        "PACKET": asdict(p),
        "ACTION_CONTRACT": {**asdict(contract), "action": contract.action.value},
        "RETAIL_SCAN": retail_scan or {},
        "CATALYSTS": [asdict(x) for x in cats],
    }, default=str)


# Matches "$1,234.56", "12.3%", and bare decimal numbers (>=2 sig figs) so a
# hallucinated RSI/R:R/analyst-count value can't slip past the $ / % cases.
_NUM_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s?%|\b(\d+\.\d+)\b")


def guard_numbers(text: str, p: SignalPacket) -> list[str]:
    """Numbers in `text` NOT present in the packet."""
    allowed = p.numeric_universe()
    bad = []
    for m in _NUM_RE.finditer(text):
        raw = (m.group(1) or m.group(2) or m.group(3)).replace(",", "")
        v = round(float(raw), 2)
        if v not in allowed and round(v) not in allowed:
            bad.append(m.group(0))
    return bad


class NarrativeEngine:
    """Layer-3 orchestrator. Cache is Redis-backed when available (survives
    backend restarts / shared across workers) with an in-memory dict fallback
    when Redis isn't configured — same optional/no-op pattern as the rest of
    this app's caching (see backend/signals/cache.py)."""

    _CACHE_TTL_SECONDS = 5 * 24 * 3600  # 5 days — comfortably longer than any
                                          # single day's decision-hash lifetime

    def __init__(self, llm: Optional[LLMFn] = None, max_retries: int = 2):
        self.llm = llm
        self.max_retries = max_retries
        self._mem_cache: dict[str, str] = {}   # fallback when Redis unavailable

    def _cache_get(self, key: str) -> Optional[str]:
        try:
            from signals.cache import get_cached
            val = get_cached(key, as_json=False)
            if val is not None:
                return val
        except Exception:
            pass
        return self._mem_cache.get(key)

    def _cache_set(self, key: str, value: str) -> None:
        self._mem_cache[key] = value
        try:
            from signals.cache import set_cached
            set_cached(key, value, self._CACHE_TTL_SECONDS)
        except Exception:
            pass

    def generate(self, p: SignalPacket, contract: ActionContract,
                 cats: list[Catalyst],
                 retail_scan: dict | None = None) -> tuple[str, str]:
        """Returns (narrative, status). status ∈ ok|cached|skipped|fallback.
        Cache key = ticker + asof date + decision_hash: regenerates only when a
        gate flips, a band moves, or RSI/regime crosses a bucket — never on a
        mere spot tick. The date prefix prevents a stale narrative from a
        previous day resurfacing just because the decision state happens to
        match. v6 uses execution-note bullets (35–50 words, mode-aware).
        """
        if self.llm is None:
            return "", "skipped"
        key = f"narrative:v8:{p.ticker}:{p.mode}:{p.asof}:{p.decision_hash()}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached, "cached"
        user = build_user_prompt(p, contract, cats, retail_scan=retail_scan)
        for attempt in range(self.max_retries + 1):
            text = self.llm(SYSTEM_PROMPT, user).strip()
            bad_n = guard_numbers(text, p)
            bad_w = layer3_banned_hits(text)
            bad_s = trading_note_structure_errors(text)
            if not bad_n and not bad_w and not bad_s:
                self._cache_set(key, text)
                return text, "ok"
            extra = []
            if bad_n:
                extra.append(f"illegal numbers {bad_n}")
            if bad_w:
                extra.append(f"forbidden jargon {bad_w} — rewrite in plain English")
            if bad_s:
                extra.append(f"structure errors {bad_s} — exactly 3 bullets, 35-50 words, status emoji on bullet 1")
            user += (f"\n\nREJECTED attempt {attempt + 1}: {'; '.join(extra)}. "
                     "Rewrite using only packet numbers and no forbidden words.")
        return "", "fallback"

    def generate_why_explainer(self, p: SignalPacket, contract: ActionContract,
                                model_checks: dict, cats: list[Catalyst]) -> tuple[str, str]:
        """Plain-English translation of the Why-panel's gates/execution targets/catalysts.

        Separate cache namespace and separate structural contract from generate() — the
        top-summary trading note is a rigid 3-bullet/35-50-word format; this is a few
        sentences of free prose, so mixing the two into one call would risk either
        blowing the note's word budget or diluting this explainer's coverage. Same
        decision-hash cache key shape, same number/jargon guards, same retry contract.
        """
        if self.llm is None:
            return "", "skipped"
        key = f"why_explainer:v1:{p.ticker}:{p.mode}:{p.asof}:{p.decision_hash()}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached, "cached"
        user = build_why_explainer_prompt(p, contract, model_checks, cats)
        for attempt in range(self.max_retries + 1):
            text = self.llm(WHY_EXPLAINER_SYSTEM_PROMPT, user).strip()
            bad_n = guard_numbers(text, p)
            bad_w = layer3_banned_hits(text)
            bad_s = why_explainer_structure_errors(text)
            if not bad_n and not bad_w and not bad_s:
                self._cache_set(key, text)
                return text, "ok"
            extra = []
            if bad_n:
                extra.append(f"illegal numbers {bad_n}")
            if bad_w:
                extra.append(f"forbidden jargon {bad_w} — rewrite in plain English")
            if bad_s:
                extra.append(f"structure errors {bad_s} — 2-4 plain sentences, 60-160 words, no bullets")
            user += (f"\n\nREJECTED attempt {attempt + 1}: {'; '.join(extra)}. "
                     "Rewrite using only packet numbers and no forbidden words.")
        return "", "fallback"


# ═════════════════════════════════════════════════════════════
# WATERFALL ORCHESTRATOR
# ═════════════════════════════════════════════════════════════

_ENGINE_SINGLETON: Optional[NarrativeEngine] = None


def build_summary(p: SignalPacket, llm: Optional[LLMFn] = None,
                  engine: Optional[NarrativeEngine] = None) -> dict:
    """The one entry point. UI renders ONLY from this dict."""
    global _ENGINE_SINGLETON
    errors = p.validate()
    if errors:
        return {"status": "blocked", "errors": errors, "ticker": p.ticker}

    contract = derive_action_contract(p)
    cats = derive_catalysts(p)
    cat_errs = validate_catalysts(p, cats)
    if cat_errs:
        logger.error("[narrative] %s (%s) catalyst validation: %s", p.ticker, p.mode, cat_errs)
        cats = [c for c in cats if not validate_catalysts(p, [c])]

    scan = render_retail_scan(p, contract, cats)
    banned = retail_scan_banned_hits(scan.get("text") or "")
    if banned:
        logger.error("[narrative] %s (%s) retail scan used banned vocab: %s",
                     p.ticker, p.mode, banned)

    why = render_explanations(p)
    sc = render_scenarios(p)
    if sc:
        why.append(sc)
    why += render_catalysts(cats)

    layer2_text = " ".join(why)
    layer2_bad = guard_numbers(layer2_text, p)
    if layer2_bad:
        logger.warning(
            "[narrative] %s (%s) Layer 2 cited numbers not in packet: %s",
            p.ticker, p.mode, layer2_bad[:8],
        )

    if engine is None:
        if _ENGINE_SINGLETON is None or _ENGINE_SINGLETON.llm is not llm:
            _ENGINE_SINGLETON = NarrativeEngine(llm)   # persist cache across calls
        engine = _ENGINE_SINGLETON
    narrative, l3_status = engine.generate(p, contract, cats, retail_scan=scan)
    trading_notes = narrative or render_plain_trading_notes(p, contract, cats)
    note_payload = build_trading_note_payload(p, contract, cats)
    primary_driver = note_payload.get("PRIMARY_DRIVER") or {}
    model_checks = build_model_checks(p, cats, primary_driver=primary_driver)
    why_explainer, why_explainer_status = engine.generate_why_explainer(p, contract, model_checks, cats)

    return {
        "status": "ok",
        "ticker": p.ticker,
        "mode": p.mode,
        "asof": p.asof,
        "action": {**asdict(contract), "action": contract.action.value,
                   "text": render_action(contract, p)},
        "retail_scan": scan,
        "trading_notes": trading_notes,
        "primary_driver": primary_driver,
        "driver_category": note_payload.get("DRIVER_CATEGORY") or "TECHNICAL",
        "driver_chip": note_payload.get("DRIVER_CHIP") or "Technical",
        "why": why,
        "model_checks": model_checks,
        "why_explainer": why_explainer,
        "why_explainer_status": why_explainer_status,
        "catalysts": [asdict(x) for x in cats],
        "scenario_ev_pct": p.scenario_ev(),
        "scenario_ev_horizon": "scenario mix · not the painted target",
        "narrative": narrative,
        "narrative_status": l3_status,
        "packet_hash": p.content_hash(),
        "layer2_guard_violations": layer2_bad or None,
        "catalyst_validation": cat_errs or None,
    }


# ═════════════════════════════════════════════════════════════
# TIERED LLM STRATEGY (pre-revenue cost control)
# ═════════════════════════════════════════════════════════════
# Layers 1+2 (action, gates, scenarios, catalysts) run for EVERY ticker at $0.
# Layer 3 (LLM narrative) runs only for tickers on the allowlist — the curated
# demo set — plus lazy on-view generation so non-listed tickers still get a
# narrative the moment someone actually opens them.
#
#   Scheduled runs:  build_summary_tiered(p, llm)            ~2x/day, allowlist only
#   Page view:       build_summary_tiered(p, llm, on_view=True)   generate + cache
#   Demo prep:       prewarm(packets, llm)                   morning of a demo
#
# Cost at 10-25 allowlisted tickers x 2 intraday runs: ~$2.50-$6/month on Haiku.

import os

def load_allowlist() -> set[str]:
    """Env-var driven so you can add a prospect's ticker without redeploying:
    export THRIVE_LLM_TICKERS='AMZN,BLK,GLD,NVDA,META'   (or back with a DB table)"""
    raw = os.environ.get("THRIVE_LLM_TICKERS", "")
    return {t.strip().upper() for t in raw.split(",") if t.strip()}


def build_summary_tiered(p: SignalPacket, llm: Optional[LLMFn] = None,
                         allowlist: Optional[set[str]] = None,
                         on_view: bool = False,
                         engine: Optional[NarrativeEngine] = None) -> dict:
    """Drop-in replacement for build_summary in scheduled jobs AND page views.

    - Scheduled run (on_view=False): LLM only for allowlisted tickers.
    - Page view (on_view=True): LLM for any ticker — first view generates,
      cache serves every view after, so the product never looks tiered.
    """
    allow = load_allowlist() if allowlist is None else allowlist
    use_llm = llm if (on_view or p.ticker.upper() in allow) else None
    if use_llm is None:
        # never route through a shared engine here — it carries its own LLM
        # reference and would silently bypass the tier decision
        return build_summary(p, llm=None, engine=NarrativeEngine(None))
    return build_summary(p, llm=use_llm, engine=engine)


def prewarm(packets: list[SignalPacket], llm: LLMFn,
            engine: Optional[NarrativeEngine] = None) -> dict[str, str]:
    """Run before a demo so nobody watches a generation spinner live.
    Returns {ticker: narrative_status}."""
    eng = engine or NarrativeEngine(llm)
    out = {}
    for p in packets:
        s = build_summary(p, engine=eng)
        out[p.ticker] = s.get("narrative_status", s.get("status", "blocked"))
    return out


# ═════════════════════════════════════════════════════════════
# LLM ADAPTERS (swap freely — any (system, user) -> str works)
# ═════════════════════════════════════════════════════════════

def make_anthropic_client(model: str = "claude-haiku-4-5-20251001") -> LLMFn:
    import anthropic                                   # pip install anthropic
    client = anthropic.Anthropic()                     # ANTHROPIC_API_KEY env var
    def call(system: str, user: str) -> str:
        msg = client.messages.create(
            model=model, max_tokens=600, system=system,
            messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in msg.content if b.type == "text")
    return call


# ═════════════════════════════════════════════════════════════
# DEMO — AMZN swing snapshot (2026-08-11 screenshots)
# ═════════════════════════════════════════════════════════════

def example_packet_amzn() -> SignalPacket:
    return SignalPacket(
        ticker="AMZN", mode="swing", asof="2026-08-11",
        spot=272.27, trend="UP", verdict="BRIDGE_PARTIAL", score=100,
        gates=[
            Gate("valuation", True, {"mos_pct": 30.4, "required_pct": 25.0}),
            Gate("market_weather", True, {"tape": "Bull", "hmm_bull_pct": 97.0, "need_pct": 60.0}),
            Gate("momentum_chop", False, {"rsi": 62.0}),
            Gate("ml_probability", True, {"ml_prob_pct": 35.0, "threshold_pct": 25.0}),
            Gate("confidence", True, {"conf_pct": 69.0}),
        ],
        entry_band=Band(245.14, 257.52), stop=232.76, invalidation=229.98,
        target=331.58, rr=1.5,
        st_band=Band(269.55, 273.63),
        bridge_band=Band(267.34, 274.36),
        bridge_levels=[267.34, 269.10, 270.85, 272.60, 274.36],
        catch_levels=[245.14, 247.62, 248.23, 251.33, 254.42, 257.52],
        anchor_levels=[247.62],
        t1=Band(225.24, 248.94), t2=Band(292.76, 310.86),
        entry_mode="STARTER_ONLY", max_tranche_pct=10.0,
        roadmap=[{"horizon": "1-3m", "alloc_pct": 35, "band": Band(225.24, 248.94)},
                 {"horizon": "3-6m", "alloc_pct": 25, "band": Band(225.24, 248.94)}],
        hmm_bull_pct=97.0, hmm_transition_pct=2.0, rsi=62.0,
        ml_prob_pct=35.0, ml_threshold_pct=25.0, fused_confidence_pct=69.0,
        options_pc=0.78, options_class="put-heavy", options_score_pct=50.0,
        unlock_conditions=["Momentum Chop clears (RSI < 50)"],
        scenarios=[Scenario("Bull Case", 43.2, 89), Scenario("Base Case", 19.4, 42),
                   Scenario("Earnings Beat", 11.0, 50), Scenario("Fed Rate Cut", 10.0, 40),
                   Scenario("Earnings Miss / Guidance Cut", -3.0, 15),
                   Scenario("Bear Case", -12.5, 5)],
        expected_value_pct=None,   # set to your engine's displayed EV to enable drift check
        sensitivities=["USD-sensitive", "volatility-sensitive"],
        street_median=329.0, street_analysts=94, street_bullish_pct=89.4,
        news_sentiment="BULLISH",
    )


if __name__ == "__main__":
    pkt = example_packet_amzn()
    out = build_summary(pkt, llm=None)   # pass llm=make_anthropic_client() to enable Layer 3
    print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
