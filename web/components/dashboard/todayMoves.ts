import type { Signal } from "@/app/page";
import type { TradingLens } from "@/lib/tradingLens";
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
  /** When multiple tickers share the same story, list them here. */
  tickers?: string[];
  title: string;
  detail: string;
  storyProvenance?: StoryProvenance;
  trimProvenance?: TrimProvenance;
};

const KIND_ORDER: Record<TradingLens, TodayMove["kind"][]> = {
  scout: ["after_hours", "story", "trim", "earnings", "macro"],
  swing: ["earnings", "trim", "story", "after_hours", "macro"],
  owner: ["trim", "story", "earnings", "macro", "after_hours"],
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
  lens?: TradingLens;
}): TodayMove[] {
  const max = input.max ?? 3;
  const lens = input.lens ?? "scout";
  const order = KIND_ORDER[lens];

  const pools: Record<TodayMove["kind"], TodayMove[]> = {
    after_hours: [],
    story: [],
    trim: [],
    earnings: [],
    macro: [],
  };

  for (const ah of input.afterHours ?? []) {
    const pct = ah.change_pct;
    const pctStr = pct != null ? `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}% AH` : "AH move";
    const note = ah.post_earnings?.transition_note || ah.post_earnings?.beat_or_miss;
    pools.after_hours.push({
      id: `ah-${ah.ticker}`,
      kind: "after_hours",
      ticker: ah.ticker,
      title: `${ah.ticker} — ${pctStr}`,
      detail: note ? String(note) : "Earnings today — mark vs prior close (score updates on next full refresh)",
    });
  }

  const storyBuckets = new Map<
    string,
    { tickers: string[]; detail: string; sample: Signal }
  >();
  for (const s of input.storyChanges) {
    if (!s.story_change) continue;
    const playbook = [
      s.short_suggestion,
      s.medium_suggestion,
      s.long_suggestion,
    ]
      .map((x) => (x ?? "").trim().toLowerCase())
      .join("|");
    const bucketKey = `${s.story_change.trim().toLowerCase()}::${playbook}`;
    const existing = storyBuckets.get(bucketKey);
    if (existing) {
      existing.tickers.push(s.ticker);
    } else {
      storyBuckets.set(bucketKey, { tickers: [s.ticker], detail: s.story_change, sample: s });
    }
  }
  for (const { tickers, detail } of Array.from(storyBuckets.values())) {
    const label =
      tickers.length > 1
        ? `${tickers.slice(0, 4).join(" + ")}${tickers.length > 4 ? ` +${tickers.length - 4}` : ""} — story shift`
        : `${tickers[0]} — story shift`;
    pools.story.push({
      id: `story-${tickers.join("-")}`,
      kind: "story",
      ticker: tickers[0],
      tickers,
      title: label,
      detail,
    });
  }

  for (const t of input.trimCandidates) {
    pools.trim.push({
      id: `trim-${t.ticker}`,
      kind: "trim",
      ticker: t.ticker,
      title: `${t.ticker} — consider trim`,
      detail: t.trim_detail || t.label,
      trimProvenance: trimProv(t),
    });
  }

  for (const s of input.earningsSignals) {
    pools.earnings.push({
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

  if (input.macroHeadline) {
    pools.macro.push({
      id: "macro",
      kind: "macro",
      title: "Market backdrop",
      detail: input.macroHeadline,
    });
  }

  // Round-robin across kinds so Owner/Swing don't fill all 3 slots with "consider trim".
  const moves: TodayMove[] = [];
  const usedTickers = new Set<string>();
  const kindCounts: Partial<Record<TodayMove["kind"], number>> = {};
  const maxPerKind = Math.max(1, Math.ceil(max / 2)); // at most 2 of 3 same kind

  const tryPush = (m: TodayMove): boolean => {
    if (moves.length >= max) return false;
    if ((kindCounts[m.kind] ?? 0) >= maxPerKind) return false;
    if (m.ticker) {
      const key = m.ticker.toUpperCase();
      if (usedTickers.has(key)) return false;
      if (m.tickers?.some((t) => usedTickers.has(t.toUpperCase()))) return false;
    }
    moves.push(m);
    kindCounts[m.kind] = (kindCounts[m.kind] ?? 0) + 1;
    if (m.tickers?.length) {
      for (const t of m.tickers) usedTickers.add(t.toUpperCase());
    } else if (m.ticker) {
      usedTickers.add(m.ticker.toUpperCase());
    }
    return true;
  };

  // Pass 1: one from each kind in lens order (mix story / trim / earnings / …).
  for (const kind of order) {
    if (moves.length >= max) break;
    for (const m of pools[kind]) {
      if (tryPush(m)) break;
    }
  }
  // Pass 2: fill remaining slots still respecting per-kind cap.
  for (const kind of order) {
    if (moves.length >= max) break;
    for (const m of pools[kind]) {
      if (moves.some((x) => x.id === m.id)) continue;
      tryPush(m);
      if (moves.length >= max) break;
    }
  }

  return moves.slice(0, max);
}

/** Tickers already surfaced in Priority alerts (for deduping briefing actions). */
export function todayMoveTickers(moves: TodayMove[]): Set<string> {
  const out = new Set<string>();
  for (const m of moves) {
    if (m.tickers?.length) {
      for (const t of m.tickers) out.add(t.toUpperCase());
    } else if (m.ticker) {
      out.add(m.ticker.toUpperCase());
    }
  }
  return out;
}
