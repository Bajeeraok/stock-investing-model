"use client";

import { useState, useMemo, useEffect } from "react";
import { clsx } from "clsx";
import { RefreshCw } from "lucide-react";
import { paginateRows, TablePager } from "./TablePager";

const FORWARD_PAGE_SIZE = 30;

interface RecordRow {
  as_of_date: string;
  next_date: string;
  ticker: string;
  horizon_days: number;
  our_signal: string;
  actual_return_pct: number;
  forward_status?: "pending" | "complete" | null;
  pending_reason?: string | null;
  data_quality?: string | null;
  gate_cleared?: boolean | null;
  go_no_go?: string | null;
  gates_passed?: number | null;
  gates_total?: number | null;
  gates_frozen?: boolean | null;
  hit_st_target?: number | null;
  hit_st_stop?: number | null;
  trim_net_score_pct?: number | null;
  trim_outcome_label?: string | null;
  max_drawdown_pct?: number | null;
  /** Which gate/band/regime logic version produced this signal — see signals/model_version.py. */
  model_version?: string | null;
}

interface HorizonSummary {
  avg_return_pct?: number;
  n_observations?: number;
  win_rate_pct?: number;
  st_target_hit_rate_pct?: number;
  st_stop_hit_rate_pct?: number;
  trim_avg_net_score_pct?: number;
  trim_helped_pct?: number;
  trim_n?: number;
}

interface SummaryByHorizon {
  [horizon: number]: HorizonSummary;
}

interface SummaryBySignal {
  [signal: string]: {
    avg_return_20d_pct?: number;
    avg_return_pct?: number;
    n_observations?: number;
    hit_rate_pct?: number;
    trim_avg_net_score_pct?: number;
    trim_helped_pct?: number;
    metric_note?: string;
  };
}

interface SummaryByGates {
  [gateKey: string]: HorizonSummary;
}

interface SummaryByGoNoGo {
  [key: string]: { avg_return_20d_pct?: number; n_observations?: number; hit_rate_pct?: number };
}

interface SummaryByModelVersion {
  [version: string]: { avg_return_20d_pct?: number; n_observations?: number; hit_rate_pct?: number };
}

interface ForwardMeta {
  eod_date_first?: string | null;
  eod_date_last?: string | null;
  eod_snapshot_count?: number;
  records_total?: number;
  records_returned?: number;
  as_of_date_min?: string | null;
  as_of_date_max?: string | null;
  newest_completed_as_of?: string | null;
  ticker_count?: number;
  current_model_version?: string | null;
}

interface Props {
  records: RecordRow[];
  summary_by_horizon: SummaryByHorizon;
  summary_by_signal: SummaryBySignal;
  summary_by_go_no_go?: SummaryByGoNoGo;
  summary_by_gates?: SummaryByGates;
  summary_actionable_buy?: HorizonSummary & { label?: string; avg_return_20d_pct?: number };
  summary_by_entry_mode?: Record<string, HorizonSummary & { avg_return_20d_pct?: number; hit_rate_pct?: number }>;
  summary_by_model_version?: SummaryByModelVersion;
  data_source_note?: string | null;
  message?: string | null;
  meta?: ForwardMeta | null;
}

