"use client";

import { Zap } from "lucide-react";

export type TacticalBreakoutRow = {
  ticker: string;
  velocity_score?: number | null;
  rvol?: number | null;
  bb_pct_b?: number | null;
  gates_passed?: number | null;
  gates_total?: number | null;
  close?: number | null;
  tactical_t1?: number | null;
  tactical_stop?: number | null;
  reasons?: string[];
};

export function TacticalBreakoutStrip({
  rows,
  onTickerClick,
}: {
  rows: TacticalBreakoutRow[] | null | undefined;
  onTickerClick?: (ticker: string) => void;
}) {
  if (!rows?.length) return null;

  return (
    <div className="rounded-xl border border-violet-500/30 bg-gradient-to-r from-violet-950/40 to-slate-900/40 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Zap className="h-4 w-4 text-violet-400 shrink-0" />
        <p className="text-sm font-semibold text-violet-200">Tactical breakout watch</p>
        <span className="text-xs text-slate-500 tabular-nums">T+5 · not full GO</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {rows.map((r) => (
          <button
            key={r.ticker}
            type="button"
            onClick={() => onTickerClick?.(r.ticker)}
            className="rounded-lg border border-violet-500/25 bg-slate-900/60 px-2.5 py-1.5 text-left hover:border-violet-400/40 touch-manipulation min-w-[7rem]"
          >
            <span className="font-mono text-sm text-violet-200">{r.ticker}</span>
            <div className="text-[10px] text-slate-400 mt-0.5 tabular-nums">
              {r.velocity_score != null ? `score ${Math.round(r.velocity_score)}` : ""}
              {r.rvol != null ? ` · RVOL ${r.rvol}×` : ""}
              {r.gates_passed != null ? ` · ${r.gates_passed}/${r.gates_total ?? 4} gates` : ""}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
