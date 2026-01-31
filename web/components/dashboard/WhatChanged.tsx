"use client";

import type { WhatChanged as WhatChangedType } from "@/app/page";
import { RefreshCw } from "lucide-react";

export function WhatChanged({ items }: { items: WhatChangedType[] }) {
  return (
    <div className="rounded-xl border border-slate-700 overflow-hidden">
      <div className="divide-y divide-slate-700">
        {items.map((w) => (
          <div
            key={w.ticker}
            className="flex items-start gap-4 px-4 py-3 hover:bg-slate-800/30"
          >
            <span className="font-mono font-medium text-emerald-400 shrink-0">{w.ticker}</span>
            <div className="flex flex-wrap gap-2">
              {w.changes.map((c, i) => (
                <span
                  key={i}
                  className="px-2 py-1 rounded text-sm bg-slate-800 text-slate-300"
                >
                  {c}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
