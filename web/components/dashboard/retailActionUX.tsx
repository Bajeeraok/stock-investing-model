"use client";

import React, { useMemo, useState } from "react";
import { clsx } from "clsx";
import { ChevronDown, ChevronRight, Lightbulb, Lock, Target, AlertTriangle } from "lucide-react";
import type { HorizonSignalPayload, InvestorDecisionSummary } from "./InvestorDecisionSummary";
import { marketWeatherFromRegimeBull } from "./patternDecisionDriver";
import { retailStatusClasses, retailStatusRowClasses } from "@/lib/retailStatusStyles";

const ST_ML_GATE = 25;
const REGIME_GATE = 60;
const CONFIDENCE_GATE = 55;

/** Core pre-flight gates shown in the global header (4-of-4 rule). */
export const PRIMARY_TRADING_GATE_IDS = ["valuation", "regime", "momentum", "ml"] as const;

export function filterPrimaryTradingGates(gates: TradingGateRow[]): TradingGateRow[] {
  return gates.filter((g) => (PRIMARY_TRADING_GATE_IDS as readonly string[]).includes(g.id));
}

export type BehavioralBadge = {
  emoji: string;
  label: string;
  tone: "red" | "amber" | "green" | "slate";
  hint?: string;
};

export type TradingGateRow = {
  id: string;
  label: string;
  detail: string;
  pass: boolean;
  icon: string;
  blockerWeight: number;
  /** Backend token: cleared | blocked | bull | stormy | hot */
  visualStatus?: string;
  gateCleared?: boolean;
  rsiStatus?: string;
  regimeWeatherStatus?: string;
};

/** API retail_action / retail_status block from FastAPI. */
export type RetailActionPayload = {
  gate_cleared?: boolean;
  gates_locked_count?: number;
  go_no_go?: "go" | "no_go";
  rsi_status?: string;
  regime_weather_status?: string;
  rr_status?: string;
  rr_ratio?: number;
  inside_buy_band?: boolean;
  assessment_pct?: number;
  action_title?: string;
  action_light?: "green" | "yellow" | "red";
  dynamic_subtitle?: string;
  coherent_story?: string;
  next_trigger?: {
    headline: string;
    detail: string;
    estimated_days?: number | null;
  } | null;
  stock_regime_bull_pct?: number | null;
  market_regime_bull_pct?: number | null;
  gates?: Array<{
    id: string;
    label: string;
    detail: string;
    pass: boolean;
    gate_cleared?: boolean;
    visual_status?: string;
    icon?: string;
    blocker_weight?: number;
    rsi_status?: string;
    regime_weather_status?: string;
    marginal_pass?: boolean;
  }>;
  primary_gate_ids?: string[];
};

export function mapApiGateToRow(g: NonNullable<RetailActionPayload["gates"]>[number]): TradingGateRow {
  return {
    id: g.id,
    label: g.label,
    detail: g.detail,
    pass: g.pass,
    icon: g.icon ?? (g.pass ? "✅" : "❌"),
    blockerWeight: g.blocker_weight ?? 0,
    visualStatus: g.visual_status,
    gateCleared: g.gate_cleared ?? g.pass,
    rsiStatus: g.rsi_status,
    regimeWeatherStatus: g.regime_weather_status,
  };
}

export function gatesFromRetailActionPayload(payload: RetailActionPayload | null | undefined): TradingGateRow[] | null {
  if (!payload?.gates?.length) return null;
  return payload.gates.map(mapApiGateToRow);
}

export type GlobalActionHeaderProps = {
  ticker: string;
  companyName?: string | null;
  sector?: string | null;
  currentPrice?: number | null;
  statusTitle: string;
  statusLight: "red" | "yellow" | "green" | "neutral";
  assessmentPct: number;
  gates: TradingGateRow[];
  /** When true, RSI-in-band copy can surface in the dynamic subtitle. */
  insideBuyBand?: boolean;
  rsi?: number | null;
  coherentStory?: string | null;
  nextTrigger?: RetailActionPayload["next_trigger"];
};

// ─── Behavioral badges (horizon cards) ───────────────────────────────────────

export function deriveShortTermBehavioralBadge(
  horizon: HorizonSignalPayload,
  regimeBullPct: number | null | undefined,
  rsi?: number | null
): BehavioralBadge {
  const verdict = String(horizon.verdict || "").toUpperCase();
  const quality = String(horizon.entry_zone?.quality || "").toLowerCase();
  const ml = Number(horizon.ml_prob);
  const rsiElevated =
    (rsi != null && rsi >= 50) ||
    quality.includes("stretch") ||
    quality.includes("elevated") ||
    /rsi\s*(6[0-9]|[7-9]\d|100)/i.test(horizon.rationale || "") ||
    /rsi\s*elevated/i.test(horizon.entry_zone?.anchor || "");

  if (verdict === "WAIT" || (verdict === "WATCH" && rsiElevated)) {
    return { emoji: "🔴", label: "DO NOT CHASE", tone: "red", hint: "Wait for pullback — momentum is extended." };
  }
  if (
    (verdict === "BUY" || verdict === "STRONG BUY") &&
    ml >= ST_ML_GATE &&
    (quality.includes("ideal") || quality.includes("acceptable") || quality.includes("in zone"))
  ) {
    return { emoji: "🟢", label: "TACTICAL ENTRY", tone: "green", hint: "Near-term add window is open — size to plan." };
  }
  if (verdict === "WATCH") {
    return { emoji: "🟡", label: "WATCH — SET ALERTS", tone: "amber", hint: "Setup forming; not a full green light." };
  }
  if (regimeBullPct != null && regimeBullPct < 48 && ml >= ST_ML_GATE) {
    return { emoji: "🟡", label: "ML OK — REGIME BLOCKED", tone: "amber", hint: "Chart likes it; macro gate has not cleared." };
  }
  return { emoji: "⚪", label: verdict || "WAIT", tone: "slate" };
}

export function deriveLongTermBehavioralBadge(
  long: HorizonSignalPayload,
  short: HorizonSignalPayload,
  assessmentPct: number,
  currentPrice: number
): BehavioralBadge {
  const tiers = long.entry_tiers?.tiers ?? [];
  const inAnyTier = currentPrice > 0 && tiers.some((t) => currentPrice >= t.low && currentPrice <= t.high);
  const t1 = tiers.find((t) => t.id === "T1") ?? tiers[0];
  const aboveAllTiers = t1 != null && currentPrice > 0 && currentPrice > t1.high;

  if (inAnyTier) {
    const active = tiers.find((t) => currentPrice >= t.low && currentPrice <= t.high);
    return {
      emoji: "🟢",
      label: `BUY THE TIER (${active?.id ?? "T1"})`,
      tone: "green",
      hint: "Inside a long-term accumulation band — scale per tier notes.",
    };
  }
  const shortGuarded =
    String(short.verdict || "").toUpperCase() === "WAIT" ||
    String(short.verdict || "").toUpperCase() === "WATCH";
  if (assessmentPct >= 5 && (shortGuarded || aboveAllTiers)) {
    return {
      emoji: "🟡",
      label: "ACCUMULATION PAUSE",
      tone: "amber",
      hint: "Cheap long-term, but tape is hot — wait for a cleaner dip.",
    };
  }
  const v = String(long.verdict || "").toUpperCase();
  if (v === "BUY" || v === "STRONG BUY") {
    return { emoji: "🟢", label: "CORE ACCUMULATION", tone: "green", hint: "Stage in on tier ladder — do not chase spikes." };
  }
  return { emoji: "🟡", label: "PATIENT ACCUMULATION", tone: "amber", hint: "Use tier ladder only on dips." };
}

export function BehavioralActionBadge({ badge }: { badge: BehavioralBadge }) {
  const toneClass =
    badge.tone === "green"
      ? "border-emerald-500/55 bg-emerald-500/15 text-emerald-100"
      : badge.tone === "amber"
        ? "border-amber-500/50 bg-amber-500/12 text-amber-100"
        : badge.tone === "red"
          ? "border-red-500/55 bg-red-500/12 text-red-100"
          : "border-slate-600 bg-slate-800/80 text-slate-200";

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 text-sm font-bold uppercase tracking-wide px-2.5 py-1 rounded-lg border",
        toneClass
      )}
      title={badge.hint}
    >
      <span aria-hidden>{badge.emoji}</span>
      {badge.label}
    </span>
  );
}

