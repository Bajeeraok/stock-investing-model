"use client";

import { useState } from "react";
import { clsx } from "clsx";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Info,
  XCircle,
} from "lucide-react";
import type { InvestorDecisionSummary, HorizonSignalPayload } from "./InvestorDecisionSummary";
import {
  BehavioralActionBadge,
  deriveLongTermBehavioralBadge,
  deriveShortTermBehavioralBadge,
  EntryZonePriceBar,
  LongTermAccumulationScale,
  LongTermTierLadder,
  filterPrimaryTradingGates,
  buildGatesFromInvestorSummary,
  resolveLongHorizonEntryZone,
} from "./retailActionUX";
import {
  type DecisionMode,
  primaryHorizonFromMode,
  horizonLabel,
} from "@/lib/decisionMode";
import { ExternalContextChip } from "./ExternalContextChip";
import { ValuationDeck } from "./ValuationDeck";
import { StreetSentimentChip } from "./StreetSentimentChip";
import { ExecutionPlanRationale } from "./ExecutionPlanRationale";
import {
  executionLabelWithReconciliation,
  getHorizonZoneReconciliation,
  reconciliationCopy,
} from "@/lib/horizonReconcile";
import { HorizonReconcileStrip } from "./zoneContextUX";

const STRENGTH_CONVICTION_HINT =
  "Strength = how strong the technical read is on this horizon. Conviction = how much the model trusts that read (gates, ML, pattern).";

function entryBandPct(
  price: number,
  low: number,
  high: number,
  opts?: { holdDespiteInBand?: boolean; bandLabel?: string },
): { inside: boolean; line: string } {
  const lo = Math.min(low, high);
  const hi = Math.max(low, high);
  const label = opts?.bandLabel ?? "short-term band";
  if (!(lo > 0 && hi > lo)) return { inside: false, line: "Entry band unavailable." };
  if (price >= lo && price <= hi) {
    if (opts?.holdDespiteInBand) {
      return {
        inside: true,
        line: `In ${label} ($${lo.toFixed(0)}–$${hi.toFixed(0)}) — hold until gates clear; band is where you'd add if conditions improve.`,
      };
    }
    return { inside: true, line: `In ${label} — favorable for staged adds when execution says enter.` };
  }
  if (price > hi) {
    const pct = ((price - hi) / hi) * 100;
    return { inside: false, line: `${pct.toFixed(1)}% above band — wait for pullback.` };
  }
  const pct = ((lo - price) / lo) * 100;
  return { inside: false, line: `${pct.toFixed(1)}% below band low — not at entry yet.` };
}

function modeHeroBadge(
  mode: DecisionMode,
  short: HorizonSignalPayload,
  medium: HorizonSignalPayload,
  long: HorizonSignalPayload,
  assessmentPct: number,
  currentPrice: number,
  regimeBullPct: number | null | undefined,
  rsi: number | null | undefined
) {
  if (mode === "scout") return deriveShortTermBehavioralBadge(short, regimeBullPct, rsi);
  if (mode === "owner") return deriveLongTermBehavioralBadge(long, short, assessmentPct, currentPrice);
  const v = String(medium.verdict || "").toUpperCase();
  if (v === "BUY" || v === "STRONG BUY") {
    return { emoji: "🟢", label: "SWING ADD ZONE", tone: "green" as const, hint: "Medium-term band supports staged adds." };
  }
  if (v === "WATCH") {
    return { emoji: "🟡", label: "STAGE ON PULLBACK", tone: "amber" as const, hint: "Setup forming on swing horizon." };
  }
  return { emoji: "🔴", label: "WAIT — NO ADD", tone: "red" as const, hint: "Swing horizon not ready — see band below." };
}

function resolveEntryZone(
  mode: DecisionMode,
  short: HorizonSignalPayload,
  medium: HorizonSignalPayload,
  long: HorizonSignalPayload,
  currentPrice: number
): { low: number; high: number; label: string } | null {
  const key = primaryHorizonFromMode(mode);
  const h = key === "short" ? short : key === "medium" ? medium : long;
  if (key === "long" && long.entry_tiers) {
    const r = resolveLongHorizonEntryZone(long, long.entry_tiers, currentPrice);
    return {
      low: r.low,
      high: r.high,
      label: r.tierId ? `Buy zone (${r.tierId})` : "Buy zone",
    };
  }
  const ez = h.entry_zone;
  if (!ez?.low || !ez?.high) return null;
  return { low: ez.low, high: ez.high, label: "Buy zone" };
}

