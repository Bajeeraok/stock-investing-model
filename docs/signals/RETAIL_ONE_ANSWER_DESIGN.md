# Retail One Answer: Design

## Goal

Answer in one place: **"Should I buy/sell this ticker today, and if not, at what price and when?"**

Two personas, two roadmaps:

| Persona | Focus | Timeframe | Key question |
|--------|--------|-----------|--------------|
| **Trader** | Tactical entry/exit | Short (≈1 mo) + Medium (≈3–6 mo) | "Enter now or wait? At what price? Stop? Target? When?" |
| **Investor** | Position build & hold | Medium (≈3–6 mo) + Long (≈6–18 mo) | "Add / hold / trim? At what levels? When to add more or reduce?" |

---

## 1. The One Answer (single headline)

One sentence that a user can read in &lt;5 seconds:

- **Format:** `[VERDICT]: [Action today]. [If not now: price and when.]`
- **Examples:**
  - *"BUY: Enter in the zone $168–$172 (near MA50). Stop $162, target $185 (~1 month)."*
  - *"HOLD: Don't add here. Buy if it pulls back to $165–$170 (short-term) or $158–$163 (medium-term)."*
  - *"REDUCE: Valuation supports entry but regime/ML say reduce. Trim into strength; add only below $155."*

**Source of truth:**  
- **Verdict** = regime/ML display verdict (REDUCE / AVOID) if set; else overall_verdict from horizons (STRONG BUY / BUY / WATCH / WAIT).  
- **Action today** = Buy / Sell or Trim / Hold (no new position).  
- **If not now** = first relevant entry zone (short for trader, medium/long for investor) + stop + target + rough timeframe.

---

## 2. Trader Roadmap (short + medium)

**Purpose:** Clear path for someone trading in weeks to a few months.

| Field | Meaning | Source |
|-------|--------|--------|
| **Verdict** | BUY / WATCH / REDUCE / AVOID (short + medium bias) | short_suggestion, medium_suggestion; prefer stricter (e.g. REDUCE over BUY) |
| **Action today** | Enter now \| Wait for pullback \| Trim \| No new position | From verdict + price vs entry zone |
| **Short-term (≈1 mo)** | Entry zone $X–$Y, stop $S, target $T, timeframe | horizons.short.entry_zone, stop_loss, target, trigger_buy |
| **Medium-term (≈3–6 mo)** | Entry zone $X–$Y, stop $S, target $T, catalyst note | horizons.medium.* + days_to_earnings |
| **When to act** | e.g. "On pullback to MA50" / "Within 5 days post-earnings if &gt;5% drop" | trigger_buy, rationale |

**Display:** One compact block: verdict badge, then "Today: [action]. Short: [zone] → target [T]. Medium: [zone] → target [T]. Stops: [short stop] / [medium stop]."

---

## 3. Investor Roadmap (medium + long)

**Purpose:** Clear path for someone building or holding a position over months to a couple of years.

| Field | Meaning | Source |
|-------|--------|--------|
| **Verdict** | BUY / WATCH / WAIT (medium + long bias) | horizons.medium.verdict, horizons.long.verdict; overall_verdict |
| **Action today** | Add \| Hold (no add) \| Trim | From verdict + MOS vs entry tiers |
| **Entry strategy** | Tiered: Tier 1 (MA200) → Tier 2 (25% MOS) → Tier 3 (52w low) | horizons.long.entry_tiers |
| **When to add more** | e.g. "Add 25% in Tier 1 ($X–$Y), 50% at Tier 2 ($A–$B)" | entry_tiers.tiers + position_sizing |
| **When to trim** | e.g. "Trim if price &gt; fair value $FV or regime turns bear" | fair_value, trigger_buy / exit condition |
| **Hold thesis** | One line: e.g. "Hold 6–18 mo toward fair value $FV; add on dips to MA200." | fair_value, rationale |

**Display:** One compact block: verdict badge, then "Today: [add/hold/trim]. Add: T1 $X–$Y (25%), T2 $A–$B (50%), T3 $C–$D (25%). Trim near $FV. Hold: [thesis]."

---

## 4. Data mapping (existing → One Answer & roadmaps)

