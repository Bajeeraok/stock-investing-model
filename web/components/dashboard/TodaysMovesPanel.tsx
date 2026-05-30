"use client";

import { ArrowRight, Calendar, Moon, Scissors, Zap } from "lucide-react";
import type { Signal } from "@/app/page";
import {
  AlertHorizonChip,
  formatHorizonSuggestionsLine,
  type AlertSourceKind,
  type StoryProvenance,
} from "./AlertHorizonChip";
import type { TradingLens } from "@/lib/tradingLens";
import {
  buildTodayMoves,
  type AfterHoursMove,
  type TodayMove,
} from "./todayMoves";

export type { AfterHoursMove, TodayMove };
export { buildTodayMoves, todayMoveTickers } from "./todayMoves";

function storyProv(s: Signal): StoryProvenance {
  return {
    source: (s as Signal & { story_change_source?: string }).story_change_source ?? null,
    trigger: (s as Signal & { story_change_trigger?: string }).story_change_trigger ?? null,
    horizon: (s as Signal & { story_change_horizon?: string }).story_change_horizon ?? null,
    horizonFlips: (s as Signal & { story_change_horizon_flips?: string[] }).story_change_horizon_flips ?? null,
  };
}

function buildTodayMovesWithProvenance(
  input: Parameters<typeof buildTodayMoves>[0]
): TodayMove[] {
  const moves = buildTodayMoves(input);
  return moves.map((m) => {
    if (m.kind !== "story" || !m.ticker) return m;
    const s = input.storyChanges.find((row) => row.ticker === m.ticker);
    if (!s) return m;
    return { ...m, storyProvenance: storyProv(s) };
  });
}

const KIND_STYLE: Record<TodayMove["kind"], { icon: typeof Zap; border: string; text: string }> = {
  story: { icon: Zap, border: "border-amber-500/35", text: "text-amber-300" },
  trim: { icon: Scissors, border: "border-red-500/35", text: "text-red-300" },
  earnings: { icon: Calendar, border: "border-violet-500/35", text: "text-violet-300" },
  after_hours: { icon: Moon, border: "border-indigo-500/35", text: "text-indigo-300" },
  macro: { icon: ArrowRight, border: "border-sky-500/35", text: "text-sky-300" },
};

export function TodaysMovesPanel({
  storyChanges,
  trimCandidates,
  signals,
  afterHours,
  macroHeadline,
  tradingLens,
  onTickerClick,
  onViewAll,
}: {
  storyChanges: Signal[];
  trimCandidates: {
    ticker: string;
    label: string;
    trim_source?: string | null;
    trim_primary_driver?: string | null;
    trim_triggers?: string[] | null;
    trim_detail?: string | null;
  }[];
  signals: Signal[];
  afterHours?: AfterHoursMove[];
  macroHeadline?: string | null;
  tradingLens?: TradingLens;
  onTickerClick?: (ticker: string) => void;
  onViewAll?: () => void;
}) {
  const earningsSignals = signals.filter(
    (s) => s.earnings_caution || (s.earnings_days_until != null && s.earnings_days_until <= 7)
  );

  const moves = buildTodayMovesWithProvenance({
    storyChanges,
    trimCandidates,
    earningsSignals,
    afterHours,
    macroHeadline,
    max: 3,
    lens: tradingLens,
  });

  if (moves.length === 0) return null;

  return (
    <div className="rounded-xl border border-emerald-500/25 bg-gradient-to-br from-emerald-950/30 to-slate-900/60 p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div>
          <h2 className="font-semibold text-emerald-300 text-sm">Today&apos;s 3 moves</h2>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Composite (MT) story & trim · ST earnings — hover chips for what drove each alert
          </p>
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
          const signalRow =
            move.ticker && signals.length > 0
              ? signals.find((s) => s.ticker === move.ticker)
              : undefined;
          const horizonLine =
            signalRow && (move.kind === "story" || move.kind === "trim")
              ? formatHorizonSuggestionsLine(signalRow)
              : null;
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
                  <AlertHorizonChip
                    kind={move.kind as AlertSourceKind}
                    compact
                    story={move.storyProvenance}
                    trim={move.trimProvenance}
                  />
                </div>
                <p className="text-xs text-slate-300 mt-0.5 leading-snug">{move.detail}</p>
                {horizonLine && (
                  <p className="text-[10px] text-slate-400 mt-1 font-mono" title="Horizon suggestions on file — context only; alert was not triggered by a horizon flip">
                    Playbooks: {horizonLine}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