function isTrimSignal(sig: string): boolean {
  const u = (sig || "").toUpperCase();
  return u.includes("TRIM") || u === "SELL" || u === "REDUCE";
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
  const complete = rows.filter(
    (r) => r.forward_status !== "pending" && r.actual_return_pct != null,
  );
  if (!complete.length) return null;
  const returns = complete.map((r) => r.actual_return_pct as number);
  const n = returns.length;
  const avg = returns.reduce((a, b) => a + b, 0) / n;
  const wins = returns.filter((r) => r > 0).length;
  const bySignal: Record<string, { n: number; avg: number }> = {};
  for (const r of complete) {
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
  summary_by_gates,
  summary_actionable_buy,
  summary_by_entry_mode,
  summary_by_model_version,
  data_source_note,
  message,
  meta,
}: Props) {
  const [tickerFilter, setTickerFilter] = useState("");
  const [dateRange, setDateRange] = useState<DateRange>("ALL");
  const [horizonFilter, setHorizonFilter] = useState<number | "">("");
  const [signalFilter, setSignalFilter] = useState("");
  const [gateFilter, setGateFilter] = useState<"" | "4" | "0" | "3plus" | "go">("");
  // Defaults to the current gate/band/regime logic version (not "All") so the headline
  // numbers you see first reflect today's model, not a blend with pre-fix signals —
  // switch to "All versions" to see the blended/legacy history. See signals/model_version.py.
  const [versionFilter, setVersionFilter] = useState(meta?.current_model_version || "");
  const [page, setPage] = useState(0);

  const uniqueTickers = useMemo(
    () => Array.from(new Set((allRecords || []).map((r) => r.ticker))).sort(),
    [allRecords],
  );

  const versionOptions = useMemo(
    () => Array.from(new Set((allRecords || []).map((r) => r.model_version || "legacy"))).sort().reverse(),
    [allRecords],
  );

  const horizonOptions = useMemo(
    () =>
      Array.from(new Set((allRecords || []).map((r) => r.horizon_days)))
        .filter((h) => Number.isFinite(h))
        .sort((a, b) => a - b),
    [allRecords],
  );

  const signalOptions = useMemo(
    () =>
      Array.from(new Set((allRecords || []).map((r) => r.our_signal).filter(Boolean))).sort(),
    [allRecords],
  );

  const records = useMemo(() => {
    const cutoff = cutoffDate(dateRange);
    const tf = tickerFilter.toUpperCase();
    const filtered = (allRecords || []).filter((r) => {
      if (tf && r.ticker !== tf) return false;
      if (cutoff && r.as_of_date < cutoff) return false;
      if (horizonFilter !== "" && r.horizon_days !== horizonFilter) return false;
      if (signalFilter && r.our_signal !== signalFilter) return false;
      if (versionFilter && (r.model_version || "legacy") !== versionFilter) return false;
      if (gateFilter === "4") {
        if ((r.gates_passed ?? 0) < (r.gates_total ?? 4)) return false;
      } else if (gateFilter === "0") {
        if ((r.gates_passed ?? 0) > 0) return false;
      } else if (gateFilter === "3plus") {
        if ((r.gates_passed ?? 0) < 3) return false;
      } else if (gateFilter === "go") {
        if (!r.gate_cleared && r.go_no_go !== "go") return false;
      }
      return true;
    });
    return [...filtered].sort((a, b) => {
      if (a.as_of_date !== b.as_of_date) return b.as_of_date.localeCompare(a.as_of_date);
      if (a.ticker !== b.ticker) return a.ticker.localeCompare(b.ticker);
      return a.horizon_days - b.horizon_days;
    });
  }, [allRecords, tickerFilter, dateRange, horizonFilter, signalFilter, gateFilter, versionFilter]);

  useEffect(() => {
    setPage(0);
  }, [tickerFilter, dateRange, horizonFilter, signalFilter, gateFilter, versionFilter]);

  const pagedRecords = useMemo(
    () => paginateRows(records, page, FORWARD_PAGE_SIZE),
    [records, page],
  );

  const filterStats = useMemo(() => filteredForwardStats(records), [records]);

  if (!allRecords?.length) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4 space-y-2">
        <p className="text-sm font-medium text-slate-400">Forward tracking</p>
        <p className="text-slate-500 text-sm leading-relaxed">
          {message ??
            "No forward-tracking rows yet. Save at least 2 EOD snapshots, then refresh the dashboard."}
        </p>
      </div>
    );
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
        EOD OHLCV between snapshot dates — return % plus ST stop/target touches. Gates frozen on new daily saves.
        {data_source_note && <span className="block mt-1 text-slate-600">{data_source_note}</span>}
        {meta?.eod_date_last && (
          <span className="block mt-1 text-slate-400">
            EOD through <span className="font-mono text-slate-300">{meta.eod_date_last}</span>
            {meta.eod_snapshot_count != null ? ` · ${meta.eod_snapshot_count} snapshots` : ""}
            {meta.newest_completed_as_of ? (
              <>
                {" "}
                · newest completed as-of{" "}
                <span className="font-mono text-slate-300">{meta.newest_completed_as_of}</span>
              </>
            ) : meta.as_of_date_max ? (
              <> · latest as-of <span className="font-mono text-slate-300">{meta.as_of_date_max}</span></>
            ) : null}
            {meta.records_total != null && meta.records_returned != null && meta.records_total > meta.records_returned
              ? ` · API capped at ${meta.records_returned} of ${meta.records_total} rows`
              : ""}
          </span>
        )}
        <span className="block mt-1 text-slate-600">
          As-of dates need a finished forward window (1/5/20/60 EOD steps). Pending = no new trading session
          between snapshots (holiday duplicate). Latest EOD day excluded until the pair completes.
        </span>
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
        <select
          value={signalFilter}
          onChange={(e) => setSignalFilter(e.target.value)}
          className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          <option value="">All signals</option>
          {signalOptions.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={gateFilter}
          onChange={(e) => setGateFilter(e.target.value as "" | "4" | "0" | "3plus" | "go")}
          className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          <option value="">All gates</option>
          <option value="4">4/4 pass</option>
          <option value="0">0/4 pass</option>
          <option value="3plus">3+ pass</option>
          <option value="go">GO only</option>
        </select>
        <select
          value={versionFilter}
          onChange={(e) => setVersionFilter(e.target.value)}
          className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          title="Which gate/band/regime logic version produced the signal — defaults to current so win-rate numbers aren't blended with pre-fix history"
        >
          <option value="">All versions</option>
          {versionOptions.map((v) => (
            <option key={v} value={v}>
              {v === meta?.current_model_version ? `${v} (current)` : v}
            </option>
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
        {(tickerFilter || dateRange !== "ALL" || horizonFilter !== "" || signalFilter !== "" || gateFilter !== "" || versionFilter !== "") && (
          <span className="text-[10px] text-slate-500">
            Showing {records.length} / {allRecords.length} records
          </span>
        )}
      </div>

      {(tickerFilter || dateRange !== "ALL" || horizonFilter !== "" || signalFilter !== "" || gateFilter !== "" || versionFilter !== "") && (
        <div className="mb-3 rounded-lg border border-slate-600/80 bg-slate-900/50 px-3 py-2 text-xs text-slate-300 flex flex-wrap gap-x-4 gap-y-1">
          <span className="text-slate-500 font-medium uppercase tracking-wide">Filtered</span>
          {filterStats ? (
            <>
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
            </>
          ) : versionFilter ? (
            <span className="text-slate-500">
              Not enough resolved outcomes yet under {versionFilter} — horizons need trading days to
              complete after each signal. Switch to "All versions" to see blended/legacy history.
            </span>
          ) : (
            <span className="text-slate-500">No matching records.</span>
          )}
        </div>
      )}

      {meta?.current_model_version && (
        <div className="mb-3 rounded-lg border border-emerald-700/50 bg-emerald-950/20 px-3 py-2 text-xs">
          <p className="text-emerald-400/90 font-medium mb-1">
            Current model ({meta.current_model_version}) · 20d win rate
          </p>
          {(() => {
            const cur = summary_by_model_version?.[meta.current_model_version as string];
            if (!cur || !cur.n_observations) {
              return (
                <p className="text-slate-500">
                  Not enough resolved 20d outcomes yet — this fills in as new EOD snapshots
                  accumulate under the current model. See "All versions" for legacy history.
                </p>
              );
            }
            return (
              <p className="text-slate-300">
                Win rate{" "}
                <span className={(cur.hit_rate_pct ?? 0) >= 50 ? "text-emerald-400" : "text-amber-300"}>
                  {cur.hit_rate_pct != null ? `${cur.hit_rate_pct}%` : "—"}
                </span>
                <span className="text-slate-600"> · n={cur.n_observations}</span>
                <span className="mx-2 text-slate-600">·</span>
                Avg return{" "}
                <span className={(cur.avg_return_20d_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {fmt(cur.avg_return_20d_pct ?? 0)}
                </span>
              </p>
            );
          })()}
        </div>
      )}

      {horizons.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 mb-3">
          {horizons.map((h) => {
            const s = summary_by_horizon[h];
            if (!s) return null;
            return (
              <div
                key={h}
                className="rounded-lg border border-slate-600/80 bg-slate-900/50 px-3 py-2 text-xs"
              >
                <p className="text-slate-400 font-medium mb-1">{h} EOD steps</p>
                <p className="text-slate-500">
                  Win rate{" "}
                  <span
                    className={
                      (s.win_rate_pct ?? 0) >= 50 ? "text-emerald-400" : "text-amber-300"
                    }
                  >
                    {s.win_rate_pct != null ? `${s.win_rate_pct}%` : "—"}
                  </span>
                  <span className="text-slate-600"> · n={s.n_observations}</span>
                </p>
                <p className="mt-0.5">
                  Avg return{" "}
                  <span
                    className={
                      s.avg_return_pct != null && s.avg_return_pct >= 0
                        ? "text-emerald-400"
                        : "text-red-400"
                    }
                  >
                    {fmt(s.avg_return_pct ?? 0)}
                  </span>
                  <span className="text-slate-600 text-[10px]"> (not win %)</span>
                </p>
                {s.win_rate_pct != null && (
                  <p className="text-slate-600 text-[10px] mt-0.5">
                    ST tgt {s.st_target_hit_rate_pct ?? "—"}% · ST stop {s.st_stop_hit_rate_pct ?? "—"}%
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {summary_actionable_buy && (summary_actionable_buy.n_observations ?? 0) > 0 && (
        <div className="mb-3 rounded-lg border border-emerald-500/35 bg-emerald-950/30 px-3 py-2">
          <p className="text-xs text-emerald-300/90 font-medium mb-1">
            Entry slice (20d) — full_go + BUY/HOLD/ADD only
          </p>
          <p className="text-sm text-slate-200">
            Avg return{" "}
            <span
              className={
                (summary_actionable_buy.avg_return_20d_pct ?? summary_actionable_buy.avg_return_pct ?? 0) >= 0
                  ? "text-emerald-400 font-semibold"
                  : "text-red-400 font-semibold"
              }
            >
              {fmt(summary_actionable_buy.avg_return_20d_pct ?? summary_actionable_buy.avg_return_pct ?? 0)}
            </span>
            <span className="text-slate-500 text-xs ml-2">
              win {summary_actionable_buy.win_rate_pct ?? "—"}% · n={summary_actionable_buy.n_observations}
            </span>
          </p>
          <p className="text-[10px] text-slate-500 mt-1">
            Use this row for entry quality — broad HOLD/ADD bucket mixes gate-blocked high scores.
          </p>
        </div>
      )}

      {summary_by_entry_mode && Object.keys(summary_by_entry_mode).length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-slate-500 mb-1">By entry mode (20d forward)</p>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {Object.entries(summary_by_entry_mode).map(([em, s]) => (
              <span key={em} className="text-slate-300">
                <span className="text-slate-400">{em}:</span>{" "}
                {fmt(s.avg_return_20d_pct ?? s.avg_return_pct ?? 0)} win {s.hit_rate_pct ?? s.win_rate_pct ?? "—"}%
                (n={s.n_observations})
              </span>
            ))}
          </div>
        </div>
      )}

      {summary_by_gates && Object.keys(summary_by_gates).length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-slate-500 mb-1">By gates (20d forward)</p>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {Object.entries(summary_by_gates)
              .sort(([a], [b]) => b.localeCompare(a))
              .map(([gk, s]) => (
                <span key={gk} className="text-slate-300">
                  <span className="text-violet-300/90 font-medium">{gk}</span>:{" "}
                  {fmt(s.avg_return_pct ?? 0)} win {s.win_rate_pct ?? "—"}% (n={s.n_observations})
                </span>
              ))}
          </div>
        </div>
      )}

      {summary_by_go_no_go && Object.keys(summary_by_go_no_go).length > 0 && (
        <div className="mb-3 rounded-lg border border-emerald-500/20 bg-emerald-950/20 px-3 py-2">
          <p className="text-xs text-emerald-300/90 font-medium mb-1">
            Model alignment (20d forward) — GO vs NO-GO (not the same as full_go entry)
          </p>
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
          <p className="text-xs text-slate-500 mb-1">
            By signal bucket (20d) — HOLD/ADD requires full_go; high score alone maps to HOLD
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {Object.entries(summary_by_signal).map(([sig, s]) => (
              <span key={sig} title={s.metric_note}>
                <span className="text-slate-400">{sig}:</span>{" "}
                {isTrimSignal(sig) && s.trim_avg_net_score_pct != null ? (
                  <>
                    <span className={s.trim_avg_net_score_pct >= 0 ? "text-emerald-400" : "text-amber-300"}>
                      trim net {s.trim_avg_net_score_pct >= 0 ? "+" : ""}
                      {s.trim_avg_net_score_pct.toFixed(1)}%
                    </span>
                    <span className="text-slate-500 text-xs">
                      {" "}
                      (helped {s.trim_helped_pct ?? "—"}% · raw {fmt(s.avg_return_20d_pct ?? s.avg_return_pct ?? 0)})
                    </span>
                  </>
                ) : (
                  <>
                    <span className={(s.avg_return_20d_pct ?? s.avg_return_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}>
                      {fmt(s.avg_return_20d_pct ?? s.avg_return_pct ?? 0)}
                    </span>
                    <span className="text-slate-500 text-xs">
                      {" "}
                      (win {s.hit_rate_pct ?? "—"}% · n={s.n_observations ?? 0})
                    </span>
                  </>
                )}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="overflow-x-auto [-webkit-overflow-scrolling:touch]">
        <table className="w-full text-sm text-left border-collapse min-w-[720px]">
          <thead>
            <tr className="text-slate-500 border-b border-slate-600">
              <th className="sticky top-0 left-0 z-[30] min-w-[5rem] w-24 py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]">As of</th>
              <th className="sticky top-0 left-24 z-[25] min-w-[4rem] w-16 py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)]">Ticker</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">Hz</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">Signal</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">Gates</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">Return</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">ST tgt</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">ST stop</th>
              <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800/95 backdrop-blur-sm">TRIM net</th>
            </tr>
          </thead>
          <tbody>
            {pagedRecords.map((r, i) => (
              <tr key={`${r.as_of_date}-${r.ticker}-${r.horizon_days}-${i}`} className="group border-b border-slate-700/50 hover:bg-slate-800/30">
                <td className="sticky left-0 z-[10] min-w-[5rem] w-24 py-1.5 pr-2 text-slate-400 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30">{r.as_of_date}</td>
                <td className="sticky left-24 z-[10] min-w-[4rem] w-16 py-1.5 pr-2 font-medium text-slate-300 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30">{r.ticker}</td>
                <td className="py-1.5 pr-2 text-slate-400">{r.horizon_days}d</td>
                <td className="py-1.5 pr-2 text-slate-400">{r.our_signal}</td>
                <td className="py-1.5 pr-2 text-slate-400 text-xs">
                  {r.gates_passed != null && r.gates_total != null ? (
                    <span className={r.go_no_go === "go" || r.gate_cleared ? "text-emerald-400" : "text-amber-300"}>
                      {r.gates_passed}/{r.gates_total}
                      {r.gates_frozen ? "" : " †"}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="py-1.5 pr-2">
                  {r.forward_status === "pending" || r.actual_return_pct == null ? (
                    <span
                      className="text-slate-500 text-xs"
                      title={r.pending_reason ?? "Waiting for next trading session EOD"}
                    >
                      pending
                    </span>
                  ) : (
                    <span className={r.actual_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                      {fmt(r.actual_return_pct)}
                      {r.data_quality === "split_adjusted" && (
                        <span className="text-slate-600 text-[10px] ml-1" title="Pre-split close scaled for corporate action (e.g. 4-for-1)">
                          adj
                        </span>
                      )}
                      {r.data_quality === "reconciled_daily_move" && (
                        <span className="text-slate-600 text-[10px] ml-1" title="Close chain broken — used EOD daily_move_pct">
                          †
                        </span>
                      )}
                    </span>
                  )}
                </td>
                <td className="py-1.5 pr-2 text-xs text-slate-400">
                  {r.hit_st_target === 1 ? "✓" : r.hit_st_target === 0 ? "·" : "—"}
                </td>
                <td className="py-1.5 pr-2 text-xs text-slate-400">
                  {r.hit_st_stop === 1 ? "✓" : r.hit_st_stop === 0 ? "·" : "—"}
                </td>
                <td className="py-1.5 pr-2 text-xs">
                  {r.trim_net_score_pct != null ? (
                    <span className={r.trim_net_score_pct >= 0 ? "text-emerald-400/90" : "text-amber-300/90"}>
                      {r.trim_net_score_pct >= 0 ? "+" : ""}
                      {r.trim_net_score_pct.toFixed(1)}%
                    </span>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-[10px] text-slate-600 mt-1">† gates recomputed from EOD (legacy snapshot). New daily runs freeze gates at save time.</p>
      </div>
      <TablePager page={page} pageSize={FORWARD_PAGE_SIZE} total={records.length} onPageChange={setPage} />
    </div>
  );
}