| One Answer / Roadmap | Existing backend |
|----------------------|------------------|
| Verdict (display) | response.short_suggestion / medium_suggestion / long_suggestion (REDUCE/AVOID override) |
| Overall verdict | investor_summary.overall_verdict (STRONG BUY/BUY/WATCH/WAIT) |
| Action today | Derived: REDUCE/AVOID → Trim or No new position; BUY + in zone → Enter now; BUY + above zone → Wait; WATCH/WAIT → Hold |
| Short entry zone | horizons.short.entry_zone.low–high, trigger_buy |
| Short stop/target | horizons.short.stop_loss, target, target_pct |
| Medium entry zone | horizons.medium.entry_zone, stop_loss, target |
| Long entry tiers | horizons.long.entry_tiers.tiers (T1/T2/T3), current_assessment.label |
| Fair value | investor_summary.fair_value |
| Timeframe copy | "~1 month" (short), "3–6 months" (medium), "6–18 months" (long) from horizon labels |

---

## 5. UI placement

1. **At top of ticker detail (modal or page)**  
   - **One Answer** card: one sentence + optional one-line sub (e.g. "Regime/ML override: REDUCE despite 25% MOS.")

2. **Below One Answer**  
   - **Trader roadmap** (collapsible): verdict, action today, short block, medium block, when to act.  
   - **Investor roadmap** (collapsible): verdict, action today, tiered add levels, when to trim, hold thesis.

3. **Existing content**  
   - Keep "Investor Decision Summary" (horizons, MOS, methodology) as the detailed breakdown; the One Answer and roadmaps are the distilled view on top.

---

## 6. Backend shape (add to investor_summary)

```yaml
# Attach to response.investor_summary

one_answer:
  headline: "BUY: Enter in the zone $168–$172 (near MA50). Stop $162, target $185 (~1 month)."
  subline: null  # or "Regime/ML say REDUCE — trim into strength; add only below $155."
  verdict: "BUY"           # display verdict for the one answer
  action_today: "wait_for_pullback"  # enter_now | wait_for_pullback | trim | no_new_position

trader_roadmap:
  verdict: "BUY"           # short+medium bias
  action_today: "wait_for_pullback"
  short:
    entry_zone: { low: 168, high: 172 }
    stop: 162
    target: 185
    target_pct: 8.2
    timeframe: "~1 month"
    trigger: "On pullback to MA50; ML > 25%."
  medium:
    entry_zone: { low: 165, high: 170 }
    stop: 158
    target: 195
    timeframe: "3–6 months"
    trigger: "Earnings within 60d; add on dip to MA50."

investor_roadmap:
  verdict: "WATCH"
  action_today: "hold"
  add_tiers:
    - { id: "T1", label: "MA200 zone", low: 158, high: 165, allocation_pct: 25 }
    - { id: "T2", label: "25% MOS", low: 142, high: 148, allocation_pct: 50 }
    - { id: "T3", label: "Deep value", low: 128, high: 138, allocation_pct: 25 }
  trim_near: 198.5   # fair_value
  hold_thesis: "Hold 6–18 mo toward fair value $198; add on dips to MA200. ML 45% supports partial add at T1."
```

---

## 7. Copy rules

- **Trader:** Use "Enter", "Stop", "Target", "pullback", "~1 month", "3–6 months". Avoid long-term MOS % unless one line.
- **Investor:** Use "Add", "Trim", "Tier 1/2/3", "fair value", "6–18 months", "margin of safety".
- When verdict is REDUCE/AVOID, one answer must mention it (e.g. "Regime/ML say REDUCE") and never say only "entry justified" without the override.

---

## 8. Summary

| Output | Content |
|--------|--------|
| **One Answer** | One sentence: verdict + action today + (if not now) price and when. |
| **Trader Roadmap** | Verdict, action today, short entry/stop/target/timeframe, medium ditto, when to act. |
| **Investor Roadmap** | Verdict, action today, tiered add levels (T1/T2/T3), trim near FV, hold thesis. |

All of this is derivable from existing `investor_summary` (horizons, fair_value, overall_verdict) plus `response` (short_suggestion, ma50, ma200, etc.). No new signal logic—only a structured summary layer and UI.