// ─── 1. Global action header (3-second rule) ─────────────────────────────────

export function buildTradingGateRows(input: {
  assessmentPct: number;
  regimeBullPct: number | null | undefined;
  patternScore: number | null | undefined;
  shortMlProb: number | null | undefined;
  rsi: number | null | undefined;
  confidenceMid: number | null | undefined;
}): TradingGateRow[] {
  const weather = marketWeatherFromRegimeBull(input.regimeBullPct);
  const regimeOk = input.regimeBullPct != null && input.regimeBullPct >= REGIME_GATE;
  const rsi = input.rsi ?? 50;
  const valuationOk = input.assessmentPct >= 5;
  const momentumOk = rsi < 50 && (input.patternScore ?? 0) >= 45;
  const mlOk = (input.shortMlProb ?? 0) >= ST_ML_GATE;
  const confOk = (input.confidenceMid ?? 0) >= CONFIDENCE_GATE;

  return [
    {
      id: "valuation",
      label: "VALUATION",
      detail: valuationOk
        ? `Deeply Undervalued (+${Math.abs(input.assessmentPct).toFixed(1)}% Fair Value)`
        : input.assessmentPct >= 0
          ? `Modest discount (+${input.assessmentPct.toFixed(1)}% Fair Value)`
          : `Rich vs Fair Value (${input.assessmentPct.toFixed(1)}%)`,
      pass: valuationOk,
      icon: valuationOk ? "✅" : "❌",
      blockerWeight: valuationOk ? 0 : 30,
    },
    {
      id: "regime",
      label: "MARKET WEATHER",
      detail: regimeOk
        ? `${weather.headline} · HMM bull ${Math.round(input.regimeBullPct!)}%`
        : `Stormy Tape (HMM Regime Non-Bull · ${input.regimeBullPct != null ? Math.round(input.regimeBullPct) : "—"}%)`,
      pass: regimeOk,
      icon: regimeOk ? "☀️" : weather.weather === "stormy" ? "⚡" : "🌧️",
      blockerWeight: regimeOk ? 0 : 45,
    },
    {
      id: "momentum",
      label: "MOMENTUM CHOP",
      detail: momentumOk
        ? `RSI ${rsi.toFixed(0)} · pattern ${Math.round(input.patternScore ?? 0)}/100`
        : rsi >= 50
          ? `RSI is extended (${rsi.toFixed(0)}/100)`
          : `Pattern weak (${Math.round(input.patternScore ?? 0)}/100)`,
      pass: momentumOk,
      icon: momentumOk ? "📉" : "📈",
      blockerWeight: momentumOk ? 0 : rsi >= 50 ? 40 : 25,
    },
    {
      id: "ml",
      label: "ML PROBABILITY",
      detail: mlOk
        ? `Validated setup (${Math.round(input.shortMlProb ?? 0)}% vs ${ST_ML_GATE}% threshold)`
        : `Weak short ML (${Math.round(input.shortMlProb ?? 0)}% · need ${ST_ML_GATE}%+)`,
      pass: mlOk,
      icon: "🤖",
      blockerWeight: mlOk ? 0 : 20,
    },
    {
      id: "confidence",
      label: "CONFIDENCE",
      detail:
        input.confidenceMid != null
          ? `${Math.round(input.confidenceMid)}% fused confidence (gate ${CONFIDENCE_GATE}%+)`
          : "Confidence not available",
      pass: confOk,
      icon: "🎯",
      blockerWeight: confOk ? 0 : 15,
    },
  ];
}

/** Build pre-flight gates from investor summary (ticker detail + One Answer tab). */
export function buildGatesFromInvestorSummary(
  inv: {
    fair_value: number;
    regime_bull_pct?: number | null;
    pattern_score?: number | null;
    rsi?: number | null;
    model_confidence_pct?: number | null;
    trade_roadmap?: {
      tldr?: { model_confidence_band?: string | null; model_confidence_pct?: number | null } | null;
    } | null;
    horizons?: { short?: { ml_prob?: number | null } | null };
    retail_action?: RetailActionPayload | null;
  },
  currentPrice: number
): TradingGateRow[] {
  const fromApi = gatesFromRetailActionPayload(inv.retail_action);
  if (fromApi) return fromApi;

  const assessmentPct =
    currentPrice > 0 && inv.fair_value > 0
      ? ((inv.fair_value - currentPrice) / currentPrice) * 100
      : 0;
  const band = inv.trade_roadmap?.tldr?.model_confidence_band?.match(/(\d+)\s*-\s*(\d+)/);
  const confidenceMid =
    band && band[1] && band[2]
      ? (Number(band[1]) + Number(band[2])) / 2
      : inv.model_confidence_pct ?? inv.trade_roadmap?.tldr?.model_confidence_pct ?? null;

  return buildTradingGateRows({
    assessmentPct,
    regimeBullPct: inv.regime_bull_pct,
    patternScore: inv.pattern_score,
    shortMlProb: inv.horizons?.short?.ml_prob ?? null,
    rsi: inv.rsi ?? null,
    confidenceMid,
  });
}

export function buildDynamicActionSubtitle(
  gates: TradingGateRow[],
  assessmentPct: number,
  rsi: number | null | undefined,
  insideBuyBand?: boolean
): string {
  const failed = gates.filter((g) => !g.pass).sort((a, b) => b.blockerWeight - a.blockerWeight);
  const passed = gates.filter((g) => g.pass).length;
  const total = gates.length;

  if (failed.length === 0) {
    return "All trading gates are green — confirm sizing on Roadmaps before adding risk.";
  }

  const top = failed[0];
  if (top.id === "momentum" && rsi != null && rsi >= 50 && insideBuyBand) {
    return `Price is inside the buy band, but short-term RSI (${rsi.toFixed(0)}) is too hot to chase today.`;
  }
  if (top.id === "regime") {
    return assessmentPct >= 5
      ? "Valuation is highly attractive, but market weather is stormy. Sit on your hands and wait for a cleaner dip."
      : "Macro regime is risk-off — wait for bull tape before sizing new entries.";
  }
  if (top.id === "valuation") {
    return "Little margin of safety vs model fair value — patience beats forcing a trade here.";
  }
  if (top.id === "ml") {
    return "ML has not validated the near-term setup yet — let probability catch up before entry.";
  }

  return `${passed} of ${total} gates pass · top blocker: ${top.label.toLowerCase().replace(/_/g, " ")} (${top.detail}).`;
}

function setupQualityLabel(passed: number, total: number): string {
  if (total <= 0) return "UNKNOWN";
  if (passed >= total) return "HIGH";
  if (passed >= total - 1) return "MEDIUM-HIGH";
  if (passed >= total - 2) return "MIXED";
  return "LOW";
}

function statusEmoji(light: GlobalActionHeaderProps["statusLight"]): string {
  if (light === "green") return "🟢";
  if (light === "red") return "🔴";
  return "⚠️";
}

