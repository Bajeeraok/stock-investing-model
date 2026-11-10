"use client";

/**
 * Shared fetch for /api/ticker/{t}/track-record — used by the Verdict tab's hit-rate card
 * and the Track tab, so both read one response (module-level cache, one in-flight request
 * per ticker) instead of each computing their own number.
 */

import { useEffect, useState } from "react";
import { apiUrl } from "./apiBase";

const TRACK_RECORD_TIMEOUT_MS = 15000;
const CACHE_TTL_MS = 5 * 60_000;

export interface TrackRecordHorizonStats {
  n_observations?: number;
  win_rate_pct?: number;
  avg_return_pct?: number;
  calls_n?: number;
  calls_right_pct?: number | null;
}

export interface DailyTradeRow {
  date: string | null;
  signal: string | null;
  model_price: number | null;
  fill_price: number | null;
  target: number | null;
  stop: number | null;
  /** Resolved: horizon-date close. Pending: latest marked EOD close (see mark_date). */
  outcome_price: number | null;
  mark_date?: string | null;
  outcome: string | null;
  win: boolean | null;
  status: "resolved" | "pending";
  return_pct: number | null;
  unrealized_return_pct: number | null;
  model_version?: string | null;
  volatile_note?: string | null;
  track?: string | null;
}

/** One scored daily call: signal at the close vs the next session's close (horizon = 1 snapshot). */
export interface DailyCallRow {
  date: string | null;
  next_date: string | null;
  signal: string | null;
  close: number | null;
  next_close: number | null;
  return_pct: number | null;
  status: "complete" | "pending" | string | null;
  gates_passed?: number | null;
  gates_total?: number | null;
  model_version?: string | null;
  data_quality?: string | null;
  /** ADD right if up, TRIM right if down, HOLD unscored (null). */
  right: boolean | null;
  /** Short-term target vs price at call, %. */
  target_pct?: number | null;
  ml_prob_pct?: number | null;
  ret_20d_pct?: number | null;
  /** 20d actual minus target, percentage points. */
  miss_pp?: number | null;
  in_range?: boolean | null;
  /** Within 20 days: short-term target / stop touched (1/0). */
  hit_st_target?: number | boolean | null;
  hit_st_stop?: number | boolean | null;
}

export interface ErrorSummary {
  n: number;
  avg_expected_pct: number;
  avg_actual_pct: number;
  mae_pp: number;
  bias_pp: number;
  within_range_pct: number | null;
  target_hit_pct: number;
  stop_hit_pct: number;
}

export interface CalibrationBucket {
  range: string;
  n: number;
  avg_predicted_pct: number;
  actual_up_pct?: number;
  actual_hit_pct?: number;
  came_true_pct?: number;
}

export interface Calibration {
  n: number;
  avg_predicted_pct: number;
  actual_up_pct?: number;
  actual_hit_pct?: number;
  brier: number;
  came_true_pct?: number;
  brier_base?: number;
  skill_pct?: number | null;
  verdict?: "unproven" | "no_edge" | "miscalibrated" | "proven";
  rose_pct?: number;
  gain_pcts?: number[];
  buckets: CalibrationBucket[];
}

export interface LatestModelDailyRow {
  date: string;
  next_date: string | null;
  tickers: number;
  signal: string | null;
  /** 1 = full position, 0.5 = trimmed/reduced (averaged across tickers when pooled). */
  exposure: number;
  model_return_pct: number;
  hold_return_pct: number;
  spy_return_pct: number | null;
}

/** Day-by-day scorecard for the live model version: following its calls vs holding vs SPY. */
export interface LatestModelDaily {
  model_version: string;
  days: number;
  target_days: number;
  first_date: string | null;
  last_date: string | null;
  model_cum_pct: number | null;
  hold_cum_pct: number | null;
  spy_cum_pct: number | null;
  model_vs_hold_pct: number | null;
  model_vs_spy_pct: number | null;
  days_reduced: number;
  skipped_days: string[];
  rows: LatestModelDailyRow[];
}

export interface LossScorecard {
  horizon_days: number;
  min_n: number;
  buys?: {
    n: number;
    avg_pnl_pct: number | null;
    loss_rate_pct: number;
    avg_loss_pct: number | null;
    avg_gain_pct: number | null;
    gain_loss_ratio: number | null;
    worst_loss_pct: number;
    worst_dip_pct: number | null;
  };
  buys_status?: "too_few" | "losing" | "weak" | "ok";
  exits?: {
    n: number;
    losses_avoided_n: number;
    avg_drop_avoided_pct: number | null;
    missed_gain_n: number;
    avg_missed_gain_pct: number | null;
    net_saved_pct: number;
  };
  exits_status?: "too_few" | "costing" | "ok";
}

