"use client";

import { AlertTriangle } from "lucide-react";
import type { Signal } from "@/app/page";
import { AlertHorizonChip, formatHorizonSuggestionsLine } from "./AlertHorizonChip";

export function StoryAlerts({ items, onTickerClick }: { items: Signal[]; onTickerClick?: (ticker: string) => void }) {
  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
      <div className="flex items-center gap-2 mb-1">
        <AlertTriangle className="h-5 w-5 text-amber-400" />
        <h2 className="font-semibold text-amber-400">Story Change Alerts</h2>
        <AlertHorizonChip kind="story" compact />
      </div>
      <p className="text-[11px] text-slate-500 mb-3 ml-7">
        Chip shows what fired the alert (composite regime/score or ST/MT/LT suggestion flip)
      </p>
      <div className="space-y-2">
        {items.map((r) => {
          const horizonLine = formatHorizonSuggestionsLine(r);
          return (
            <div
              key={r.ticker}
              className="py-2 px-3 rounded-lg bg-slate-900/80 space-y-1"
            >
              <div className="flex items-center justify-between gap-2 flex-wrap">
                {onTickerClick ? (
                  <button
                    type="button"
                    onClick={() => onTickerClick(r.ticker)}
                    className="font-mono font-medium text-emerald-400 hover:underline cursor-pointer"
                  >
                    {r.ticker}
                  </button>
                ) : (
                  <span className="font-mono font-medium text-slate-200">{r.ticker}</span>
                )}
                <span className="text-amber-300 text-sm text-right">{r.story_change}</span>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <AlertHorizonChip
                  kind="story"
                  compact
                  story={{
                    source: (r as Signal & { story_change_source?: string }).story_change_source,
                    trigger: (r as Signal & { story_change_trigger?: string }).story_change_trigger,
                    horizon: (r as Signal & { story_change_horizon?: string }).story_change_horizon,
                    horizonFlips: (r as Signal & { story_change_horizon_flips?: string[] }).story_change_horizon_flips,
                  }}
                />
              </div>
              {horizonLine && (
                <p className="text-[10px] text-slate-500 font-mono" title="Current horizon suggestions for context">
                  Playbooks: {horizonLine}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
