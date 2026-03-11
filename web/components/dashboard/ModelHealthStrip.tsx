"use client";

import { Activity } from "lucide-react";

interface SummaryBySignal {
  [signal: string]: { avg_return_20d_pct?: number; n_observations?: number; hit_rate_pct?: number };
}

interface Props {
  summary_by_signal?: SummaryBySignal | null;
  summary_by_horizon?: Record<number, { avg_return_pct: number; n_observations: number }> | null;
  message?: string | null;
}

export function ModelHealthStrip({ summary_by_signal, summary_by_horizon, message }: Props) {
  if (!summary_by_signal || Object.keys(summary_by_signal).length === 0) {
    if (message) {
      return (
        <div className="rounded-lg border border-slate-600 bg-slate-800/30 px-3 py-2 flex items-center gap-2">
          <Activity className="h-4 w-4 text-slate-500 shrink-0" />
          <span className="text-xs text-slate-500">Model health: {message}</span>
        </div>
      );
    }
    return null;
  }

  const parts: string[] = [];
  Object.entries(summary_by_signal).forEach(([sig, data]) => {
    const hr = data?.hit_rate_pct;
    const n = data?.n_observations;
    if (hr != null && n != null) {
      parts.push(`${sig} ${hr.toFixed(0)}% (n=${n})`);
    }
  });
  const horizonCount = summary_by_horizon ? Object.keys(summary_by_horizon).length : 0;

  return (
    <div
      className="rounded-lg border border-slate-600 bg-slate-800/30 px-3 py-2 flex flex-wrap items-center gap-x-4 gap-y-1"
      title="Forward tracking: 20d hit rate by signal (HOLD/ADD vs CONSIDER TRIM). Based on EOD snapshots."
    >
      <Activity className="h-4 w-4 text-emerald-400 shrink-0" />
      <span className="text-xs text-slate-400 font-medium">Model health</span>
      <span className="text-xs text-slate-300">
        {parts.join(" · ")}
        {horizonCount > 0 && ` · ${horizonCount} horizon(s)`}
      </span>
    </div>
  );
}
