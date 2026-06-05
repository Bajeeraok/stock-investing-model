import type { DecisionMode } from "./decisionMode";
import { resolveLongHorizonEntryZone } from "@/components/dashboard/retailActionUX";
import type { InvestorDecisionSummary } from "@/components/dashboard/InvestorDecisionSummary";

export interface HorizonZoneReconciliation {
  active: boolean;
  st_zone?: string;
  lt_zone?: string;
  lt_tier_id?: string | null;
  gap_pct_above_lt?: number;
  execution_label?: string;
  summary?: string;
  owner_summary?: string;
  scout_summary?: string;
}

function fmtZone(lo: number, hi: number): string {
  return `$${lo.toFixed(0)}–$${hi.toFixed(0)}`;
}

/** Prefer API payload; compute client-side when ticker detail was cached before backend shipped split logic. */
export function getHorizonZoneReconciliation(
  summary: InvestorDecisionSummary | null | undefined,
  currentPrice: number,
): HorizonZoneReconciliation | null {
  const fromApi = summary?.one_answer?.horizon_zone_reconciliation;
  if (fromApi?.active) return fromApi as HorizonZoneReconciliation;
  if (!summary || !(currentPrice > 0)) return null;

  const actionToday = summary.one_answer?.action_today;
  if (actionToday !== "enter_now") return null;

  const short = summary.horizons?.short;
  const long = summary.horizons?.long;
  if (!short?.entry_zone) return null;

  const sLo = short.entry_zone.low;
  const sHi = short.entry_zone.high;
  const inShort =
    sLo != null && sHi != null && currentPrice >= Math.min(sLo, sHi) && currentPrice <= Math.max(sLo, sHi);
  if (!inShort) return null;

  const lt = resolveLongHorizonEntryZone(long, long.entry_tiers, currentPrice);
  if (lt.inside || currentPrice <= lt.high) return null;

  const stZone = fmtZone(Math.min(sLo, sHi), Math.max(sLo, sHi));
  const ltZone = fmtZone(lt.low, lt.high);
  const tierLabel = lt.tierId || "core";
  const gapPct = lt.high > 0 ? ((currentPrice - lt.high) / lt.high) * 100 : 0;

  return {
    active: true,
    st_zone: stZone,
    lt_zone: ltZone,
    lt_tier_id: lt.tierId,
    gap_pct_above_lt: Math.round(gapPct * 10) / 10,
    execution_label: "Short-term add OK (staged)",
    summary: `Short-term add OK in ${stZone} · Core tier (${tierLabel}) still ${ltZone} (${gapPct.toFixed(0)}% below spot) — size for swing, not full core.`,
    owner_summary: `Above ${tierLabel} core band (${ltZone}). Hold core sizing; any add here is tactical (${stZone}) only.`,
    scout_summary: `Gates clear for a staged short-term add in ${stZone}. Long-term core builds lower at ${ltZone}.`,
  };
}

export function reconciliationCopy(
  hr: HorizonZoneReconciliation | null | undefined,
  mode: DecisionMode,
): string | null {
  if (!hr?.active) return null;
  if (mode === "owner") return hr.owner_summary ?? hr.summary ?? null;
  if (mode === "scout") return hr.scout_summary ?? hr.summary ?? null;
  return hr.summary ?? null;
}

export function executionLabelWithReconciliation(
  actionToday: string | null | undefined,
  hr: HorizonZoneReconciliation | null | undefined,
  mode: DecisionMode,
): string | null {
  if (!hr?.active) return null;
  if (mode === "owner") {
    return `Core tier ${hr.lt_zone} — tactical only at ${hr.st_zone}`;
  }
  if (actionToday === "enter_now") {
    return hr.execution_label ?? "Short-term add OK (staged)";
  }
  return null;
}
