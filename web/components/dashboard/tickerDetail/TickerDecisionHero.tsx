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
  green: "border-td-accent/50 bg-td-accent-weak text-td-accent",
  yellow: "border-td-warn/50 bg-td-warn-weak text-td-warn",
  red: "border-td-crit/50 bg-td-crit-weak text-td-crit",
  neutral: "border-td-line bg-td-surface2 text-td-muted",
};
const LIGHT_DOT: Record<RetailActionLight, string> = {
  green: "bg-td-accent",
  yellow: "bg-td-warn",
  red: "bg-td-crit",
  neutral: "bg-td-muted",
};
const STANCE_CHIP: Record<"helps" | "hurts" | "neutral", string> = {
  helps: "text-td-accent border-td-accent/35 bg-td-accent-weak",
  hurts: "text-td-warn border-td-warn/35 bg-td-warn-weak",
  neutral: "text-td-muted border-td-line bg-td-surface2/60",
};
const MODE_ACCENT: Record<DecisionMode, string> = {
  scout: "border-td-info/25",
  swing: "border-td-owner/25",
  owner: "border-td-accent/25",
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
    <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface2/50 border border-td-line">
      <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-td-muted">{shown}</span>
      <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">
        {fmt(level.price)}
        <span className="ml-1.5 text-[10px] font-td-sans font-medium text-td-muted normal-case">{level.label}</span>
      </span>
      <span className={clsx("text-[10px] font-mono tabular-nums", below ? "text-td-crit/80" : "text-td-accent/80")}>
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
      <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface2/70 border border-td-line">
        <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-td-muted">Stop</span>
        <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">{fmt(horizon.stop_loss)}</span>
        <span className="text-[10px] font-mono text-td-crit/80 tabular-nums">
          {pctFromSpot(horizon.stop_loss, currentPrice)}
        </span>
      </div>
      <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface2/70 border border-td-line">
        <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-td-muted">Target</span>
        <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">{fmt(horizon.target)}</span>
        <span className="text-[10px] font-mono text-td-accent/80 tabular-nums">
          {pctFromSpot(horizon.target, currentPrice)}
          {/* Same R:R (and basis) as the Verdict tile — entry-mid when the plan has one, else spot. */}
          {(horizon.risk_reward_from_entry ?? horizon.risk_reward)
            ? ` · R:R ${(horizon.risk_reward_from_entry ?? horizon.risk_reward)!.toFixed(1)}${horizon.risk_reward_from_entry != null ? " from entry" : ""}`
            : ""}
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
            className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface2/70 border border-td-line"
          >
            <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-td-muted">{t.id}</span>
            <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">
              &le; {fmt(t.high)}
            </span>
            <span className="text-[10px] font-mono text-td-muted tabular-nums">
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
        <p className="text-[10px] text-td-muted leading-snug -mt-0.5 mb-0.5">
          Wide zone — scale in across these levels, not one price
        </p>
        {picked.map((lvl, i) => (
          <div
            key={lvl.id}
            className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface2/70 border border-td-line"
          >
            <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-td-muted truncate">
              {RUNG_TAG[i] ?? lvl.label}
            </span>
            <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">{fmt(lvl.price)}</span>
            <span className="text-[10px] font-mono text-td-muted tabular-nums">
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
      <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface2/70 border border-td-line">
        <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-td-muted">Entry</span>
        <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">
          {ez?.low != null && ez?.high != null ? `${fmt(ez.low)} – ${fmt(ez.high)}` : "—"}
        </span>
        <span className="text-[10px] font-mono text-td-muted tabular-nums">
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
  compact = false,
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
  /** Reason + levels only — the Verdict tab's VerdictPanel already shows the badge and gates. */
  compact?: boolean;
}) {
  const reason: SignalReasonPayload | null | undefined =
    summary.signal_reason_by_persona?.[mode] ?? summary.signal_reason;
  const horizonKey = primaryHorizonFromMode(mode);
  const horizon = summary.horizons[horizonKey];
  const factors = (reason?.factors ?? []).slice(0, 4);

  return (
    <div className={clsx("rounded-2xl bg-td-surface overflow-hidden", compact ? "border border-td-line" : "border-2", !compact && MODE_ACCENT[mode])}>
      {/* Ticker · verdict · price */}
      {!compact && (
      <div className="flex items-center justify-between gap-3 px-4 sm:px-5 py-3.5 border-b border-td-line">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-lg font-bold text-td-text tracking-tight">{ticker}</span>
            <span className="text-xs text-td-muted truncate">
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
          <p className="text-lg font-mono font-bold text-td-text tabular-nums">{fmt(currentPrice)}</p>
          {dailyMovePct != null && (
            <p
              className={clsx(
                "text-[11px] font-mono tabular-nums",
                dailyMovePct >= 0 ? "text-td-accent" : "text-td-crit",
              )}
            >
              {dailyMovePct >= 0 ? "+" : "−"}
              {Math.abs(dailyMovePct).toFixed(1)}% today
            </p>
          )}
        </div>
      </div>
      )}

      {/* Reason + levels */}
      <div className="grid sm:grid-cols-[1.2fr_1fr] gap-4 px-4 sm:px-5 py-4">
        <div className="min-w-0">
          {reason?.headline && (
            <p className="text-[15px] text-td-text leading-snug text-balance">{reason.headline}</p>
          )}
          {reason?.wait_plain && (
            <p className="text-[12.5px] text-td-muted mt-1.5 leading-relaxed">{reason.wait_plain}</p>
          )}
          {!reason?.headline && actionStatus.subtitle && (
            <p className="text-[13.5px] text-td-text/90 leading-snug">{actionStatus.subtitle}</p>
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
              className="inline-flex items-center gap-1 text-[11.5px] text-td-muted hover:text-td-accent mt-3"
            >
              Full breakdown <ChevronRight className="h-3 w-3" />
            </button>
          )}
        </div>
        <div>
          <p className="text-[10px] font-mono uppercase tracking-wider text-td-muted mb-1.5">
            {horizonLabel(horizonKey)} levels
          </p>
          <LevelRows mode={mode} horizon={horizon} currentPrice={currentPrice} />
        </div>
      </div>

      {/* Gates */}
      {!compact && gates.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 px-4 sm:px-5 py-3 bg-td-surface2/40 border-t border-td-line">
          {gates.map((g) => (
            <div
              key={g.id}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface border border-td-line"
              title={g.detail}
            >
              <span
                className={clsx(
                  "w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold shrink-0",
                  g.pass ? "bg-td-accent-weak text-td-accent" : "bg-td-crit-weak text-td-crit",
                )}
              >
                {g.pass ? "✓" : "✕"}
              </span>
              <div className="min-w-0">
                <p className="text-[10.5px] font-semibold text-td-text truncate">{g.label}</p>
                <p className="text-[9.5px] text-td-muted truncate">{g.detail}</p>
              </div>
            </div>
          ))}
          <div className="col-span-2 sm:col-span-4 text-[10px] font-mono text-td-muted tabular-nums pt-0.5">
            {gatesPassed}/{gatesTotal} gates
          </div>
        </div>
      )}
    </div>
  );
}
