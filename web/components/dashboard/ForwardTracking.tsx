"use client";

import { useState, useMemo } from "react";
import { clsx } from "clsx";
import { RefreshCw } from "lucide-react";

interface RecordRow {
  as_of_date: string;
  next_date: string;
  ticker: string;
  horizon_days: number;
  our_signal: string;
  actual_return_pct: number;
  gate_cleared?: boolean | null;
  go_no_go?: string | null;
  gates_passed?: number | null;
  gates_total?: number | null;
}

interface SummaryByHorizon {
  [horizon: number]: { avg_return_pct: number; n_observations: number };
}

interface SummaryBySignal {
  [signal: string]: { avg_return_20d_pct?: number; n_observations?: number; hit_rate_pct?: number };
}

interface SummaryByGoNoGo {
  [key: string]: { avg_return_20d_pct?: number; n_observations?: number; hit_rate_pct?: number };
}

interface ForwardMeta {
  eod_date_first?: string | null;
  eod_date_last?: string | null;
  eod_snapshot_count?: number;
  records_total?: number;
  records_returned?: number;
  as_of_date_min?: string | null;
  as_of_date_max?: string | null;
  ticker_count?: number;
}

interface Props {
  records: RecordRow[];
  summary_by_horizon: SummaryByHorizon;
  summary_by_signal: SummaryBySignal;
  summary_by_go_no_go?: SummaryByGoNoGo;
  message?: string | null;
  meta?: ForwardMeta | null;
}