function verdictIcon(verdict: string) {
  switch (verdict) {
    case "STRONG BUY":
    case "BUY":
      return <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0" aria-hidden />;
    case "WATCH":
      return <AlertCircle className="h-4 w-4 text-teal-400 shrink-0" aria-hidden />;
    default:
      return <XCircle className="h-4 w-4 text-red-400 shrink-0" aria-hidden />;
  }
}

const ACTION_TODAY_LABEL: Record<string, string> = {
  enter_now: "Short-term add OK (staged)",
  wait_for_pullback: "Wait for pullback",
  hold: "Hold / watch",
  trim: "Trim",
  no_new_position: "No new adds",
};

function executionLabel(action: string | null | undefined): string {
  if (!action) return "Hold / watch";
  return ACTION_TODAY_LABEL[action] ?? action.replace(/_/g, " ");
}

function verdictTextClass(verdict: string): string {
  if (verdict === "BUY" || verdict === "STRONG BUY") return "text-emerald-400";
  if (verdict === "WATCH") return "text-teal-400";
  return "text-red-400";
}

function PlanCaveats({
  rationale,
  warnings,
}: {
  rationale?: string | null;
  warnings: string[];
}) {
  const [open, setOpen] = useState(false);
  const hasRationale = Boolean(rationale?.trim());
  const count = warnings.length + (hasRationale ? 1 : 0);
  if (count === 0) return null;

  return (
    <div className="border-t border-slate-600/80 pt-2">
      <button
        type="button"
        onClick={() => setOpen((s) => !s)}
        className="text-sm text-amber-300/90 flex items-center gap-1 hover:text-amber-200"
      >
        <AlertTriangle className="h-3 w-3 shrink-0" />
        {count} caveat{count > 1 ? "s" : ""}
        {open ? <ChevronUp className="h-3 w-3 shrink-0" /> : <ChevronDown className="h-3 w-3 shrink-0" />}
      </button>
      {open && (
        <div className="mt-2 space-y-1.5">
          {hasRationale && <p className="text-sm text-slate-300 leading-snug">{rationale!.trim()}</p>}
          {warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-1.5 text-sm text-amber-300/90">
              <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function DecisionDeck({
  summary,
  currentPrice,
  mode,
  tacticalActive,
  ltEntryTiersOpen,
  onToggleLtTiers,
  hideHero = false,
  hideExecutionEvidence = false,
}: {
  summary: InvestorDecisionSummary;
  currentPrice: number;
  mode: DecisionMode;
  tacticalActive?: boolean;
  ltEntryTiersOpen?: boolean;
  onToggleLtTiers?: () => void;
  /** When command card already shows action headline — skip duplicate hero rows. */
  hideHero?: boolean;
  /** Signal breakdown grid already shows evidence rows — skip duplicate in execution plan. */
  hideExecutionEvidence?: boolean;
}) {
  const { horizons, one_answer, regime_bull_pct, rsi, valuation_deck, fair_value, fair_value_vs_external } =
    summary;
  const short = horizons.short;
  const medium = horizons.medium;
  const long = horizons.long;
  const primaryKey = primaryHorizonFromMode(mode);
  const primary = primaryKey === "short" ? short : primaryKey === "medium" ? medium : long;

  const gates = filterPrimaryTradingGates(buildGatesFromInvestorSummary(summary, currentPrice));
  const passed = gates.filter((g) => g.pass).length;

  const badge = modeHeroBadge(
    mode,
    short,
    medium,
    long,
    currentPrice > 0 ? ((summary.fair_value - currentPrice) / currentPrice) * 100 : 0,
    currentPrice,
    regime_bull_pct,
    rsi ?? null
  );

  const warnings = Array.isArray(primary.warnings)
    ? primary.warnings.filter((w) => w && String(w).trim())
    : [];

  const showOwnerTierLadder =
    mode === "owner" && primaryKey === "long" && Boolean(long.entry_tiers?.tiers?.length);

  const actionToday = one_answer?.action_today;
  const hr = getHorizonZoneReconciliation(summary, currentPrice);
  const reconcileText = reconciliationCopy(hr, mode);
  const executionOverride = executionLabelWithReconciliation(actionToday, hr, mode);
  const executionToday = executionOverride ?? executionLabel(actionToday);
  const splitActive = Boolean(hr?.active);
  const horizonVerdict = (primary.verdict || "").toUpperCase();
  const horizonBuy = horizonVerdict === "BUY" || horizonVerdict === "STRONG BUY";
  const executionBlocksChase =
    actionToday === "hold" ||
    actionToday === "wait_for_pullback" ||
    actionToday === "no_new_position";

  const ez = resolveEntryZone(mode, short, medium, long, currentPrice);
  const band = ez
    ? entryBandPct(currentPrice, ez.low, ez.high, {
        holdDespiteInBand: executionBlocksChase,
        bandLabel: mode === "owner" ? "long-term tier" : mode === "swing" ? "swing band" : "short-term band",
      })
    : null;

  return (
    <section
      className={clsx(
        "rounded-2xl border overflow-hidden",
        mode === "scout" && "border-cyan-500/30 bg-gradient-to-br from-cyan-950/40 to-slate-950/80",
        mode === "swing" && "border-violet-500/30 bg-gradient-to-br from-violet-950/40 to-slate-950/80",
        mode === "owner" && "border-emerald-500/30 bg-gradient-to-br from-emerald-950/40 to-slate-950/80"
      )}
      aria-label={`Today’s decision — ${horizonLabel(primaryKey)}`}
    >
      <div className="px-4 py-3 border-b border-slate-700/50 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] uppercase tracking-[0.14em] font-bold text-slate-200">
          {horizonLabel(primaryKey)} plan
        </p>
        {!hideHero && (
        <span
          className={clsx(
            "text-[10px] font-mono tabular-nums px-2 py-0.5 rounded border",
            passed >= 3
              ? "border-emerald-500/35 text-emerald-300 bg-emerald-500/10"
              : "border-amber-500/35 text-amber-200 bg-amber-500/10"
          )}
        >
          {passed}/{gates.length} gates
        </span>
        )}
      </div>
      <div className="p-4 space-y-3">
        {!hideHero && (
          <>
        <BehavioralActionBadge badge={badge} />

        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="text-sm font-medium text-slate-300">{primary.label}</span>
          <span className="flex items-center gap-1.5">
            {verdictIcon(primary.verdict)}
            <span className={clsx("text-sm font-semibold", verdictTextClass(primary.verdict))}>
              {primary.verdict}
            </span>
          </span>
        </div>

        <p className="text-xs text-slate-500 flex items-center gap-1.5 flex-wrap -mt-1">
          <span title={STRENGTH_CONVICTION_HINT} className="cursor-help border-b border-dotted border-slate-500/50">
            {primary.signal} strength · {primary.conviction} conviction
          </span>
          <span title={STRENGTH_CONVICTION_HINT} className="inline-flex shrink-0">
            <Info className="h-3.5 w-3.5 text-slate-500 cursor-help" aria-hidden />
          </span>
        </p>
          </>
        )}

        {reconcileText && <HorizonReconcileStrip text={reconcileText} mode={mode} />}

        <p
          className={clsx(
            "text-xs font-medium rounded-lg px-2.5 py-1.5 border",
            splitActive && mode === "owner"
              ? "text-violet-100 border-violet-500/35 bg-violet-950/30"
              : splitActive
                ? "text-amber-100 border-amber-500/35 bg-amber-950/25"
                : actionToday === "enter_now"
                  ? "text-emerald-200 border-emerald-500/35 bg-emerald-950/30"
                  : "text-amber-100 border-amber-500/30 bg-amber-950/25",
          )}
          title="Horizon verdict is trend bias; execution is whether to act at this price today."
        >
          <span className="text-slate-400 font-normal">Execution today: </span>
          {executionToday}
          {horizonBuy && executionBlocksChase && !splitActive && (
            <span className="text-slate-500 font-normal">
              {" "}
              — horizon still {horizonVerdict} (trend vs entry timing)
            </span>
          )}
        </p>

        {!hideHero && tacticalActive && mode === "scout" && (
          <p
            className={clsx(
              "text-xs rounded-lg px-2.5 py-1.5 border",
              executionBlocksChase
                ? "text-amber-200/90 border-amber-500/35 bg-amber-950/30"
                : splitActive
                  ? "text-amber-200/90 border-amber-500/35 bg-amber-950/30"
                  : "text-cyan-200/90 border-cyan-500/30 bg-cyan-950/40",
            )}
          >
            {splitActive
              ? "4/4 gates = short-term lane only. Long-term core tier is lower — see banner above."
              : executionBlocksChase
                ? "Tactical breakout is momentum context — not a chase-the-close buy. Use act-when triggers below."
                : "Velocity lane aligns with enter-now — still use stops and staged size."}
          </p>
        )}

        <ExternalContextChip context={one_answer?.external_context} />

        {mode === "owner" && valuation_deck && currentPrice > 0 && (
          <ValuationDeck
            deck={valuation_deck}
            currentPrice={currentPrice}
            modelFairValue={fair_value}
            external={fair_value_vs_external}
            mode="owner"
            variant="full"
          />
        )}
        {mode === "swing" && valuation_deck && currentPrice > 0 && (
          <ValuationDeck
            deck={valuation_deck}
            currentPrice={currentPrice}
            modelFairValue={fair_value}
            external={fair_value_vs_external}
            mode="swing"
            variant="compact"
          />
        )}
        {mode === "scout" && valuation_deck && (
          <StreetSentimentChip deck={valuation_deck} executionLabel={executionToday} />
        )}

        {band && !showOwnerTierLadder && (
          <p className={clsx("text-sm font-medium leading-snug", band.inside ? "text-emerald-200" : "text-amber-100")}>
            {band.line}
          </p>
        )}

        {showOwnerTierLadder && currentPrice > 0 ? (
          <LongTermAccumulationScale
            horizon={long}
            entryTiers={long.entry_tiers!}
            currentPrice={currentPrice}
            stopLoss={primary.stop_loss > 0 ? primary.stop_loss : null}
            target={primary.target > 0 ? primary.target : null}
            variant="deck"
          />
        ) : (
          ez &&
          ez.low < ez.high &&
          currentPrice > 0 && (
            <EntryZonePriceBar
              entryLow={ez.low}
              entryHigh={ez.high}
              currentPrice={currentPrice}
              stopLoss={primary.stop_loss > 0 ? primary.stop_loss : null}
              target={primary.target > 0 ? primary.target : null}
              bandLabel={ez.label}
              quality={primary.entry_zone?.quality}
              touchForecast={primary.entry_touch_forecast}
              spotPosition={primary.entry_zone?.spot_position}
              levels={primary.entry_zone?.levels}
              holdDespiteInBand={executionBlocksChase}
            />
          )
        )}

        {(primary.stop_loss > 0 || primary.target > 0) && (
          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            {primary.stop_loss > 0 && (
              <div className="rounded-lg bg-slate-900/80 border border-red-500/35 px-2.5 py-2">
                <p className="text-[10px] uppercase text-red-200/90 font-semibold mb-0.5">Stop</p>
                <p className="text-red-200 tabular-nums font-semibold">${primary.stop_loss.toFixed(2)}</p>
              </div>
            )}
            {primary.target > 0 && (
              <div className="rounded-lg bg-slate-900/80 border border-emerald-500/35 px-2.5 py-2">
                <p className="text-[10px] uppercase text-emerald-200/90 font-semibold mb-0.5">Target</p>
                <p className="text-emerald-200 tabular-nums font-semibold">
                  ${primary.target.toFixed(2)}
                  {primary.target_pct > 0 ? (
                    <span className="text-emerald-300/80 font-normal ml-1">(+{primary.target_pct.toFixed(0)}%)</span>
                  ) : null}
                </p>
              </div>
            )}
          </div>
        )}

        {one_answer && (
          <ExecutionPlanRationale
            summary={summary}
            currentPrice={currentPrice}
            mode={mode}
            variant="deck"
            showTickerLine={false}
            showEvidence={!hideExecutionEvidence}
            hideValuationHeader={hideHero}
            hideBuyStages={false}
          />
        )}

        <PlanCaveats rationale={primary.rationale} warnings={warnings} />

        {showOwnerTierLadder && onToggleLtTiers && (
          <div className="border-t border-slate-600/60 pt-2">
            <button
              type="button"
              onClick={onToggleLtTiers}
              className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300"
            >
              {ltEntryTiersOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              {ltEntryTiersOpen ? "Hide entry tiers" : "Show entry tiers"}
            </button>
            {ltEntryTiersOpen && long.entry_tiers && (
              <div className="mt-2">
                <LongTermTierLadder
                  entryTiers={long.entry_tiers}
                  currentPrice={currentPrice}
                  modeLabel={long.entry_tiers.current_assessment?.label}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