export interface TrackRecordResponse {
  latest_model_daily?: LatestModelDaily | null;
  available: boolean;
  daily_calls?: DailyCallRow[] | null;
  latest_call_date?: string | null;
  /** Newest EOD snapshot the server's forward tracking was computed through. */
  eod_date_last?: string | null;
  ticker?: string;
  current_model_version?: string | null;
  current?: TrackRecordHorizonStats | null;
  legacy?: TrackRecordHorizonStats | null;
  by_horizon?: Record<string, { current?: TrackRecordHorizonStats | null; legacy?: TrackRecordHorizonStats | null }> | null;
  daily_trades?: DailyTradeRow[] | null;
  loss_scorecard?: Record<string, { current?: LossScorecard | null; all?: LossScorecard | null }> | null;
  error_summary?: { horizon_days: number; current?: ErrorSummary | null; all?: ErrorSummary | null } | null;
  prob_calibration?: Record<string, Calibration | null> | null;
  prob_calibration_pooled?: Record<string, Calibration | null> | null;
  level_odds_check?: {
    ticker?: Record<string, Calibration | null> | null;
    pooled?: Record<string, Calibration | null> | null;
    pending?: number | null;
  } | null;
}

const cache = new Map<string, { at: number; data: TrackRecordResponse | null }>();
const inflight = new Map<string, Promise<TrackRecordResponse | null>>();

function load(ticker: string): Promise<TrackRecordResponse | null> {
  const hit = cache.get(ticker);
  if (hit && Date.now() - hit.at < CACHE_TTL_MS) return Promise.resolve(hit.data);
  const pending = inflight.get(ticker);
  if (pending) return pending;
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TRACK_RECORD_TIMEOUT_MS);
  const p = fetch(apiUrl(`/api/ticker/${ticker}/track-record`), { signal: ac.signal, cache: "no-store" })
    .then((r) => (r.ok ? (r.json() as Promise<TrackRecordResponse>) : null))
    .catch(() => null)
    .then((data) => {
      cache.set(ticker, { at: Date.now(), data });
      return data;
    })
    .finally(() => {
      clearTimeout(timer);
      inflight.delete(ticker);
    });
  inflight.set(ticker, p);
  return p;
}

export function useTickerTrackRecord(ticker: string | null | undefined): {
  data: TrackRecordResponse | null;
  loading: boolean;
} {
  const key = (ticker || "").toUpperCase();
  const [state, setState] = useState<{ key: string; data: TrackRecordResponse | null; loading: boolean }>(() => ({
    key,
    data: cache.get(key)?.data ?? null,
    loading: !!key && !cache.has(key),
  }));

  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    setState({ key, data: cache.get(key)?.data ?? null, loading: !cache.has(key) });
    load(key).then((data) => {
      if (!cancelled) setState({ key, data, loading: false });
    });
    return () => {
      cancelled = true;
    };
  }, [key]);

  return state.key === key ? { data: state.data, loading: state.loading } : { data: null, loading: true };
}

/** Shortest horizon with at least one resolved "current"-version observation. */
export function earliestAvailableHorizon(
  byHorizon: TrackRecordResponse["by_horizon"],
): { horizon: number; stats: TrackRecordHorizonStats } | null {
  if (!byHorizon) return null;
  const horizons = Object.keys(byHorizon).map(Number).filter((h) => !Number.isNaN(h)).sort((a, b) => a - b);
  for (const h of horizons) {
    const stats = byHorizon[String(h)]?.current;
    if (stats && (stats.n_observations ?? 0) > 0) {
      return { horizon: h, stats };
    }
  }
  return null;
}

/**
 * How long the latest signal has held: walks daily_trades newest-first while the signal
 * string stays the same. Returns the oldest date of that run (the "Wait since Oct 3" line).
 */
export function currentSignalSince(
  trades: Array<{ date: string | null; signal: string | null }> | null | undefined,
): { signal: string; since: string; latest: string } | null {
  const rows = (trades ?? []).filter((t) => t.date && t.signal).slice();
  if (!rows.length) return null;
  rows.sort((a, b) => String(b.date).localeCompare(String(a.date)));
  const sig = String(rows[0].signal).toUpperCase();
  let since = rows[0].date as string;
  for (const r of rows) {
    if (String(r.signal).toUpperCase() !== sig) break;
    since = r.date as string;
  }
  return { signal: sig, since, latest: rows[0].date as string };
}