function fmt(pct: number): string {
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

type DateRange = "1W" | "1M" | "3M" | "ALL";
const DATE_RANGES: { label: string; value: DateRange }[] = [
  { label: "1 W", value: "1W" },
  { label: "1 M", value: "1M" },
  { label: "3 M", value: "3M" },
  { label: "All", value: "ALL" },
];

function cutoffDate(range: DateRange): string | null {
  if (range === "ALL") return null;
  const d = new Date();
  if (range === "1W") d.setDate(d.getDate() - 7);
  else if (range === "1M") d.setMonth(d.getMonth() - 1);
  else if (range === "3M") d.setMonth(d.getMonth() - 3);
  return d.toISOString().slice(0, 10);
}

function filteredForwardStats(rows: RecordRow[]) {
  if (!rows.length) return null;
  const returns = rows.map((r) => r.actual_return_pct);
  const n = returns.length;
  const avg = returns.reduce((a, b) => a + b, 0) / n;
  const wins = returns.filter((r) => r > 0).length;
  const bySignal: Record<string, { n: number; avg: number }> = {};
  for (const r of rows) {
    const sig = r.our_signal || "N/A";
    if (!bySignal[sig]) bySignal[sig] = { n: 0, avg: 0 };
    bySignal[sig].n += 1;
    bySignal[sig].avg += r.actual_return_pct;
  }
  for (const sig of Object.keys(bySignal)) {
    bySignal[sig].avg /= bySignal[sig].n;
  }
  return { n, avg, winRate: (100 * wins) / n, bySignal };
}

export function ForwardTracking({
  records: allRecords,
  summary_by_horizon,
  summary_by_signal,
  summary_by_go_no_go,
  message,
  meta,
}: Props) {
  const [tickerFilter, setTickerFilter] = useState("");
  const [dateRange, setDateRange] = useState<DateRange>("ALL");
  const [horizonFilter, setHorizonFilter] = useState<number | "">("");

  const uniqueTickers = useMemo(
    () => Array.from(new Set((allRecords || []).map((r) => r.ticker))).sort(),
    [allRecords],
  );

  const horizonOptions = useMemo(
    () =>
      Array.from(new Set((allRecords || []).map((r) => r.horizon_days)))
        .filter((h) => Number.isFinite(h))
        .sort((a, b) => a - b),
    [allRecords],
  );

  const records = useMemo(() => {
    const cutoff = cutoffDate(dateRange);
    const tf = tickerFilter.toUpperCase();
    const filtered = (allRecords || []).filter((r) => {
      if (tf && r.ticker !== tf) return false;
      if (cutoff && r.as_of_date < cutoff) return false;
      if (horizonFilter !== "" && r.horizon_days !== horizonFilter) return false;
      return true;
    });
    return [...filtered].sort((a, b) => {
      if (a.as_of_date !== b.as_of_date) return b.as_of_date.localeCompare(a.as_of_date);
      if (a.ticker !== b.ticker) return a.ticker.localeCompare(b.ticker);
      return a.horizon_days - b.horizon_days;
    });
  }, [allRecords, tickerFilter, dateRange, horizonFilter]);

  const filterStats = useMemo(() => filteredForwardStats(records), [records]);

  if (!allRecords?.length && message) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4">
        <p className="text-sm font-medium text-slate-400 mb-1">Forward tracking</p>
        <p className="text-slate-500 text-sm">{message}</p>
      </div>
    );
  }

  if (!allRecords?.length) {
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
      <p className="text-xs text-slate-500 mb-3" title="Multi-horizon actual returns for all portfolio/watchlist tickers based on EOD snapshots. Signal accuracy: when we said CONSIDER TRIM vs HOLD/ADD, avg 20d return.">
        Uses EOD snapshots (Redis + disk). Avg return by horizon and by signal (score-based).
        {meta?.eod_date_last && (
          <span className="block mt-1 text-slate-400">
            EOD through <span className="font-mono text-slate-300">{meta.eod_date_last}</span>
            {meta.eod_snapshot_count != null ? ` · ${meta.eod_snapshot_count} snapshots` : ""}
            {meta.as_of_date_max ? ` · latest as-of ${meta.as_of_date_max}` : ""}
            {meta.records_total != null && meta.records_returned != null && meta.records_total > meta.records_returned
              ? ` · showing ${meta.records_returned} most recent of ${meta.records_total}`
              : ""}
          </span>
        )}
      </p>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <select
          value={tickerFilter}
          onChange={(e) => setTickerFilter(e.target.value)}
          className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          <option value="">All tickers ({uniqueTickers.length})</option>
          {uniqueTickers.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select
          value={horizonFilter === "" ? "" : String(horizonFilter)}
          onChange={(e) => setHorizonFilter(e.target.value === "" ? "" : Number(e.target.value))}
          className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          <option value="">All horizons</option>
          {horizonOptions.map((h) => (
            <option key={h} value={h}>{h}d steps</option>
          ))}
        </select>
        <div className="flex rounded border border-slate-600 overflow-hidden">
          {DATE_RANGES.map((dr) => (
            <button
              key={dr.value}
              type="button"
              onClick={() => setDateRange(dr.value)}
              className={clsx(
                "px-2.5 py-1 text-xs font-medium transition-colors",
                dateRange === dr.value
                  ? "bg-emerald-600/70 text-white"
                  : "bg-slate-900 text-slate-400 hover:bg-slate-800",
              )}
            >
              {dr.label}
            </button>
          ))}
        </div>
        {(tickerFilter || dateRange !== "ALL" || horizonFilter !== "") && (
          <span className="text-[10px] text-slate-500">
            Showing {records.length} / {allRecords.length} records
          </span>
        )}
      </div>

      {filterStats && (tickerFilter || dateRange !== "ALL" || horizonFilter !== "") && (
        <div className="mb-3 rounded-lg border border-slate-600/80 bg-slate-900/50 px-3 py-2 text-xs text-slate-300 flex flex-wrap gap-x-4 gap-y-1">
          <span className="text-slate-500 font-medium uppercase tracking-wide">Filtered</span>
          <span>n={filterStats.n}</span>
          <span>
            Win rate{" "}
            <span className={filterStats.winRate >= 50 ? "text-emerald-400" : "text-amber-300"}>
              {filterStats.winRate.toFixed(1)}%
            </span>
          </span>
          <span>
            Avg return{" "}
            <span className={filterStats.avg >= 0 ? "text-emerald-400" : "text-red-400"}>
              {fmt(filterStats.avg)}
            </span>
          </span>
          {Object.entries(filterStats.bySignal).slice(0, 4).map(([sig, s]) => (
            <span key={sig} className="text-slate-400">
              {sig}: {fmt(s.avg)} <span className="text-slate-600">(n={s.n})</span>
            </span>
          ))}
        </div>
      )}

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

      {summary_by_go_no_go && Object.keys(summary_by_go_no_go).length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-slate-500 mb-1">By gate status (20d forward, gates enriched from EOD)</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {Object.entries(summary_by_go_no_go).map(([go, s]) => (
              <span key={go}>
                <span className="text-slate-400">{go.toUpperCase()}:</span>{" "}
                <span className={(s.avg_return_20d_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {fmt(s.avg_return_20d_pct ?? 0)}
                </span>
                <span className="text-slate-500 text-xs"> (n={s.n_observations ?? 0})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {summary_by_signal && Object.keys(summary_by_signal).length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-slate-500 mb-1">Signal accuracy (20d forward)</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {Object.entries(summary_by_signal).map(([sig, s]) => (
              <span key={sig}>
                <span className="text-slate-400">{sig}:</span>{" "}
                <span className={(s.avg_return_20d_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {fmt(s.avg_return_20d_pct ?? 0)}
                </span>
                <span className="text-slate-500 text-xs"> (n={s.n_observations ?? 0})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="overflow-x-auto [-webkit-overflow-scrolling:touch]">
        <table className="w-full text-sm text-left border-collapse min-w-[400px]">
          <thead>
            <tr className="text-slate-500 border-b border-slate-600">
              <th className="sticky top-0 left-0 z-[30] min-w-[5rem] w-24 py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]">As of</th>
              <th className="sticky top-0 left-24 z-[25] min-w-[4rem] w-16 py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)]">Ticker</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">Horizon</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">Signal</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">Gates</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">Actual %</th>
            </tr>
          </thead>
          <tbody>
            {records.slice(0, 50).map((r, i) => (
              <tr key={`${r.as_of_date}-${r.ticker}-${r.horizon_days}-${i}`} className="group border-b border-slate-700/50 hover:bg-slate-800/30">
                <td className="sticky left-0 z-[10] min-w-[5rem] w-24 py-1.5 pr-2 text-slate-400 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30">{r.as_of_date}</td>
                <td className="sticky left-24 z-[10] min-w-[4rem] w-16 py-1.5 pr-2 font-medium text-slate-300 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30">{r.ticker}</td>
                <td className="py-1.5 pr-2 text-slate-400">{r.horizon_days}d</td>
                <td className="py-1.5 pr-2 text-slate-400">{r.our_signal}</td>
                <td className="py-1.5 pr-2 text-slate-400 text-xs">
                  {r.gates_passed != null && r.gates_total != null ? (
                    <span className={r.go_no_go === "go" || r.gate_cleared ? "text-emerald-400" : "text-amber-300"}>
                      {r.gates_passed}/{r.gates_total}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className={r.actual_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}>{fmt(r.actual_return_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
