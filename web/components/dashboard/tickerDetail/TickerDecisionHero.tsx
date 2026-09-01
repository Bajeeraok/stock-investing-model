"use client";

/**
 * One decision band: verdict, plain-English reason, price levels, and gate status —
 * everything needed to call buy/watch/sell without scrolling. Persona swaps the data
 * (band, framing, MOS ladder), never the shape. Replaces TickerCommandCard,
 * SignalReasonCard, SignalBreakdownGrid, the contextOnly GlobalActionHeader block, and
 * StreetVsExecutionCard, which each rendered their own version of the same verdict.
 */

import { clsx } from "clsx";
import { ChevronRight } from "lucide-react";
import type { DecisionMode } from "@/lib/decisionMode";
import { horizonLabel, primaryHorizonFromMode } from "@/lib/decisionMode";
import type { InvestorDecisionSummary, HorizonSignalPayload } from "../InvestorDecisionSummary";
import type { TradingGateRow } from "../retailActionUX";
import type { SignalReasonPayload } from "./SignalReasonCard";

/** Matches RetailActionLight / RetailActionStatus in TickerDetailModal.tsx — kept local
 * (not imported) to avoid a circular import between the modal and this component. */
type RetailActionLight = "red" | "yellow" | "green" | "neutral";
type RetailActionStatus = { light: RetailActionLight; title: string; subtitle: string };

