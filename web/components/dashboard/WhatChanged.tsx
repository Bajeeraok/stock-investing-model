"use client";

import type { WhatChanged as WhatChangedType } from "@/app/page";
import { RefreshCw } from "lucide-react";

export function WhatChanged({ items, onTickerClick }: { items: WhatChangedType[]; onTickerClick?: (ticker: string) => void }) {
  return (
    <div className="rounded-xl border border-slate-700 overflow-hidden">
      <div className="divide-y divide-slate-700">
        {items.map((w) => (
          <div
            key={w.ticker}
            className="flex flex-col gap-2 px-4 py-3 hover:bg-slate-800/30"
          >
            <div className="flex items-start gap-4">
              {onTickerClick ? (
                <button type="button" onClick={() => onTickerClick(w.ticker)} className="font-mono font-medium text-emerald-400 hover:underline cursor-pointer shrink-0">
                  {w.ticker}
                </button>
              ) : (
                <span className="font-mono font-medium text-emerald-400 shrink-0">{w.ticker}</span>
              )}
              {w.summary && (
                <p className="text-sm text-slate-300 flex-1">{w.summary}</p>
              )}
            </div>
            {w.changes.length > 0 && (
              <div className="flex flex-wrap gap-2 pl-0">
                {w.changes.map((c, i) => (
                  <span
                    key={i}
                    className="px-2 py-1 rounded text-xs bg-slate-800 text-slate-400"
                  >
                    {c}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
