import type { Signal } from "@/app/page";
import type { SignalListContext } from "@/components/dashboard/retailActionUX";
import { PRIMARY_TRADING_GATE_IDS } from "@/components/dashboard/retailActionUX";
import { gatesForSignal } from "@/lib/signalsTableViewGates";

export type EntryMode = "full_go" | "starter_only" | "hard_lock" | string;

const ENTRY_MODE_ORDER: Record<string, number> = { full_go: 0, starter_only: 1, hard_lock: 2 };

export function entryModeLabel(mode: EntryMode | null | undefined): { label: string; cls: string } {
  switch (mode) {
    case "full_go":
      return { label: "Full Go", cls: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" };
    case "starter_only":
      return { label: "Starter", cls: "text-amber-400 bg-amber-500/10 border-amber-500/30" };
    case "hard_lock":
      return { label: "Locked", cls: "text-slate-400 bg-slate-700/40 border-slate-600/30" };
    default:
      return { label: mode ?? "—", cls: "text-slate-500 bg-slate-800 border-slate-700" };
  }
}

export function resolveEntryMode(r: Signal): EntryMode | null {
  const rs = r.retail_status;
  const raw = rs?.entry_mode ?? (r as { entry_mode?: string }).entry_mode ?? null;
  if (raw === "go" || raw === "GO") return "full_go";
  if (raw === "no_go" || raw === "NO_GO") {
    const { passed } = resolveGatesCount(r, {});
    return passed === 0 ? "hard_lock" : "starter_only";
  }
  if (raw === "full_go" || raw === "starter_only" || raw === "hard_lock") return raw;
  return raw;
}

export function resolveGatesCount(
  r: Signal,
  gateContext: SignalListContext,
): { passed: number; total: number } {
  const row = r as Signal & { gates_passed?: number | null; gates_total?: number | null };
  if (row.gates_passed != null) {
    return { passed: row.gates_passed, total: row.gates_total ?? 4 };
  }
  const gates = r.retail_status?.gates;
  if (gates?.length) {
    const primary = gates.filter((g) =>
      (PRIMARY_TRADING_GATE_IDS as readonly string[]).includes(g.id),
    );
    const use = primary.length ? primary : gates;
    return { passed: use.filter((g) => g.pass).length, total: use.length || 4 };
  }
  const computed = gatesForSignal(r, gateContext);
  return { passed: computed.filter((g) => g.pass).length, total: computed.length || 4 };
}

export function resolveConfidencePct(r: Signal): number | null {
  const row = r as Signal & { model_confidence_pct?: number | null; confidence_mid?: number | null };
  if (row.model_confidence_pct != null) {
    return Math.round(Number(row.model_confidence_pct) * 10) / 10;
  }
  if (row.confidence_mid != null) {
    return Math.round(Number(row.confidence_mid) * 10) / 10;
  }
  if (r.plan_confidence != null) {
    const pc = Number(r.plan_confidence);
    return Math.round((pc <= 1 ? pc * 100 : pc) * 10) / 10;
  }
  return null;
}

export function entryModeSortKey(mode: EntryMode | null | undefined): number {
  return ENTRY_MODE_ORDER[mode ?? ""] ?? 9;
}

/**
 * Reward:risk from the ST band (stop = low, target = high) vs close — the ratio a
 * retail trader actually sizes off of, vs. a dollar risk figure that only makes sense
 * next to a specific account size.
 */
export function riskRewardRatio(r: Signal): number | null {
  const close = r.close;
  const stop = r.st_band?.low;
  const target = r.st_band?.high;
  if (close == null || stop == null || target == null) return null;
  const risk = close - stop;
  const reward = target - close;
  if (risk <= 0 || reward <= 0) return null;
  return reward / risk;
}

/**
 * "Best conditions to buy" composite: entry_mode tier first (full_go clears all gates and is
 * actually fillable; starter_only is partial size; hard_lock is blocked regardless of how good
 * the technicals look), then composite_buy as the tie-break within a tier. composite_buy —
 * not confluence_score — because it's the canonical 0-100 Trend+RSI+MACD score the row's own
 * action text ("Score NN. Consider small add...", see retail_briefing.py) is generated from;
 * sorting by confluence_score (a separate technical-setup-quality metric — see the dedicated
 * "Confluence" sort option) silently ranked rows in an order that contradicted the score
 * printed in their own description (confirmed: a ticker showing "Score 77" sorted below one
 * showing "Score 66" because both happened to tie on confluence_score, a number never shown
 * in that text at all).
 */
export function buyReadinessSortValue(r: Signal): number {
  const tier = entryModeSortKey(resolveEntryMode(r));
  const score = r.composite_buy ?? r.confluence_score ?? 0;
  return tier * 1000 - score;
}
