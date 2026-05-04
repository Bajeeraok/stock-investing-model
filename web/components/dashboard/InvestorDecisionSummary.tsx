"use client";

import React, { useState } from "react";
import { CheckCircle, XCircle, AlertCircle, ChevronDown, ChevronRight, AlertTriangle, Info, Zap, TrendingUp, Calendar } from "lucide-react";
import type { TradeRoadmapData } from "./TradeRoadmapCard";

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
    current_assessment: { verdict: string; label: string; color?: string };
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

function verdictIcon(verdict: string) {
  switch (verdict) {
    case "STRONG BUY":
    case "BUY":
      return <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0" aria-hidden />;
    case "WATCH":
      return <AlertCircle className="h-4 w-4 text-amber-400 shrink-0" aria-hidden />;
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
        ? "text-amber-400"
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
    React.createElement("p", { className: "text-slate-500 text-xs" }, `${horizon.signal} strength · ${horizon.conviction} conviction`),
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
        "button",
        {
          type: "button",
          onClick: onToggleTiers,
          className: "mt-2 flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300",
        },
        tiersOpen ? React.createElement(ChevronDown, { className: "h-3 w-3" }) : React.createElement(ChevronRight, { className: "h-3 w-3" }),
        tiersOpen ? " Hide" : "+ Entry Tiers"
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

  const marketStatus: "Supportive" | "Neutral" | "Cautionary" =
    dual?.display_mode === "pre_flip_watch"
      ? "Cautionary"
      : overall_verdict === "STRONG BUY" || overall_verdict === "BUY"
        ? "Supportive"
        : overall_verdict === "WATCH"
          ? "Neutral"
          : "Cautionary";
  const chartStatus: "Supportive" | "Neutral" | "Cautionary" =
    (pattern_score ?? 50) >= 65 && (short?.verdict === "BUY" || short?.verdict === "STRONG BUY")
      ? "Supportive"
      : (pattern_score ?? 50) < 45 || short?.verdict === "WAIT"
        ? "Cautionary"
        : "Neutral";
  const flowStatus: "Supportive" | "Neutral" | "Cautionary" =
    (medium?.ml_prob ?? 50) >= 60
      ? "Supportive"
      : (medium?.ml_prob ?? 50) < 40
        ? "Cautionary"
        : "Neutral";
  const businessStatus: "Supportive" | "Neutral" | "Cautionary" =
    long?.verdict === "BUY" || long?.verdict === "STRONG BUY"
      ? "Supportive"
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
  const contextFlags: Array<{ severity: "warning" | "info"; message: string }> = [
    ...(patternLow
      ? [{
          severity: "warning" as const,
          message: `Pattern score low (${Math.round(Number(pattern_score))}/100) - short-term setup is weaker.`,
        }]
      : []),
    ...(hasDivergence && divergenceMessage
      ? [{ severity: "warning" as const, message: divergenceMessage }]
      : []),
    ...((Array.isArray(one_answer?.signal_reconciliation_notes) ? one_answer.signal_reconciliation_notes : [])
      .slice(0, 2)
      .map((m) => ({ severity: "info" as const, message: m }))),
  ];
  const statusTone = (status: "Supportive" | "Neutral" | "Cautionary"): string =>
    status === "Supportive"
      ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/30"
      : status === "Cautionary"
        ? "text-amber-200 bg-amber-500/10 border-amber-500/30"
        : "text-slate-300 bg-slate-700/40 border-slate-600/60";

  return React.createElement(
    "div",
    {
      role: "region",
      "aria-label": "Investor Decision Summary",
      className: "bg-slate-800/55 border border-slate-700/80 rounded-2xl overflow-hidden shadow-xl shadow-black/20",
    },
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
                : overall_verdict === "WATCH" || overall_verdict === "WAIT"
                  ? "text-[11px] px-2 py-0.5 rounded border border-amber-500/40 bg-amber-500/15 text-amber-300 font-semibold"
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
      React.createElement(
        "div",
        { className: "mt-3 rounded-lg border border-slate-700/70 bg-slate-900/40 overflow-hidden" },
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setEvidenceOpen((s) => ({ ...s, market: !s.market })),
            className: "w-full px-3 py-2 text-left hover:bg-slate-800/60 flex items-center justify-between gap-2",
          },
          React.createElement(
            "span",
            { className: "text-xs text-slate-200 flex items-center gap-2" },
            "Market structure",
            React.createElement("span", { className: `text-[10px] px-1.5 py-0.5 rounded border ${statusTone(marketStatus)}` }, marketStatus)
          ),
          evidenceOpen.market ? React.createElement(ChevronDown, { className: "h-3.5 w-3.5 text-slate-500" }) : React.createElement(ChevronRight, { className: "h-3.5 w-3.5 text-slate-500" })
        ),
        evidenceOpen.market &&
          React.createElement(
            "p",
            { className: "px-3 pb-2 text-[11px] text-slate-300 border-t border-slate-700/60 pt-2" },
            dual?.bridge_note || tldr?.strategy || "Regime and structure are mixed; wait for confirmation before sizing up."
          ),
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setEvidenceOpen((s) => ({ ...s, chart: !s.chart })),
            className: "w-full px-3 py-2 text-left hover:bg-slate-800/60 flex items-center justify-between gap-2 border-t border-slate-700/60",
          },
          React.createElement(
            "span",
            { className: "text-xs text-slate-200 flex items-center gap-2" },
            "Chart & momentum",
            React.createElement("span", { className: `text-[10px] px-1.5 py-0.5 rounded border ${statusTone(chartStatus)}` }, chartStatus)
          ),
          evidenceOpen.chart ? React.createElement(ChevronDown, { className: "h-3.5 w-3.5 text-slate-500" }) : React.createElement(ChevronRight, { className: "h-3.5 w-3.5 text-slate-500" })
        ),
        evidenceOpen.chart &&
          React.createElement(
            "p",
            { className: "px-3 pb-2 text-[11px] text-slate-300 border-t border-slate-700/60 pt-2" },
            `Pattern ${Math.round(Number(pattern_score ?? 50))}/100, short-horizon verdict ${short?.verdict || "N/A"}, medium-horizon ML ${Number(medium?.ml_prob ?? 0).toFixed(0)}%.`
          ),
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setEvidenceOpen((s) => ({ ...s, flow: !s.flow })),
            className: "w-full px-3 py-2 text-left hover:bg-slate-800/60 flex items-center justify-between gap-2 border-t border-slate-700/60",
          },
          React.createElement(
            "span",
            { className: "text-xs text-slate-200 flex items-center gap-2" },
            "Smart money",
            React.createElement("span", { className: `text-[10px] px-1.5 py-0.5 rounded border ${statusTone(flowStatus)}` }, flowStatus)
          ),
          evidenceOpen.flow ? React.createElement(ChevronDown, { className: "h-3.5 w-3.5 text-slate-500" }) : React.createElement(ChevronRight, { className: "h-3.5 w-3.5 text-slate-500" })
        ),
        evidenceOpen.flow &&
          React.createElement(
            "p",
            { className: "px-3 pb-2 text-[11px] text-slate-300 border-t border-slate-700/60 pt-2" },
            `Medium/long confidence reads are ${medium?.conviction || "mixed"} / ${long?.conviction || "mixed"}. Keep sizing staged while transition risk remains.`
          ),
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setEvidenceOpen((s) => ({ ...s, business: !s.business })),
            className: "w-full px-3 py-2 text-left hover:bg-slate-800/60 flex items-center justify-between gap-2 border-t border-slate-700/60",
          },
          React.createElement(
            "span",
            { className: "text-xs text-slate-200 flex items-center gap-2" },
            "Business & news",
            React.createElement("span", { className: `text-[10px] px-1.5 py-0.5 rounded border ${statusTone(businessStatus)}` }, businessStatus)
          ),
          evidenceOpen.business ? React.createElement(ChevronDown, { className: "h-3.5 w-3.5 text-slate-500" }) : React.createElement(ChevronRight, { className: "h-3.5 w-3.5 text-slate-500" })
        ),
        evidenceOpen.business &&
          React.createElement(
            "p",
            { className: "px-3 pb-2 text-[11px] text-slate-300 border-t border-slate-700/60 pt-2" },
            `Long-horizon verdict ${long?.verdict || "N/A"} with fair value ${assessmentPct >= 0 ? "+" : ""}${assessmentPct.toFixed(1)}% vs current.`
          )
      ),
      React.createElement(
        "div",
        { className: "mt-3 rounded-lg border border-slate-700/70 bg-slate-900/30 px-3 py-2" },
        React.createElement("p", { className: "text-[11px] text-slate-400 mb-1" }, "What would change this?"),
        React.createElement(
          "div",
          { className: "text-[11px] text-slate-300 space-y-1 font-mono" },
          regime_bull_pct != null && React.createElement("p", null, `Regime  ${regime_bull_pct.toFixed(0)}% -> needs 60%`),
          React.createElement("p", null, `Pattern ${Math.round(Number(pattern_score ?? 50))} -> needs 60`),
          confidenceBandMid != null &&
            React.createElement("p", null, `Confidence ${confidenceBandMid.toFixed(0)}% -> needs 55%`)
        ),
        React.createElement(
          "p",
          { className: "text-[11px] text-slate-400 mt-2" },
          etaDays != null
            ? `Estimated time: ~${etaDays} trading days (model-based transition estimate).`
            : "Estimated time: timing uncertain; wait for gate progress above."
        )
      ),
      Array.isArray(one_answer.why_this_call) &&
        one_answer.why_this_call.length > 0 &&
        React.createElement(
          "ul",
          { className: "mt-2 space-y-1 text-xs text-slate-400 leading-snug list-disc list-inside" },
          one_answer.why_this_call.map((line, i) =>
            React.createElement("li", { key: i }, line)
          )
        ),
      one_answer.next_trigger &&
        React.createElement(
          "p",
          { className: "mt-2 text-xs text-sky-200/90 border-l-2 border-sky-500/40 pl-2 leading-snug" },
          React.createElement("span", { className: "text-sky-100 font-medium" }, "Next trigger: "),
          one_answer.next_trigger
        ),
      Array.isArray(one_answer.execution_plan_lines) &&
        one_answer.execution_plan_lines.length > 0 &&
        React.createElement(
          "ul",
          { className: "mt-2 space-y-1 text-xs text-slate-300 leading-snug list-disc list-inside" },
          one_answer.execution_plan_lines.map((line, i) =>
            React.createElement("li", { key: i }, line)
          )
        ),
      Array.isArray(one_answer.signal_reconciliation_notes) &&
        one_answer.signal_reconciliation_notes.length > 0 &&
        React.createElement(
          "ul",
          { className: "mt-2 space-y-1 text-xs text-amber-200/90 leading-snug list-disc list-inside" },
          one_answer.signal_reconciliation_notes.map((line, i) =>
            React.createElement("li", { key: i }, line)
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
