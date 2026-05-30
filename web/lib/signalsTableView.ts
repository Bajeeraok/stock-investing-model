import type { Signal } from "@/app/page";
import {
  deriveListActionStatus,
  type SignalListContext,
} from "@/components/dashboard/retailActionUX";

export { tradingGateSummaryLabel, gatesForSignal } from "./signalsTableViewGates";

export type SignalsViewMode = "quick" | "full";

export const SIGNALS_VIEW_MODE_KEY = "thrive-signals-view-mode";

export function loadSignalsViewMode(): SignalsViewMode {
  try {
    const raw = typeof window !== "undefined" ? localStorage.getItem(SIGNALS_VIEW_MODE_KEY) : null;
    if (raw === "full") return "full";
  } catch {
    /* ignore */
  }
  return "quick";
}

export function saveSignalsViewMode(mode: SignalsViewMode): void {
  try {
    localStorage.setItem(SIGNALS_VIEW_MODE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function rowActionKey(
  signal: Signal,
  listContext: SignalListContext,
  oneLiner?: string | null
): string {
  const status = deriveListActionStatus(signal);
  const subtitle =
    oneLiner?.trim() ||
    signal.retail_status?.dynamic_subtitle ||
    signal.retail_status?.action_title ||
    "";
  return `${status.title}|||${subtitle.slice(0, 120)}`;
}

export function parseRowActionKey(key: string): { title: string; subtitle: string } {
  const [title, subtitle] = key.split("|||");
  return { title: title ?? "—", subtitle: subtitle ?? "" };
}

export type SignalActionGroup = {
  key: string;
  title: string;
  subtitle: string;
  rows: Signal[];
};

export function groupSignalsByAction(
  rows: Signal[],
  listContext: SignalListContext,
  tickerActions?: Record<string, { action: string; one_liner: string }>
): SignalActionGroup[] {
  const map = new Map<string, Signal[]>();
  for (const r of rows) {
    const key = rowActionKey(r, listContext, tickerActions?.[r.ticker]?.one_liner);
    const bucket = map.get(key) ?? [];
    bucket.push(r);
    map.set(key, bucket);
  }
  return Array.from(map.entries()).map(([key, groupRows]) => {
    const { title, subtitle } = parseRowActionKey(key);
    return { key, title, subtitle, rows: groupRows };
  });
}

/** True when earnings cell would show something besides placeholder/unavailable noise. */
export function signalHasEarningsInsight(r: Signal): boolean {
  if (r.earnings_caution) return true;
  if (r.earnings_days_until != null && r.earnings_days_until <= 21) return true;
  if (r.earnings_note?.trim()) return true;
  const flags = (r.earnings_quality?.flags ?? []).filter(Boolean);
  const usefulFlag = flags.some((f) => !/unavailable|403|forbidden|timeout/i.test(f));
  if (usefulFlag) return true;
  if (r.earnings_quality?.grade && !flags.some((f) => /unavailable/i.test(f))) return true;
  return false;
}

export function signalHasLiquidity(r: Signal): boolean {
  return r.liquidity_days_to_exit != null || r.liquidity_score != null;
}
