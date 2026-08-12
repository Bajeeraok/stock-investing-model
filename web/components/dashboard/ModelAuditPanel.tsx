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
  win_rate_pct?: number | null;
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
  entry_mode?: "full_go" | "starter_only" | "hard_lock" | null;
  gates_passed?: number | null;
  gates_total?: number | null;
  gates_failed?: string | null;
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

const ENTRY_MODE_CFG = {
  full_go:      { label: "FULL GO",   cls: "border-emerald-500/50 bg-emerald-500/15 text-emerald-200" },
  starter_only: { label: "STARTER",   cls: "border-amber-500/40  bg-amber-500/10  text-amber-200"   },
  hard_lock:    { label: "HARD LOCK", cls: "border-red-500/35    bg-red-500/10    text-red-300"      },
} as const;

function EntryModePill({ mode }: { mode?: string | null }) {
  const cfg = ENTRY_MODE_CFG[mode as keyof typeof ENTRY_MODE_CFG];
  if (!cfg) return <span className="text-slate-600 text-[9px]">—</span>;
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-full border text-[9px] font-black uppercase tracking-wider whitespace-nowrap ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

export type ModelAuditActionableSlice = {
  n?: number;
  wins?: number;
  losses?: number;
  neutral?: number;
  win_rate_pct?: number | null;
  actionable_win_rate_pct?: number | null;
};

export type ModelAuditOutcomeSummary = {
  events_total?: number;
  resolved_n?: number;
  pending_n?: number;
  partial_7d_n?: number;
  win_rate_pct?: number | null;
  wins?: number;
  losses?: number;
  neutral?: number;
  blended_win_rate_pct?: number | null;
  all_tracks_actionable_win_rate_pct?: number | null;
  track_scope?: string;
  track_scope_note?: string;
  resolved_n_accumulate?: number;
  resolved_n_velocity?: number;
  tactical_summary?: ModelAuditActionableSlice | null;
  headline_actionable_win_rate_pct?: number | null;
  headline_actionable_n?: number;
  /** Which actionable_slices key actually produced the headline number (falls through go_4_gates -> full_go -> gates_3plus -> all_go when a stricter slice has <5 resolved rows). */
  headline_actionable_slice?: "go_4_gates" | "full_go" | "gates_3plus" | "all_go";
  headline_actionable_slice_label?: string;
  actionable_slices?: Record<string, ModelAuditActionableSlice>;
  by_verdict?: { bucket: string; n: number; avg_return_7d_pct?: number | null; avg_return_30d_pct?: number | null }[];
  by_go_no_go?: { bucket: string; n: number; win_rate_pct?: number | null }[];
  by_ml_signal?: { bucket: string; n: number; win_rate_pct?: number | null }[];
  by_gates_passed?: { bucket: string | number; n: number; win_rate_pct?: number | null }[];
  by_entry_mode?: { bucket: string; n: number; win_rate_pct?: number | null }[];
  by_track?: { bucket: string; n: number; win_rate_pct?: number | null }[];
  by_category?: { bucket: string; n: number; win_rate_pct?: number | null }[];
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
  breakdown_by_entry_mode?: ModelAuditBreakdownRow[];
  gate_blocker_breakdown?: { gate: string; n: number; pct_of_events?: number }[];
  gate_pass_rates?: { gate: string; pass_n?: number; pass_pct?: number; fail_pct?: number }[];
  gate_calibration?: {
    recommend_loosen_valuation?: boolean;
    recommend_loosen_regime?: boolean;
    recommend_momentum_review?: boolean;
    thresholds?: Record<string, number>;
    notes?: string[];
  };
  buy_win_gap?: {
    methodology_note?: string;
    buy_all?: ModelAuditActionableSlice & { avg_score?: number | null };
    buy_full_go?: ModelAuditActionableSlice & { avg_score?: number | null };
    buy_go_4_gates?: ModelAuditActionableSlice;
    recommendations?: string[];
    target_win_rate_pct?: number;
  } | null;
  eod_snapshot_count?: number;
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

type ColumnFilters = {
  ticker: string;
  category: string;
  retail: string;
  mlSignal: string;
  gates: string;
  track: string;
  entryMode: string;
  verdict: string;
  rsiMin: string;
  rsiMax: string;
  scoreMin: string;
  scoreMax: string;
};

const EMPTY_COL_FILTERS: ColumnFilters = {
  ticker: "",
  category: "",
  retail: "",
  mlSignal: "",
  gates: "",
  track: "",
  entryMode: "",
  verdict: "",
  rsiMin: "",
  rsiMax: "",
  scoreMin: "",
  scoreMax: "",
};

function uniqueSorted(values: (string | null | undefined)[]): string[] {
  return Array.from(new Set(values.map((v) => String(v || "").trim()).filter(Boolean))).sort();
}

function ColFilterSelect({
  value,
  onChange,
  options,
  placeholder,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder: string;
  className?: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={clsx(
        "w-full min-w-0 rounded border border-slate-700 bg-slate-950/80 px-1 py-0.5 text-[10px] text-slate-300",
        className,
      )}
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  );
}

function ColFilterNum({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full min-w-0 rounded border border-slate-700 bg-slate-950/80 px-1 py-0.5 text-[10px] text-slate-300 tabular-nums"
    />
  );
}
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
  hint,
}: {
  title: string;
  rows: ModelAuditBreakdownRow[];
  bucketLabel: string;
  hint?: string;
}) {
  if (!rows?.length) return null;
  const showWinRate = rows.some((r) => r.win_rate_pct != null);
  return (
    <div className="rounded-lg border border-slate-600/70 bg-slate-900/40 overflow-hidden">
      <div className="px-3 py-2 border-b border-slate-700/60">
        <p className="text-[10px] uppercase tracking-wider text-slate-500">{title}</p>
        {hint && <p className="text-[10px] text-slate-600 mt-0.5">{hint}</p>}
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500 border-b border-slate-700/50">
            <th className="text-left py-1.5 px-3 font-medium">{bucketLabel}</th>
            <th className="text-right py-1.5 px-2 font-medium">n</th>
            <th className="text-right py-1.5 px-2 font-medium">GO %</th>
            {showWinRate && (
              <th className="text-right py-1.5 px-2 font-medium">Win %</th>
            )}
            <th className="text-right py-1.5 px-3 font-medium">Avg score</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 12).map((r, i) => (
            <tr key={`${title}-${i}`} className="border-b border-slate-800/60 text-slate-300">
              <td className="py-1 px-3">{fmtBucket(r.bucket)}</td>
              <td className="py-1 px-2 text-right tabular-nums">{r.n}</td>
              <td className="py-1 px-2 text-right tabular-nums text-slate-400">{r.go_pct ?? "—"}</td>
              {showWinRate && (
                <td
                  className={clsx(
                    "py-1 px-2 text-right tabular-nums",
                    r.win_rate_pct != null && r.win_rate_pct >= 55
                      ? "text-emerald-400"
                      : r.win_rate_pct != null
                        ? "text-amber-300/90"
                        : "text-slate-600",
                  )}
                >
                  {r.win_rate_pct != null ? `${r.win_rate_pct.toFixed(1)}%` : "—"}
                </td>
              )}
              <td className="py-1 px-3 text-right tabular-nums">{r.avg_score ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ModelAuditPanel({ audit }: { audit: ModelAuditPayload | null | undefined }) {
  const [dateRange, setDateRange] = useState<DateRange>("ALL");
  const [trackFilter, setTrackFilter] = useState<TrackFilter>("all");
  const [recommendedOnly, setRecommendedOnly] = useState(false);
  const [colFilters, setColFilters] = useState<ColumnFilters>(EMPTY_COL_FILTERS);
  const [page, setPage] = useState(0);

  const setColFilter = (key: keyof ColumnFilters, value: string) => {
    setColFilters((prev) => ({ ...prev, [key]: value }));
  };

  const clearAllFilters = () => {
    setDateRange("ALL");
    setTrackFilter("all");
    setRecommendedOnly(false);
    setColFilters(EMPTY_COL_FILTERS);
  };

  const records = audit?.enabled ? audit.recent_records ?? [] : [];
  const uniqueTickers = useMemo(() => uniqueSorted(records.map((r) => r.ticker)), [records]);
  const uniqueCategories = useMemo(() => uniqueSorted(records.map((r) => r.market_cap_bucket)), [records]);
  const uniqueRetail = useMemo(() => uniqueSorted(records.map((r) => r.retail_verdict)), [records]);
  const uniqueMlSignals = useMemo(() => uniqueSorted(records.map((r) => r.ml_signal)), [records]);
  const uniqueTracks = useMemo(() => uniqueSorted(records.map((r) => r.track || "accumulate")), [records]);
  const uniqueEntryModes = useMemo(() => uniqueSorted(records.map((r) => r.entry_mode)), [records]);
  const uniqueVerdicts = useMemo(() => uniqueSorted(records.map((r) => r.verdict)), [records]);

  const filtered = useMemo(() => {
    const cutoff = cutoffDate(dateRange);
    const trk = trackFilter;
    const cf = colFilters;
    const rsiMin = cf.rsiMin.trim() ? parseFloat(cf.rsiMin) : null;
    const rsiMax = cf.rsiMax.trim() ? parseFloat(cf.rsiMax) : null;
    const scoreMin = cf.scoreMin.trim() ? parseFloat(cf.scoreMin) : null;
    const scoreMax = cf.scoreMax.trim() ? parseFloat(cf.scoreMax) : null;

    return records.filter((r) => {
      if (cutoff && r.signal_date < cutoff) return false;
      const track = (r.track || "accumulate").toLowerCase();
      if (trk === "accumulate" && track === "velocity") return false;
      if (trk === "velocity" && track !== "velocity") return false;
      if (recommendedOnly) {
        if (track === "velocity") return false;
        if (r.entry_mode !== "full_go") return false;
      }
      if (cf.ticker && r.ticker !== cf.ticker) return false;
      if (cf.category && String(r.market_cap_bucket || "") !== cf.category) return false;
      if (cf.retail && String(r.retail_verdict || "") !== cf.retail) return false;
      if (cf.mlSignal && String(r.ml_signal || "") !== cf.mlSignal) return false;
      if (cf.gates !== "" && String(r.gates_passed ?? "") !== cf.gates) return false;
      if (cf.track && track !== cf.track.toLowerCase()) return false;
      if (cf.entryMode && String(r.entry_mode || "") !== cf.entryMode) return false;
      if (cf.verdict && String(r.verdict || "") !== cf.verdict) return false;
      if (rsiMin != null && (r.rsi == null || r.rsi < rsiMin)) return false;
      if (rsiMax != null && (r.rsi == null || r.rsi > rsiMax)) return false;
      if (scoreMin != null && (r.composite_score == null || r.composite_score < scoreMin)) return false;
      if (scoreMax != null && (r.composite_score == null || r.composite_score > scoreMax)) return false;
      return true;
    });
  }, [records, dateRange, trackFilter, recommendedOnly, colFilters]);

  const gateOptions = useMemo(() => {
    const set = new Set(records.map((r) => r.gates_passed).filter((g) => g != null));
    const arr = Array.from(set).sort((a, b) => Number(a) - Number(b));
    for (const g of [0, 4]) {
      if (!arr.includes(g)) arr.push(g);
    }
    return arr.sort((a, b) => Number(a) - Number(b));
  }, [records]);

  const hasActiveFilters =
    recommendedOnly ||
    dateRange !== "ALL" ||
    trackFilter !== "all" ||
    Object.values(colFilters).some((v) => v !== "");

  useEffect(() => {
    setPage(0);
  }, [dateRange, trackFilter, recommendedOnly, colFilters]);

  const pagedRows = useMemo(
    () => paginateRows(filtered, page, AUDIT_PAGE_SIZE),
    [filtered, page],
  );

  if (!audit?.enabled) {
    const msg =
      audit?.message ??
      (audit == null
        ? "Analysis data not loaded — open Overview or click Refresh, then return to Analysis."
        : "Model audit not enabled.");
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4">
        <p className="text-sm text-slate-400">{msg}</p>
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

      {audit.outcomes_note && (
        <p className="text-xs text-slate-500 border-l-2 border-violet-500/40 pl-2">{audit.outcomes_note}</p>
      )}

      {(audit.gate_blocker_breakdown?.length ?? 0) > 0 && (
        <div className="rounded-lg border border-slate-700/50 bg-slate-900/40 p-3">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Gate blocker attribution — which gate fails most
            <span className="ml-1 font-normal text-slate-600">(% of all captured events where this gate was blocking)</span>
          </p>
          <div className="flex flex-wrap gap-2">
            {audit.gate_blocker_breakdown!.map((b) => {
              const isValuation = b.gate === "valuation";
              const isRegime = b.gate === "regime";
              const isMomentum = b.gate === "momentum";
              return (
                <div
                  key={b.gate}
                  className={clsx(
                    "flex items-center gap-2 rounded-lg border px-3 py-2",
                    isValuation ? "border-amber-500/40 bg-amber-950/20"
                      : isRegime ? "border-sky-500/35 bg-sky-950/20"
                      : isMomentum ? "border-violet-500/35 bg-violet-950/20"
                      : "border-slate-700/50 bg-slate-900/30",
                  )}
                >
                  <span className={clsx(
                    "text-[10px] font-bold uppercase tracking-wider",
                    isValuation ? "text-amber-300" : isRegime ? "text-sky-300" : isMomentum ? "text-violet-300" : "text-slate-400",
                  )}>
                    {b.gate}
                  </span>
                  <span className="text-xs font-mono tabular-nums text-slate-200">
                    {b.pct_of_events != null ? `${b.pct_of_events.toFixed(1)}%` : ""}
                  </span>
                  <span className="text-[9px] text-slate-500">n={b.n}</span>
                </div>
              );
            })}
          </div>
          <p className="text-[9px] text-slate-600 mt-2 leading-snug">
            If <span className="text-sky-400/70">regime</span> dominates: gates are filtering macro risk, not stock fundamentals — consider whether stormy-tape blocks are too aggressive for accumulation setups.
            If <span className="text-amber-400/70">valuation</span> dominates: most names are richly priced relative to model FV — correct behavior in an elevated market.
          </p>
        </div>
      )}

      {(audit.gate_pass_rates?.length ?? 0) > 0 && (
        <div className="rounded-lg border border-slate-700/50 bg-slate-900/40 p-3">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Gate pass rates
            <span className="ml-1 font-normal text-slate-600">(% of captured events where gate cleared)</span>
          </p>
          <div className="flex flex-wrap gap-2">
            {audit.gate_pass_rates!.map((g) => (
              <div
                key={g.gate}
                className="flex items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-900/30 px-3 py-2"
              >
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{g.gate}</span>
                <span className="text-xs font-mono tabular-nums text-emerald-300/90">
                  {g.pass_pct != null ? `${g.pass_pct.toFixed(1)}% pass` : "—"}
                </span>
                <span className="text-[9px] text-slate-600">n={g.pass_n ?? "—"}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(audit.gate_calibration?.notes?.length ?? 0) > 0 && (
        <div className="rounded-lg border border-violet-500/25 bg-violet-950/15 px-3 py-2.5 space-y-1.5">
          <p className="text-[10px] font-semibold text-violet-300/90 uppercase tracking-wider">
            Gate calibration — keep or loosen?
          </p>
          {audit.gate_calibration!.notes!.map((note, i) => (
            <p key={i} className="text-[11px] text-slate-400 leading-snug">{note}</p>
          ))}
          {audit.gate_calibration?.thresholds && (
            <p className="text-[9px] text-slate-600 pt-1">
              Current: regime ≥{audit.gate_calibration.thresholds.regime_bull_pct_min}% · full MOS ≥
              {audit.gate_calibration.thresholds.valuation_full_mos_pct}% · starter MOS ≥
              {audit.gate_calibration.thresholds.valuation_partial_mos_pct}% · ML ≥
              {audit.gate_calibration.thresholds.ml_short_prob_min}% · momentum RSI &lt;
              {audit.gate_calibration.thresholds.momentum_rsi_max} + pattern ≥
              {audit.gate_calibration.thresholds.momentum_pattern_min}
            </p>
          )}
        </div>
      )}

      {audit.outcome_summary &&
        ((audit.outcome_summary.resolved_n ?? 0) > 0 || (audit.outcome_summary.partial_7d_n ?? 0) > 0) && (
        <div className="rounded-lg border border-emerald-500/25 bg-emerald-950/20 px-3 py-2.5 space-y-2">
          <p className="text-xs font-semibold text-emerald-200/90 uppercase tracking-wide">
            Outcome track record
            <span className="ml-2 text-[10px] font-normal text-slate-500 normal-case">
              accumulate · excludes velocity tactical
            </span>
          </p>
          {(audit.outcome_summary.headline_actionable_win_rate_pct != null ||
            (audit.outcome_summary.headline_actionable_n ?? 0) > 0) && (
            <div className="rounded border border-emerald-500/30 bg-emerald-950/30 px-2.5 py-2">
              <p className="text-[10px] uppercase tracking-wider text-emerald-300/80 mb-1">
                Actionable slice ({audit.outcome_summary.headline_actionable_slice_label ?? "4/4 GO or full_go"})
              </p>
              <p className="text-sm text-slate-200">
                Win rate{" "}
                <strong
                  className={
                    (audit.outcome_summary.headline_actionable_win_rate_pct ?? 0) >= 55
                      ? "text-emerald-400"
                      : "text-amber-300"
                  }
                >
                  {audit.outcome_summary.headline_actionable_win_rate_pct != null
                    ? `${audit.outcome_summary.headline_actionable_win_rate_pct.toFixed(1)}%`
                    : "—"}
                </strong>
                <span className="text-slate-500 text-xs">
                  {" "}
                  (n={audit.outcome_summary.headline_actionable_n ?? 0} resolved)
                </span>
              </p>
              <p className="text-[9px] text-slate-500 mt-0.5">
                {audit.outcome_summary.headline_actionable_slice === "gates_3plus" ||
                audit.outcome_summary.headline_actionable_slice === "all_go"
                  ? "Too few 4/4 GO rows have resolved yet — showing a looser fallback slice instead (see label above). Not the broad accumulate headline (HOLD-heavy) either way."
                  : "Win % on resolved 4/4 GO rows — not the broad accumulate headline (HOLD-heavy)."}
              </p>
            </div>
          )}
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-300">
            <span>
              Resolved:{" "}
              <strong className="text-slate-100 tabular-nums">
                {audit.outcome_summary.resolved_n_accumulate ?? audit.outcome_summary.resolved_n}/
                {audit.outcome_summary.events_total}
              </strong>
              {(audit.outcome_summary.resolved_n_velocity ?? 0) > 0 && (
                <span className="text-violet-400/80 text-[10px] ml-1">
                  (+{audit.outcome_summary.resolved_n_velocity} velocity tactical separate)
                </span>
              )}
            </span>
            {audit.outcome_summary.win_rate_pct != null && (
              <span>
                Actionable win rate (W÷W+L):{" "}
                <strong
                  className={
                    audit.outcome_summary.win_rate_pct >= 70 ? "text-emerald-400" : audit.outcome_summary.win_rate_pct >= 55 ? "text-amber-300" : "text-red-300"
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
            {audit.outcome_summary.blended_win_rate_pct != null && (
              <span className="text-slate-500">
                All tracks blended (incl. neutral): {audit.outcome_summary.blended_win_rate_pct.toFixed(1)}%
              </span>
            )}
            {audit.outcome_summary.tactical_summary &&
              (audit.outcome_summary.tactical_summary.n ?? 0) > 0 && (
              <span className="text-violet-300/90">
                Velocity tactical: n={audit.outcome_summary.tactical_summary.n}
                {audit.outcome_summary.tactical_summary.actionable_win_rate_pct != null
                  ? ` · ${audit.outcome_summary.tactical_summary.actionable_win_rate_pct.toFixed(0)}% W/L`
                  : ""}
              </span>
            )}
            {(audit.outcome_summary.partial_7d_n ?? 0) > 0 && (
              <span className="text-violet-300/90">
                {audit.outcome_summary.partial_7d_n} with 7d return only
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
          {audit.outcome_summary.actionable_slices && (
            <div className="flex flex-wrap gap-2 text-[10px]">
              {Object.entries(audit.outcome_summary.actionable_slices).map(([key, slice]) => (
                <span
                  key={key}
                  className="rounded border border-slate-700/60 bg-slate-900/50 px-2 py-0.5 text-slate-500"
                >
                  {key.replace(/_/g, " ")}: n={slice.n ?? 0}
                  {slice.actionable_win_rate_pct != null
                    ? ` · ${slice.actionable_win_rate_pct.toFixed(0)}% W/L`
                    : ""}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* BUY win-rate gap (ml_signal=BUY vs headline) */}
      {audit.buy_win_gap && (audit.buy_win_gap.buy_all?.n ?? 0) > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 space-y-2">
          <p className="text-[11px] font-semibold text-amber-200 uppercase tracking-wide">
            BUY win-rate gap
          </p>
          <p className="text-[10px] text-slate-400 leading-relaxed">
            {audit.buy_win_gap.methodology_note}
          </p>
          <div className="flex flex-wrap gap-2 text-[10px]">
            {[
              { label: "All BUY labels", data: audit.buy_win_gap.buy_all },
              { label: "full_go BUY", data: audit.buy_win_gap.buy_full_go },
              { label: "4/4 GO BUY", data: audit.buy_win_gap.buy_go_4_gates },
            ].map(({ label, data }) =>
              data?.n ? (
                <span
                  key={label}
                  className="rounded border border-slate-600/80 bg-slate-900/60 px-2 py-1 text-slate-300"
                >
                  {label}:{" "}
                  <span className="font-bold text-slate-100 tabular-nums">
                    {data.actionable_win_rate_pct ?? "—"}%
                  </span>
                  <span className="text-slate-500"> (n={data.n})</span>
                </span>
              ) : null,
            )}
          </div>
          {audit.buy_win_gap.recommendations && audit.buy_win_gap.recommendations.length > 0 && (
            <ul className="text-[10px] text-slate-400 space-y-1 list-disc pl-4">
              {audit.buy_win_gap.recommendations.slice(0, 4).map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Breakdown grids */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <BreakdownTable
          title="By gates passed"
          rows={audit.breakdown_by_gates ?? []}
          bucketLabel="Passed"
          hint="X of 4 primary gates cleared at signal time · Win % from resolved outcomes"
        />
        <BreakdownTable title="By GO / NO-GO" rows={audit.breakdown_by_go_no_go ?? []} bucketLabel="Status" />
        <BreakdownTable title="By category" rows={audit.breakdown_by_category ?? []} bucketLabel="Category" />
        <BreakdownTable
          title="By ML signal"
          rows={audit.breakdown_by_signal ?? []}
          bucketLabel="Signal"
          hint="Entry quality: BUY / STRONG BUY rows — not HOLD-heavy headline. Win % = W÷(W+L) on ~30d verdict rules."
        />
        <BreakdownTable title="By track" rows={audit.breakdown_by_track ?? []} bucketLabel="Track" hint="Velocity uses 5d tactical verdict rules — not in headline win %" />
        <BreakdownTable title="By readiness" rows={audit.breakdown_by_readiness ?? []} bucketLabel="Tier" />
        <BreakdownTable title="By entry mode" rows={audit.breakdown_by_entry_mode ?? []} bucketLabel="Mode" hint="full_go = 4/4 · starter_only = value present, tech blocked · hard_lock = no MOS" />
      </div>


      {/* Recent captures table */}
      <div>
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">Recent captures</p>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <button
            type="button"
            onClick={() => setRecommendedOnly((v) => !v)}
            className={clsx(
              "rounded border px-2.5 py-1 text-[11px] font-medium touch-manipulation",
              recommendedOnly
                ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-200"
                : "border-slate-600 text-slate-400 hover:border-slate-500",
            )}
            title="full_go + accumulate only — highest-quality entry slice"
          >
            Recommended entries only
          </button>
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
          {hasActiveFilters && (
            <button
              type="button"
              onClick={clearAllFilters}
              className="text-[11px] text-violet-300 hover:text-violet-200 underline"
            >
              Clear filters
            </button>
          )}
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
                  <th className="py-1.5 pr-2 font-medium">Retail</th>
                  <th className="py-1.5 pr-2 font-medium">ML</th>
                  <th className="py-1.5 pr-2 font-medium">Gates</th>
                  <th className="py-1.5 pr-2 font-medium">Conf</th>
                  <th className="py-1.5 pr-2 font-medium">Track</th>
                  <th className="py-1.5 pr-2 font-medium" title="full_go = 4/4 · starter_only = value OK, tech gates blocked · hard_lock = no MOS / overvalued">Entry Mode</th>
                  <th className="py-1.5 pr-2 font-medium">Price</th>
                  <th className="py-1.5 pr-2 font-medium">Score</th>
                  <th className="py-1.5 pr-2 font-medium">RSI</th>
                  <th className="py-1.5 pr-2 font-medium">7d</th>
                  <th className="py-1.5 pr-2 font-medium">~20d</th>
                  <th className="py-1.5 pr-2 font-medium">Verdict</th>
                </tr>
                <tr className="border-b border-slate-700/60 bg-slate-900/60">
                  <th className="py-1 pr-1" />
                  <th className="py-1 pr-1 min-w-[4.5rem]">
                    <ColFilterSelect
                      value={colFilters.ticker}
                      onChange={(v) => setColFilter("ticker", v)}
                      options={uniqueTickers}
                      placeholder="All"
                    />
                  </th>
                  <th className="py-1 pr-1 min-w-[5.5rem]">
                    <ColFilterSelect
                      value={colFilters.category}
                      onChange={(v) => setColFilter("category", v)}
                      options={uniqueCategories}
                      placeholder="All"
                    />
                  </th>
                  <th className="py-1 pr-1 min-w-[6rem]">
                    <ColFilterSelect
                      value={colFilters.retail}
                      onChange={(v) => setColFilter("retail", v)}
                      options={uniqueRetail}
                      placeholder="All"
                    />
                  </th>
                  <th className="py-1 pr-1 min-w-[4.5rem]">
                    <ColFilterSelect
                      value={colFilters.mlSignal}
                      onChange={(v) => setColFilter("mlSignal", v)}
                      options={uniqueMlSignals}
                      placeholder="All"
                    />
                  </th>
                  <th className="py-1 pr-1 min-w-[3rem]">
                    <ColFilterSelect
                      value={colFilters.gates}
                      onChange={(v) => setColFilter("gates", v)}
                      options={gateOptions.map(String)}
                      placeholder="All"
                    />
                  </th>
                  <th className="py-1 pr-1" />
                  <th className="py-1 pr-1 min-w-[4.5rem]">
                    <ColFilterSelect
                      value={colFilters.track}
                      onChange={(v) => setColFilter("track", v)}
                      options={uniqueTracks}
                      placeholder="All"
                    />
                  </th>
                  <th className="py-1 pr-1 min-w-[4.5rem]">
                    <ColFilterSelect
                      value={colFilters.entryMode}
                      onChange={(v) => setColFilter("entryMode", v)}
                      options={uniqueEntryModes}
                      placeholder="All"
                    />
                  </th>
                  <th className="py-1 pr-1" />
                  <th className="py-1 pr-1 min-w-[3rem]">
                    <div className="flex gap-0.5">
                      <ColFilterNum
                        value={colFilters.scoreMin}
                        onChange={(v) => setColFilter("scoreMin", v)}
                        placeholder="min"
                      />
                      <ColFilterNum
                        value={colFilters.scoreMax}
                        onChange={(v) => setColFilter("scoreMax", v)}
                        placeholder="max"
                      />
                    </div>
                  </th>
                  <th className="py-1 pr-1 min-w-[3rem]">
                    <div className="flex gap-0.5">
                      <ColFilterNum
                        value={colFilters.rsiMin}
                        onChange={(v) => setColFilter("rsiMin", v)}
                        placeholder="min"
                      />
                      <ColFilterNum
                        value={colFilters.rsiMax}
                        onChange={(v) => setColFilter("rsiMax", v)}
                        placeholder="max"
                      />
                    </div>
                  </th>
                  <th className="py-1 pr-1" />
                  <th className="py-1 pr-1" />
                  <th className="py-1 pr-1 min-w-[4rem]">
                    <ColFilterSelect
                      value={colFilters.verdict}
                      onChange={(v) => setColFilter("verdict", v)}
                      options={uniqueVerdicts}
                      placeholder="All"
                    />
                  </th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.map((r) => (
                  <tr key={`${r.signal_date}-${r.ticker}-${r.id ?? ""}`} className="border-b border-slate-700/50 text-slate-300">                    <td className="py-1 pr-2 text-slate-400 font-mono">{r.signal_date}</td>
                    <td className="py-1 pr-2 font-mono font-medium">{r.ticker}</td>
                    <td className="py-1 pr-2 text-slate-500">{r.market_cap_bucket ?? "—"}</td>
                    <td className="py-1 pr-2 text-slate-400 max-w-[7rem] truncate" title={r.retail_verdict ?? ""}>
                      {r.retail_verdict ?? "—"}
                    </td>
                    <td className="py-1 pr-2">{r.ml_signal ?? "—"}</td>
                    <td
                      className="py-1 pr-2 tabular-nums"
                      title={r.gates_failed ? `Blocked: ${r.gates_failed}` : undefined}
                    >
                      {r.gates_passed ?? "—"}/{r.gates_total ?? 4}
                      {r.gates_failed ? (
                        <span className="block text-[9px] text-amber-400/80 truncate max-w-[5rem]">
                          {r.gates_failed}
                        </span>
                      ) : null}
                    </td>
                    <td className="py-1 pr-2 tabular-nums text-slate-500 text-[10px]">
                      {r.confidence_low != null && r.confidence_high != null
                        ? `${r.confidence_low}-${r.confidence_high}`
                        : "—"}
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
                      {r.entry_mode ? (
                        <EntryModePill mode={r.entry_mode} />
                      ) : (
                        /* fallback to legacy go_no_go for old rows that predate entry_mode */
                        <span className={clsx(
                          "px-1.5 py-0.5 rounded text-[9px] uppercase",
                          r.go_no_go === "go" ? "bg-emerald-500/15 text-emerald-300"
                            : r.go_no_go === "no_go" ? "bg-slate-700/50 text-slate-500"
                            : "bg-slate-700 text-slate-400",
                        )}>
                          {r.go_no_go ?? "—"}
                        </span>
                      )}
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
