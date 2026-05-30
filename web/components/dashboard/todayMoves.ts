import type { Signal } from "@/app/page";
import type { StoryProvenance, TrimProvenance } from "./AlertHorizonChip";

function trimProv(h: {
  trim_source?: string | null;
  trim_primary_driver?: string | null;
  trim_triggers?: string[] | null;
  trim_horizon?: string | null;
}): TrimProvenance {
  return {
    source: h.trim_source ?? null,
    primaryDriver: h.trim_primary_driver ?? null,
    triggers: h.trim_triggers ?? null,
    horizon: h.trim_horizon ?? null,
  };
}

export type AfterHoursMove = {
  ticker: string;
  change_pct?: number | null;
  post_earnings?: { transition_note?: string | null; beat_or_miss?: string | null };
};

export type TodayMove = {
  id: string;
  kind: "story" | "trim" | "earnings" | "macro" | "after_hours";
  ticker?: string;
  title: string;
  detail: string;
  storyProvenance?: import("./AlertHorizonChip").StoryProvenance;
  trimProvenance?: TrimProvenance;
};

export function buildTodayMoves(input: {
  storyChanges: Signal[];
  trimCandidates: {
    ticker: string;
    label: string;
    trim_source?: string | null;
    trim_primary_driver?: string | null;
    trim_triggers?: string[] | null;
    trim_detail?: string | null;
  }[];
  earningsSignals: Signal[];
  afterHours?: AfterHoursMove[];
  macroHeadline?: string | null;
  max?: number;
}): TodayMove[] {
  const max = input.max ?? 3;
  const moves: TodayMove[] = [];

  for (const ah of (input.afterHours ?? []).slice(0, 2)) {
    const pct = ah.change_pct;
    const pctStr = pct != null ? `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}% AH` : "AH move";
    const note = ah.post_earnings?.transition_note || ah.post_earnings?.beat_or_miss;
    moves.push({
      id: `ah-${ah.ticker}`,
      kind: "after_hours",
      ticker: ah.ticker,
      title: `${ah.ticker} — ${pctStr}`,
      detail: note ? String(note) : "Earnings today — mark vs prior close (score updates on next full refresh)",
    });
  }

  for (const s of input.storyChanges.slice(0, 2)) {
    if (!s.story_change) continue;
    moves.push({
      id: `story-${s.ticker}`,
      kind: "story",
      ticker: s.ticker,
      title: `${s.ticker} — story shift`,
      detail: s.story_change,
    });
  }

  for (const t of input.trimCandidates.slice(0, 2)) {
    if (moves.length >= max) break;
    if (moves.some((m) => m.ticker === t.ticker)) continue;
    moves.push({
      id: `trim-${t.ticker}`,
      kind: "trim",
      ticker: t.ticker,
      title: `${t.ticker} — consider trim`,
      detail: t.trim_detail || t.label,
      trimProvenance: trimProv(t),
    });
  }

  for (const s of input.earningsSignals.slice(0, 2)) {
    if (moves.length >= max) break;
    if (moves.some((m) => m.ticker === s.ticker)) continue;
    moves.push({
      id: `earn-${s.ticker}`,
      kind: "earnings",
      ticker: s.ticker,
      title: `${s.ticker} — earnings soon`,
      detail:
        s.earnings_caution
          ? `Caution window${s.earnings_days_until != null ? ` · ${s.earnings_days_until}d` : ""}`
          : `${s.earnings_days_until ?? "?"} days to report`,
    });
  }

  if (moves.length < max && input.macroHeadline) {
    moves.push({
      id: "macro",
      kind: "macro",
      title: "Market backdrop",
      detail: input.macroHeadline,
    });
  }

  return moves.slice(0, max);
}

/** Tickers already surfaced in Today's 3 moves (for deduping briefing actions). */
export function todayMoveTickers(moves: TodayMove[]): Set<string> {
  const out = new Set<string>();
  for (const m of moves) {
    if (m.ticker) out.add(m.ticker.toUpperCase());
  }
  return out;
}