export function GlobalActionHeader({
  ticker,
  companyName,
  sector,
  currentPrice,
  statusTitle,
  statusLight,
  assessmentPct,
  gates,
  insideBuyBand = false,
  rsi,
  coherentStory,
  nextTrigger,
}: GlobalActionHeaderProps) {
  const primaryGates = filterPrimaryTradingGates(gates);
  const displayGates = primaryGates.length > 0 ? primaryGates : gates;
  const passCount = displayGates.filter((g) => g.pass).length;
  const gateTotal = displayGates.length;
  const dynamicLine = buildDynamicActionSubtitle(displayGates, assessmentPct, rsi, insideBuyBand);
  const storyLine = coherentStory?.trim() || dynamicLine;

  const marginalCount = displayGates.filter((g) => g.visualStatus === "marginal").length;

  const accent =
    statusLight === "green"
      ? "from-emerald-950/90 via-slate-950 to-slate-950 border-emerald-500/40"
      : statusLight === "red"
        ? "from-red-950/90 via-slate-950 to-slate-950 border-red-500/40"
        : "from-amber-950/90 via-slate-950 to-slate-950 border-amber-500/40";

  return (
    <header className={clsx("border-b bg-gradient-to-b", accent)}>
      <div className="px-4 sm:px-6 pt-3 pb-2 border-b border-white/5 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Now</p>
          <p className="text-base sm:text-lg font-semibold text-slate-100">
            <span className="font-mono text-emerald-400">{ticker}</span>
            {companyName ? <span className="text-slate-300 font-normal"> · {companyName}</span> : null}
          </p>
        </div>
        {currentPrice != null && currentPrice > 0 && (
          <p className="text-lg font-mono font-bold text-slate-100 tabular-nums">${currentPrice.toFixed(2)}</p>
        )}
      </div>
      {sector && (
        <p className="px-4 sm:px-6 pb-2 text-sm uppercase tracking-wider text-slate-500">{sector}</p>
      )}
      <div className="px-4 sm:px-6 pb-3">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500 mb-1">Status</p>
        <p className="text-xl sm:text-2xl font-black tracking-tight text-slate-50 flex items-center gap-2">
          <span aria-hidden>{statusEmoji(statusLight)}</span>
          {statusTitle}
        </p>
        <p className="mt-2 text-sm text-slate-200/95 leading-relaxed max-w-3xl border-l-2 border-sky-500/40 pl-3">
          {storyLine}
        </p>
        {nextTrigger && (
          <div className="mt-3 rounded-lg border border-emerald-500/25 bg-emerald-950/25 px-3 py-2.5 max-w-3xl">
            <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-400/90">Next trigger</p>
            <p className="text-sm font-semibold text-emerald-100 mt-0.5">{nextTrigger.headline}</p>
            {nextTrigger.detail ? (
              <p className="text-xs text-slate-300 mt-1 leading-snug">{nextTrigger.detail}</p>
            ) : null}
          </div>
        )}
      </div>
      <div className="px-3 sm:px-5 pb-4">
        <TradingGateStatus gates={displayGates} />
        {gateTotal > 0 && (
          <p className="mt-2 px-1 text-xs text-slate-500">
            Gates:{" "}
            <span className="text-slate-200 font-semibold tabular-nums">
              {passCount} of {gateTotal} pass
              {marginalCount > 0 ? ` (${marginalCount} marginal)` : ""}
              {" · "}
              {setupQualityLabel(passCount, gateTotal)}
            </span>
          </p>
        )}
      </div>
    </header>
  );
}

// ─── 3. Trading gate status (pre-flight) ───────────────────────────────────

export function TradingGateStatus({ gates, className }: { gates: TradingGateRow[]; className?: string }) {
  const passCount = gates.filter((g) => g.pass).length;
  const total = gates.length;
  const locked = total - passCount;
  const allGo = locked === 0;

  return (
    <section
      className={clsx(
        "rounded-xl border border-slate-600/80 bg-slate-950/80 overflow-hidden shadow-inner shadow-black/30",
        className
      )}
      aria-label="Trading gate status"
    >
      <div className="px-3.5 py-2 border-b border-slate-700/70 bg-slate-900/80 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-bold uppercase tracking-[0.15em] text-slate-300">
            Trading gate status
          </p>
          <p className="text-xs text-slate-500 mt-0.5 normal-case tracking-normal font-normal">
            If / then — what must be true before you add size
          </p>
        </div>
        <span
          className={clsx(
            "text-xs font-bold uppercase px-2.5 py-1 rounded border tracking-wide",
            allGo
              ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
              : "border-red-500/45 bg-red-500/10 text-red-200"
          )}
        >
          {allGo ? "Go" : "No-Go"}
        </span>
      </div>
      <ul className="divide-y divide-slate-800/90 text-sm">
        {gates.map((g) => {
          const visual = g.visualStatus ?? (g.pass ? "cleared" : g.pass === false ? "blocked" : "neutral");
          const isMarginal = visual === "marginal" && g.pass;
          return (
          <li
            key={g.id}
            className={clsx(
              "px-3.5 py-3 border-l-2",
              retailStatusRowClasses(visual, g.pass),
              g.pass && !isMarginal ? "border-l-emerald-600/60" : isMarginal ? "border-l-amber-600/60" : "border-l-orange-600/70"
            )}
          >
            <div className="flex items-start gap-2 sm:gap-3">
              <span className="shrink-0 font-mono text-sm pt-0.5" aria-hidden>
                {isMarginal ? "⚠️" : g.pass ? "✅" : "❌"}
              </span>
              <div className="min-w-0 flex-1 space-y-1.5">
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className={clsx("shrink-0 font-bold uppercase tracking-wide flex items-center gap-1.5", retailStatusClasses(visual, "text"))}>
                    <span aria-hidden>{g.icon}</span>
                    {g.label}
                  </span>
                  <span
                    className="hidden sm:block flex-1 border-b border-dotted border-slate-600/80 min-w-[1.5rem] translate-y-[-3px]"
                    aria-hidden
                  />
                  <span
                    className={clsx(
                      "shrink-0 font-bold uppercase text-xs px-2 py-0.5 rounded border",
                      isMarginal
                        ? retailStatusClasses("marginal")
                        : retailStatusClasses(g.pass ? "cleared" : "blocked")
                    )}
                  >
                    {isMarginal ? "Marginal" : g.pass ? "Pass" : "Fail"}
                  </span>
                </div>
                <p className="text-slate-300 leading-snug pl-0 sm:pl-0">{g.detail}</p>
              </div>
            </div>
          </li>
          );
        })}
      </ul>
      <div
        className={clsx(
          "px-3.5 py-2.5 border-t text-sm leading-snug flex items-start gap-2",
          allGo ? "border-emerald-500/30 bg-emerald-950/40 text-emerald-100" : "border-amber-500/30 bg-amber-950/30 text-amber-100"
        )}
      >
        <span className="shrink-0" aria-hidden>
          👉
        </span>
        <span>
          {allGo ? (
            <strong className="text-emerald-300">ACTION:</strong>
          ) : (
            <strong className="text-amber-200">ACTION REQUIRED:</strong>
          )}{" "}
          {allGo
            ? " Gates are open — still confirm stops and size on Roadmaps."
            : ` ${locked} gate${locked === 1 ? "" : "s"} still locked (${passCount}/${total} pass). Do not initiate new entries.`}
        </span>
      </div>
    </section>
  );
}

// ─── Dashboard list view (signals table) ───────────────────────────────────

export type SignalListInput = {
  ticker: string;
  close: number | null;
  rsi: number | null;
  confluence_score?: number | null;
  composite_buy?: number | null;
  ml_short_prob?: number | null;
  plan_action?: string | null;
  plan_confidence?: number | null;
  signal?: string | null;
  st_band?: { low: number; high: number } | null;
  lt_band?: { low: number; high: number } | null;
  retail_status?: RetailActionPayload | null;
  rsi_status?: string | null;
  gate_cleared?: boolean | null;
};

export type SignalListContext = {
  regimeBullPct?: number | null;
};

export function deriveRegimeBullPctFromDashboard(ctx: {
  globalMarketRegime?: string | null;
  macroRegime?: string | null;
  hmmBearPct?: number | null;
}): number | null {
  if (ctx.hmmBearPct != null && !Number.isNaN(ctx.hmmBearPct)) {
    return Math.max(0, Math.min(100, 100 - ctx.hmmBearPct));
  }
  const g = ctx.globalMarketRegime?.toUpperCase();
  if (g === "BULL") return 68;
  if (g === "BEAR") return 32;
  if (g === "NEUTRAL") return 50;
  if (ctx.macroRegime === "Risk-On") return 62;
  if (ctx.macroRegime === "Risk-Off") return 38;
  return 50;
}

export function deriveAssessmentPctFromSignal(
  close: number | null | undefined,
  ltBand?: { low: number; high: number } | null
): number {
  if (close == null || !(close > 0) || !ltBand) return 0;
  const fv = (ltBand.low + ltBand.high) / 2;
  return ((fv - close) / close) * 100;
}

export function signalInsideStBand(signal: SignalListInput): boolean {
  const close = signal.close;
  const band = signal.st_band;
  if (close == null || !band) return false;
  const low = Math.min(band.low, band.high);
  const high = Math.max(band.low, band.high);
  return close >= low && close <= high;
}

export function buildSignalListGates(signal: SignalListInput, listContext: SignalListContext): TradingGateRow[] {
  const fromApi = gatesFromRetailActionPayload(signal.retail_status);
  if (fromApi) return fromApi;

  return buildTradingGateRows({
    assessmentPct: deriveAssessmentPctFromSignal(signal.close, signal.lt_band),
    regimeBullPct: listContext.regimeBullPct,
    patternScore: signal.confluence_score ?? signal.composite_buy,
    shortMlProb: signal.ml_short_prob != null ? signal.ml_short_prob * 100 : null,
    rsi: signal.rsi,
    confidenceMid: signal.plan_confidence != null ? signal.plan_confidence * 100 : null,
  });
}

