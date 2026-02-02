"use client";

import type { ThesisCheck as ThesisCheckType } from "@/app/page";
import { FileText } from "lucide-react";

export function ThesisCheck({ items, onTickerClick }: { items: ThesisCheckType[]; onTickerClick?: (ticker: string) => void }) {
  return (
    <div className="space-y-4">
      {items.map((t) => (
        <div
          key={t.ticker}
          className="rounded-xl border border-slate-700 bg-slate-900/50 p-4"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2 mb-2">
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
              <span className="px-2 py-1 rounded text-sm bg-amber-500/20 text-amber-400 font-medium">
                {t.nudge}
              </span>
            )}
          </div>
          <p className="text-slate-300 text-sm mb-1">
            <span className="text-slate-500">Why:</span> {t.thesis}
          </p>
          <p className="text-slate-400 text-sm">
            <span className="text-slate-500">Exit if:</span> {t.exit_condition}
          </p>
        </div>
      ))}
    </div>
  );
}
