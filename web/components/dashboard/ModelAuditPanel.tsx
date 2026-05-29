"use client";

import { useMemo, useState, useEffect } from "react";
import { clsx } from "clsx";
import { ClipboardCheck } from "lucide-react";
import { paginateRows, TablePager } from "./TablePager";

const AUDIT_PAGE_SIZE = 25;
export type ModelAuditBreakdownRow = {
  bucket: string | number | null;
  n: number;
  avg_score?: number | null;
  go_pct?: number;
};

export type ModelAuditRecord = {
  id?: number;
  signal_date: string;
  signal_ts?: string;
  ticker: string;
  market_cap_bucket?: string | null;
  retail_verdict?: string | null;
  ml_signal?: string | null;
  go_no_go?: string | null;
  gates_passed?: number | null;
  gates_total?: number | null;
  price_at_signal?: number | null;
  st_target?: number | null;
  stop_swing?: number | null;
  composite_score?: number | null;
  rsi?: number | null;
  regime_label?: string | null;
  ml_short_prob?: number | null;
  confidence_low?: number | null;
  confidence_high?: number | null;
  run_source?: string | null;
  return_7d_pct?: number | null;
  return_30d_pct?: number | null;
  verdict?: string | null;
  verdict_rule?: string | null;
  hit_st_target?: number | null;
  hit_stop_swing?: number | null;
  max_gain_pct?: number | null;
  max_drawdown_pct?: number | null;
  benchmark_return_30d_pct?: number | null;
  track?: string | null;
  velocity_triggered?: number | boolean | null;
  velocity_score?: number | null;
  rvol?: number | null;
  bb_pct_b?: number | null;
  readiness_tier?: string | null;
  readiness_score?: number | null;
};

export type ModelAuditOutcomeSummary = {
  events_total?: number;
  resolved_n?: number;
  pending_n?: number;
  win_rate_pct?: number | null;
  wins?: number;
  losses?: number;
  neutral?: number;
  by_verdict?: { bucket: string; n: number; avg_return_7d_pct?: number | null; avg_return_30d_pct?: number | null }[];
  by_go_no_go?: { bucket: string; n: number; win_rate_pct?: number | null }[];
  by_ml_signal?: { bucket: string; n: number; win_rate_pct?: number | null }[];
};

export type ModelAuditPayload = {
  enabled?: boolean;
  cohort_tag?: string;
  cohort_size?: number;
  pilot_target_days?: number;
  pilot_progress_days?: number;
  pilot?: {
    total_events?: number;
    distinct_days?: number;
    first_date?: string | null;
    last_date?: string | null;
    db_path?: string;
    expected_tickers_per_day?: number;
  };
  category_sizes?: Record<string, number>;
  last_session?: {
    date?: string | null;
    captured?: number;
    expected?: number;
    missing_count?: number;
    missing_tickers?: string[];
  };
  daily_captures?: { date: string; count: number }[];
  breakdown_by_gates?: ModelAuditBreakdownRow[];
  breakdown_by_go_no_go?: ModelAuditBreakdownRow[];
  breakdown_by_category?: ModelAuditBreakdownRow[];
  breakdown_by_signal?: ModelAuditBreakdownRow[];
  breakdown_by_regime?: ModelAuditBreakdownRow[];
  breakdown_by_track?: ModelAuditBreakdownRow[];
  breakdown_by_readiness?: ModelAuditBreakdownRow[];
  batch_queues?: {
    signal_date?: string | null;
    accumulate_count?: number;
    tactical_count?: number;
    accumulate_tickers?: string[];
    tactical_tickers?: string[];
    tactical_preview?: ModelAuditRecord[];
    accumulate_preview?: ModelAuditRecord[];
  } | null;
  recent_records?: ModelAuditRecord[];
  outcomes_available?: boolean;
  outcome_summary?: ModelAuditOutcomeSummary | null;
  outcomes_note?: string | null;
  message?: string | null;
  methodology?: string | null;
  export_url?: string | null;
  report_url?: string | null;
};

type DateRange = "1W" | "1M" | "ALL";
type TrackFilter = "all" | "accumulate" | "velocity";
const DATE_RANGES: { label: string; value: DateRange }[] = [
  { label: "1 W", value: "1W" },
  { label: "1 M", value: "1M" },
  { label: "All", value: "ALL" },
];

function cutoffDate(range: DateRange): string | null {
  if (range === "ALL") return null;
  const d = new Date();
  if (range === "1W") d.setDate(d.getDate() - 7);
  else if (range === "1M") d.setMonth(d.getMonth() - 1);
  return d.toISOString().slice(0, 10);
}

