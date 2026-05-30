"use client";

import { clsx } from "clsx";
import type { InvestorDecisionSummary, HorizonSignalPayload } from "./InvestorDecisionSummary";
import {
  BehavioralActionBadge,
  deriveLongTermBehavioralBadge,
  deriveShortTermBehavioralBadge,
  EntryZonePriceBar,
  LongTermAccumulationScale,
  filterPrimaryTradingGates,
  buildGatesFromInvestorSummary,
  resolveLongHorizonEntryZone,
} from "./retailActionUX";
import {
  type DecisionMode,
  primaryHorizonFromMode,
  horizonLabel,
} from "@/lib/decisionMode";
import type { RetailActionPayload } from "./retailActionUX";

type NextTriggerInput = RetailActionPayload["next_trigger"] | string | null | undefined;

function formatNextTriggerText(trigger: NextTriggerInput): string | null {
  if (trigger == null) return null;
  if (typeof trigger === "string") {
    const t = trigger.trim();
    return t || null;
  }
  const parts: string[] = [];
  if (trigger.headline?.trim()) parts.push(trigger.headline.trim());
  if (trigger.detail?.trim()) parts.push(trigger.detail.trim());
  if (trigger.estimated_days != null && trigger.estimated_days > 0) {
    parts.push(`~${trigger.estimated_days}d`);
  }
  return parts.length ? parts.join(" — ") : null;
}

function entryBandPct(price: number, low: number, high: number): { inside: boolean; line: string } {
  const lo = Math.min(low, high);
  const hi = Math.max(low, high);
  if (!(lo > 0 && hi > lo)) return { inside: false, line: "Entry band unavailable." };
  if (price >= lo && price <= hi) return { inside: true, line: "Price is inside the buy zone now." };
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

export function DecisionDeck({
  summary,
  currentPrice,
  mode,
  tacticalActive,
}: {
  summary: InvestorDecisionSummary;
  currentPrice: number;
  mode: DecisionMode;
  tacticalActive?: boolean;
}) {
  const { horizons, one_answer, retail_action, regime_bull_pct, rsi } = summary;
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

  const ez = resolveEntryZone(mode, short, medium, long, currentPrice);
  const band = ez ? entryBandPct(currentPrice, ez.low, ez.high) : null;

  const nextTriggerText = formatNextTriggerText(
    retail_action?.next_trigger ??
      one_answer?.next_trigger ??
      primary.trigger_buy ??
      null
  );

  const nextLabelClass =
    mode === "scout" ? "text-cyan-300/90" : mode === "swing" ? "text-violet-300/90" : "text-emerald-300/90";

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
        <p className="text-[10px] uppercase tracking-[0.14em] font-bold text-slate-400">
          Today · {horizonLabel(primaryKey)}
        </p>
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
      </div>
      <div className="p-4 space-y-3">
        <BehavioralActionBadge badge={badge} />
        {tacticalActive && mode === "scout" && (
          <p className="text-xs text-cyan-200/90 border border-cyan-500/30 rounded-lg px-2.5 py-1.5 bg-cyan-950/40">
            Velocity / tactical lane active — confirm GO/NO-GO in scout panel above.
          </p>
        )}
        {band && (
          <p className={clsx("text-sm font-medium leading-snug", band.inside ? "text-emerald-200" : "text-amber-200/95")}>
            {band.line}
          </p>
        )}
        {mode === "owner" && long.entry_tiers?.tiers?.length && currentPrice > 0 ? (
          <LongTermAccumulationScale
            horizon={long}
            entryTiers={long.entry_tiers}
            currentPrice={currentPrice}
            stopLoss={primary.stop_loss > 0 ? primary.stop_loss : null}
            target={primary.target > 0 ? primary.target : null}
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
            />
          )
        )}
        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          {primary.stop_loss > 0 && (
            <div className="rounded-lg bg-slate-900/80 border border-red-500/25 px-2.5 py-2">
              <p className="text-[10px] uppercase text-slate-500 mb-0.5">Stop</p>
              <p className="text-red-300 tabular-nums">${primary.stop_loss.toFixed(2)}</p>
            </div>
          )}
          {primary.target > 0 && (
            <div className="rounded-lg bg-slate-900/80 border border-emerald-500/25 px-2.5 py-2">
              <p className="text-[10px] uppercase text-slate-500 mb-0.5">Target</p>
              <p className="text-emerald-300 tabular-nums">${primary.target.toFixed(2)}</p>
            </div>
          )}
        </div>
        {nextTriggerText && (
          <p className="text-xs text-slate-400 leading-snug border-t border-slate-700/60 pt-2">
            <span className={clsx("font-semibold", nextLabelClass)}>Next: </span>
            {nextTriggerText.length > 160 ? `${nextTriggerText.slice(0, 157)}…` : nextTriggerText}
          </p>
        )}
        {one_answer?.bottom_line && (
          <p className="text-[11px] text-slate-500 leading-snug">{one_answer.bottom_line}</p>
        )}
      </div>
    </section>
  );
}
