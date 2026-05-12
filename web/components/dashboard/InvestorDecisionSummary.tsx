"use client";

import React, { useState } from "react";
import {
  CheckCircle,
  XCircle,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Info,
  Zap,
  TrendingUp,
  Calendar,
  Target,
  Sun,
  CloudSun,
  CloudRain,
  Cloud,
} from "lucide-react";
import type { TradeRoadmapData } from "./TradeRoadmapCard";
import {
  buildPatternDecisionDriverSummary,
  buildMlHorizonGapExplainer,
  marketWeatherFromRegimeBull,
  type MarketWeather,
} from "./patternDecisionDriver";

const STRENGTH_CONVICTION_HINT =
  "Strength = this horizon’s ML signal tier (how bullish the model read is for that specific window). " +
  "Conviction = how confident the fused stack is about acting on that horizon (timing / sizing). " +
  "They can disagree: e.g. a statistically strong 3‑month window can still show Low conviction if regime or other layers want more proof.";

function horizonVerdictPillClass(v: string | undefined): string {
  const u = String(v || "").toUpperCase();
  if (u === "STRONG BUY" || u === "BUY") return "border-emerald-500/55 bg-emerald-500/15 text-emerald-200";
  if (u === "WATCH") return "border-teal-500/55 bg-teal-500/12 text-teal-200";
  if (u === "WAIT") return "border-red-500/55 bg-red-500/12 text-red-200";
  return "border-slate-600 bg-slate-800/80 text-slate-300";
}

// Use bracket types to avoid ambiguous generics in .tsx (Array<T> can be parsed as JSX)
export interface FairValueMetadata {
  bear_case?: number | null;
  method_used?: string | null;
  methodology_summary?: string | null;
  notes?: string[] | null;
}

/** One sentence answer: "Should I buy/sell today, and if not, at what price and when?" */
export interface OneAnswer {
  headline: string;
  subline?: string | null;
  verdict: string;
  action_today: string;
  bottom_line?: string | null;
  why_this_call?: string[];
  next_trigger?: string | null;
  execution_plan_lines?: string[];
  signal_reconciliation_notes?: string[];
  /** When bull regime + near highs + rising ML clash with stretched FV (catalyst / momentum risk). */
  momentum_valuation_tension?: {
    active: boolean;
    headline: string;
    detail: string;
    premium_vs_fair_value_pct?: number;
    regime_bull_pct?: number;
    momentum_target?: number;
    momentum_target_method?: string;
    momentum_stop?: number;
    momentum_upside_pct?: number;
    momentum_risk_pct?: number;
    catalyst_active?: boolean;
  } | null;
  /** Strong non-bull HMM vs price at highs — regime is macro-heavy, not necessarily name weakness. */
  ath_macro_regime_disconnect?: {
    active: boolean;
    headline: string;
    detail: string;
    non_bull_pct?: number;
  } | null;
  /** Retail: hold 5–10y vs take profits — education + tie-in to today’s signals */
  hold_vs_trade?: {
    title: string;
    long_term: string;
    short_term: string;
    signal_bridge: string;
    disclaimer: string;
  } | null;
}

/** Trader roadmap: short/medium entry, stop, target, when to act. */
export interface TraderRoadmap {
  verdict: string;
  action_today: string;
  short: {
    entry_zone: { low: number; high: number } | null;
    stop: number | null;
    target: number | null;
    target_pct: number | null;
    timeframe: string;
    trigger: string;
  };
  medium: {
    entry_zone: { low: number; high: number } | null;
    stop: number | null;
    target: number | null;
    timeframe: string;
    trigger: string;
  };
}

/** Investor roadmap: tiered add levels, trim near FV, hold thesis. */
export interface InvestorRoadmap {
  verdict: string;
  action_today: string;
  add_tiers: { id?: string; label?: string; low?: number; high?: number; allocation_pct?: number }[];
  trim_near: number;
  hold_thesis: string;
}

/** Compare headline model fair value to vendor analyst targets (Yahoo + FMP when available). */
export interface FairValueVsExternal {
  yahoo_12m_mean_usd?: number | null;
  pct_model_vs_yahoo_mean?: number | null;
  fmp_consensus_low_usd?: number | null;
  fmp_consensus_high_usd?: number | null;
  fmp_consensus_median_usd?: number | null;
  /** True when median was inferred as (low+high)/2 — label as range midpoint, not analyst median. */
  fmp_median_is_range_midpoint?: boolean | null;
  pct_model_vs_fmp_median?: number | null;
  note?: string | null;
}

export interface InvestorDecisionSummary {
  fair_value: number;
  overall_verdict: "WAIT" | "WATCH" | "BUY" | "STRONG BUY";
  /** HMM label when provided by API (e.g. Bull / Non-bull) — optional display */
  regime_hmm_label?: string | null;
  regime_bull_pct?: number | null;
  model_confidence_pct?: number | null;
  /** TTM PE used for fair value (FMP > price/trailingEps > yfinance). Shown so card reflects correct PE, not stale feed. */
  ttm_pe_used?: number;
  /** Forward PE used for fair value when available. */
  forward_pe_used?: number;
  /** Bear case, method, and notes so users can interrogate FV vs lt_band. */
  fair_value_metadata?: FairValueMetadata | null;
  /** Model FV vs Yahoo mean and FMP consensus (when API key present). */
  fair_value_vs_external?: FairValueVsExternal | null;
  /** Short-term pattern score (0-100); when low, show signal-deterioration banner. */
  pattern_score?: number | null;
  /** One Answer + Trader / Investor roadmaps (retail design). */
  one_answer?: OneAnswer | null;
  trader_roadmap?: TraderRoadmap | null;
  investor_roadmap?: InvestorRoadmap | null;
  /** Complete Trade Roadmap: buy/sell stages + trader summary (tabbed card). */
  trade_roadmap?: TradeRoadmapData | null;
  horizons: {
    short: HorizonSignalPayload;
    medium: HorizonSignalPayload;
    long: HorizonSignalPayload;
  };
}

export interface HorizonSignalPayload {
  label: string;
  duration: string;
  verdict: string;
  signal: string;
  conviction: string;
  ml_prob: number;
  entry_zone: { low: number; high: number; anchor: string; quality: string; quality_color: string };
  target: number;
  target_pct: number;
  stop_loss: number;
  stop_loss_pct: number;
  risk_reward: number;
  rationale: string;
  trigger_buy: string;
  warnings: string[];
  /** "trailing" for short/medium; long-term uses structural_invalidation for 52w-floor level */
  stop_loss_kind?: string | null;
  /** Explains wide long-term level vs a normal stop */
  stop_loss_framing?: string | null;
  entry_tiers?: {
    current_assessment: {
      verdict: string;
      label: string;
      color?: string;
      margin_of_safety_pct?: number | null;
      min_price_to_buy?: number | null;
    };
    tiers: {
      id: string;
      label: string;
      description: string;
      low: number;
      high: number;
      upside_to_fv_pct: number;
      margin_of_safety_pct: number;
      estimated_rr: string;
      conviction: string;
      color: string;
      reachable: boolean;
      drop_needed_pct: number | null;
    }[];
    position_sizing?: { tier: string; allocation_pct: number; note: string }[];
    structural_invalidation?: {
      price: number;
      kind: string;
      note: string;
    };
  };
  fair_value?: number;
}

function regimeWeatherIcon(weather: MarketWeather) {
  const cls = "h-3.5 w-3.5 shrink-0";
  switch (weather) {
    case "favorable":
      return React.createElement(Sun, { className: `${cls} text-amber-300`, "aria-hidden": true });
    case "mixed":
      return React.createElement(CloudSun, { className: `${cls} text-slate-400`, "aria-hidden": true });
    case "stormy":
      return React.createElement(CloudRain, { className: `${cls} text-sky-400`, "aria-hidden": true });
    default:
      return React.createElement(Cloud, { className: `${cls} text-slate-500`, "aria-hidden": true });
  }
}

function verdictIcon(verdict: string) {
  switch (verdict) {
    case "STRONG BUY":
    case "BUY":
      return <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0" aria-hidden />;
    case "WATCH":
      return <AlertCircle className="h-4 w-4 text-teal-400 shrink-0" aria-hidden />;
    case "WAIT":
      return <XCircle className="h-4 w-4 text-red-400 shrink-0" aria-hidden />;
    default:
      return <XCircle className="h-4 w-4 text-red-400 shrink-0" aria-hidden />;
  }
}

