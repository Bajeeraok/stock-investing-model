"use client";

import type { ThesisCheck as ThesisCheckType } from "@/app/page";
import { FileText, RefreshCw } from "lucide-react";

export function ThesisCheck({ items, onTickerClick }: { items: ThesisCheckType[]; onTickerClick?: (ticker: string) => void }) {
  const sorted = [...items].sort((a, b) => {
    if (a.nudge && !b.nudge) return -1;
    if (!a.nudge && b.nudge) return 1;
    return a.ticker.localeCompare(b.ticker);
  });
  const hasResurface = sorted.some((t) => t.nudge);

  return (
    <div className="space-y-4">
      {hasResurface && (
        <p className="text-xs text-slate-400 border border-slate-700 rounded-lg px-3 py-2 bg-slate-900/80 flex items-start gap-2">
          <RefreshCw className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" aria-hidden />
          <span>
            When regime or score moves vs your last saved run, we surface your stored thesis and exit rule so you can re-check whether the setup still matches.
          </span>
        </p>
      )}
      {sorted.map((t) => (
        <div
          key={t.ticker}
          className={`rounded-xl border p-4 ${
            t.nudge ? "border-amber-500/40 bg-amber-500/5" : "border-slate-700 bg-slate-900/50"
          }`}
        >
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div className="flex items-center gap-2 mb-1">
              {onTickerClick ? (
                <button type="button" onClick={() => onTickerClick(t.ticker)} className="font-mono font-medium text-emerald-400 hover:underline cursor-pointer">
                  {t.ticker}
                </button>
              ) : (
                <span className="font-mono font-medium text-emerald-400">{t.ticker}</span>
              )}
              <FileText className="h-4 w-4 text-slate-500" />
            </div>
            {t.nudge && (
              <p className="text-sm text-amber-200/95 leading-snug sm:max-w-[65%] sm:text-right">
                {t.nudge}
              </p>
            )}
          </div>
          <p className="text-slate-300 text-sm mb-1 mt-2">
            <span className="text-slate-500">Why:</span> {t.thesis || "—"}
          </p>
          <p className="text-slate-400 text-sm">
            <span className="text-slate-500">Exit if:</span> {t.exit_condition || "—"}
          </p>
        </div>
      ))}
    </div>
  );
}
