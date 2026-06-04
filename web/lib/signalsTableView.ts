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

export function rowActionSubtitle(
  signal: Signal,
  listContext: SignalListContext,
  oneLiner?: string | null
): string {
  return (
    oneLiner?.trim() ||
    signal.retail_status?.dynamic_subtitle ||
    signal.retail_status?.action_title ||
    ""
  ).slice(0, 120);
}

/** Group key — action title only so identical labels (e.g. DO NOT CHASE) stay together. */
export function rowActionKey(
  signal: Signal,
  _listContext: SignalListContext,
  _oneLiner?: string | null
): string {
  return deriveListActionStatus(signal).title;
}

export function parseRowActionKey(key: string): { title: string; subtitle: string } {
  const [title, subtitle] = key.split("|||");
  return { title: title ?? "—", subtitle: subtitle ?? "" };
}

function pickGroupSubtitle(subtitles: string[]): string {
  const trimmed = subtitles.map((s) => s.trim()).filter(Boolean);
  if (trimmed.length === 0) return "";
  const unique = new Set(trimmed);
  if (unique.size === 1) return trimmed[0];
  return "";
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
  const map = new Map<string, { rows: Signal[]; subtitles: string[] }>();
  for (const r of rows) {
    const key = rowActionKey(r, listContext, tickerActions?.[r.ticker]?.one_liner);
    const subtitle = rowActionSubtitle(r, listContext, tickerActions?.[r.ticker]?.one_liner);
    const bucket = map.get(key) ?? { rows: [], subtitles: [] };
    bucket.rows.push(r);
    bucket.subtitles.push(subtitle);
    map.set(key, bucket);
  }
  const groups = Array.from(map.entries()).map(([key, { rows: groupRows, subtitles }]) => ({
    key,
    title: key,
    subtitle: pickGroupSubtitle(subtitles),
    rows: groupRows,
  }));
  return sortSignalActionGroups(groups);
}

const ACTION_GROUP_PRIORITY: Record<string, number> = {
  "TACTICAL ENTRY": 0,
  "WATCH OR HOLD": 1,
  "DO NOT CHASE": 2,
};

/** Stable action-first ordering for grouped quick view. */
export function sortSignalActionGroups(groups: SignalActionGroup[]): SignalActionGroup[] {
  return [...groups].sort((a, b) => {
    const pa = ACTION_GROUP_PRIORITY[a.title] ?? 99;
    const pb = ACTION_GROUP_PRIORITY[b.title] ?? 99;
    if (pa !== pb) return pa - pb;
    if (b.rows.length !== a.rows.length) return b.rows.length - a.rows.length;
    return a.title.localeCompare(b.title);
  });
}

export function actionGroupTickerPreview(rows: Signal[], max = 5): string {
  return rows
    .slice(0, max)
    .map((r) => r.ticker)
    .filter(Boolean)
    .join(" · ");
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
