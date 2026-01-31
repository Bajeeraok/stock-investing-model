"use client";

import { AlertTriangle } from "lucide-react";
import type { Signal } from "@/app/page";

export function StoryAlerts({ items }: { items: Signal[] }) {
  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="h-5 w-5 text-amber-400" />
        <h2 className="font-semibold text-amber-400">Story Change Alerts</h2>
      </div>
      <div className="space-y-2">
        {items.map((r) => (
          <div
            key={r.ticker}
            className="flex items-center justify-between py-2 px-3 rounded-lg bg-slate-900/80"
          >
            <span className="font-mono font-medium text-slate-200">{r.ticker}</span>
            <span className="text-amber-300 text-sm">{r.story_change}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