function HorizonCard({
  horizon,
  entryTiers,
  tiersOpen,
  onToggleTiers,
}: {
  horizon: HorizonSignalPayload;
  entryTiers?: HorizonSignalPayload["entry_tiers"];
  tiersOpen?: boolean;
  onToggleTiers?: () => void;
}) {
  const [showCaveats, setShowCaveats] = useState(false);
  const ez = horizon.entry_zone;
  const verdictClass =
    horizon.verdict === "BUY" || horizon.verdict === "STRONG BUY"
      ? "text-emerald-400"
      : horizon.verdict === "WATCH"
        ? "text-teal-400"
        : horizon.verdict === "WAIT"
          ? "text-red-400"
          : "text-red-400";
  const hasRationale = horizon.rationale && horizon.rationale.trim().length > 0;
  const hasTrigger = horizon.trigger_buy && horizon.trigger_buy.trim().length > 0;
  const warnings = Array.isArray(horizon.warnings) ? horizon.warnings.filter((w) => w && String(w).trim()) : [];
  const triggerLine = hasTrigger ? String(horizon.trigger_buy).trim() : "Wait for setup confirmation.";
  const hasStop = horizon.stop_loss != null && horizon.stop_loss > 0;
  const structuralStop = horizon.stop_loss_kind === "structural_invalidation";

  return React.createElement(
    "div",
    { className: "bg-slate-800 border border-slate-700 rounded-lg p-3 text-sm" },
    React.createElement(
      "div",
      { className: "flex items-center justify-between gap-2 mb-2" },
      React.createElement("span", { className: "font-medium text-slate-300" }, horizon.label),
      React.createElement(
        "span",
        { className: "flex items-center gap-1" },
        verdictIcon(horizon.verdict),
        React.createElement("span", { className: verdictClass }, horizon.verdict)
      )
    ),
    React.createElement(
      "p",
      {
        className: "text-slate-500 text-xs flex items-center gap-1.5 flex-wrap",
      },
      React.createElement(
        "span",
        {
          className: "cursor-help border-b border-dotted border-slate-500/50",
          title: STRENGTH_CONVICTION_HINT,
        },
        `${horizon.signal} strength · ${horizon.conviction} conviction`
      ),
      React.createElement(
        "span",
        { className: "inline-flex shrink-0", title: STRENGTH_CONVICTION_HINT, "aria-label": "Strength vs conviction" },
        React.createElement(Info, { className: "h-3.5 w-3.5 text-slate-500 cursor-help" })
      )
    ),
    React.createElement("p", { className: "text-slate-400 mt-1 font-mono" }, `Entry: $${ez.low.toFixed(2)} – $${ez.high.toFixed(2)}`),
    React.createElement(
      "p",
      { className: "text-slate-500 text-xs", title: "ML probabilities can vary day-to-day as new price and volume data are included; large moves may reflect updated features rather than a change in thesis." },
      `Target: +${horizon.target_pct.toFixed(0)}% · ML prob: ${Number(horizon.ml_prob).toFixed(0)}%`
    ),
    hasStop &&
      React.createElement(
        "p",
        {
          className: "text-slate-500 text-xs mt-0.5",
          title: structuralStop
            ? horizon.stop_loss_framing || "52-week stress floor — not a day-to-day trailing stop"
            : undefined,
        },
        structuralStop
          ? `Structural invalidation (52w stress floor): ~$${Number(horizon.stop_loss).toFixed(2)} — not a normal trailing stop`
          : `Stop below $${Number(horizon.stop_loss).toFixed(2)}`
      ),
    React.createElement(
      "p",
      { className: "text-slate-400 text-[11px] mt-1.5 leading-snug" },
      React.createElement("span", { className: "text-slate-500 font-medium" }, "Act when: "),
      triggerLine
    ),
    (warnings.length > 0 || hasRationale) &&
      React.createElement(
        React.Fragment,
        null,
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setShowCaveats((s) => !s),
            className: "mt-2 text-[11px] text-amber-300/90 flex items-center gap-1 hover:text-amber-200",
          },
          React.createElement(AlertTriangle, { className: "h-3 w-3 shrink-0" }),
          `${warnings.length + (hasRationale ? 1 : 0)} caveat${warnings.length + (hasRationale ? 1 : 0) > 1 ? "s" : ""}`,
          showCaveats ? " ▲" : " ▼"
        ),
        showCaveats &&
          React.createElement(
            "div",
            { className: "mt-2 space-y-1 border-t border-slate-700/50 pt-2" },
            hasRationale &&
              React.createElement("p", { className: "text-[11px] text-slate-300 leading-snug" }, horizon.rationale),
            warnings.map((w, i) =>
              React.createElement(
                "div",
                { key: i, className: "flex items-start gap-1.5 text-[11px] text-amber-300/90" },
                React.createElement(AlertTriangle, { className: "h-3 w-3 shrink-0 mt-0.5" }),
                React.createElement("span", null, w)
              )
            )
          )
      ),
    entryTiers &&
      onToggleTiers &&
      React.createElement(
        React.Fragment,
        null,
        React.createElement(
          "button",
          {
            type: "button",
            onClick: onToggleTiers,
            className: "mt-2 flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300",
          },
          tiersOpen ? React.createElement(ChevronDown, { className: "h-3 w-3" }) : React.createElement(ChevronRight, { className: "h-3 w-3" }),
          tiersOpen ? " Hide Entry Tiers" : "+ Entry Tiers"
        ),
        tiersOpen &&
          entryTiers.tiers &&
          React.createElement(
            "div",
            { className: "mt-2 rounded-lg border border-slate-700/70 bg-slate-900/30 overflow-hidden" },
            /* Header row: assessment + MOS */
            entryTiers.current_assessment &&
              React.createElement(
                "div",
                { className: "px-3 py-2 border-b border-slate-700/50 flex items-center justify-between gap-2 bg-slate-800/40" },
                React.createElement(
                  "span",
                  { className: "text-[11px] font-semibold text-slate-300" },
                  "Long-term entry tiers"
                ),
                React.createElement(
                  "div",
                  { className: "flex items-center gap-2" },
                  React.createElement(
                    "span",
                    {
                      className:
                        "text-[10px] px-1.5 py-0.5 rounded border font-medium " +
                        (entryTiers.current_assessment.color === "emerald"
                          ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                          : entryTiers.current_assessment.color === "amber"
                            ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
                            : "border-slate-600 bg-slate-700/30 text-slate-300"),
                    },
                    entryTiers.current_assessment.label
                  ),
                  entryTiers.current_assessment.margin_of_safety_pct != null &&
                    React.createElement(
                      "span",
                      { className: "text-[10px] text-slate-500" },
                      `MOS ${entryTiers.current_assessment.margin_of_safety_pct.toFixed(0)}%`
                    )
                )
              ),
            /* Tier cards */
            React.createElement(
              "div",
              { className: "divide-y divide-slate-700/40" },
              entryTiers.tiers.map((tier) =>
                React.createElement(
                  "div",
                  {
                    key: tier.id,
                    className:
                      "px-3 py-2.5 " +
                      (tier.reachable ? "bg-emerald-500/[0.04]" : ""),
                  },
                  /* Row 1: label + conviction pill */
                  React.createElement(
                    "div",
                    { className: "flex items-center justify-between gap-2 mb-1" },
                    React.createElement(
                      "span",
                      { className: "text-[11px] font-semibold text-slate-200" },
                      tier.label
                    ),
                    React.createElement(
                      "span",
                      {
                        className:
                          "text-[9px] px-1.5 py-0.5 rounded font-medium " +
                          (tier.conviction === "High"
                            ? "bg-emerald-500/15 text-emerald-300"
                            : tier.conviction === "Medium"
                              ? "bg-amber-500/10 text-amber-300"
                              : "bg-slate-700/40 text-slate-400"),
                      },
                      tier.conviction
                    )
                  ),
                  /* Row 2: price range (large mono) */
                  React.createElement(
                    "p",
                    { className: "text-sm font-mono font-semibold text-slate-100" },
                    `$${tier.low.toFixed(2)} – $${tier.high.toFixed(2)}`
                  ),
                  /* Row 3: stats row */
                  React.createElement(
                    "div",
                    { className: "flex flex-wrap gap-x-4 gap-y-0.5 mt-1 text-[10px] text-slate-400" },
                    React.createElement("span", null, `+${tier.upside_to_fv_pct.toFixed(0)}% to fair value`),
                    tier.estimated_rr &&
                      React.createElement("span", null, `R:R ${tier.estimated_rr}`),
                    tier.drop_needed_pct != null &&
                      React.createElement(
                        "span",
                        { className: tier.reachable ? "text-emerald-400" : "text-slate-500" },
                        tier.reachable ? "Reachable now" : `${Math.abs(tier.drop_needed_pct).toFixed(0)}% drop needed`
                      )
                  ),
                  /* Row 4: description */
                  React.createElement(
                    "p",
                    { className: "text-[10px] text-slate-500 mt-1 leading-snug" },
                    tier.description
                  )
                )
              )
            ),
            /* Footer: structural floor */
            entryTiers.structural_invalidation &&
              React.createElement(
                "div",
                { className: "px-3 py-2 border-t border-slate-700/50 bg-slate-800/30" },
                React.createElement(
                  "p",
                  { className: "text-[10px] text-slate-500 leading-snug" },
                  React.createElement("span", { className: "font-medium text-slate-400" }, "Structural floor: "),
                  `$${entryTiers.structural_invalidation.price.toFixed(2)} — ${entryTiers.structural_invalidation.note}`
                )
              )
          )
      )
  );
}

function anchorSnippet(anchor: string | undefined, max = 160): string {
  if (!anchor || !anchor.trim()) return "";
  const t = anchor.trim();
  return t.length <= max ? t : `${t.slice(0, max).trim()}…`;
}