export function deriveListActionStatus(signal: SignalListInput): {
  title: string;
  light: GlobalActionHeaderProps["statusLight"];
} {
  const pa = String(signal.plan_action || signal.signal || "HOLD").toUpperCase();
  if (pa.includes("STRONG BUY") || (pa.includes("BUY") && !pa.includes("WATCH") && !pa.includes("AVOID"))) {
    return { title: "TACTICAL ENTRY", light: "green" };
  }
  if (pa.includes("AVOID") || pa.includes("REDUCE") || pa.includes("SELL")) {
    return { title: "DO NOT CHASE", light: "red" };
  }
  if (pa.includes("WAIT")) {
    return { title: "DO NOT CHASE", light: "red" };
  }
  return { title: "WATCH OR HOLD", light: "yellow" };
}

const GATE_MINI_LABEL: Record<string, string> = {
  valuation: "Val",
  regime: "Wx",
  momentum: "Mom",
  ml: "ML",
};

export function TradingGateMiniPills({ gates, className }: { gates: TradingGateRow[]; className?: string }) {
  const primary = filterPrimaryTradingGates(gates);
  const locked = primary.filter((g) => !g.pass).length;
  const allGo = locked === 0;

  return (
    <div className={clsx("flex flex-wrap items-center gap-1", className)}>
      {primary.map((g) => {
        const visual = g.visualStatus ?? (g.pass ? "cleared" : "blocked");
        return (
        <span
          key={g.id}
          title={`${g.label}: ${g.detail} · ${g.pass ? "Pass" : "Fail"}`}
          className={clsx(
            "inline-flex items-center gap-0.5 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border tabular-nums",
            retailStatusClasses(visual)
          )}
        >
          <span aria-hidden>{g.pass ? "✓" : "✕"}</span>
          {GATE_MINI_LABEL[g.id] ?? g.label.slice(0, 3)}
        </span>
        );
      })}
      <span
        className={clsx(
          "text-[9px] font-semibold uppercase",
          allGo ? "text-emerald-400" : "text-amber-300"
        )}
      >
        {allGo ? "Go" : `${locked}/4 locked`}
      </span>
    </div>
  );
}

function listStatusEmoji(light: GlobalActionHeaderProps["statusLight"]): string {
  if (light === "green") return "🟢";
  if (light === "red") return "🔴";
  return "⚠️";
}

