"use client";

import { clsx } from "clsx";
import type { DecisionMode } from "@/lib/decisionMode";
import { horizonLabel, primaryHorizonFromMode } from "@/lib/decisionMode";
import type { InvestorDecisionSummary, HorizonSignalPayload } from "../InvestorDecisionSummary";
import { RegimeBar } from "./RegimeBar";
import {
  deriveLongTermBehavioralBadge,
  deriveShortTermBehavioralBadge,
  filterPrimaryTradingGates,
  buildGatesFromInvestorSummary,
} from "../retailActionUX";
import {
  getHorizonZoneReconciliation,
} from "@/lib/horizonReconcile";

const LIGHT_BORDER: Record<"red" | "yellow" | "green" | "neutral", string> = {
  green: "border-emerald-500/25 bg-emerald-500/5",
  yellow: "border-amber-500/20 bg-amber-500/5",
  red: "border-red-500/25 bg-red-500/5",
  neutral: "border-slate-600/50 bg-slate-800/40",
};

const LIGHT_BADGE: Record<"red" | "yellow" | "green" | "neutral", string> = {
  green: "border-emerald-500/50 bg-emerald-500/10 text-emerald-400",
  yellow: "border-amber-500/50 bg-amber-500/10 text-amber-400",
  red: "border-red-500/50 bg-red-500/10 text-red-400",
  neutral: "border-slate-500/50 bg-slate-500/10 text-slate-300",
};

const LIGHT_DOT: Record<"red" | "yellow" | "green" | "neutral", string> = {
  green: "bg-emerald-400",
  yellow: "bg-amber-400",
  red: "bg-red-400",
  neutral: "bg-slate-400",
};

const MODE_BORDER: Record<DecisionMode, string> = {
  scout: "border-cyan-500/20",
  swing: "border-violet-500/20",
  owner: "border-emerald-500/20",
};

function planHeadline(
  mode: DecisionMode,
  short: HorizonSignalPayload,
  medium: HorizonSignalPayload,
  long: HorizonSignalPayload,
  assessmentPct: number,
  currentPrice: number,
  regimeBullPct: number | null | undefined,
  rsi: number | null | undefined,
): string {
  if (mode === "scout") return deriveShortTermBehavioralBadge(short, regimeBullPct, rsi).label;
  if (mode === "owner") return deriveLongTermBehavioralBadge(long, short, assessmentPct, currentPrice).label;
  const v = String(medium.verdict || "").toUpperCase();
  if (v === "BUY" || v === "STRONG BUY") return "Swing add zone";
  if (v === "WATCH") return "Stage on pullback";
  return "Wait — no add";
}

export function TickerCommandCard({
  summary,
  currentPrice,
  mode,
  actionTitle,
  actionLight,
}: {
  summary: InvestorDecisionSummary;
  currentPrice: number;
  mode: DecisionMode;
  actionTitle: string;
  actionLight: "red" | "yellow" | "green" | "neutral";
}) {
  const { horizons, fair_value, regime_bull_pct, rsi, one_answer } = summary;
  const short = horizons.short;
  const medium = horizons.medium;
  const long = horizons.long;
  const primaryKey = primaryHorizonFromMode(mode);
  const primary = primaryKey === "short" ? short : primaryKey === "medium" ? medium : long;

  const assessmentPct =
    currentPrice > 0 && fair_value > 0 ? ((fair_value - currentPrice) / currentPrice) * 100 : 0;

  const gates = filterPrimaryTradingGates(buildGatesFromInvestorSummary(summary, currentPrice));
  const passed = gates.filter((g) => g.pass).length;
  const hr = getHorizonZoneReconciliation(summary, currentPrice);
  const splitActive = Boolean(hr?.active);

  const headline = planHeadline(
    mode,
    short,
    medium,
    long,
    assessmentPct,
    currentPrice,
    regime_bull_pct,
    rsi ?? null,
  );

  const actionLabel = primary.verdict || one_answer?.verdict || actionTitle;
  const gateHint =
    splitActive && passed >= gates.length
      ? mode === "owner"
        ? "4/4 ST gates · core tier below"
        : "4/4 ST gates · LT tier lower"
      : null;
  const mosLabel =
    assessmentPct >= 0
      ? `${Math.abs(assessmentPct).toFixed(1)}% to FV`
      : `${Math.abs(assessmentPct).toFixed(1)}% above FV`;

  return (
    <div
      className={clsx(
        "rounded-2xl border p-4 space-y-3",
        MODE_BORDER[mode],
        LIGHT_BORDER[actionLight],
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span
              className={clsx(
                "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[11px] font-mono font-bold uppercase",
                LIGHT_BADGE[actionLight],
              )}
            >
              <span className={clsx("w-1.5 h-1.5 rounded-full animate-pulse", LIGHT_DOT[actionLight])} />
              {actionLabel}
            </span>
            <span className="text-[10px] font-mono text-slate-500 tabular-nums">
              {passed}/{gates.length} gates
            </span>
            {gateHint && (
              <span className="text-[9px] font-mono text-amber-300/90 uppercase">{gateHint}</span>
            )}
          </div>
          <p className="text-base font-semibold text-white leading-snug">{headline}</p>
          <p className="text-xs text-slate-400 mt-0.5">
            {horizonLabel(primaryKey)} · {primary.signal} strength · {primary.conviction} conviction
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xl font-bold text-white tabular-nums">
            ${currentPrice > 0 ? currentPrice.toFixed(2) : "—"}
          </p>
          <p
            className={clsx(
              "text-[11px] font-mono tabular-nums",
              assessmentPct >= 0 ? "text-teal-400" : "text-red-400",
            )}
          >
            {assessmentPct >= 0 ? "+" : "−"}
            {mosLabel}
          </p>
        </div>
      </div>

      <RegimeBar bullPct={regime_bull_pct} />

      {fair_value > 0 && (
        <div className="flex items-center gap-2 pt-1 border-t border-white/5">
          <div className="h-1.5 flex-1 rounded-full bg-slate-800 overflow-hidden">
            <div
              className={clsx(
                "h-full rounded-full",
                assessmentPct >= 0 ? "bg-gradient-to-r from-teal-600 to-teal-400" : "bg-gradient-to-r from-red-600 to-red-400",
              )}
              style={{ width: `${Math.min(100, Math.abs(assessmentPct))}%` }}
            />
          </div>
          <span className="text-[10px] font-mono text-slate-400 shrink-0 max-w-[11rem] text-right leading-tight">
            {assessmentPct >= 0 ? "Undervalued" : "Overvalued"} · FV ${fair_value.toFixed(0)}
          </span>
        </div>
      )}
    </div>
  );
}