/** Retail-focused buy band vs spot vs risk floors — uses short-term horizon entry_zone + stops from API. */
function BuyRangeRetailCard({
  currentPrice,
  short,
  long,
  overallVerdict,
}: {
  currentPrice: number;
  short: HorizonSignalPayload;
  long: HorizonSignalPayload;
  overallVerdict: "WAIT" | "WATCH" | "BUY" | "STRONG BUY";
}): React.ReactElement | null {
  const ez = short?.entry_zone;
  if (!ez || !(ez.low > 0) || !(ez.high > 0)) return null;
  const low = Math.min(ez.low, ez.high);
  const high = Math.max(ez.low, ez.high);
  const range = high - low;
  const stStop = short.stop_loss != null && short.stop_loss > 0 ? short.stop_loss : null;
  const stressRaw =
    long?.entry_tiers?.structural_invalidation?.price ??
    (long?.stop_loss != null && long.stop_loss > 0 ? long.stop_loss : null);
  const stress = stressRaw != null && stressRaw > 0 ? stressRaw : null;

  let statusLabel = "—";
  let statusBadgeClass =
    "text-[11px] px-2 py-0.5 rounded border font-semibold border-slate-500/40 bg-slate-600/20 text-slate-300";
  if (currentPrice > 0) {
    if (currentPrice >= low && currentPrice <= high) {
      statusLabel = "Inside buy zone";
      statusBadgeClass =
        "text-[11px] px-2 py-0.5 rounded border font-semibold border-emerald-500/45 bg-emerald-500/15 text-emerald-300";
    } else if (currentPrice > high) {
      statusLabel = "Wait for pullback";
      statusBadgeClass =
        "text-[11px] px-2 py-0.5 rounded border font-semibold border-amber-500/45 bg-amber-500/15 text-amber-200";
    } else {
      statusLabel = "Below modeled band";
      statusBadgeClass =
        "text-[11px] px-2 py-0.5 rounded border font-semibold border-sky-500/40 bg-sky-500/10 text-sky-200";
    }
  }

  const pad = Math.max(range * 0.25, Math.max(low, high) * 0.008, 0.5);
  const scaleMin = low - pad;
  const scaleMax = high + pad;
  const denom = scaleMax - scaleMin;
  const pctRaw = denom > 0 && currentPrice > 0 ? ((currentPrice - scaleMin) / denom) * 100 : 50;
  const pct = Math.max(0, Math.min(100, pctRaw));
  const zoneStartPct = denom > 0 ? ((low - scaleMin) / denom) * 100 : 0;
  const zoneWidthPct = denom > 0 ? ((high - low) / denom) * 100 : 100;

  const anchorNote = anchorSnippet(ez.anchor);

  const maxBuyMos = long?.entry_tiers?.current_assessment?.min_price_to_buy;
  const rr = short?.risk_reward != null && Number(short.risk_reward) > 0 ? Number(short.risk_reward) : null;
  const rrRiskShare = rr != null ? 1 / (1 + rr) : null;
  const insideBandButNotBuy =
    statusLabel === "Inside buy zone" &&
    (overallVerdict === "WAIT" || overallVerdict === "WATCH");

  return React.createElement(
    "section",
    {
      className:
        "p-4 border-b border-emerald-500/30 bg-gradient-to-br from-emerald-950/50 via-slate-900/60 to-slate-950/80",
      "aria-label": "Buy range and stress levels",
    },
    React.createElement(
      "div",
      { className: "flex items-start justify-between gap-3 flex-wrap mb-3" },
      React.createElement(
        "div",
        { className: "flex items-center gap-2 min-w-0" },
        React.createElement(Target, { className: "h-5 w-5 text-emerald-400 shrink-0", "aria-hidden": true }),
        React.createElement(
          "div",
          { className: "min-w-0" },
          React.createElement(
            "h3",
            { className: "text-xs font-semibold text-emerald-200/95 uppercase tracking-wide" },
            "Buy zone vs stress"
          ),
          React.createElement(
            "p",
            { className: "text-[11px] text-slate-500 mt-0.5" },
            "Near-term buy band vs today’s price — green range comes from the same support / VWAP logic as your stops."
          )
        )
      ),
      React.createElement("span", { className: statusBadgeClass }, statusLabel)
    ),
    insideBandButNotBuy &&
      React.createElement(
        "p",
        { className: "text-[11px] text-amber-200/90 mb-3 px-3 py-2 rounded-lg border border-amber-500/30 bg-amber-950/50 leading-snug" },
        `Price is inside the near-term band but the overall signal is ${overallVerdict} because regime and confidence gates haven\u2019t cleared \u2014 the band shows where you\u2019d buy if conditions improve, not a current buy signal.`
      ),
    React.createElement(
      "div",
      { className: "grid grid-cols-1 sm:grid-cols-2 gap-4 mb-3" },
      React.createElement(
        "div",
        {
          className:
            "rounded-xl border border-emerald-500/35 bg-emerald-950/25 px-3.5 py-3 shadow-inner shadow-black/20",
        },
        React.createElement(
          "p",
          { className: "text-[11px] text-emerald-200/80 uppercase tracking-wide font-semibold mb-1" },
          "Optimal entry (near-term)"
        ),
        React.createElement(
          "p",
          { className: "text-xl font-bold font-mono text-emerald-100 tracking-tight" },
          `$${low.toFixed(2)} – $${high.toFixed(2)}`
        ),
        ez.quality
          ? React.createElement(
              "div",
              { className: "mt-1" },
              React.createElement(
                "p",
                { className: "text-[11px] text-slate-400" },
                React.createElement("span", { className: "text-slate-500" }, "Band quality: "),
                React.createElement(
                  "span",
                  { className: String(ez.quality).toLowerCase() === "stretched" ? "text-red-300/90" : String(ez.quality).toLowerCase() === "ideal" ? "text-emerald-300/90" : "" },
                  ez.quality
                )
              ),
              String(ez.quality).toLowerCase() === "stretched" &&
                React.createElement(
                  "p",
                  { className: "text-[10px] text-amber-200/80 mt-0.5 leading-snug" },
                  "\"Stretched\" means price is extended above its key support level (VWAP or MA50) \u2014 the band is still valid but the risk/reward is less favorable here. Waiting for a pullback toward the band low improves the entry; buying now isn\u2019t wrong for long-term conviction, just less optimal short-term."
                ),
              String(ez.quality).toLowerCase() === "waiting" &&
                React.createElement(
                  "p",
                  { className: "text-[10px] text-slate-500 mt-0.5 leading-snug" },
                  "\"Waiting\" means conditions haven\u2019t aligned yet \u2014 check back after a pullback or regime shift."
                )
            )
          : null
      ),
      React.createElement(
        "div",
        {
          className:
            "rounded-xl border border-slate-600/70 bg-slate-950/50 px-3.5 py-3",
        },
        React.createElement(
          "p",
          { className: "text-[11px] text-slate-400 uppercase tracking-wide font-semibold mb-1" },
          "Current price"
        ),
        React.createElement(
          "p",
          { className: "text-xl font-bold font-mono text-slate-100 tracking-tight" },
          currentPrice > 0 ? `$${currentPrice.toFixed(2)}` : "—"
        ),
        React.createElement(
          "p",
          { className: "mt-2 text-sm font-medium text-slate-200" },
          React.createElement("span", { className: "text-slate-500 font-normal text-xs mr-2" }, "Status:"),
          statusLabel
        )
      )
    ),
    React.createElement(
      "div",
      { className: "mb-3" },
      React.createElement(
        "p",
        { className: "text-[10px] text-slate-500 mb-1 flex justify-between font-mono gap-2" },
        React.createElement("span", null, `$${low.toFixed(2)} band low`),
        React.createElement("span", null, `$${high.toFixed(2)} band high`)
      ),
      React.createElement(
        "div",
        { className: "relative h-4 rounded-full bg-slate-800/90 border border-slate-700/80" },
        React.createElement("div", {
          className: "absolute top-0 bottom-0 rounded-full bg-emerald-500/30 border border-emerald-400/25",
          style: { left: `${zoneStartPct}%`, width: `${zoneWidthPct}%` },
        }),
        React.createElement("div", {
          className:
            "absolute top-1/2 w-2.5 h-2.5 rounded-full bg-white border-2 border-emerald-600 shadow-md z-10",
          style: {
            left: `${pct}%`,
            transform: "translate(-50%, -50%)",
            top: "50%",
          },
          title: currentPrice > 0 ? `Spot $${currentPrice.toFixed(2)}` : "Spot",
        })
      ),
      React.createElement(
        "p",
        { className: "text-[10px] text-slate-500 mt-1 text-center" },
        "Dot = last price vs modeled buy band (not a forecast)."
      )
    ),
    ((maxBuyMos != null && maxBuyMos > 0) || rr != null) &&
      React.createElement(
        "div",
        { className: "mb-3 grid grid-cols-1 sm:grid-cols-2 gap-3" },
        maxBuyMos != null &&
          maxBuyMos > 0 &&
          React.createElement(
            "div",
            {
              className:
                "rounded-xl border border-cyan-500/35 bg-cyan-950/20 px-3.5 py-3",
            },
            React.createElement(
              "p",
              { className: "text-[11px] text-cyan-200/85 uppercase tracking-wide font-semibold mb-1" },
              "Max buy price (full MOS)"
            ),
            React.createElement(
              "p",
              { className: "text-lg font-bold font-mono text-cyan-100 tracking-tight" },
              `$${maxBuyMos.toFixed(2)}`
            ),
            React.createElement(
              "p",
              { className: "text-[10px] text-slate-500 mt-1 leading-snug" },
              "Rough ceiling from long-term margin-of-safety rule — stricter than the near-term band."
            )
          ),
        rr != null &&
          React.createElement(
            "div",
            {
              className:
                "rounded-xl border border-slate-600/70 bg-slate-950/50 px-3.5 py-3",
            },
            React.createElement(
              "p",
              { className: "text-[11px] text-slate-400 uppercase tracking-wide font-semibold mb-1" },
              "Near-term risk / reward"
            ),
            React.createElement(
              "p",
              { className: "text-lg font-bold font-mono text-slate-100 mb-2" },
              `1 : ${rr.toFixed(1)}`
            ),
            React.createElement(
              "div",
              { className: "flex h-2.5 rounded-full overflow-hidden bg-slate-800 border border-slate-700/80" },
              React.createElement("div", {
                className: "h-full bg-amber-500/70",
                style: { width: `${((rrRiskShare ?? 0.5) * 100).toFixed(1)}%` },
                title: "Risk (unit)",
              }),
              React.createElement("div", {
                className: "h-full bg-emerald-500/55 flex-1 min-w-0",
                title: "Reward (modeled vs stop)",
              })
            ),
            React.createElement(
              "p",
              { className: "text-[10px] text-slate-500 mt-1 leading-snug" },
              "Bar width is proportional (1 unit risk vs modeled reward). From short-term horizon math."
            ),
            rr < 0.5 &&
              React.createElement(
                "p",
                { className: "text-[10px] text-amber-200/90 mt-1.5 leading-snug border-t border-amber-500/20 pt-1.5" },
                "Near-term R:R is tight \u2014 this entry is designed for the medium/long horizon, not a 1-month trade. Size accordingly and use long-term tiers for conviction adds."
              ),
            rr >= 0.8 && (overallVerdict === "WAIT" || overallVerdict === "WATCH") &&
              React.createElement(
                "p",
                { className: "text-[10px] text-amber-200/90 mt-1.5 leading-snug border-t border-amber-500/20 pt-1.5" },
                `R:R of 1:${rr.toFixed(1)} looks reasonable, but ${overallVerdict} reflects regime/confidence gates that haven\u2019t cleared \u2014 R:R improves further if price pulls back to the entry zone low.`
              )
          )
      ),
    (stStop != null || stress != null) &&
      React.createElement(
        "div",
        {
          className:
            "rounded-lg border border-slate-700/80 bg-slate-900/40 px-3 py-2.5 grid grid-cols-1 sm:grid-cols-2 gap-3",
        },
        stStop != null &&
          React.createElement(
            "div",
            null,
            React.createElement(
              "p",
              { className: "text-[10px] text-slate-500 uppercase tracking-wide font-semibold" },
              "Risk reference (short-term stop)"
            ),
            React.createElement(
              "p",
              { className: "text-sm font-mono text-amber-200/95" },
              `~$${stStop.toFixed(2)}`
            ),
            React.createElement(
              "p",
              { className: "text-[10px] text-slate-500 mt-0.5 leading-snug" },
              "Break here challenges the tactical setup — not where we aim to initiate."
            )
          ),
        stress != null &&
          React.createElement(
            "div",
            null,
            React.createElement(
              "p",
              { className: "text-[10px] text-slate-500 uppercase tracking-wide font-semibold" },
              "Stress / structural floor"
            ),
            React.createElement(
              "p",
              { className: "text-sm font-mono text-slate-400" },
              `~$${stress.toFixed(2)}`
            ),
            React.createElement(
              "p",
              { className: "text-[10px] text-slate-500 mt-0.5 leading-snug" },
              long?.stop_loss_kind === "structural_invalidation"
                ? "Tail-risk / thesis-break reference — not an entry zone."
                : "Long-horizon floor reference."
            )
          )
      ),
    anchorNote &&
      React.createElement(
        "p",
        {
          className: "text-[11px] text-slate-400 leading-snug border-t border-slate-700/60 pt-2 mt-1",
          title: ez.anchor,
        },
        React.createElement("span", { className: "text-slate-500" }, "Why this band: "),
        anchorNote
      )
  );
}

