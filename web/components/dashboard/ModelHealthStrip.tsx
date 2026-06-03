"use client";

import { Activity } from "lucide-react";

interface SummaryBySignal {
  [signal: string]: { avg_return_20d_pct?: number; n_observations?: number; hit_rate_pct?: number };
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

/** API `model_health` + optional forward-tracking fallbacks */
export interface WalkForwardRegimeBreakdownEntry {
  window_count?: number;
  avg_hit_rate_pct?: number | null;
  avg_net_return_pct?: number | null;
}

export interface ModelHealthData {
  accuracy_as_of?: string | null;
  eod_latest_date?: string | null;
  forward_hold_add_hit_rate_20d?: number | null;
  forward_observations_20d?: number | null;
  validation_direction_accuracy_pct?: number | null;
  calibration_ok?: boolean | null;
  calibration_score?: number | null;
  walk_forward_ok?: boolean | null;
  /** Walk-forward windows grouped by SPY vs SMA regime at test start (from update_model_health.py). */
  walk_forward_regime_breakdown?: Record<string, WalkForwardRegimeBreakdownEntry> | null;
  backtest_last_run?: string | null;
  backtest_ticker?: string | null;
  message?: string | null;
}

interface Props {
  model_health?: ModelHealthData | null;
  summary_by_signal?: SummaryBySignal | null;
  summary_by_horizon?: Record<number, HorizonSummary> | null;
  message?: string | null;
}

export function ModelHealthStrip({ model_health, summary_by_signal, summary_by_horizon, message }: Props) {
  const mh = model_health || {};
  const parts: string[] = [];

  if (mh.eod_latest_date) {
    parts.push(`Latest EOD ${mh.eod_latest_date}`);
  }
  if (mh.accuracy_as_of) {
    const short = mh.accuracy_as_of.length > 10 ? mh.accuracy_as_of.slice(0, 10) : mh.accuracy_as_of;
    parts.push(`Targets ${short}`);
  }
  if (mh.calibration_score != null && mh.calibration_score !== undefined) {
    const ok = mh.calibration_ok === true ? "OK" : mh.calibration_ok === false ? "check" : "?";
    parts.push(`Calibration ${mh.calibration_score.toFixed(0)}/100 (${ok})`);
  }
  if (mh.walk_forward_ok != null) {
    parts.push(`Walk-forward ${mh.walk_forward_ok ? "consistent" : "review"}`);
  }
  const wrb = mh.walk_forward_regime_breakdown;
  if (wrb && typeof wrb === "object" && Object.keys(wrb).length > 0) {
    const seg = Object.entries(wrb)
      .filter(([, v]) => v && (v.window_count ?? 0) > 0)
      .map(([k, v]) => `${k}:${v.window_count}w`)
      .join(" · ");
    if (seg) {
      parts.push(`WF by regime ${seg}`);
    }
  }
  if (mh.forward_hold_add_hit_rate_20d != null && mh.forward_observations_20d != null) {
    parts.push(
      `ADD 20d hit ${mh.forward_hold_add_hit_rate_20d.toFixed(0)}% (n=${mh.forward_observations_20d})`
    );
  }
  if (mh.validation_direction_accuracy_pct != null) {
    parts.push(`Next-day bias ${mh.validation_direction_accuracy_pct.toFixed(0)}%`);
  }

  if (parts.length === 0 && summary_by_signal && Object.keys(summary_by_signal).length > 0) {
    Object.entries(summary_by_signal).forEach(([sig, data]) => {
      const hr = data?.hit_rate_pct;
      const n = data?.n_observations;
      if (hr != null && n != null) {
        parts.push(`${sig} ${hr.toFixed(0)}% (n=${n})`);
      }
    });
  }

  const horizonCount = summary_by_horizon ? Object.keys(summary_by_horizon).length : 0;
  const showMsg = (mh.message || message) && parts.length === 0;

  if (showMsg) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 px-3 py-2 flex items-center gap-2">
        <Activity className="h-4 w-4 text-slate-500 shrink-0" />
        <span className="text-xs text-slate-500">Model health: {mh.message || message}</span>
      </div>
    );
  }

  if (parts.length === 0) {
    return null;
  }

  return (
    <div
      className="rounded-lg border border-slate-600 bg-slate-800/30 px-3 py-2 flex flex-wrap items-center gap-x-4 gap-y-1"
      title="EOD freshness, price-target report, optional weekly backtest (data/model_health.json), forward ADD hit rate."
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
