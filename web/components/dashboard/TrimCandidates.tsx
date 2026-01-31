"use client";

import type { PortfolioHolding } from "@/app/page";
import { AlertTriangle } from "lucide-react";

export function TrimCandidates({ items }: { items: PortfolioHolding[] }) {
  const sorted = [...items].sort((a, b) => (a.score ?? 0) - (b.score ?? 0));
  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {sorted.map((h) => (
          <div
            key={h.ticker}
            className="flex items-center justify-between p-3 rounded-lg bg-slate-900/80 border border-amber-500/20"
          >
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-400" />
              <span className="font-mono font-medium">{h.ticker}</span>
            </div>
            <div className="text-right text-sm">
              <p className="text-amber-400">score {h.score?.toFixed(1)}</p>
              <p className="text-slate-400">{h.regime} • {h.suggestion}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
