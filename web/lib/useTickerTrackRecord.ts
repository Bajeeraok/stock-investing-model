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
  /** ADD right if up, TRIM right if down, HOLD unscored (null). */
  right: boolean | null;
}

export interface TrackRecordResponse {
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
): { signal: string; since: string } | null {
  const rows = (trades ?? []).filter((t) => t.date && t.signal).slice();
  if (!rows.length) return null;
  rows.sort((a, b) => String(b.date).localeCompare(String(a.date)));
  const sig = String(rows[0].signal).toUpperCase();
  let since = rows[0].date as string;
  for (const r of rows) {
    if (String(r.signal).toUpperCase() !== sig) break;
    since = r.date as string;
  }
  return { signal: sig, since };
}
