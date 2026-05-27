"use client";

import { useMemo, useState } from "react";
import { clsx } from "clsx";
import { ClipboardCheck } from "lucide-react";

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
  recent_records?: ModelAuditRecord[];
  outcomes_available?: boolean;
  outcomes_note?: string | null;
  message?: string | null;
  methodology?: string | null;
};

type DateRange = "1W" | "1M" | "ALL";
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

  if (!audit?.enabled) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4">
        <p className="text-sm text-slate-400">{audit?.message ?? "Model audit not enabled."}</p>
      </div>
    );
  }

  const records = audit.recent_records ?? [];
  const uniqueTickers = useMemo(
    () => Array.from(new Set(records.map((r) => r.ticker))).sort(),
    [records],
  );

  const filtered = useMemo(() => {
    const cutoff = cutoffDate(dateRange);
    const tf = tickerFilter.toUpperCase();
    const gf = gatesFilter;
    return records.filter((r) => {
      if (tf && r.ticker !== tf) return false;
      if (cutoff && r.signal_date < cutoff) return false;
      if (gf !== "" && String(r.gates_passed ?? "") !== gf) return false;
      return true;
    });
  }, [records, tickerFilter, dateRange, gatesFilter]);

  const targetDays = audit.pilot_target_days ?? 30;
  const progressDays = audit.pilot_progress_days ?? audit.pilot?.distinct_days ?? 0;
  const progressPct = Math.min(100, Math.round((100 * progressDays) / Math.max(1, targetDays)));

  const gateOptions = useMemo(() => {
    const set = new Set(records.map((r) => r.gates_passed).filter((g) => g != null));
    return Array.from(set).sort((a, b) => Number(a) - Number(b));
  }, [records]);

  return (
    <div className="rounded-lg border border-violet-500/30 bg-gradient-to-b from-violet-950/20 to-slate-800/30 p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-200 flex items-center gap-2">
            <ClipboardCheck className="h-4 w-4 text-violet-400" />
            Model audit — {audit.cohort_tag ?? "cohort"} ({audit.cohort_size ?? "—"} tickers)
          </p>
          <p className="text-xs text-slate-500 mt-1 max-w-2xl leading-relaxed">
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

      {audit.message && (
        <p className="text-xs text-amber-200/90 rounded-lg border border-amber-500/30 bg-amber-950/30 px-3 py-2">{audit.message}</p>
      )}

      {audit.outcomes_note && !audit.outcomes_available && (
        <p className="text-xs text-slate-500 border-l-2 border-slate-600 pl-2">{audit.outcomes_note}</p>
      )}

      {/* Breakdown grids */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <BreakdownTable title="By gates passed" rows={audit.breakdown_by_gates ?? []} bucketLabel="Gates" />
        <BreakdownTable title="By GO / NO-GO" rows={audit.breakdown_by_go_no_go ?? []} bucketLabel="Status" />
        <BreakdownTable title="By category" rows={audit.breakdown_by_category ?? []} bucketLabel="Category" />
        <BreakdownTable title="By ML signal" rows={audit.breakdown_by_signal ?? []} bucketLabel="Signal" />
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
                  <th className="py-1.5 pr-2 font-medium">GO?</th>
                  <th className="py-1.5 pr-2 font-medium">Price</th>
                  <th className="py-1.5 pr-2 font-medium">Score</th>
                  <th className="py-1.5 pr-2 font-medium">RSI</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 50).map((r) => (
                  <tr key={`${r.signal_date}-${r.ticker}-${r.id ?? ""}`} className="border-b border-slate-700/50 text-slate-300">
                    <td className="py-1 pr-2 text-slate-400 font-mono">{r.signal_date}</td>
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {audit.pilot?.db_path && (
        <p className="text-[10px] text-slate-600 truncate" title={audit.pilot.db_path}>
          DB: {audit.pilot.db_path}
        </p>
      )}
    </div>
  );
}
