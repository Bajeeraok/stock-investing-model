"use client";

import { ArrowRight, Calendar, Scissors, Zap } from "lucide-react";
import type { Signal } from "@/app/page";

export type TodayMove = {
  id: string;
  kind: "story" | "trim" | "earnings" | "macro";
  ticker?: string;
  title: string;
  detail: string;
};

function buildTodayMoves(input: {
  storyChanges: Signal[];
  trimCandidates: { ticker: string; label: string }[];
  earningsSignals: Signal[];
  macroHeadline?: string | null;
  max?: number;
}): TodayMove[] {
  const max = input.max ?? 3;
  const moves: TodayMove[] = [];

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
      detail: t.label,
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

const KIND_STYLE: Record<TodayMove["kind"], { icon: typeof Zap; border: string; text: string }> = {
  story: { icon: Zap, border: "border-amber-500/35", text: "text-amber-300" },
  trim: { icon: Scissors, border: "border-red-500/35", text: "text-red-300" },
  earnings: { icon: Calendar, border: "border-violet-500/35", text: "text-violet-300" },
  macro: { icon: ArrowRight, border: "border-sky-500/35", text: "text-sky-300" },
};

export function TodaysMovesPanel({
  storyChanges,
  trimCandidates,
  signals,
  macroHeadline,
  onTickerClick,
  onViewAll,
}: {
  storyChanges: Signal[];
  trimCandidates: { ticker: string; label: string }[];
  signals: Signal[];
  macroHeadline?: string | null;
  onTickerClick?: (ticker: string) => void;
  onViewAll?: () => void;
}) {
  const earningsSignals = signals.filter(
    (s) => s.earnings_caution || (s.earnings_days_until != null && s.earnings_days_until <= 7)
  );

  const moves = buildTodayMoves({
    storyChanges,
    trimCandidates,
    earningsSignals,
    macroHeadline,
    max: 3,
  });

  if (moves.length === 0) return null;

  return (
    <div className="rounded-xl border border-emerald-500/25 bg-gradient-to-br from-emerald-950/30 to-slate-900/60 p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div>
          <h2 className="font-semibold text-emerald-300 text-sm">Today&apos;s 3 moves</h2>
          <p className="text-[11px] text-slate-500 mt-0.5">What changed · trim flags · earnings — tap to open ticker</p>
        </div>
        {onViewAll && (
          <button
            type="button"
            onClick={onViewAll}
            className="text-[11px] text-emerald-400 hover:text-emerald-300 shrink-0"
          >
            All signals →
          </button>
        )}
      </div>
      <div className="space-y-2">
        {moves.map((move) => {
          const style = KIND_STYLE[move.kind];
          const Icon = style.icon;
          return (
            <div
              key={move.id}
              className={`flex items-start gap-3 rounded-lg border ${style.border} bg-slate-900/70 px-3 py-2.5`}
            >
              <Icon className={`h-4 w-4 shrink-0 mt-0.5 ${style.text}`} aria-hidden />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  {move.ticker && onTickerClick ? (
                    <button
                      type="button"
                      onClick={() => onTickerClick(move.ticker!)}
                      className="font-mono text-sm font-semibold text-emerald-400 hover:underline"
                    >
                      {move.title}
                    </button>
                  ) : (
                    <span className={`text-sm font-medium ${style.text}`}>{move.title}</span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-0.5 leading-snug">{move.detail}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
