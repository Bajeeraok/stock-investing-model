"use client";

import { RefreshCw } from "lucide-react";

interface RecordRow {
  as_of_date: string;
  next_date: string;
  ticker: string;
  horizon_days: number;
  our_signal: string;
  actual_return_pct: number;
}

interface SummaryByHorizon {
  [horizon: number]: { avg_return_pct: number; n_observations: number };
}

interface SummaryBySignal {
  [signal: string]: { avg_return_20d_pct: number; n_observations: number };
}

interface Props {
  records: RecordRow[];
  summary_by_horizon: SummaryByHorizon;
  summary_by_signal: SummaryBySignal;
  message?: string | null;
}

function fmt(pct: number): string {
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

export function ForwardTracking({
  records,
  summary_by_horizon,
  summary_by_signal,
  message,
}: Props) {
  if (!records?.length && message) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4">
        <p className="text-sm font-medium text-slate-400 mb-1">Forward tracking</p>
        <p className="text-slate-500 text-sm">{message}</p>
      </div>
    );
  }

  if (!records?.length) {
    return null;
  }

  const horizons = Object.keys(summary_by_horizon || {})
    .map(Number)
    .sort((a, b) => a - b);

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4">
      <div className="flex items-center gap-2 mb-3">
        <RefreshCw className="h-4 w-4 text-emerald-400 shrink-0" />
        <p className="text-sm font-medium text-slate-300">Forward tracking (what we said vs what happened)</p>
      </div>
      <p className="text-xs text-slate-500 mb-3" title="Multi-horizon actual returns for SPY/QQQ based on EOD snapshots. Signal accuracy: when we said CONSIDER TRIM vs HOLD/ADD, avg 20d return.">
        Uses EOD snapshots. Avg return by horizon and by signal (score-based).
      </p>

      {horizons.length > 0 && (
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-300 mb-3">
          {horizons.map((h) => {
            const s = summary_by_horizon[h];
            if (!s) return null;
            return (
              <span key={h}>
                <span className="text-slate-500">{h}d:</span>{" "}
                <span className={s.avg_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {fmt(s.avg_return_pct)}
                </span>
                <span className="text-slate-500 text-xs"> (n={s.n_observations})</span>
              </span>
            );
          })}
        </div>
      )}

      {summary_by_signal && Object.keys(summary_by_signal).length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-slate-500 mb-1">Signal accuracy (20d forward)</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {Object.entries(summary_by_signal).map(([sig, s]) => (
              <span key={sig}>
                <span className="text-slate-400">{sig}:</span>{" "}
                <span className={s.avg_return_20d_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {fmt(s.avg_return_20d_pct)}
                </span>
                <span className="text-slate-500 text-xs"> (n={s.n_observations})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="overflow-auto [-webkit-overflow-scrolling:touch] max-h-[min(50vh,400px)]">
        <table className="w-full text-sm text-left border-collapse min-w-[400px]">
          <thead>
            <tr className="text-slate-500 border-b border-slate-600">
              <th className="sticky top-0 left-0 z-[30] min-w-[5rem] w-24 py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]">As of</th>
              <th className="sticky top-0 left-24 z-[25] min-w-[4rem] w-16 py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)]">Ticker</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">Horizon</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">Signal</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">Actual %</th>
            </tr>
          </thead>
          <tbody>
            {records.slice(0, 30).map((r, i) => (
              <tr key={`${r.as_of_date}-${r.ticker}-${r.horizon_days}-${i}`} className="group border-b border-slate-700/50 hover:bg-slate-800/30">
                <td className="sticky left-0 z-[10] min-w-[5rem] w-24 py-1.5 pr-2 text-slate-400 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30">{r.as_of_date}</td>
                <td className="sticky left-24 z-[10] min-w-[4rem] w-16 py-1.5 pr-2 font-medium text-slate-300 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30">{r.ticker}</td>
                <td className="py-1.5 pr-2 text-slate-400">{r.horizon_days}d</td>
                <td className="py-1.5 pr-2 text-slate-400">{r.our_signal}</td>
                <td className={r.actual_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}>{fmt(r.actual_return_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