const LIGHT_BADGE: Record<RetailActionLight, string> = {
  green: "border-emerald-500/50 bg-emerald-500/10 text-emerald-400",
  yellow: "border-amber-500/50 bg-amber-500/10 text-amber-400",
  red: "border-red-500/50 bg-red-500/10 text-red-400",
  neutral: "border-slate-500/50 bg-slate-500/10 text-slate-300",
};
const LIGHT_DOT: Record<RetailActionLight, string> = {
  green: "bg-emerald-400",
  yellow: "bg-amber-400",
  red: "bg-red-400",
  neutral: "bg-slate-400",
};
const STANCE_CHIP: Record<"helps" | "hurts" | "neutral", string> = {
  helps: "text-emerald-400 border-emerald-500/35 bg-emerald-500/10",
  hurts: "text-amber-300 border-amber-500/35 bg-amber-500/10",
  neutral: "text-slate-400 border-slate-600/50 bg-slate-800/40",
};
const MODE_ACCENT: Record<DecisionMode, string> = {
  scout: "border-cyan-500/25",
  swing: "border-violet-500/25",
  owner: "border-emerald-500/25",
};

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${n.toFixed(digits)}`;
}

function pctFromSpot(level: number | null | undefined, spot: number | null | undefined): string {
  if (level == null || spot == null || !(spot > 0)) return "";
  const pct = ((level - spot) / spot) * 100;
  return `${pct >= 0 ? "+" : "−"}${Math.abs(pct).toFixed(1)}%`;
}

/** Levels row: long/owner uses the tier ladder when present, everyone else uses entry_zone/target/stop. */
function srSideTag(
  side: "Support" | "Resist",
  level: { label: string } | null | undefined,
): "Support" | "Resist" | "Pivot" {
  const lbl = (level?.label || "").toLowerCase();
  if (lbl.includes("pivot") || lbl.includes("20d")) return "Pivot";
  return side;
}

function SrRow({
  tag,
  level,
}: {
  tag: "Support" | "Resist";
  level: { price: number; label: string; dist_pct: number } | null | undefined;
}) {
  if (!level || !(level.price > 0)) return null;
  const below = level.dist_pct < 0;
  const shown = srSideTag(tag, level);
  return (
    <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-800/40 border border-slate-800">
      <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-slate-500">{shown}</span>
      <span className="text-[13px] font-mono font-semibold text-slate-200 tabular-nums">
        {fmt(level.price)}
        <span className="ml-1.5 text-[10px] font-sans font-medium text-slate-500 normal-case">{level.label}</span>
      </span>
      <span className={clsx("text-[10px] font-mono tabular-nums", below ? "text-red-400/80" : "text-emerald-400/80")}>
        {level.dist_pct >= 0 ? "+" : "−"}
        {Math.abs(level.dist_pct).toFixed(1)}%
      </span>
    </div>
  );
}

function NearbySrRows({ horizon }: { horizon: HorizonSignalPayload }) {
  const sr = horizon.nearby_sr;
  if (!sr?.next_support && !sr?.next_resistance) return null;
  return (
    <>
      <SrRow tag="Support" level={sr.next_support} />
      <SrRow tag="Resist" level={sr.next_resistance} />
    </>
  );
}

function StopTargetRows({
  horizon,
  currentPrice,
}: {
  horizon: HorizonSignalPayload;
  currentPrice: number | null | undefined;
}) {
  return (
    <>
      <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-800/70 border border-slate-700/70">
        <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-slate-500">Stop</span>
        <span className="text-[13px] font-mono font-semibold text-white tabular-nums">{fmt(horizon.stop_loss)}</span>
        <span className="text-[10px] font-mono text-red-400/80 tabular-nums">
          {pctFromSpot(horizon.stop_loss, currentPrice)}
        </span>
      </div>
      <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-800/70 border border-slate-700/70">
        <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-slate-500">Target</span>
        <span className="text-[13px] font-mono font-semibold text-white tabular-nums">{fmt(horizon.target)}</span>
        <span className="text-[10px] font-mono text-emerald-400/80 tabular-nums">
          {pctFromSpot(horizon.target, currentPrice)}
          {horizon.risk_reward ? ` · R:R ${horizon.risk_reward.toFixed(1)}` : ""}
        </span>
      </div>
    </>
  );
}

function LevelRows({
  mode,
  horizon,
  currentPrice,
}: {
  mode: DecisionMode;
  horizon: HorizonSignalPayload;
  currentPrice: number | null | undefined;
}) {
  const tiers = mode === "owner" ? horizon.entry_tiers?.tiers : undefined;
  if (tiers && tiers.length > 0) {
    return (
      <div className="flex flex-col gap-1.5">
        {tiers.slice(0, 3).map((t) => (
          <div
            key={t.id}
            className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-800/70 border border-slate-700/70"
          >
            <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-slate-500">{t.id}</span>
            <span className="text-[13px] font-mono font-semibold text-white tabular-nums">
              &le; {fmt(t.high)}
            </span>
            <span className="text-[10px] font-mono text-slate-500 tabular-nums">
              {pctFromSpot(t.high, currentPrice)}
            </span>
          </div>
        ))}
        <NearbySrRows horizon={horizon} />
      </div>
    );
  }
  const ez = horizon.entry_zone;
  const ezWidthPct =
    ez?.low != null && ez?.high != null && currentPrice ? ((ez.high - ez.low) / currentPrice) * 100 : 0;
  // Wide bands (e.g. medium-term "bridge to MA50" during a real pullback) read as imprecise
  // when flattened into one range — show the staged scale-in rungs instead (data already
  // computed server-side via build_entry_band_levels, just unused in this compact card until now).
  const stagedLevels =
    ezWidthPct >= 8 ? (ez?.levels ?? []).filter((l) => l.role !== "anchor") : [];
  if (stagedLevels.length > 0) {
    const picked = [
      stagedLevels[0],
      stagedLevels[Math.floor((stagedLevels.length - 1) / 2)],
      stagedLevels[stagedLevels.length - 1],
    ].filter((l, i, arr) => arr.findIndex((x) => x.id === l.id) === i);
    const RUNG_TAG = ["1st add", "Scale", "Last add"];
    return (
      <div className="flex flex-col gap-1.5">
        <p className="text-[10px] text-slate-500 leading-snug -mt-0.5 mb-0.5">
          Wide zone — scale in across these levels, not one price
        </p>
        {picked.map((lvl, i) => (
          <div
            key={lvl.id}
            className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-800/70 border border-slate-700/70"
          >
            <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-slate-500 truncate">
              {RUNG_TAG[i] ?? lvl.label}
            </span>
            <span className="text-[13px] font-mono font-semibold text-white tabular-nums">{fmt(lvl.price)}</span>
            <span className="text-[10px] font-mono text-slate-500 tabular-nums">
              {pctFromSpot(lvl.price, currentPrice)}
            </span>
          </div>
        ))}
        <StopTargetRows horizon={horizon} currentPrice={currentPrice} />
        <NearbySrRows horizon={horizon} />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-800/70 border border-slate-700/70">
        <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-slate-500">Entry</span>
        <span className="text-[13px] font-mono font-semibold text-white tabular-nums">
          {ez?.low != null && ez?.high != null ? `${fmt(ez.low)} – ${fmt(ez.high)}` : "—"}
        </span>
        <span className="text-[10px] font-mono text-slate-500 tabular-nums">
          {pctFromSpot(ez?.low, currentPrice)}
        </span>
      </div>
      <StopTargetRows horizon={horizon} currentPrice={currentPrice} />
      <NearbySrRows horizon={horizon} />
    </div>
  );
}

export function TickerDecisionHero({
  ticker,
  companyName,
  sector,
  currentPrice,
  dailyMovePct,
  summary,
  mode,
  actionStatus,
  gates,
  gatesPassed,
  gatesTotal,
  onOpenWhy,
}: {
  ticker: string;
  companyName?: string | null;
  sector?: string | null;
  currentPrice: number | null | undefined;
  dailyMovePct?: number | null;
  summary: InvestorDecisionSummary;
  mode: DecisionMode;
  actionStatus: RetailActionStatus;
  gates: TradingGateRow[];
  gatesPassed: number;
  gatesTotal: number;
  onOpenWhy?: () => void;
}) {
  const reason: SignalReasonPayload | null | undefined =
    summary.signal_reason_by_persona?.[mode] ?? summary.signal_reason;
  const horizonKey = primaryHorizonFromMode(mode);
  const horizon = summary.horizons[horizonKey];
  const factors = (reason?.factors ?? []).slice(0, 4);

  return (
    <div className={clsx("rounded-2xl border-2 bg-slate-900 overflow-hidden", MODE_ACCENT[mode])}>
      {/* Ticker · verdict · price */}
      <div className="flex items-center justify-between gap-3 px-4 sm:px-5 py-3.5 border-b border-slate-800">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-lg font-bold text-white tracking-tight">{ticker}</span>
            <span className="text-xs text-slate-500 truncate">
              {companyName ?? ""}
              {sector ? ` · ${sector}` : ""}
            </span>
          </div>
        </div>
        <span
          className={clsx(
            "inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-[12px] font-mono font-bold uppercase whitespace-nowrap",
            LIGHT_BADGE[actionStatus.light],
          )}
        >
          <span className={clsx("w-1.5 h-1.5 rounded-full", LIGHT_DOT[actionStatus.light])} />
          {actionStatus.title}
        </span>
        <div className="text-right shrink-0">
          <p className="text-lg font-mono font-bold text-white tabular-nums">{fmt(currentPrice)}</p>
          {dailyMovePct != null && (
            <p
              className={clsx(
                "text-[11px] font-mono tabular-nums",
                dailyMovePct >= 0 ? "text-emerald-400" : "text-red-400",
              )}
            >
              {dailyMovePct >= 0 ? "+" : "−"}
              {Math.abs(dailyMovePct).toFixed(1)}% today
            </p>
          )}
        </div>
      </div>

      {/* Reason + levels */}
      <div className="grid sm:grid-cols-[1.2fr_1fr] gap-4 px-4 sm:px-5 py-4">
        <div className="min-w-0">
          {reason?.headline && (
            <p className="text-[15px] text-slate-100 leading-snug text-balance">{reason.headline}</p>
          )}
          {reason?.wait_plain && (
            <p className="text-[12.5px] text-slate-400 mt-1.5 leading-relaxed">{reason.wait_plain}</p>
          )}
          {!reason?.headline && actionStatus.subtitle && (
            <p className="text-[13.5px] text-slate-300 leading-snug">{actionStatus.subtitle}</p>
          )}
          {factors.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {factors.map((f, i) => (
                <span
                  key={f.id ?? i}
                  className={clsx(
                    "text-[11px] font-medium px-2 py-1 rounded-md border",
                    STANCE_CHIP[f.stance ?? "neutral"],
                  )}
                >
                  {f.label}
                  {f.summary ? `: ${f.summary}` : ""}
                </span>
              ))}
            </div>
          )}
          {onOpenWhy && (
            <button
              type="button"
              onClick={onOpenWhy}
              className="inline-flex items-center gap-1 text-[11.5px] text-slate-500 hover:text-emerald-400 mt-3"
            >
              Full breakdown <ChevronRight className="h-3 w-3" />
            </button>
          )}
        </div>
        <div>
          <p className="text-[10px] font-mono uppercase tracking-wider text-slate-600 mb-1.5">
            {horizonLabel(horizonKey)} levels
          </p>
          <LevelRows mode={mode} horizon={horizon} currentPrice={currentPrice} />
        </div>
      </div>

      {/* Gates */}
      {gates.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 px-4 sm:px-5 py-3 bg-slate-800/40 border-t border-slate-800">
          {gates.map((g) => (
            <div
              key={g.id}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-900/60 border border-slate-800"
              title={g.detail}
            >
              <span
                className={clsx(
                  "w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold shrink-0",
                  g.pass ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400",
                )}
              >
                {g.pass ? "✓" : "✕"}
              </span>
              <div className="min-w-0">
                <p className="text-[10.5px] font-semibold text-slate-300 truncate">{g.label}</p>
                <p className="text-[9.5px] text-slate-500 truncate">{g.detail}</p>
              </div>
            </div>
          ))}
          <div className="col-span-2 sm:col-span-4 text-[10px] font-mono text-slate-600 tabular-nums pt-0.5">
            {gatesPassed}/{gatesTotal} gates
          </div>
        </div>
      )}
    </div>
  );
}