export function CompactSignalActionStrip({
  signal,
  listContext,
  oneLiner,
  variant = "card",
  onOpenDetail,
}: {
  signal: SignalListInput;
  listContext: SignalListContext;
  oneLiner?: string | null;
  variant?: "card" | "column";
  onOpenDetail?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const gates = useMemo(() => buildSignalListGates(signal, listContext), [signal, listContext]);
  const primaryGates = useMemo(() => filterPrimaryTradingGates(gates), [gates]);
  const status = deriveListActionStatus(signal);
  const assessmentPct = deriveAssessmentPctFromSignal(signal.close, signal.lt_band);
  const insideBuyBand = signalInsideStBand(signal);
  const subtitle =
    oneLiner?.trim() ||
    signal.retail_status?.dynamic_subtitle ||
    buildDynamicActionSubtitle(primaryGates, assessmentPct, signal.rsi, insideBuyBand);
  const displayStatus = signal.retail_status?.action_title
    ? {
        title: signal.retail_status.action_title,
        light: (signal.retail_status.action_light ?? status.light) as GlobalActionHeaderProps["statusLight"],
      }
    : status;

  const wrapClass =
    variant === "card"
      ? "rounded-lg border border-slate-700/80 bg-gradient-to-br from-slate-950/90 to-slate-900/50 px-3 py-2.5"
      : "min-w-[14rem] max-w-[18rem]";

  return (
    <div className={wrapClass}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Now</p>
          <p className="text-sm font-black text-slate-100 flex items-center gap-1.5 leading-tight">
            <span aria-hidden>{listStatusEmoji(displayStatus.light)}</span>
            <span className="truncate">{displayStatus.title}</span>
          </p>
        </div>
        {variant === "card" && onOpenDetail && (
          <button
            type="button"
            onClick={onOpenDetail}
            className="shrink-0 text-xs font-semibold text-emerald-400 hover:text-emerald-300 uppercase"
          >
            Detail
          </button>
        )}
      </div>
      <p className="mt-1.5 text-sm text-slate-300/95 leading-snug line-clamp-2 italic">&ldquo;{subtitle}&rdquo;</p>
      <div className="mt-2">
        <TradingGateMiniPills gates={gates} />
      </div>
      {variant === "card" && (
        <button
          type="button"
          onClick={() => setExpanded((o) => !o)}
          className="mt-2 text-xs text-slate-500 hover:text-slate-300 flex items-center gap-1"
        >
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          {expanded ? "Hide gate checklist" : "Show gate checklist"}
        </button>
      )}
      {expanded && variant === "card" && (
        <div className="mt-2">
          <TradingGateStatus gates={primaryGates} />
        </div>
      )}
    </div>
  );
}

// Legacy export — delegates to new gate builder
export type ReadinessRow = TradingGateRow & { condition: string; statusLabel: string; ready: boolean };

export function buildTradeReadinessRows(input: Parameters<typeof buildTradingGateRows>[0]): ReadinessRow[] {
  return buildTradingGateRows(input).map((g) => ({
    ...g,
    condition: g.label,
    statusLabel: g.detail,
    ready: g.pass,
  }));
}

export function TradeReadinessChecklist({
  rows,
  className,
}: {
  rows: ReadinessRow[];
  className?: string;
  compact?: boolean;
}) {
  const gates: TradingGateRow[] = rows.map((r) => ({
    id: r.id,
    label: r.label || r.condition,
    detail: r.detail || r.statusLabel,
    pass: r.pass ?? r.ready,
    icon: r.icon,
    blockerWeight: r.blockerWeight ?? 0,
  }));
  return <TradingGateStatus gates={gates} className={className} />;
}

// ─── 2. Stop → target risk bar (short-term thermometer) ─────────────────────

export function StopTargetRiskBar({
  stopLoss,
  target,
  currentPrice,
  className,
}: {
  stopLoss: number;
  target: number;
  currentPrice: number;
  className?: string;
}) {
  const stop = Math.min(stopLoss, target, currentPrice);
  const tgt = Math.max(stopLoss, target, currentPrice);
  const span = tgt - stop;
  if (!(span > 0)) return null;

  const pct = Math.max(0, Math.min(100, ((currentPrice - stop) / span) * 100));
  const riskPct = pct;
  const rewardPct = 100 - pct;
  const tightReward = rewardPct < 35;

  return (
    <div className={clsx("space-y-2", className)}>
      <div className="flex justify-between text-xs font-mono text-slate-500">
        <span className="text-red-300/90">Stop ${stopLoss.toFixed(2)}</span>
        <span className="text-slate-400">Now ${currentPrice.toFixed(2)}</span>
        <span className="text-emerald-300/90">Target ${target.toFixed(2)}</span>
      </div>
      <div className="relative h-4 rounded-full overflow-hidden border border-slate-700 bg-slate-900">
        <div className="absolute inset-0 flex">
          <div
            className={clsx("h-full", tightReward ? "bg-gradient-to-r from-red-600 to-orange-500" : "bg-gradient-to-r from-red-600/90 to-amber-500/80")}
            style={{ width: `${riskPct}%` }}
            title="Downside to stop"
          />
          <div
            className={clsx("h-full", tightReward ? "bg-emerald-600/35" : "bg-gradient-to-r from-emerald-600/70 to-emerald-400/80")}
            style={{ width: `${rewardPct}%` }}
            title="Upside to target"
          />
        </div>
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-white shadow-[0_0_8px_rgba(255,255,255,0.8)] z-10"
          style={{ left: `calc(${pct}% - 1px)` }}
          title={`Current price $${currentPrice.toFixed(2)}`}
        />
        <div
          className="absolute top-1/2 z-20 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-slate-900 shadow-md"
          style={{ left: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-400 leading-snug">
        {tightReward ? (
          <>
            <span className="text-red-300 font-semibold">Asymmetric risk:</span> large red zone (fall to stop) vs a small
            green slice (room to target). Favor pullbacks or longer horizons.
          </>
        ) : (
          <>
            Bar spans stop → target. Marker = last price.{" "}
            <span className="text-slate-500">Left = downside to stop · Right = upside to target.</span>
          </>
        )}
      </p>
    </div>
  );
}

/** TradingView-style buy zone on a price scale — emerald band + spot marker (distinct from stop→target bar). */
export function EntryZonePriceBar({
  entryLow,
  entryHigh,
  currentPrice,
  stopLoss,
  target,
  bandLabel = "Buy zone",
  quality,
  anchorNote,
  className,
}: {
  entryLow: number;
  entryHigh: number;
  currentPrice: number;
  stopLoss?: number | null;
  target?: number | null;
  bandLabel?: string;
  quality?: string | null;
  anchorNote?: string | null;
  className?: string;
}) {
  const low = Math.min(entryLow, entryHigh);
  const high = Math.max(entryLow, entryHigh);
  if (!(low > 0 && high > low && currentPrice > 0)) return null;

  const stretch = String(quality || "").toLowerCase().includes("stretch");
  const inside = currentPrice >= low && currentPrice <= high;
  const above = currentPrice > high;
  const below = currentPrice < low;

  const points = [low, high, currentPrice];
  if (stopLoss != null && stopLoss > 0) points.push(stopLoss);
  if (target != null && target > 0) points.push(target);
  const pad = (Math.max(...points) - Math.min(...points)) * 0.04 || low * 0.01;
  const min = Math.min(...points) - pad;
  const max = Math.max(...points) + pad;
  const span = max - min;
  if (!(span > 0)) return null;

  const pct = (v: number) => Math.max(0, Math.min(100, ((v - min) / span) * 100));
  const zoneL = pct(low);
  const zoneW = Math.max(3, pct(high) - zoneL);
  const nowP = pct(currentPrice);
  const stopP = stopLoss != null && stopLoss > 0 ? pct(stopLoss) : null;
  const highP = pct(high);

  let statusLine: React.ReactNode;
  if (inside) {
    statusLine = (
      <>
        <span className="text-emerald-300 font-semibold">Inside buy zone</span>
        <span className="text-slate-500"> — favorable for staged adds per your plan.</span>
      </>
    );
  } else if (above) {
    const gapPct = ((currentPrice - high) / high) * 100;
    statusLine = (
      <>
        <span className="text-amber-300 font-semibold">{gapPct.toFixed(1)}% above band</span>
        <span className="text-slate-500"> — wait for pullback into the green zone before adding.</span>
      </>
    );
  } else {
    const gapPct = ((low - currentPrice) / low) * 100;
    statusLine = (
      <>
        <span className="text-sky-300/90 font-semibold">{gapPct.toFixed(1)}% below band low</span>
        <span className="text-slate-500"> — price hasn&apos;t reached the planned entry floor yet.</span>
      </>
    );
  }

  return (
    <div className={clsx("space-y-2", className)} aria-label={`${bandLabel} price scale`}>
      <div className="flex justify-between gap-2 text-[11px] font-mono text-slate-500">
        <span className="text-slate-500 shrink-0">${min.toFixed(2)}</span>
        <span className="text-slate-200 font-medium shrink-0">Now ${currentPrice.toFixed(2)}</span>
        <span className="text-slate-500 shrink-0">${max.toFixed(2)}</span>
      </div>
      <div className="relative h-5 rounded-full overflow-hidden border border-slate-700 bg-slate-900">
        <div className="absolute inset-0 bg-slate-800/90" />
        <div
          className={clsx(
            "absolute top-0 bottom-0 border-x border-emerald-500/50",
            stretch ? "bg-emerald-500/25" : "bg-emerald-500/40",
          )}
          style={{ left: `${zoneL}%`, width: `${zoneW}%` }}
          title={`Entry band $${low.toFixed(2)}–$${high.toFixed(2)}`}
        />
        {above && (
          <div
            className="absolute top-0 bottom-0 bg-gradient-to-r from-amber-600/30 via-amber-500/15 to-transparent"
            style={{ left: `${highP}%`, width: `${Math.max(0, nowP - highP)}%` }}
            title="Price extended above buy zone"
          />
        )}
        {below && zoneL > 0 && (
          <div
            className="absolute top-0 bottom-0 bg-sky-500/15"
            style={{ left: 0, width: `${zoneL}%` }}
            title="Below entry band"
          />
        )}
        {stopP != null && (
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-red-500/80 z-10"
            style={{ left: `calc(${stopP}% - 1px)` }}
            title={`Stop $${stopLoss!.toFixed(2)}`}
          />
        )}
        <div
          className={clsx(
            "absolute top-1/2 z-20 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 shadow-md",
            inside ? "border-emerald-200 bg-emerald-600" : "border-white bg-slate-950",
          )}
          style={{ left: `${nowP}%` }}
          title={`Last price $${currentPrice.toFixed(2)}`}
        />
      </div>
      <p className="text-xs text-slate-400 leading-snug">{statusLine}</p>
      {stretch && (
        <p className="text-[11px] text-amber-300/85 leading-snug">
          Stretched vs anchor — band still valid; pullback toward band low improves entry quality.
        </p>
      )}
      {anchorNote && (
        <p className="text-[11px] text-slate-500 leading-snug">{anchorNote}</p>
      )}
      {(stopP != null || (target != null && target > 0)) && (
        <p className="text-[10px] text-slate-600 leading-snug">
          {stopP != null && <span className="text-red-400/80">Red tick = stop </span>}
          {target != null && target > 0 && (
            <span className="text-slate-500">
              {stopP != null ? "· " : ""}
              Target ${target.toFixed(2)} on scale for context
            </span>
          )}
        </p>
      )}
    </div>
  );
}

/** Long-term ladder: nearest target tier (emerald) + other tiers (faint) + full-position MOS ceiling (cyan). */
type ScaleMarker = {
  value: number;
  label: string;
  tone: "emerald" | "slate" | "cyan" | "red" | "violet" | "white";
  priority: number;
};

export function LongTermAccumulationScale({
  horizon,
  entryTiers,
  currentPrice,
  stopLoss,
  target,
  className,
  variant = "full",
}: {
  horizon: Pick<HorizonSignalPayload, "entry_zone">;
  entryTiers: NonNullable<HorizonSignalPayload["entry_tiers"]>;
  currentPrice: number;
  stopLoss?: number | null;
  target?: number | null;
  className?: string;
  /** deck = Today hero (bar labels only); full = horizon card + extra copy */
  variant?: "full" | "deck";
}) {
  const tiers = [...(entryTiers.tiers ?? [])].sort((a, b) => a.low - b.low);
  if (!tiers.length || !(currentPrice > 0)) return null;

  const resolved = resolveLongHorizonEntryZone(horizon, entryTiers, currentPrice);
  const mos = entryTiers.current_assessment?.min_price_to_buy;
  const primaryId = resolved.tierId;

  const points: number[] = [currentPrice, resolved.low, resolved.high];
  for (const t of tiers) {
    points.push(Math.min(t.low, t.high), Math.max(t.low, t.high));
  }
  if (mos != null && mos > 0) {
    const mosPad = mos * 0.008;
    points.push(mos - mosPad, mos + mosPad);
  }
  if (stopLoss != null && stopLoss > 0) points.push(stopLoss);
  if (target != null && target > 0) points.push(target);

  const rawSpan = Math.max(...points) - Math.min(...points);
  const pad = rawSpan * 0.06 || Math.max(...points) * 0.02;
  const scaleMin = Math.min(...points) - pad;
  const scaleMax = Math.max(...points) + pad;
  const span = scaleMax - scaleMin;
  if (!(span > 0)) return null;

  const pct = (v: number) => Math.max(0, Math.min(100, ((v - scaleMin) / span) * 100));
  const nowP = pct(currentPrice);
  const primaryLo = Math.min(resolved.low, resolved.high);
  const primaryHi = Math.max(resolved.low, resolved.high);
  const insidePrimary = currentPrice >= primaryLo && currentPrice <= primaryHi;
  const abovePrimary = currentPrice > primaryHi;
  const mosP = mos != null && mos > 0 ? pct(mos) : null;
  const aboveMos = mos != null && mos > 0 && currentPrice > mos;

  const tierLabel = resolved.tierLabel || primaryId || "tier";
  const primaryBandLabel = primaryId
    ? `Target band (${primaryId})`
    : "Target accumulation band";

  let statusHeadline: string;
  let statusDetail: string;
  if (insidePrimary) {
    statusHeadline = `Inside ${tierLabel}`;
    statusDetail = "Staged long-term adds per your tier plan.";
  } else if (abovePrimary) {
    const gapPct = ((currentPrice - primaryHi) / primaryHi) * 100;
    statusHeadline = `${gapPct.toFixed(1)}% above ${tierLabel}`;
    statusDetail = "Wait for pullback into the highlighted band.";
  } else {
    const gapPct = ((primaryLo - currentPrice) / primaryLo) * 100;
    statusHeadline = `${gapPct.toFixed(1)}% below ${tierLabel} low`;
    statusDetail = "Spot has not reached that accumulation sleeve yet.";
  }

  const markerToneClass: Record<ScaleMarker["tone"], string> = {
    emerald: "text-emerald-200",
    slate: "text-slate-300",
    cyan: "text-cyan-200",
    red: "text-red-300",
    violet: "text-violet-200",
    white: "text-white",
  };

  const barMarkers: ScaleMarker[] = [];
  for (const t of tiers) {
    const lo = Math.min(t.low, t.high);
    const hi = Math.max(lo, t.high);
    const isPrimary = t.id === primaryId;
    barMarkers.push({
      value: lo,
      label: `${t.id} ${lo.toFixed(0)}`,
      tone: isPrimary ? "emerald" : "slate",
      priority: isPrimary ? 2 : 1,
    });
    if (hi - lo > scaleMax * 0.02) {
      barMarkers.push({
        value: hi,
        label: `${hi.toFixed(0)}`,
        tone: isPrimary ? "emerald" : "slate",
        priority: isPrimary ? 2 : 0,
      });
    }
  }
  if (mos != null && mos > 0) {
    barMarkers.push({ value: mos, label: `MOS ${mos.toFixed(0)}`, tone: "cyan", priority: 5 });
  }
  if (stopLoss != null && stopLoss > 0) {
    barMarkers.push({ value: stopLoss, label: `Stop ${stopLoss.toFixed(0)}`, tone: "red", priority: 4 });
  }
  if (target != null && target > 0) {
    barMarkers.push({ value: target, label: `Tgt ${target.toFixed(0)}`, tone: "violet", priority: 3 });
  }

  const placedMarkers = barMarkers
    .sort((a, b) => b.priority - a.priority || a.value - b.value)
    .filter((m, i, arr) => {
      const p = pct(m.value);
      return !arr.slice(0, i).some((o) => Math.abs(pct(o.value) - p) < 7);
    });

  return (
    <div className={clsx("space-y-2.5", className)} aria-label="Long-term accumulation price scale">
      <div className="flex justify-between gap-2 text-xs font-mono text-slate-300">
        <span className="shrink-0 tabular-nums">${scaleMin.toFixed(2)}</span>
        <span className="text-white font-semibold shrink-0 tabular-nums">Now ${currentPrice.toFixed(2)}</span>
        <span className="shrink-0 tabular-nums">${scaleMax.toFixed(2)}</span>
      </div>
      <div className="relative">
        <div className="relative h-8 rounded-lg overflow-hidden border border-slate-600 bg-slate-900">
          <div className="absolute inset-0 bg-slate-800/90" />
          {tiers.map((t) => {
            const lo = Math.min(t.low, t.high);
            const hi = Math.max(lo, t.high);
            const isPrimary = t.id === primaryId;
            const left = pct(lo);
            const width = Math.max(3, pct(hi) - left);
            return (
              <div
                key={t.id}
                className={clsx(
                  "absolute top-0 bottom-0 border-x flex items-center justify-center overflow-hidden",
                  isPrimary
                    ? "border-emerald-400/70 bg-emerald-500/40 z-[2]"
                    : "border-slate-500/50 bg-slate-600/25 z-[1]",
                )}
                style={{ left: `${left}%`, width: `${width}%` }}
                title={`${t.label || t.id}: $${lo.toFixed(2)}–$${hi.toFixed(2)}`}
              >
                {width >= 10 && (
                  <span
                    className={clsx(
                      "text-[9px] font-mono font-semibold truncate px-0.5",
                      isPrimary ? "text-emerald-100" : "text-slate-400",
                    )}
                  >
                    {t.id} ${lo.toFixed(0)}–{hi.toFixed(0)}
                  </span>
                )}
              </div>
            );
          })}
          {mosP != null && (
            <div
              className="absolute top-0 bottom-0 w-1.5 bg-cyan-400 z-[3] shadow-[0_0_8px_rgba(34,211,238,0.65)]"
              style={{ left: `calc(${mosP}% - 3px)` }}
              title={`Full-position MOS ceiling $${mos!.toFixed(2)}`}
            />
          )}
          {stopLoss != null && stopLoss > 0 && (
            <div
              className="absolute top-0 bottom-0 w-1 bg-red-500 z-[4]"
              style={{ left: `calc(${pct(stopLoss)}% - 1px)` }}
              title={`Stop $${stopLoss.toFixed(2)}`}
            />
          )}
          <div
            className={clsx(
              "absolute top-1/2 z-20 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 shadow-md",
              insidePrimary ? "border-emerald-100 bg-emerald-500" : "border-white bg-slate-950",
            )}
            style={{ left: `${nowP}%` }}
            title={`Last price $${currentPrice.toFixed(2)}`}
          />
        </div>
        <div className="relative h-9 mt-1">
          {placedMarkers.map((m) => (
            <span
              key={`${m.label}-${m.value}`}
              className={clsx(
                "absolute top-0 -translate-x-1/2 text-[10px] font-mono font-semibold tabular-nums whitespace-nowrap",
                markerToneClass[m.tone],
              )}
              style={{ left: `${pct(m.value)}%` }}
            >
              {m.label}
            </span>
          ))}
        </div>
      </div>
      <div className="text-sm leading-snug">
        <p className="font-semibold text-amber-100">{statusHeadline}</p>
        <p className="text-slate-200 mt-0.5">{statusDetail}</p>
      </div>
      {variant === "full" && (
        <p className="text-xs text-slate-200 leading-snug">
          <span className="text-emerald-300 font-semibold">{primaryBandLabel}</span>
          {" "}
          <span className="font-mono tabular-nums">
            ${primaryLo.toFixed(2)}–${primaryHi.toFixed(2)}
          </span>
          {mos != null && mos > 0 && (
            <>
              {" · "}
              <span className="text-cyan-300 font-semibold">Full MOS</span>{" "}
              <span className="font-mono tabular-nums">${mos.toFixed(2)}</span>
              {aboveMos && (
                <span className="text-amber-100"> — above full-position ceiling (partial size only).</span>
              )}
            </>
          )}
        </p>
      )}
    </div>
  );
}

function stopRiskPct(
  stop: number,
  currentPrice: number,
  fallbackPct?: number | null
): number | null {
  if (fallbackPct != null && Number.isFinite(fallbackPct)) return Math.abs(fallbackPct);
  if (currentPrice <= 0 || stop <= 0) return null;
  return Math.abs(((currentPrice - stop) / currentPrice) * 100);
}

/** Three-stop ladder: swing (days) → build (months) → thesis (years). */
export function StopHierarchyPanel({
  short,
  medium,
  long,
  currentPrice,
  stockRegimeBullPct,
  marketRegimeBullPct,
  className,
}: {
  short: HorizonSignalPayload;
  medium: HorizonSignalPayload;
  long: HorizonSignalPayload;
  currentPrice: number;
  stockRegimeBullPct?: number | null;
  marketRegimeBullPct?: number | null;
  className?: string;
}) {
  const thesisStop =
    long.entry_tiers?.structural_invalidation?.price ??
    (long.stop_loss_kind === "structural_invalidation" && long.stop_loss > 0 ? long.stop_loss : null);

  const rows: { label: string; context: string; detail?: string | null; price: number; tone: string }[] = [];
  if (short.stop_loss != null && short.stop_loss > 0) {
    const pct = stopRiskPct(short.stop_loss, currentPrice, short.stop_loss_pct);
    rows.push({
      label: "Swing stop",
      context: pct != null ? `${pct.toFixed(0)}% risk · days–weeks` : "days–weeks",
      detail: short.stop_loss_framing,
      price: short.stop_loss,
      tone: "text-amber-200/95",
    });
  }
  if (medium.stop_loss != null && medium.stop_loss > 0) {
    rows.push({
      label: "Build stop",
      context: "pause tranches · 1–3 mo",
      detail: medium.stop_loss_framing,
      price: medium.stop_loss,
      tone: "text-orange-200/90",
    });
  }
  if (thesisStop != null && thesisStop > 0) {
    rows.push({
      label: "Thesis stop",
      context: "exit thesis · years",
      detail: long.stop_loss_framing || long.entry_tiers?.structural_invalidation?.note,
      price: thesisStop,
      tone: "text-red-300/90",
    });
  }

  if (rows.length === 0) return null;

  const hmmDiverge =
    stockRegimeBullPct != null &&
    marketRegimeBullPct != null &&
    marketRegimeBullPct >= 60 &&
    stockRegimeBullPct < 42;

  return (
    <section
      className={clsx(
        "rounded-xl border border-slate-700/80 bg-slate-950/50 px-3.5 py-3",
        className
      )}
      aria-label="Stop hierarchy by timeframe"
    >
      <p className="text-xs uppercase tracking-wide font-semibold text-slate-400 mb-2">
        Stop hierarchy — match the stop to your horizon
      </p>
      <ul className="space-y-2.5">
        {rows.map((row) => (
          <li key={row.label}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <div className="min-w-0">
                <span className="font-medium text-slate-200">{row.label}</span>
                <span className="text-slate-500"> · {row.context}</span>
              </div>
              <span className={clsx("font-mono tabular-nums shrink-0", row.tone)}>
                ${row.price.toFixed(2)}
              </span>
            </div>
            {row.detail && (
              <p className="text-xs text-slate-500 mt-0.5 leading-snug pl-0.5">{row.detail}</p>
            )}
          </li>
        ))}
      </ul>
      {hmmDiverge && (
        <p className="text-xs text-sky-300/85 mt-3 pt-2 border-t border-slate-700/70 leading-snug">
          HMM: market ~{Math.round(marketRegimeBullPct!)}% bull vs this name ~{Math.round(stockRegimeBullPct!)}% — can mean the stock is lagging a strong tape (not necessarily a model bug). Use stock HMM for this ticker; market HMM for backdrop only.
        </p>
      )}
    </section>
  );
}

/** Simple R:R ratio bar (fallback when only ratio known). */
export function RiskRewardThermometer({
  riskReward,
  className,
}: {
  riskReward: number;
  className?: string;
}) {
  const rr = Math.max(0.01, riskReward);
  const rewardShare = rr / (1 + rr);
  const riskShare = 1 - rewardShare;
  const tight = rr < 0.6;

  return (
    <div className={clsx("space-y-1.5", className)}>
      <div className="flex justify-between text-xs font-mono text-slate-500">
        <span className="text-red-300/90">Risk $1.00</span>
        <span className="text-emerald-300/90">Reward ${rr.toFixed(2)}</span>
      </div>
      <div className="flex h-3 rounded-full overflow-hidden border border-slate-700/80 bg-slate-900">
        <div className={clsx("h-full", tight ? "bg-red-500/85" : "bg-amber-500/75")} style={{ width: `${riskShare * 100}%` }} />
        <div className={clsx("h-full flex-1", tight ? "bg-emerald-600/30" : "bg-emerald-500/65")} />
      </div>
      <p className="text-xs text-slate-400">
        {tight ? (
          <span className="text-red-300 font-medium">You risk ~$1.00 to make ~${rr.toFixed(2)}</span>
        ) : (
          <span>R:R 1 : {rr.toFixed(1)}</span>
        )}
      </p>
    </div>
  );
}

// ─── 4. Long-term tier ladder (fader) ──────────────────────────────────────────

const TIER_RETAIL_COPY: Record<string, { zone: string; sizing: string; mode: string }> = {
  T1: {
    zone: "Nibble Zone",
    sizing: "Start with a small ~5% tester position.",
    mode: "Starter tranche",
  },
  T2: {
    zone: "Core Accumulation Zone",
    sizing: "Partial position only — scale to Tier 2 allocation on dips, not full MOS.",
    mode: "Partial position only",
  },
  T3: {
    zone: "Max Margin of Safety",
    sizing: "Back-the-truck-up level — only on deep dislocations.",
    mode: "Stress / tail sleeve",
  },
};

export function tierPriceState(
  tier: { low: number; high: number },
  price: number
): "active" | "above" | "below" {
  if (price >= tier.low && price <= tier.high) return "active";
  if (price > tier.high) return "above";
  return "below";
}

/** Distance from spot to a tier band (0 if inside the band). */
export function distanceToTierBand(
  tier: { low: number; high: number },
  price: number
): number {
  const lo = Math.min(tier.low, tier.high);
  const hi = Math.max(tier.low, tier.high);
  if (price >= lo && price <= hi) return 0;
  if (price < lo) return lo - price;
  return price - hi;
}

/** Nearest accumulation tier for display when spot is between bands or far from T3 stress sleeve. */
export function pickCurrentTargetTierId(
  tiers: { id: string; low: number; high: number }[],
  price: number
): string | null {
  if (!tiers.length || !(price > 0)) return null;
  const active = tiers.find((t) => price >= t.low && price <= t.high);
  if (active) return active.id;
  let best = tiers[0];
  let bestDist = Infinity;
  for (const t of tiers) {
    const d = distanceToTierBand(t, price);
    if (d < bestDist) {
      bestDist = d;
      best = t;
    }
  }
  return best.id;
}

/** Long-term horizon card entry band — matches tier ladder + backend entry_zone. */
export function resolveLongHorizonEntryZone(
  horizon: Pick<HorizonSignalPayload, "entry_zone">,
  entryTiers: NonNullable<HorizonSignalPayload["entry_tiers"]> | undefined,
  currentPrice: number
): { low: number; high: number; tierId: string | null; tierLabel: string | null; inside: boolean } {
  const fallback = horizon.entry_zone;
  const tiers = entryTiers?.tiers ?? [];
  if (!tiers.length || !(currentPrice > 0)) {
    return {
      low: fallback.low,
      high: fallback.high,
      tierId: null,
      tierLabel: null,
      inside: currentPrice >= fallback.low && currentPrice <= fallback.high,
    };
  }
  const insideTier = tiers.find((t) => currentPrice >= t.low && currentPrice <= t.high);
  const tierId =
    entryTiers?.active_tier_id ??
    insideTier?.id ??
    pickCurrentTargetTierId(tiers, currentPrice);
  const tier = tiers.find((t) => t.id === tierId) ?? insideTier;
  if (tier) {
    return {
      low: tier.low,
      high: tier.high,
      tierId: tier.id,
      tierLabel: tier.label,
      inside: currentPrice >= tier.low && currentPrice <= tier.high,
    };
  }
  return {
    low: fallback.low,
    high: fallback.high,
    tierId: null,
    tierLabel: null,
    inside: currentPrice >= fallback.low && currentPrice <= fallback.high,
  };
}

export function LongTermTierLadder({
  entryTiers,
  currentPrice,
  modeLabel,
}: {
  entryTiers: NonNullable<HorizonSignalPayload["entry_tiers"]>;
  currentPrice: number;
  modeLabel?: string;
}) {
  const targetTierId = pickCurrentTargetTierId(entryTiers.tiers, currentPrice);
  const sorted = [...entryTiers.tiers].sort((a, b) => b.low - a.low);

  return (
    <div className="mt-2 rounded-xl border border-violet-500/25 bg-gradient-to-b from-violet-950/30 to-slate-950/50 overflow-hidden">
      <div className="px-3 py-2 border-b border-violet-500/20 bg-violet-950/40 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-[0.12em] text-violet-200">
          Long-term accumulation mode
        </p>
        <span className="text-xs font-semibold text-amber-200/90 uppercase">
          {modeLabel ?? entryTiers.current_assessment?.label ?? "Watching"}
        </span>
      </div>
      <ul className="p-2 space-y-1.5">
        {sorted.map((tier) => {
          const state = currentPrice > 0 ? tierPriceState(tier, currentPrice) : "above";
          const isInside = state === "active";
          const isAbove = state === "above";
          const isTarget = tier.id === targetTierId;
          const isHighlighted = isInside || (isTarget && isAbove);
          const copy = TIER_RETAIL_COPY[tier.id] ?? {
            zone: tier.label,
            sizing: tier.description,
            mode: "",
          };
          const irrelevant = isAbove && !isTarget;

          return (
            <li
              key={tier.id}
              className={clsx(
                "rounded-lg border px-3 py-2.5 transition-all",
                isHighlighted
                  ? "border-emerald-500/50 bg-emerald-500/10 ring-1 ring-emerald-500/30 opacity-100"
                  : irrelevant
                    ? "border-slate-800/80 bg-slate-900/20 opacity-35"
                    : "border-slate-700/60 bg-slate-900/40 opacity-70"
              )}
            >
              <div className="flex items-start gap-2">
                <span className="shrink-0 mt-0.5 text-base" aria-hidden>
                  {isHighlighted ? (
                    <Target className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <Lock className="h-4 w-4 text-slate-500" />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-bold text-slate-200">{tier.label}</span>
                    <span className="text-xs font-semibold text-emerald-300/90">{copy.zone}</span>
                    {isHighlighted && (
                      <span className="text-[9px] uppercase font-black text-emerald-300 bg-emerald-500/20 px-1.5 py-0.5 rounded border border-emerald-500/40">
                        {isInside
                          ? tier.id === "T2" || tier.id === "tier2"
                            ? "Partial position only"
                            : "Active accumulation"
                          : "Target tier"}
                      </span>
                    )}
                  </div>
                  <p className="text-sm font-mono text-slate-100 mt-0.5">
                    ${tier.low.toFixed(2)} – ${tier.high.toFixed(2)}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">{copy.sizing}</p>
                  <p className="text-xs mt-1 text-slate-400">
                    {isInside ? (
                      <span className="text-emerald-300/95">
                        {tier.id === "T2" || tier.id === "tier2"
                          ? `Current price ($${currentPrice.toFixed(2)}) is inside Tier 2 — partial position only; full MOS is lower (see max buy price).`
                          : `Current price ($${currentPrice.toFixed(2)}) is inside this band — scale here first.`}
                      </span>
                    ) : isTarget && isAbove ? (
                      <span className="text-emerald-300/90">
                        Current price (${currentPrice.toFixed(2)}) is gravitating toward this structural floor.
                      </span>
                    ) : isAbove && tier.drop_needed_pct != null ? (
                      <span className="text-slate-500">
                        🔒 Price is above zone — needs ~{Math.abs(tier.drop_needed_pct).toFixed(0)}% pullback
                      </span>
                    ) : state === "below" ? (
                      <span className="text-slate-500">🔒 Price is below zone (not actionable yet)</span>
                    ) : null}
                  </p>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function EntryTierPanel(props: Parameters<typeof LongTermTierLadder>[0]) {
  return <LongTermTierLadder {...props} />;
}

// ─── Plain English (collapsible detail) ──────────────────────────────────────

export function buildPlainEnglishTake(summary: InvestorDecisionSummary, currentPrice: number) {
  const ra = summary.retail_action;
  if (ra?.dynamic_subtitle) {
    const pct =
      ra.assessment_pct ??
      (currentPrice > 0 && summary.fair_value > 0
        ? ((summary.fair_value - currentPrice) / currentPrice) * 100
        : 0);
    const good =
      pct >= 5
        ? `The stock looks cheaper than our model fair value (~${Math.abs(pct).toFixed(0)}% discount).`
        : `Fundamentals anchor near $${summary.fair_value.toFixed(2)} — less margin of safety at today's price.`;
    const bad =
      ra.regime_weather_status === "stormy"
        ? "The broader market tape is stormy (non-bull HMM regime)."
        : ra.rsi_status === "hot"
          ? "Short-term momentum is extended — today's move may be hard to chase."
          : "Some timing gates have not cleared yet.";
    return {
      good,
      bad,
      move: ra.dynamic_subtitle,
    };
  }

  const fv = summary.fair_value;
  const pct = currentPrice > 0 ? ((fv - currentPrice) / currentPrice) * 100 : 0;
  const oa = summary.one_answer;
  const short = summary.horizons.short;

  const good =
    pct >= 3
      ? `The stock looks cheaper than our model fair value (~${Math.abs(pct).toFixed(0)}% discount).`
      : `Fundamentals anchor near $${fv.toFixed(2)} — less margin of safety at today's price.`;

  const badParts: string[] = [];
  if (summary.regime_bull_pct != null && summary.regime_bull_pct < 48) badParts.push("stormy market weather");
  if (String(short.entry_zone?.quality || "").toLowerCase().includes("stretch")) badParts.push("price is extended");
  if (summary.pattern_score != null && summary.pattern_score < 45) badParts.push("weak chart structure");

  const move =
    oa?.bottom_line ||
    oa?.action_today ||
    (summary.overall_verdict === "WAIT" || summary.overall_verdict === "WATCH"
      ? "DO NOT CHASE — wait for gates to turn green."
      : "Stage in via tier ladder — nibble, then core.");

  return {
    good,
    bad: badParts.length ? `Caution: ${badParts.join(", ")}.` : "No major red flags in the quick scan.",
    move,
  };
}

export function PlainEnglishTakeCard({
  summary,
  currentPrice,
  defaultOpen = false,
  prominent = false,
}: {
  summary: InvestorDecisionSummary;
  currentPrice: number;
  defaultOpen?: boolean;
  /** Always-visible Quick Take block (top of One Answer). */
  prominent?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen || prominent);
  const take = useMemo(() => buildPlainEnglishTake(summary, currentPrice), [summary, currentPrice]);

  if (prominent) {
    return (
      <section className="rounded-xl border border-amber-500/30 bg-gradient-to-br from-amber-950/40 via-slate-950/80 to-slate-900/60 overflow-hidden">
        <div className="px-4 py-3 border-b border-amber-500/20">
          <p className="flex items-center gap-2 text-sm font-semibold text-amber-100">
            <Lightbulb className="h-4 w-4 text-amber-300" />
            The Quick Take
          </p>
          <p className="text-xs text-slate-500 mt-0.5">Plain English — no jargon</p>
        </div>
        <ul className="px-4 py-3 space-y-2.5 text-sm text-slate-200 leading-relaxed">
          <li>
            <span className="text-emerald-300 font-semibold">The Good: </span>
            {take.good}
          </li>
          <li>
            <span className="text-amber-300 font-semibold">The Bad: </span>
            {take.bad}
          </li>
          <li>
            <span className="text-sky-300 font-semibold">The Move: </span>
            {take.move}
          </li>
        </ul>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-slate-700/80 bg-slate-900/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 px-3.5 py-2.5 text-left hover:bg-slate-800/50"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-400 uppercase tracking-wide">
          <Lightbulb className="h-3.5 w-3.5" />
          More detail (plain English)
        </span>
        {open ? <ChevronDown className="h-4 w-4 text-slate-500" /> : <ChevronRight className="h-4 w-4 text-slate-500" />}
      </button>
      {open && (
        <ul className="px-3.5 pb-3.5 space-y-2 text-[12px] text-slate-200 leading-snug border-t border-slate-700/50">
          <li>
            <span className="text-emerald-300 font-semibold">Good: </span>
            {take.good}
          </li>
          <li>
            <span className="text-amber-300 font-semibold">Bad: </span>
            {take.bad}
          </li>
          <li>
            <span className="text-sky-300 font-semibold">Move: </span>
            {take.move}
          </li>
        </ul>
      )}
    </section>
  );
}

/** One-line explainer when short/medium/long verdicts disagree at the same price. */
export function HorizonDivergenceNote({
  short,
  long,
}: {
  short: HorizonSignalPayload;
  long: HorizonSignalPayload;
}) {
  const st = String(short.verdict || "").toUpperCase();
  const lt = String(long.verdict || "").toUpperCase();
  const stBlock = st === "WAIT" || st === "REDUCE";
  const ltAdd = lt === "BUY" || lt === "STRONG BUY" || lt === "WATCH";
  if (!stBlock || !ltAdd) return null;
  return (
    <p className="text-sm text-cyan-100 leading-snug border border-cyan-500/35 bg-cyan-950/40 rounded-lg px-3 py-2.5">
      <span className="font-semibold text-cyan-50">Different horizons, different rules: </span>
      Near-term gates block adds (swing), while long-term tiers can still show value — that is not a bug. Match the row to your holding period.
    </p>
  );
}