function fmtBucket(b: string | number | null | undefined): string {
  if (b == null || b === "") return "—";
  return String(b);
}

function BreakdownTable({
  title,
  rows,
  bucketLabel,
}: {
  title: string;
  rows: ModelAuditBreakdownRow[];
  bucketLabel: string;
}) {
  if (!rows?.length) return null;
  return (
    <div className="rounded-lg border border-slate-600/70 bg-slate-900/40 overflow-hidden">
      <p className="text-[10px] uppercase tracking-wider text-slate-500 px-3 py-2 border-b border-slate-700/60">{title}</p>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500 border-b border-slate-700/50">
            <th className="text-left py-1.5 px-3 font-medium">{bucketLabel}</th>
            <th className="text-right py-1.5 px-2 font-medium">n</th>
            <th className="text-right py-1.5 px-2 font-medium">GO %</th>
            <th className="text-right py-1.5 px-3 font-medium">Avg score</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 12).map((r, i) => (
            <tr key={`${title}-${i}`} className="border-b border-slate-800/60 text-slate-300">
              <td className="py-1 px-3">{fmtBucket(r.bucket)}</td>
              <td className="py-1 px-2 text-right tabular-nums">{r.n}</td>
              <td className="py-1 px-2 text-right tabular-nums text-slate-400">{r.go_pct ?? "—"}</td>
              <td className="py-1 px-3 text-right tabular-nums">{r.avg_score ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ModelAuditPanel({ audit }: { audit: ModelAuditPayload | null | undefined }) {
  const [tickerFilter, setTickerFilter] = useState("");
  const [dateRange, setDateRange] = useState<DateRange>("ALL");
  const [gatesFilter, setGatesFilter] = useState<string>("");
  const [trackFilter, setTrackFilter] = useState<TrackFilter>("all");
  const [page, setPage] = useState(0);

  const records = audit?.enabled ? audit.recent_records ?? [] : [];
  const uniqueTickers = useMemo(
    () => Array.from(new Set(records.map((r) => r.ticker))).sort(),
    [records],
  );

  const filtered = useMemo(() => {
    const cutoff = cutoffDate(dateRange);
    const gf = gatesFilter;
    const trk = trackFilter;
    return records.filter((r) => {
      if (tickerFilter && r.ticker !== tickerFilter) return false;
      if (cutoff && r.signal_date < cutoff) return false;
      if (gf !== "" && String(r.gates_passed ?? "") !== gf) return false;
      const track = (r.track || "accumulate").toLowerCase();
      if (trk === "accumulate" && track === "velocity") return false;
      if (trk === "velocity" && track !== "velocity") return false;
      return true;
    });
  }, [records, tickerFilter, dateRange, gatesFilter, trackFilter]);

  const gateOptions = useMemo(() => {
    const set = new Set(records.map((r) => r.gates_passed).filter((g) => g != null));
    return Array.from(set).sort((a, b) => Number(a) - Number(b));
  }, [records]);

  useEffect(() => {
    setPage(0);
  }, [tickerFilter, dateRange, gatesFilter, trackFilter]);

  const pagedRows = useMemo(
    () => paginateRows(filtered, page, AUDIT_PAGE_SIZE),
    [filtered, page],
  );

  if (!audit?.enabled) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4">
        <p className="text-sm text-slate-400">{audit?.message ?? "Model audit not enabled."}</p>
      </div>
    );
  }

  const targetDays = audit.pilot_target_days ?? 30;
  const progressDays = audit.pilot_progress_days ?? audit.pilot?.distinct_days ?? 0;
  const progressPct = Math.min(100, Math.round((100 * progressDays) / Math.max(1, targetDays)));
  return (
    <div className="rounded-lg border border-violet-500/30 bg-gradient-to-b from-violet-950/20 to-slate-800/30 p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-200 flex items-center gap-2 flex-wrap">
            <ClipboardCheck className="h-4 w-4 text-violet-400 shrink-0" />
            <span>
              Model audit — {audit.cohort_tag ?? "cohort"}{" "}
              <span className="text-violet-300">({audit.cohort_size ?? "—"} tickers)</span>
            </span>
          </p>          <p className="text-xs text-slate-500 mt-1 max-w-2xl leading-relaxed">
            {audit.methodology ??
              "Fixed cohort captured once per EOD run. Gates and levels frozen at signal time in signal_audit.db."}
          </p>
        </div>
        {audit.pilot?.last_date && (
          <div className="text-xs text-slate-500 text-right">
            Last capture <span className="font-mono text-slate-300">{audit.pilot.last_date}</span>
            <br />
            {audit.pilot.total_events ?? 0} total rows
          </div>
        )}
        {audit.export_url && (
          <a
            href={audit.export_url}
            className="text-xs font-medium text-violet-300 hover:text-violet-200 border border-violet-500/40 rounded px-2.5 py-1.5"
            download
          >
            Export CSV
          </a>
        )}
      </div>

      {/* Pilot progress */}
      <div className="rounded-lg border border-violet-500/25 bg-slate-900/50 px-3 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs mb-2">
          <span className="text-violet-200/90 font-semibold uppercase tracking-wide">30-day pilot progress</span>
          <span className="text-slate-400 tabular-nums">
            Day {progressDays} of {targetDays}
            {audit.pilot?.first_date ? ` · since ${audit.pilot.first_date}` : ""}
          </span>
        </div>
        <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-violet-600 to-emerald-500 transition-all"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        {audit.last_session && (
          <p className="text-[11px] text-slate-500 mt-2">
            Last session:{" "}
            <span className="text-slate-300 tabular-nums">
              {audit.last_session.captured}/{audit.last_session.expected}
            </span>{" "}
            tickers
            {(audit.last_session.missing_count ?? 0) > 0 && (
              <span className="text-amber-400/90">
                {" "}
                · {audit.last_session.missing_count} missing
                {audit.last_session.missing_tickers?.length
                  ? ` (e.g. ${audit.last_session.missing_tickers.slice(0, 5).join(", ")})`
                  : ""}
              </span>
            )}
          </p>
        )}
      </div>

      {(audit.daily_captures?.length ?? 0) > 0 && (
        <div className="rounded-lg border border-slate-600/70 bg-slate-900/40 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Daily cohort captures</p>
          <div className="flex flex-wrap gap-1.5">
            {audit.daily_captures!.slice(0, 10).map((d) => (
              <span
                key={d.date}
                className="inline-flex items-center gap-1 rounded bg-slate-800/80 px-2 py-0.5 text-[11px] text-slate-300 tabular-nums"
              >
                <span className="font-mono text-slate-400">{d.date.slice(5)}</span>
                <span className="text-violet-300">{d.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {audit.message && (        <p className="text-xs text-amber-200/90 rounded-lg border border-amber-500/30 bg-amber-950/30 px-3 py-2">{audit.message}</p>
      )}

      {audit.batch_queues && (
        <div className="rounded-lg border border-slate-600/70 bg-slate-900/40 px-3 py-2.5 space-y-2">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">
            Batch split
            {audit.batch_queues.signal_date ? ` · ${audit.batch_queues.signal_date}` : ""}
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setTrackFilter("accumulate")}
              className={clsx(
                "rounded border px-2.5 py-1 text-[11px] font-medium touch-manipulation",
                trackFilter === "accumulate"
                  ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-200"
                  : "border-slate-600 text-slate-400 hover:border-slate-500",
              )}
            >
              Watch / accumulate{" "}
              <span className="tabular-nums">{audit.batch_queues.accumulate_count ?? 0}</span>
            </button>
            <button
              type="button"
              onClick={() => setTrackFilter("velocity")}
              className={clsx(
                "rounded border px-2.5 py-1 text-[11px] font-medium touch-manipulation",
                trackFilter === "velocity"
                  ? "border-violet-500/40 bg-violet-500/15 text-violet-200"
                  : "border-slate-600 text-slate-400 hover:border-slate-500",
              )}
            >
              Tactical breakout{" "}
              <span className="tabular-nums">{audit.batch_queues.tactical_count ?? 0}</span>
            </button>
            <button
              type="button"
              onClick={() => setTrackFilter("all")}
              className={clsx(
                "rounded border px-2.5 py-1 text-[11px] touch-manipulation",
                trackFilter === "all"
                  ? "border-slate-500 bg-slate-800 text-slate-200"
                  : "border-slate-700 text-slate-500 hover:border-slate-600",
              )}
            >
              All tracks
            </button>
          </div>
          {(audit.batch_queues.tactical_tickers?.length ?? 0) > 0 && (
            <p className="text-[11px] text-violet-300/80 leading-snug">
              Velocity: {audit.batch_queues.tactical_tickers!.slice(0, 12).join(", ")}
              {(audit.batch_queues.tactical_tickers!.length ?? 0) > 12 ? "…" : ""}
            </p>
          )}
        </div>
      )}

      {audit.outcomes_note && !audit.outcomes_available && (
        <p className="text-xs text-slate-500 border-l-2 border-slate-600 pl-2">{audit.outcomes_note}</p>
      )}

      {audit.outcome_summary && (audit.outcome_summary.resolved_n ?? 0) > 0 && (
        <div className="rounded-lg border border-emerald-500/25 bg-emerald-950/20 px-3 py-2.5 space-y-2">
          <p className="text-xs font-semibold text-emerald-200/90 uppercase tracking-wide">Outcome track record</p>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-300">
            <span>
              Resolved:{" "}
              <strong className="text-slate-100 tabular-nums">
                {audit.outcome_summary.resolved_n}/{audit.outcome_summary.events_total}
              </strong>
            </span>
            {audit.outcome_summary.win_rate_pct != null && (
              <span>
                Win rate:{" "}
                <strong
                  className={
                    audit.outcome_summary.win_rate_pct >= 55 ? "text-emerald-400" : "text-amber-300"
                  }
                >
                  {audit.outcome_summary.win_rate_pct.toFixed(1)}%
                </strong>
                <span className="text-slate-500">
                  {" "}
                  (W {audit.outcome_summary.wins ?? 0} · L {audit.outcome_summary.losses ?? 0} · N{" "}
                  {audit.outcome_summary.neutral ?? 0})
                </span>
              </span>
            )}
            {(audit.outcome_summary.pending_n ?? 0) > 0 && (
              <span className="text-slate-500">{audit.outcome_summary.pending_n} awaiting EOD history</span>
            )}
          </div>
          {(audit.outcome_summary.by_go_no_go?.length ?? 0) > 0 && (
            <div className="flex flex-wrap gap-2 text-[11px]">
              {audit.outcome_summary.by_go_no_go!.map((r) => (
                <span key={String(r.bucket)} className="rounded bg-slate-800/80 px-2 py-0.5 text-slate-400">
                  {String(r.bucket ?? "—").toUpperCase()}: n={r.n}
                  {r.win_rate_pct != null ? ` · win ${r.win_rate_pct.toFixed(0)}%` : ""}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Breakdown grids */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <BreakdownTable title="By gates passed" rows={audit.breakdown_by_gates ?? []} bucketLabel="Gates" />
        <BreakdownTable title="By GO / NO-GO" rows={audit.breakdown_by_go_no_go ?? []} bucketLabel="Status" />
        <BreakdownTable title="By category" rows={audit.breakdown_by_category ?? []} bucketLabel="Category" />
        <BreakdownTable title="By ML signal" rows={audit.breakdown_by_signal ?? []} bucketLabel="Signal" />
        <BreakdownTable title="By track" rows={audit.breakdown_by_track ?? []} bucketLabel="Track" />
        <BreakdownTable title="By readiness" rows={audit.breakdown_by_readiness ?? []} bucketLabel="Tier" />
      </div>

      {/* Recent captures table */}
      <div>
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">Recent captures</p>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <select
            value={tickerFilter}
            onChange={(e) => setTickerFilter(e.target.value)}
            className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-300"
          >
            <option value="">All tickers ({uniqueTickers.length})</option>
            {uniqueTickers.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <select
            value={gatesFilter}
            onChange={(e) => setGatesFilter(e.target.value)}
            className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-300"
          >
            <option value="">All gates</option>
            {gateOptions.map((g) => (
              <option key={String(g)} value={String(g)}>{g}/{records[0]?.gates_total ?? 4} pass</option>
            ))}
          </select>
          <div className="flex rounded border border-slate-600 overflow-hidden">
            {DATE_RANGES.map((dr) => (
              <button
                key={dr.value}
                type="button"
                onClick={() => setDateRange(dr.value)}
                className={clsx(
                  "px-2.5 py-1 text-xs font-medium",
                  dateRange === dr.value ? "bg-violet-600/70 text-white" : "bg-slate-900 text-slate-400 hover:bg-slate-800",
                )}
              >
                {dr.label}
              </button>
            ))}
          </div>
          <span className="text-[10px] text-slate-600">{filtered.length} rows</span>
        </div>

        {filtered.length === 0 ? (
          <p className="text-sm text-slate-500">No audit rows match filters yet.</p>
        ) : (
          <div className="overflow-x-auto [-webkit-overflow-scrolling:touch]">
            <table className="w-full text-xs text-left border-collapse min-w-[720px]">
              <thead>
                <tr className="text-slate-500 border-b border-slate-600">
                  <th className="py-1.5 pr-2 font-medium">Date</th>
                  <th className="py-1.5 pr-2 font-medium">Ticker</th>
                  <th className="py-1.5 pr-2 font-medium">Category</th>
                  <th className="py-1.5 pr-2 font-medium">Signal</th>
                  <th className="py-1.5 pr-2 font-medium">Gates</th>
                  <th className="py-1.5 pr-2 font-medium">Track</th>
                  <th className="py-1.5 pr-2 font-medium">GO?</th>
                  <th className="py-1.5 pr-2 font-medium">Price</th>
                  <th className="py-1.5 pr-2 font-medium">Score</th>
                  <th className="py-1.5 pr-2 font-medium">RSI</th>
                  <th className="py-1.5 pr-2 font-medium">7d</th>
                  <th className="py-1.5 pr-2 font-medium">~20d</th>
                  <th className="py-1.5 pr-2 font-medium">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.map((r) => (
                  <tr key={`${r.signal_date}-${r.ticker}-${r.id ?? ""}`} className="border-b border-slate-700/50 text-slate-300">                    <td className="py-1 pr-2 text-slate-400 font-mono">{r.signal_date}</td>
                    <td className="py-1 pr-2 font-mono font-medium">{r.ticker}</td>
                    <td className="py-1 pr-2 text-slate-500">{r.market_cap_bucket ?? "—"}</td>
                    <td className="py-1 pr-2">{r.ml_signal ?? r.retail_verdict ?? "—"}</td>
                    <td className="py-1 pr-2 tabular-nums">
                      {r.gates_passed ?? "—"}/{r.gates_total ?? 4}
                    </td>
                    <td className="py-1 pr-2">
                      <span
                        className={clsx(
                          "px-1.5 py-0.5 rounded text-[10px] uppercase",
                          (r.track || "accumulate") === "velocity"
                            ? "bg-violet-500/15 text-violet-300"
                            : "bg-slate-700/50 text-slate-400",
                        )}
                      >
                        {r.track || "accumulate"}
                      </span>
                    </td>
                    <td className="py-1 pr-2">
                      <span
                        className={clsx(
                          "px-1.5 py-0.5 rounded text-[10px] uppercase",
                          r.go_no_go === "go"
                            ? "bg-emerald-500/15 text-emerald-300"
                            : r.go_no_go === "no_go"
                              ? "bg-red-500/15 text-red-300"
                              : "bg-slate-700 text-slate-400",
                        )}
                      >
                        {r.go_no_go ?? "—"}
                      </span>
                    </td>
                    <td className="py-1 pr-2 tabular-nums">${Number(r.price_at_signal ?? 0).toFixed(2)}</td>
                    <td className="py-1 pr-2 tabular-nums">{r.composite_score?.toFixed(0) ?? "—"}</td>
                    <td className="py-1 pr-2 tabular-nums">{r.rsi?.toFixed(0) ?? "—"}</td>
                    <td className="py-1 pr-2 tabular-nums text-slate-400">
                      {r.return_7d_pct != null ? `${r.return_7d_pct >= 0 ? "+" : ""}${r.return_7d_pct.toFixed(1)}%` : "—"}
                    </td>
                    <td className="py-1 pr-2 tabular-nums text-slate-400">
                      {r.return_30d_pct != null ? `${r.return_30d_pct >= 0 ? "+" : ""}${r.return_30d_pct.toFixed(1)}%` : "—"}
                    </td>
                    <td className="py-1 pr-2">
                      {r.verdict ? (
                        <span
                          className={clsx(
                            "px-1.5 py-0.5 rounded text-[10px] uppercase",
                            r.verdict === "WIN" && "bg-emerald-500/15 text-emerald-300",
                            r.verdict === "LOSS" && "bg-red-500/15 text-red-300",
                            r.verdict === "NEUTRAL" && "bg-slate-700 text-slate-400",
                          )}
                        >
                          {r.verdict}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <TablePager page={page} pageSize={AUDIT_PAGE_SIZE} total={filtered.length} onPageChange={setPage} />
      </div>
      {audit.pilot?.db_path && (
        <p className="text-[10px] text-slate-600 truncate" title={audit.pilot.db_path}>
          DB: {audit.pilot.db_path}
          {audit.export_url ? " · CSV via Export button (verdict rule audit_v1, 7/20 EOD-step horizons)" : ""}
        </p>
      )}
    </div>
  );
}
