"use client";

import React from "react";
import { CheckCircle, XCircle, AlertCircle, Target, ChevronDown, ChevronRight, AlertTriangle } from "lucide-react";

// Use bracket types to avoid ambiguous generics in .tsx (Array<T> can be parsed as JSX)
export interface InvestorDecisionSummary {
  fair_value: number;
  overall_verdict: "WAIT" | "WATCH" | "BUY" | "STRONG BUY";
  /** TTM PE used for fair value (FMP > price/trailingEps > yfinance). Shown so card reflects correct PE, not stale feed. */
  ttm_pe_used?: number;
  /** Forward PE used for fair value when available. */
  forward_pe_used?: number;
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
  const hasStop = horizon.stop_loss != null && horizon.stop_loss > 0;

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
    React.createElement("p", { className: "text-slate-500 text-xs" }, `Target: +${horizon.target_pct.toFixed(0)}% · ML prob: ${Number(horizon.ml_prob).toFixed(0)}%`),
    hasStop &&
      React.createElement(
        "p",
        { className: "text-slate-500 text-xs mt-0.5" },
        `Stop below $${Number(horizon.stop_loss).toFixed(2)}`
      ),
    hasRationale &&
      React.createElement(
        "p",
        { className: "text-slate-300 text-xs mt-2 leading-snug border-t border-slate-700/50 pt-2" },
        horizon.rationale
      ),
    hasTrigger &&
      React.createElement(
        "p",
        { className: "text-slate-400 text-[11px] mt-1.5 leading-snug" },
        React.createElement("span", { className: "text-slate-500 font-medium" }, "When to act: "),
        horizon.trigger_buy
      ),
    warnings.length > 0 &&
      React.createElement(
        "div",
        { className: "mt-2 space-y-1 border-t border-slate-700/50 pt-2" },
        warnings.map((w, i) =>
          React.createElement(
            "div",
            { key: i, className: "flex items-start gap-1.5 text-[11px] text-amber-300/90" },
            React.createElement(AlertTriangle, { className: "h-3 w-3 shrink-0 mt-0.5" }),
            React.createElement("span", null, w)
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
  const { fair_value, overall_verdict, horizons, ttm_pe_used, forward_pe_used } = summary;
  const assessmentPct = currentPrice > 0 ? ((fair_value - currentPrice) / currentPrice) * 100 : 0;
  const short = horizons.short;
  const medium = horizons.medium;
  const long = horizons.long;

  return React.createElement(
    "div",
    {
      role: "region",
      "aria-label": "Investor Decision Summary",
      className: "bg-slate-800/50 border border-slate-700 rounded-xl overflow-hidden",
    },
    React.createElement(
      "div",
      { className: "p-4 border-b border-slate-700" },
      React.createElement("h3", { className: "flex items-center gap-2 text-sm font-semibold text-slate-200 mb-3" },
        React.createElement(Target, { className: "h-4 w-4 text-emerald-500" }),
        " Investor Decision Summary"
      ),
      React.createElement(
        "div",
        { className: "flex flex-wrap items-center gap-x-4 gap-y-1 text-sm" },
        companyName && React.createElement("span", { className: "text-slate-300" }, companyName),
        sector && React.createElement("span", { className: "text-slate-500" }, sector),
        React.createElement("span", { className: "text-slate-100 font-mono" }, `$${currentPrice.toFixed(2)}`),
        React.createElement("span", { className: "text-slate-400" }, `Fair value $${fair_value.toFixed(2)}`),
        React.createElement(
          "span",
          { className: assessmentPct >= 0 ? "text-emerald-400" : "text-red-400" },
          `${assessmentPct.toFixed(1)}% ${assessmentPct >= 0 ? "undervalued" : "overvalued"}`
        ),
        (ttm_pe_used != null || forward_pe_used != null) &&
          React.createElement(
            "span",
            { className: "text-slate-500 text-xs" },
            [ttm_pe_used != null ? `TTM PE ${ttm_pe_used.toFixed(1)}×` : null, forward_pe_used != null ? `Fwd PE ${forward_pe_used.toFixed(1)}×` : null].filter(Boolean).join(" · ")
          ),
        React.createElement(
          "span",
          { className: "flex items-center gap-1" },
          verdictIcon(overall_verdict),
          React.createElement("span", { className: "font-medium text-slate-200" }, overall_verdict)
        )
      )
    ),
    React.createElement(
      "div",
      { className: "p-4 space-y-4" },
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
      ),
      ltEntryTiersOpen &&
        long.entry_tiers &&
        React.createElement(
          "div",
          { className: "pt-2 space-y-3 border-t border-slate-700" },
          long.entry_tiers.current_assessment &&
            React.createElement(
              "div",
              { className: "flex items-center gap-2 text-sm" },
              verdictIcon(long.entry_tiers.current_assessment.verdict),
              React.createElement("span", { className: "text-slate-300" }, long.entry_tiers.current_assessment.label)
            ),
          long.entry_tiers.tiers?.length
            ? React.createElement(
                "div",
                { className: "grid grid-cols-1 md:grid-cols-3 gap-3" },
                long.entry_tiers.tiers.map((tier) =>
                  React.createElement(
                    "div",
                    {
                      key: tier.id,
                      className: "rounded-lg border p-3 text-sm",
                      style: {
                        borderColor: tier.color ? `${tier.color}40` : undefined,
                        backgroundColor: tier.color ? `${tier.color}10` : undefined,
                      },
                    },
                    React.createElement("p", { className: "font-semibold text-slate-200" }, tier.label),
                    React.createElement("p", { className: "text-slate-500 text-xs mt-0.5" }, tier.description),
                    React.createElement("p", { className: "text-slate-300 mt-2 font-mono" }, `$${tier.low.toFixed(2)} – $${tier.high.toFixed(2)}`),
                    React.createElement("p", { className: "text-slate-400 text-xs mt-1" }, `Upside to FV: +${tier.upside_to_fv_pct.toFixed(1)}% · MOS: ${tier.margin_of_safety_pct.toFixed(0)}% · R/R ${tier.estimated_rr}`),
                    React.createElement("p", { className: "text-slate-500 text-xs mt-1" }, `Conviction: ${tier.conviction}`),
                    tier.reachable &&
                      tier.drop_needed_pct != null &&
                      React.createElement("p", { className: "text-amber-400 text-xs mt-1" }, `Price needs to drop ${tier.drop_needed_pct.toFixed(1)}% from current`)
                  )
                )
              )
            : null,
          long.entry_tiers.position_sizing &&
            long.entry_tiers.position_sizing.length > 0 &&
            React.createElement(
              "div",
              { className: "text-xs text-slate-500" },
              React.createElement("p", { className: "font-medium text-slate-400 mb-1" }, "Position sizing"),
              React.createElement(
                "ul",
                { className: "space-y-0.5" },
                long.entry_tiers.position_sizing.map((ps, i) =>
                  React.createElement("li", { key: i }, `${ps.tier} → ${ps.allocation_pct}% — ${ps.note}`)
                )
              )
            )
        )
    )
  );
}