export function InvestorDecisionSummarySection({
  summary,
  currentPrice,
  sector,
  companyName,
  ltEntryTiersOpen,
  onToggleLtTiers,
}: {
  summary: InvestorDecisionSummary;
  currentPrice: number;
  ma200?: number | null;
  sector?: string | null;
  companyName?: string | null;
  ltEntryTiersOpen: boolean;
  onToggleLtTiers: () => void;
}) {
  const {
    fair_value,
    fair_value_vs_external: fve,
    overall_verdict,
    regime_bull_pct,
    model_confidence_pct,
    horizons,
    ttm_pe_used,
    forward_pe_used,
    fair_value_metadata,
    pattern_score,
    one_answer,
    trader_roadmap,
    investor_roadmap,
  } = summary;
  const assessmentPct = currentPrice > 0 ? ((fair_value - currentPrice) / currentPrice) * 100 : 0;
  const short = horizons.short;
  const medium = horizons.medium;
  const long = horizons.long;

  const [methodologyOpen, setMethodologyOpen] = useState(false);
  const [traderOpen, setTraderOpen] = useState(false);
  const [investorOpen, setInvestorOpen] = useState(false);
  const [holdVsTradeOpen, setHoldVsTradeOpen] = useState(false);
  const [advancedDiagnosticsOpen, setAdvancedDiagnosticsOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState<{
    market: boolean;
    chart: boolean;
    flow: boolean;
    business: boolean;
  }>({
    market: false,
    chart: false,
    flow: false,
    business: false,
  });
  const verdicts = [short?.verdict, medium?.verdict, long?.verdict].filter(Boolean);
  const hasDivergence = verdicts.length >= 2 && new Set(verdicts).size > 1;
  const divergenceMessage =
    short?.verdict === "WATCH" && medium?.verdict === "BUY" && long?.verdict === "WATCH"
      ? "Short and long are cautious; medium-term setup is stronger — consider entry on pullbacks."
      : hasDivergence
        ? "Horizons disagree — short/medium/long use different inputs (RSI, volume, ML). Prefer the horizon that matches your holding period."
        : null;
  const swingVsShortLift =
    String(short?.verdict || "").toUpperCase() === "WAIT" &&
    String(medium?.verdict || "").toUpperCase() === "WATCH";
  // When pattern_score is 0, the card already shows "Confluence" fallback — avoid duplicate "Pattern score low (0/100)" block
  const patternLow = pattern_score != null && pattern_score > 0 && pattern_score < 50;
  const tldr = summary.trade_roadmap?.tldr ?? null;
  const dual = tldr?.dual_signal ?? null;
  const confidenceBand = tldr?.model_confidence_band ?? null;
  const confidenceBandMatch = confidenceBand?.match(/(\d+)\s*-\s*(\d+)%?/);
  const confidenceBandMid =
    confidenceBandMatch && confidenceBandMatch[1] && confidenceBandMatch[2]
      ? (Number(confidenceBandMatch[1]) + Number(confidenceBandMatch[2])) / 2
      : (model_confidence_pct ?? tldr?.model_confidence_pct ?? null);

  const marketStatus: "Constructive" | "Neutral" | "Cautionary" =
    dual?.display_mode === "pre_flip_watch"
      ? "Cautionary"
      : overall_verdict === "STRONG BUY" || overall_verdict === "BUY"
        ? "Constructive"
        : overall_verdict === "WATCH"
          ? "Neutral"
          : "Cautionary";
  const chartStatus: "Constructive" | "Neutral" | "Cautionary" =
    (pattern_score ?? 50) >= 65 && (short?.verdict === "BUY" || short?.verdict === "STRONG BUY")
      ? "Constructive"
      : (pattern_score ?? 50) < 45 || short?.verdict === "WAIT"
        ? "Cautionary"
        : "Neutral";
  const flowStatus: "Constructive" | "Neutral" | "Cautionary" =
    (medium?.ml_prob ?? 50) >= 60
      ? "Constructive"
      : (medium?.ml_prob ?? 50) < 40
        ? "Cautionary"
        : "Neutral";
  const businessStatus: "Constructive" | "Neutral" | "Cautionary" =
    long?.verdict === "BUY" || long?.verdict === "STRONG BUY"
      ? "Constructive"
      : long?.verdict === "WATCH"
        ? "Neutral"
        : "Cautionary";

  const combinedNotes = [
    ...(Array.isArray(one_answer?.why_this_call) ? one_answer!.why_this_call : []),
    ...(Array.isArray(one_answer?.signal_reconciliation_notes) ? one_answer!.signal_reconciliation_notes : []),
  ];
  const etaNote = combinedNotes.find((n) => /trading days/i.test(n));
  const etaDaysMatch = etaNote?.match(/(\d+)\s*trading days/i);
  const etaDays = etaDaysMatch ? Number(etaDaysMatch[1]) : null;
  const shortWaitOverallBuy =
    (String(short?.verdict || "").toUpperCase() === "WAIT" || String(short?.verdict || "").toUpperCase() === "WATCH") &&
    (overall_verdict === "BUY" || overall_verdict === "STRONG BUY");
  const mlHighHmmBlocks: Array<{ label: string; ml: number; bullPct: number }> = (
    [
      ["Short", short] as const,
      ["Medium", medium] as const,
      ["Long", long] as const,
    ] as const
  )
    .filter(([, h]) =>
      h &&
      String(h.verdict || "").toUpperCase() === "WAIT" &&
      h.ml_prob >= 80 &&
      regime_bull_pct != null &&
      regime_bull_pct < 60
    )
    .map(([label, h]) => ({
      label,
      ml: h!.ml_prob,
      bullPct: regime_bull_pct!,
    }));
  const contextFlags: Array<{ severity: "warning" | "info"; message: string }> = [
    ...(shortWaitOverallBuy
      ? [{
          severity: "info" as const,
          message: "Long-term thesis is actionable even though the short-term setup is weak \u2014 the overall BUY is driven by medium/long horizon strength, not a 1-month trade signal.",
        }]
      : []),
    ...mlHighHmmBlocks.map((m) => ({
      severity: "info" as const,
      message: `${m.label} ML is ${m.ml}% constructive but the regime gate requires HMM Bull \u2265 60% before activating \u2014 current Bull is ~${Math.round(m.bullPct)}%, so the signal is blocked. The ML read is stored; once regime clears, the verdict will upgrade automatically.`,
    })),
    ...((short?.ml_prob != null && short.ml_prob < 30 && regime_bull_pct != null && regime_bull_pct >= 80)
      ? [{
          severity: "info" as const,
          message: `Near-term ML is only ${Math.round(short.ml_prob)}% despite ${Math.round(regime_bull_pct)}% bull regime \u2014 ML is trained on price-momentum patterns (RSI, chart structure), not news or regime. It\u2019s seeing conditions that historically precede consolidation before breakouts. Regime and fundamentals are the longer-term anchor; ML is the short-term timing layer.`,
        }]
      : []),
    ...(patternLow
      ? [{
          severity: "info" as const,
          message: `Pattern reads ${Math.round(Number(pattern_score))}/100 — expand “Why this score?” below (often regime-weighted, not “bad company”).`,
        }]
      : []),
    ...(hasDivergence && divergenceMessage
      ? [{ severity: "warning" as const, message: divergenceMessage }]
      : []),
    ...((Array.isArray(one_answer?.signal_reconciliation_notes) ? one_answer.signal_reconciliation_notes : [])
      .slice(0, 2)
      .map((m) => ({ severity: "info" as const, message: m }))),
  ];
  const statusTone = (status: "Constructive" | "Neutral" | "Cautionary"): string =>
    status === "Constructive"
      ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/30"
      : status === "Cautionary"
        ? "text-amber-200 bg-amber-500/10 border-amber-500/30"
        : "text-slate-300 bg-slate-700/40 border-slate-600/60";
  const prioritizeBullets = (lines: string[], maxBullets = 3): string[] => {
    const priorityKeywords = [
      "pulls back", "entry", "stop",
      "scale", "powder", "partial",
      "loses", "reassess",
    ];
    const score = (line: string): number => {
      const lower = line.toLowerCase();
      const idx = priorityKeywords.findIndex((k) => lower.includes(k));
      return idx === -1 ? 99 : idx;
    };
    return [...lines].sort((a, b) => score(a) - score(b)).slice(0, maxBullets);
  };
  const executionBullets = prioritizeBullets(
    Array.isArray(one_answer?.execution_plan_lines) ? one_answer.execution_plan_lines : [],
    3
  );
  const whyBullets = (Array.isArray(one_answer?.why_this_call) ? one_answer.why_this_call : []).slice(0, 2);
  const marketSummary = dual?.bridge_note || tldr?.strategy || "Regime context is mixed.";
  const chartSummary = `Pattern ${Math.round(Number(pattern_score ?? 50))}/100 · Short ${short?.verdict || "N/A"} · ML ${Number(medium?.ml_prob ?? 0).toFixed(0)}%`;
  const flowSummary = `Confidence ${medium?.conviction || "mixed"} / ${long?.conviction || "mixed"}`;
  const businessSummary = `Long verdict ${long?.verdict || "N/A"} · FV gap ${assessmentPct >= 0 ? "+" : ""}${assessmentPct.toFixed(1)}%`;
  const gateRows: Array<{ label: string; value: number | null; target: number; unit: "%" | "pts" }> = [
    { label: "Regime", value: regime_bull_pct ?? null, target: 60, unit: "%" },
    { label: "Pattern", value: pattern_score ?? null, target: 60, unit: "pts" },
    { label: "Confidence", value: confidenceBandMid ?? null, target: 55, unit: "%" },
  ];
  const gateTone = (v: number | null, t: number): string =>
    v == null
      ? "text-slate-400"
      : v >= t
        ? "text-emerald-300"
        : v >= Math.max(t - 10, 0)
          ? "text-amber-300"
          : "text-red-300";

  const regimeWeather = marketWeatherFromRegimeBull(regime_bull_pct);
  const patternDecisionOneLiner = buildPatternDecisionDriverSummary({
    patternScore: pattern_score,
    regimeBullPct: regime_bull_pct,
    undervaluationPct: assessmentPct,
    shortVerdict: short?.verdict,
  });

  const CONFIDENCE_GATE_TARGET = 55;
  const ptsToConfidenceGate =
    confidenceBandMid != null && !Number.isNaN(Number(confidenceBandMid))
      ? CONFIDENCE_GATE_TARGET - Number(confidenceBandMid)
      : null;
  const confidenceNearlyThere =
    ptsToConfidenceGate != null && ptsToConfidenceGate > 0 && ptsToConfidenceGate <= 10;

  const mlHorizonGapExplainer = buildMlHorizonGapExplainer(
    short?.ml_prob,
    medium?.ml_prob,
    long?.ml_prob
  );

  return React.createElement(
    "div",
    {
      role: "region",
      "aria-label": "Investor Decision Summary",
      className: "bg-slate-800/55 border border-slate-700/80 rounded-2xl overflow-hidden shadow-xl shadow-black/20",
    },
    React.createElement(BuyRangeRetailCard, { currentPrice, short, long, overallVerdict: overall_verdict }),
    /* One Answer card (top) */
    one_answer && React.createElement(
      "div",
      { className: "p-4 border-b border-slate-700/80 bg-gradient-to-br from-emerald-500/10 via-slate-900/60 to-slate-900/40" },
      React.createElement("h3", { className: "flex items-center gap-2 text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2" },
        React.createElement(Zap, { className: "h-3.5 w-3.5 text-emerald-500" }),
        " One answer"
      ),
      React.createElement(
        "div",
        { className: "flex items-center justify-between gap-2 flex-wrap mb-2" },
        React.createElement(
          "span",
          {
            className:
              overall_verdict === "STRONG BUY" || overall_verdict === "BUY"
                ? "text-[11px] px-2 py-0.5 rounded border border-emerald-500/40 bg-emerald-500/15 text-emerald-300 font-semibold"
                : overall_verdict === "WATCH"
                  ? "text-[11px] px-2 py-0.5 rounded border border-teal-500/55 bg-teal-500/10 text-teal-200 font-semibold"
                  : overall_verdict === "WAIT"
                    ? "text-[11px] px-2 py-0.5 rounded border border-red-500/55 bg-red-500/10 text-red-200 font-semibold"
                    : "text-[11px] px-2 py-0.5 rounded border border-slate-500/40 bg-slate-500/15 text-slate-300 font-semibold",
          },
          overall_verdict
        ),
        React.createElement(
          "span",
          {
            className:
              assessmentPct >= 0
                ? "text-[11px] text-emerald-300 font-medium"
                : "text-[11px] text-red-300 font-medium",
          },
          `${Math.abs(assessmentPct).toFixed(1)}% ${assessmentPct >= 0 ? "undervalued" : "overvalued"}`
        )
      ),
      confidenceNearlyThere &&
        React.createElement(
          "div",
          {
            className:
              "mb-3 rounded-xl border-2 border-violet-400/60 bg-violet-950/45 px-3 py-2.5 shadow-[0_0_22px_-6px_rgba(167,139,250,0.45)] ring-1 ring-violet-400/25",
            role: "status",
          },
          React.createElement(
            "p",
            { className: "text-[11px] font-semibold text-violet-200 mb-0.5 flex items-center gap-1.5" },
            React.createElement("span", { className: "inline-block h-1.5 w-1.5 rounded-full bg-violet-400 animate-pulse" }),
            "Nearly there — confidence gate"
          ),
          React.createElement(
            "p",
            { className: "text-[11px] text-violet-100/95 leading-snug" },
            `Fused model confidence is ${Math.round(Number(confidenceBandMid))}% vs ${CONFIDENCE_GATE_TARGET}% used here — you’re within about ${Math.ceil(Number(ptsToConfidenceGate))} point${Math.ceil(Number(ptsToConfidenceGate)) === 1 ? "" : "s"}. Fresh sessions often move this; worth a quick revisit.`
          )
        ),
      one_answer.momentum_valuation_tension?.active &&
        React.createElement(
          "div",
          {
            className:
              "mb-3 rounded-xl border border-cyan-500/45 bg-cyan-950/35 px-3 py-2.5 ring-1 ring-cyan-400/20",
            role: "note",
          },
          React.createElement(
            "p",
            { className: "text-[11px] font-semibold text-cyan-200 mb-1" },
            one_answer.momentum_valuation_tension.headline
          ),
          React.createElement(
            "p",
            { className: "text-[11px] text-cyan-100/90 leading-snug" },
            one_answer.momentum_valuation_tension.detail
          ),
          one_answer.momentum_valuation_tension.momentum_target != null &&
            React.createElement(
              "div",
              { className: "mt-2 pt-2 border-t border-cyan-500/20 grid grid-cols-2 gap-x-4 gap-y-1" },
              React.createElement(
                "div",
                { className: "text-[10px] text-cyan-300/80" },
                "Momentum target"
              ),
              React.createElement(
                "div",
                { className: "text-[11px] font-medium text-cyan-100 text-right" },
                `$${one_answer.momentum_valuation_tension.momentum_target.toFixed(2)} (+${one_answer.momentum_valuation_tension.momentum_upside_pct ?? 0}%)`
              ),
              React.createElement(
                "div",
                { className: "text-[10px] text-cyan-300/80" },
                "Momentum stop"
              ),
              React.createElement(
                "div",
                { className: "text-[11px] font-medium text-cyan-100 text-right" },
                `$${(one_answer.momentum_valuation_tension.momentum_stop ?? 0).toFixed(2)} (-${one_answer.momentum_valuation_tension.momentum_risk_pct ?? 0}%)`
              ),
              React.createElement(
                "div",
                { className: "text-[10px] text-cyan-300/80 col-span-2 mt-1 italic" },
                one_answer.momentum_valuation_tension.momentum_target_method === "analyst_consensus_high"
                  ? "Based on analyst consensus high"
                  : "Based on ATR breakout extension"
              )
            )
        ),
      one_answer.ath_macro_regime_disconnect?.active &&
        React.createElement(
          "div",
          {
            className:
              "mb-3 rounded-xl border border-amber-500/45 bg-amber-950/30 px-3 py-2.5 ring-1 ring-amber-400/20",
            role: "note",
          },
          React.createElement(
            "p",
            { className: "text-[11px] font-semibold text-amber-200 mb-1" },
            one_answer.ath_macro_regime_disconnect.headline
          ),
          React.createElement(
            "p",
            { className: "text-[11px] text-amber-100/90 leading-snug" },
            one_answer.ath_macro_regime_disconnect.detail
          )
        ),
      React.createElement(
        "p",
        { className: "text-[11px] text-slate-400 mb-1" },
        `${companyName || "This ticker"}${sector ? ` • ${sector}` : ""} • $${currentPrice.toFixed(2)} • Fair value $${fair_value.toFixed(2)}`
      ),
      one_answer.bottom_line &&
        React.createElement(
          "p",
          { className: "text-sm font-semibold text-emerald-200/95 leading-snug mb-2" },
          one_answer.bottom_line
        ),
      React.createElement("p", { className: "text-base font-medium text-slate-100 leading-snug" }, one_answer.headline),
      one_answer.subline && React.createElement("p", { className: "mt-1 text-sm text-amber-200/90" }, one_answer.subline),
      /* --- WHY THIS CALL (promoted) --- */
      whyBullets.length > 0 &&
        React.createElement(
          "div",
          { className: "mt-3 rounded-lg border border-slate-600/70 bg-slate-900/40 px-3 py-2.5" },
          React.createElement("p", { className: "text-[10px] text-slate-500 uppercase tracking-wide font-semibold mb-1.5" }, "Why this call"),
          React.createElement(
            "ul",
            { className: "space-y-1.5 text-[11px] text-slate-200 leading-snug" },
            whyBullets.map((line, i) =>
              React.createElement(
                "li",
                { key: i, className: "flex items-start gap-2" },
                React.createElement("span", { className: "text-emerald-400 shrink-0 mt-0.5" }, "›"),
                React.createElement("span", null, line)
              )
            )
          )
        ),
      /* --- YOUR TRIGGER (promoted) --- */
      one_answer.next_trigger &&
        React.createElement(
          "div",
          { className: "mt-3 rounded-lg border border-sky-500/35 bg-sky-950/25 px-3 py-2.5" },
          React.createElement(
            "p",
            { className: "text-[11px] text-sky-100 leading-snug" },
            React.createElement("span", { className: "font-semibold text-sky-200" }, "Your trigger: "),
            one_answer.next_trigger
          )
        ),
      /* --- EXECUTION PLAN (promoted, numbered) --- */
      executionBullets.length > 0 &&
        React.createElement(
          "div",
          { className: "mt-3 rounded-lg border border-emerald-500/25 bg-emerald-950/20 px-3 py-2.5" },
          React.createElement("p", { className: "text-[10px] text-emerald-300/80 uppercase tracking-wide font-semibold mb-1.5" }, "Action plan"),
          React.createElement(
            "ol",
            { className: "space-y-1.5 text-[11px] text-slate-200 leading-snug list-none" },
            executionBullets.map((line, i) =>
              React.createElement(
                "li",
                { key: i, className: "flex items-start gap-2" },
                React.createElement("span", { className: "text-emerald-400 font-bold shrink-0 w-4 text-center" }, `${i + 1}`),
                React.createElement("span", null, line)
              )
            )
          )
        ),
      /* --- NEAR-TERM BUY STAGES PREVIEW (from trade_roadmap) --- */
      (() => {
        const stages = summary.trade_roadmap?.buy_roadmap;
        if (!Array.isArray(stages) || stages.length === 0) return null;
        const preview = stages.slice(0, 3).filter((s) => s.price_zone_low != null && s.price_zone_high != null);
        if (preview.length === 0) return null;
        return React.createElement(
          "div",
          { className: "mt-3 rounded-lg border border-slate-600/70 bg-slate-900/40 px-3 py-2.5" },
          React.createElement("p", { className: "text-[10px] text-slate-500 uppercase tracking-wide font-semibold mb-2" }, "Staged buy timeline"),
          React.createElement(
            "div",
            { className: "space-y-1.5" },
            preview.map((s) =>
              React.createElement(
                "div",
                { key: s.timeline_key, className: "flex items-center gap-2 text-[11px]" },
                React.createElement(
                  "span",
                  { className: "shrink-0 w-20 text-slate-400 font-medium" },
                  s.label
                ),
                React.createElement(
                  "span",
                  {
                    className:
                      "shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium " +
                      (s.when_to_act.toLowerCase().includes("add") || s.when_to_act.toLowerCase().includes("start")
                        ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                        : s.when_to_act.toLowerCase().includes("watch")
                          ? "bg-amber-500/10 text-amber-300 border border-amber-500/30"
                          : "bg-slate-700/40 text-slate-400 border border-slate-600/60"),
                  },
                  s.when_to_act
                ),
                React.createElement(
                  "span",
                  { className: "font-mono text-slate-300" },
                  `$${Number(s.price_zone_low).toFixed(2)}–$${Number(s.price_zone_high).toFixed(2)}`
                ),
                s.position_pct > 0 &&
                  React.createElement(
                    "span",
                    { className: "text-slate-500" },
                    `${s.position_pct}%`
                  )
              )
            )
          )
        );
      })(),
      React.createElement(
        "div",
        { className: "mt-3 rounded-xl border border-slate-700/80 bg-slate-900/50 overflow-hidden divide-y divide-slate-700/60" },
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setEvidenceOpen((s) => ({ ...s, market: !s.market })),
            className: "w-full px-3.5 py-2.5 text-left hover:bg-slate-800/70 flex items-center justify-between gap-2",
          },
          React.createElement(
            "div",
            { className: "min-w-0" },
            React.createElement(
              "span",
              { className: "text-xs text-slate-200 flex items-center gap-2" },
              "Market structure",
              React.createElement("span", { className: `text-[10px] px-1.5 py-0.5 rounded border ${statusTone(marketStatus)}` }, marketStatus)
            ),
            React.createElement("p", { className: "text-[10px] text-slate-500 mt-0.5 truncate" }, marketSummary)
          ),
          evidenceOpen.market ? React.createElement(ChevronDown, { className: "h-3.5 w-3.5 text-slate-500" }) : React.createElement(ChevronRight, { className: "h-3.5 w-3.5 text-slate-500" })
        ),
        evidenceOpen.market &&
          React.createElement(
            "p",
            { className: "px-3.5 pb-2.5 text-[11px] text-slate-300 bg-slate-950/40 leading-snug" },
            marketSummary
          ),
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setEvidenceOpen((s) => ({ ...s, chart: !s.chart })),
            className: "w-full px-3.5 py-2.5 text-left hover:bg-slate-800/70 flex items-center justify-between gap-2",
          },
          React.createElement(
            "div",
            { className: "min-w-0" },
            React.createElement(
              "span",
              { className: "text-xs text-slate-200 flex items-center gap-2" },
              "Chart & momentum",
              React.createElement("span", { className: `text-[10px] px-1.5 py-0.5 rounded border ${statusTone(chartStatus)}` }, chartStatus)
            ),
            React.createElement("p", { className: "text-[10px] text-slate-500 mt-0.5 truncate" }, chartSummary)
          ),
          evidenceOpen.chart ? React.createElement(ChevronDown, { className: "h-3.5 w-3.5 text-slate-500" }) : React.createElement(ChevronRight, { className: "h-3.5 w-3.5 text-slate-500" })
        ),
        evidenceOpen.chart &&
          React.createElement(
            "p",
            { className: "px-3.5 pb-2.5 text-[11px] text-slate-300 bg-slate-950/40 leading-snug" },
            chartSummary
          ),
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setEvidenceOpen((s) => ({ ...s, flow: !s.flow })),
            className: "w-full px-3.5 py-2.5 text-left hover:bg-slate-800/70 flex items-center justify-between gap-2",
          },
          React.createElement(
            "div",
            { className: "min-w-0" },
            React.createElement(
              "span",
              { className: "text-xs text-slate-200 flex items-center gap-2" },
              "Smart money",
              React.createElement("span", { className: `text-[10px] px-1.5 py-0.5 rounded border ${statusTone(flowStatus)}` }, flowStatus)
            ),
            React.createElement("p", { className: "text-[10px] text-slate-500 mt-0.5 truncate" }, flowSummary)
          ),
          evidenceOpen.flow ? React.createElement(ChevronDown, { className: "h-3.5 w-3.5 text-slate-500" }) : React.createElement(ChevronRight, { className: "h-3.5 w-3.5 text-slate-500" })
        ),
        evidenceOpen.flow &&
          React.createElement(
            "p",
            { className: "px-3.5 pb-2.5 text-[11px] text-slate-300 bg-slate-950/40 leading-snug" },
            `${flowSummary}. Keep sizing staged while transition risk remains.`
          ),
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setEvidenceOpen((s) => ({ ...s, business: !s.business })),
            className: "w-full px-3.5 py-2.5 text-left hover:bg-slate-800/70 flex items-center justify-between gap-2",
          },
          React.createElement(
            "div",
            { className: "min-w-0" },
            React.createElement(
              "span",
              { className: "text-xs text-slate-200 flex items-center gap-2" },
              "Business & news",
              React.createElement("span", { className: `text-[10px] px-1.5 py-0.5 rounded border ${statusTone(businessStatus)}` }, businessStatus)
            ),
            React.createElement("p", { className: "text-[10px] text-slate-500 mt-0.5 truncate" }, businessSummary)
          ),
          evidenceOpen.business ? React.createElement(ChevronDown, { className: "h-3.5 w-3.5 text-slate-500" }) : React.createElement(ChevronRight, { className: "h-3.5 w-3.5 text-slate-500" })
        ),
        evidenceOpen.business &&
          React.createElement(
            "p",
            { className: "px-3.5 pb-2.5 text-[11px] text-slate-300 bg-slate-950/40 leading-snug" },
            businessSummary
          )
      ),
      React.createElement(
        "div",
        { className: "mt-3 rounded-xl border border-slate-700/80 bg-slate-900/35 px-3.5 py-3" },
        React.createElement("p", { className: "text-[11px] text-slate-400 mb-2 uppercase tracking-wide font-semibold" }, "What would change this"),
        React.createElement(
          "div",
          { className: "space-y-2" },
          gateRows.map((g) => {
            const val = g.value;
            const shown = val == null ? "N/A" : `${Math.round(val)}${g.unit}`;
            const tgt = `${Math.round(g.target)}${g.unit}`;
            const barPct = val == null ? 0 : Math.max(0, Math.min(100, (val / g.target) * 100));
            const pass = val != null && val >= g.target;
            const isRegime = g.label === "Regime";
            const isPattern = g.label === "Pattern";
            const isConfidenceRow = g.label === "Confidence";
            const confidenceRowHot = isConfidenceRow && confidenceNearlyThere;
            return React.createElement(
              "div",
              {
                key: g.label,
                className:
                  "rounded-lg border px-2.5 py-2 " +
                  (confidenceRowHot
                    ? "border-violet-400/65 bg-violet-950/30 ring-1 ring-violet-400/35 shadow-[0_0_18px_-8px_rgba(167,139,250,0.5)]"
                    : "border-slate-700/70 bg-slate-950/40"),
              },
              React.createElement(
                "div",
                { className: "flex items-center justify-between text-[11px] gap-2" },
                React.createElement(
                  "span",
                  { className: "text-slate-300 font-medium flex items-center gap-1.5 min-w-0" },
                  isRegime ? regimeWeatherIcon(regimeWeather.weather) : null,
                  isRegime
                    ? React.createElement(
                        "span",
                        { className: "flex flex-col gap-0.5 min-w-0" },
                        React.createElement("span", null, g.label),
                        React.createElement(
                          "span",
                          { className: "text-[10px] font-normal text-slate-500 leading-tight" },
                          regimeWeather.headline
                        )
                      )
                    : g.label
                ),
                React.createElement(
                  "span",
                  { className: `${gateTone(val, g.target)} shrink-0 text-right` },
                  `${shown} -> needs ${tgt}`
                )
              ),
              isRegime &&
                React.createElement(
                  "p",
                  { className: "text-[10px] text-slate-500 mt-1 leading-snug pl-5" },
                  regimeWeather.detail
                ),
              React.createElement(
                "div",
                { className: "mt-1.5 h-1.5 rounded-full bg-slate-800 overflow-hidden" },
                React.createElement("div", {
                  className: pass ? "h-full bg-emerald-500" : "h-full bg-amber-500",
                  style: { width: `${barPct}%` },
                })
              ),
              isPattern &&
                React.createElement(
                  "p",
                  {
                    className:
                      "text-[10px] text-slate-500 mt-1.5 leading-snug border-t border-slate-700/50 pt-1.5",
                  },
                  "Raw score measures chart structure — see ",
                  React.createElement(
                    "span",
                    { className: "text-sky-300/90 font-medium" },
                    "Why this score?"
                  ),
                  " below for what actually drives it."
                )
            );
          })
        ),
        React.createElement(
          "div",
          {
            className:
              "mt-3 rounded-lg border border-sky-500/30 bg-sky-950/30 px-3 py-2.5",
            role: "note",
          },
          React.createElement(
            "p",
            { className: "text-[10px] text-sky-200/85 uppercase tracking-wide font-semibold mb-1" },
            "Why this score?"
          ),
          React.createElement(
            "p",
            { className: "text-[11px] text-sky-50/95 leading-snug" },
            patternDecisionOneLiner
          )
        ),
        React.createElement(
          "p",
          { className: "text-[11px] text-slate-400 mt-2 leading-snug" },
          etaDays != null
            ? `Estimated time: about ${etaDays} trading days if regime confirms.`
            : "Estimated time: uncertain — wait for gate progress above."
        )
      ),
      one_answer.hold_vs_trade &&
        React.createElement(
          "div",
          { className: "mt-3 rounded-lg border border-slate-600/80 bg-slate-900/40 overflow-hidden" },
          React.createElement(
            "button",
            {
              type: "button",
              onClick: () => setHoldVsTradeOpen((o) => !o),
              className: "w-full flex items-center justify-between gap-2 px-3 py-2 text-left hover:bg-slate-700/30 transition-colors",
            },
            React.createElement(
              "span",
              { className: "flex items-center gap-2 text-xs font-semibold text-slate-300" },
              React.createElement(Info, { className: "h-3.5 w-3.5 text-sky-400 shrink-0" }),
              one_answer.hold_vs_trade.title
            ),
            holdVsTradeOpen
              ? React.createElement(ChevronDown, { className: "h-4 w-4 text-slate-500 shrink-0" })
              : React.createElement(ChevronRight, { className: "h-4 w-4 text-slate-500 shrink-0" })
          ),
          holdVsTradeOpen &&
            React.createElement(
              "div",
              { className: "px-3 pb-3 pt-0 space-y-2 text-xs text-slate-400 leading-relaxed border-t border-slate-700/50" },
              React.createElement("p", { className: "text-slate-300 mt-2" }, React.createElement("span", { className: "font-medium text-slate-200" }, "Long-term (5–10+ yr): "), one_answer.hold_vs_trade.long_term),
              React.createElement("p", { className: "text-slate-300" }, React.createElement("span", { className: "font-medium text-slate-200" }, "Shorter-term / trading: "), one_answer.hold_vs_trade.short_term),
              React.createElement("p", { className: "text-sky-200/90 border-l-2 border-sky-500/50 pl-2" }, one_answer.hold_vs_trade.signal_bridge),
              React.createElement("p", { className: "text-slate-500 italic" }, one_answer.hold_vs_trade.disclaimer)
            )
        )
    ),
    React.createElement(
      "div",
      { className: "p-4 border-b border-slate-700/80 bg-slate-900/30" },
      React.createElement("p", { className: "text-xs text-slate-400 uppercase tracking-wide mb-2" }, "Which timeframe fits you?"),
      React.createElement(
        "div",
        {
          className:
            "mb-3 rounded-xl border px-3 py-2.5 " +
            (hasDivergence || swingVsShortLift
              ? "border-amber-500/45 bg-amber-500/10"
              : "border-slate-600/70 bg-slate-950/50"),
        },
        React.createElement(
          "p",
          { className: "text-[10px] text-slate-500 uppercase tracking-wide font-semibold mb-2" },
          "Horizon verdicts — compare tickers at a glance"
        ),
        React.createElement(
          "div",
          { className: "flex flex-wrap gap-2 items-center" },
          (
            [
              ["Short", short?.verdict] as const,
              ["Medium", medium?.verdict] as const,
              ["Long", long?.verdict] as const,
            ] as const
          ).map(([label, v]) =>
            React.createElement(
              "span",
              {
                key: label,
                className:
                  "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-semibold " +
                  horizonVerdictPillClass(v),
              },
              React.createElement("span", { className: "text-slate-500 font-normal" }, `${label}:`),
              v || "—"
            )
          )
        ),
        swingVsShortLift &&
          React.createElement(
            "p",
            {
              className:
                "mt-2 text-[11px] text-cyan-100/95 leading-snug border-t border-cyan-500/25 pt-2",
              role: "note",
            },
            React.createElement("span", { className: "font-semibold text-cyan-200" }, "Swing vs short-term: "),
            "Medium is WATCH while Short is WAIT — the 3‑month ladder can still allow staged adds on pullbacks even when the 1‑month tape is guarded (e.g. growth vs a defensive where both horizons sit on WAIT). Match the row to your actual holding period."
          ),
        hasDivergence &&
          divergenceMessage &&
          React.createElement(
            "p",
            { className: "mt-2 text-[11px] text-amber-200/90 leading-snug border-t border-amber-500/20 pt-2" },
            divergenceMessage
          )
      ),
      mlHorizonGapExplainer &&
        React.createElement(
          "p",
          {
            className:
              "text-[11px] text-slate-300 leading-snug mb-3 rounded-lg border border-slate-600/70 bg-slate-950/50 px-3 py-2",
            role: "note",
          },
          React.createElement(
            "span",
            { className: "font-semibold text-cyan-200/95" },
            "Why ML % differs by horizon: "
          ),
          mlHorizonGapExplainer
        ),
      React.createElement(
        "div",
        { className: "grid grid-cols-1 sm:grid-cols-3 gap-3" },
        React.createElement(HorizonCard, { horizon: short }),
        React.createElement(HorizonCard, { horizon: medium }),
        React.createElement(HorizonCard, {
          horizon: long,
          entryTiers: long.entry_tiers,
          tiersOpen: ltEntryTiersOpen,
          onToggleTiers: onToggleLtTiers,
        })
      )
    ),
    contextFlags.length > 0 &&
      React.createElement(
        "div",
        { className: "p-4 border-b border-slate-700/80 space-y-2 bg-slate-900/20" },
        contextFlags.map((flag, i) =>
          React.createElement(
            "div",
            {
              key: i,
              className:
                flag.severity === "warning"
                  ? "flex items-start gap-2 rounded-lg border border-amber-500/35 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
                  : "flex items-start gap-2 rounded-lg border border-slate-600/60 bg-slate-800/60 px-3 py-2 text-xs text-slate-300",
            },
            React.createElement("span", null, flag.severity === "warning" ? "⚠" : "i"),
            React.createElement("span", null, flag.message)
          )
        )
      ),
    /* Trader roadmap (collapsible) */
    trader_roadmap && React.createElement(
      "div",
      { className: "border-b border-slate-700" },
      React.createElement(
        "button",
        {
          type: "button",
          onClick: () => setTraderOpen((o) => !o),
          className: "w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-700/30 transition-colors",
        },
        React.createElement("span", { className: "flex items-center gap-2 text-sm font-semibold text-slate-200" },
          React.createElement(TrendingUp, { className: "h-4 w-4 text-amber-500" }),
          " Trader roadmap (short / medium)"
        ),
        traderOpen ? React.createElement(ChevronDown, { className: "h-4 w-4 text-slate-400" }) : React.createElement(ChevronRight, { className: "h-4 w-4 text-slate-400" })
      ),
      traderOpen && React.createElement(
        "div",
        { className: "px-4 pb-4 pt-0 space-y-3 text-sm" },
        React.createElement("p", { className: "text-slate-300" },
          "Today: ", React.createElement("span", { className: "font-medium text-slate-200" }, trader_roadmap.action_today.replace(/_/g, " ")), "."
        ),
        trader_roadmap.short.entry_zone && React.createElement("p", { className: "text-slate-400" },
          "Short (~1 mo): Entry $", trader_roadmap.short.entry_zone.low?.toFixed(2), "–$", trader_roadmap.short.entry_zone.high?.toFixed(2),
          trader_roadmap.short.target != null ? ` → target $${trader_roadmap.short.target.toFixed(2)}` : "",
          trader_roadmap.short.stop != null ? ` · stop $${trader_roadmap.short.stop.toFixed(2)}` : "",
          ". ", trader_roadmap.short.trigger
        ),
        trader_roadmap.medium.entry_zone && React.createElement("p", { className: "text-slate-400" },
          "Medium (3–6 mo): Entry $", trader_roadmap.medium.entry_zone.low?.toFixed(2), "–$", trader_roadmap.medium.entry_zone.high?.toFixed(2),
          trader_roadmap.medium.target != null ? ` → target $${trader_roadmap.medium.target.toFixed(2)}` : "",
          trader_roadmap.medium.stop != null ? ` · stop $${trader_roadmap.medium.stop.toFixed(2)}` : "",
          ". ", trader_roadmap.medium.trigger
        )
      )
    ),
    /* Investor roadmap (collapsible) */
    investor_roadmap && React.createElement(
      "div",
      { className: "border-b border-slate-700" },
      React.createElement(
        "button",
        {
          type: "button",
          onClick: () => setInvestorOpen((o) => !o),
          className: "w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-700/30 transition-colors",
        },
        React.createElement("span", { className: "flex items-center gap-2 text-sm font-semibold text-slate-200" },
          React.createElement(Calendar, { className: "h-4 w-4 text-emerald-500" }),
          " Investor roadmap (medium / long)"
        ),
        investorOpen ? React.createElement(ChevronDown, { className: "h-4 w-4 text-slate-400" }) : React.createElement(ChevronRight, { className: "h-4 w-4 text-slate-400" })
      ),
      investorOpen && React.createElement(
        "div",
        { className: "px-4 pb-4 pt-0 space-y-3 text-sm" },
        React.createElement("p", { className: "text-slate-300" },
          "Today: ", React.createElement("span", { className: "font-medium text-slate-200" }, investor_roadmap.action_today), "."
        ),
        investor_roadmap.add_tiers.length > 0 && React.createElement("p", { className: "text-slate-400" },
          "Add: ",
          investor_roadmap.add_tiers
            .filter((t) => t.low != null && t.high != null)
            .map((t) => `${t.label ?? t.id}: $${(t.low as number).toFixed(2)}–$${(t.high as number).toFixed(2)} (${t.allocation_pct ?? 0}%)`)
            .join(" · ")
        ),
        React.createElement("p", { className: "text-slate-400" },
          "Trim near $", investor_roadmap.trim_near.toFixed(2), ". ", investor_roadmap.hold_thesis
        )
      )
    ),
    React.createElement(
      "div",
      { className: "p-4 space-y-4" },
      React.createElement(
        "button",
        {
          type: "button",
          onClick: () => setAdvancedDiagnosticsOpen((o) => !o),
          className: "w-full rounded-lg border border-slate-700/80 bg-slate-900/40 px-3 py-2 text-left hover:bg-slate-800/50 flex items-center justify-between gap-2",
        },
        React.createElement("span", { className: "text-xs text-slate-300" }, "Advanced diagnostics (methodology, external checks, long-tier details)"),
        advancedDiagnosticsOpen ? React.createElement(ChevronDown, { className: "h-4 w-4 text-slate-500" }) : React.createElement(ChevronRight, { className: "h-4 w-4 text-slate-500" })
      ),
      advancedDiagnosticsOpen &&
        React.createElement(
          "div",
          { className: "space-y-3 rounded-lg border border-slate-700/70 bg-slate-900/40 p-3" },
          fve &&
            (fve.yahoo_12m_mean_usd != null ||
              fve.fmp_consensus_median_usd != null ||
              fve.fmp_consensus_low_usd != null) &&
            React.createElement(
              "div",
              { className: "rounded-lg border border-slate-600/50 bg-slate-900/40 px-3 py-2 text-[11px] leading-relaxed text-slate-400 space-y-1" },
              React.createElement("p", { className: "text-slate-500 font-medium" }, "External target checks"),
              fve.yahoo_12m_mean_usd != null &&
                React.createElement("p", null, `Yahoo 12m mean: $${fve.yahoo_12m_mean_usd.toFixed(2)}`),
              (fve.fmp_consensus_low_usd != null || fve.fmp_consensus_median_usd != null) &&
                React.createElement(
                  "p",
                  null,
                  "FMP consensus: ",
                  fve.fmp_consensus_low_usd != null && fve.fmp_consensus_high_usd != null
                    ? `$${fve.fmp_consensus_low_usd.toFixed(2)}-$${fve.fmp_consensus_high_usd.toFixed(2)}`
                    : "N/A",
                  fve.fmp_consensus_median_usd != null
                    ? `${fve.fmp_median_is_range_midpoint ? " | midpoint " : " | median "}$${fve.fmp_consensus_median_usd.toFixed(2)}`
                    : ""
                ),
              fve.note && React.createElement("p", { className: "text-slate-500" }, fve.note)
            ),
          fair_value_metadata &&
            (fair_value_metadata.bear_case != null || fair_value_metadata.methodology_summary || fair_value_metadata.method_used) &&
            React.createElement(
              "div",
              { className: "text-xs" },
              React.createElement(
                "button",
                {
                  type: "button",
                  onClick: () => setMethodologyOpen((o) => !o),
                  className: "flex items-center gap-1.5 text-slate-400 hover:text-slate-300",
                },
                methodologyOpen ? React.createElement(ChevronDown, { className: "h-3.5 w-3.5" }) : React.createElement(ChevronRight, { className: "h-3.5 w-3.5" }),
                React.createElement(Info, { className: "h-3.5 w-3.5" }),
                "Methodology and bear case"
              ),
              methodologyOpen &&
                React.createElement(
                  "div",
                  { className: "mt-1.5 space-y-1 text-slate-400" },
                  fair_value_metadata.bear_case != null &&
                    React.createElement("p", null, `Bear case: $${fair_value_metadata.bear_case.toFixed(2)} (FVx0.6)`),
                  fair_value_metadata.method_used &&
                    React.createElement("p", null, `Method: ${fair_value_metadata.method_used}`),
                  fair_value_metadata.methodology_summary &&
                    React.createElement("p", { className: "text-slate-500" }, fair_value_metadata.methodology_summary),
                  Array.isArray(fair_value_metadata.notes) &&
                    fair_value_metadata.notes.map((note: string, i: number) =>
                      React.createElement("p", { key: i, className: "text-slate-500" }, note)
                    )
                )
            ),
          long.entry_tiers &&
            React.createElement(
              "p",
              { className: "text-[11px] text-slate-500" },
              "Long-tier allocations and detailed caveats are available from the long-term card's + Entry Tiers control."
            )
        )
    )
  );
}
