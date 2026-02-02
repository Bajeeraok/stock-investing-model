"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Dashboard } from "@/components/Dashboard";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";
const AUTO_REFRESH_MARKET_MIN = 30;
const AUTO_REFRESH_OFF_HOURS_MIN = 30;
const DASHBOARD_FETCH_DEBOUNCE_MS = 2000;

/** US market hours: 9:30 AM–4:00 PM Eastern, Mon–Fri */
function isUSMarketHours(): boolean {
  const now = new Date();
  const opts: Intl.DateTimeFormatOptions = {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
    weekday: "short",
  };
  const parts = new Intl.DateTimeFormat("en-US", opts).formatToParts(now);
  const weekday = parts.find((p) => p.type === "weekday")?.value ?? "";
  const hour = parseInt(parts.find((p) => p.type === "hour")?.value ?? "0", 10);
  const minute = parseInt(parts.find((p) => p.type === "minute")?.value ?? "0", 10);
  if (weekday === "Sat" || weekday === "Sun") return false;
  const totalMins = hour * 60 + minute;
  return totalMins >= 570 && totalMins < 960;
}

export default function Home() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const lastFetchRef = useRef<number>(0);

  const refresh = useCallback(async () => {
    const now = Date.now();
    if (now - lastFetchRef.current < DASHBOARD_FETCH_DEBOUNCE_MS) return;
    lastFetchRef.current = now;

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(API_BASE ? `${API_BASE}/api/dashboard` : "/api/dashboard");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load";
      console.error("[Dashboard] Fetch error:", msg, e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Auto-refresh: every 5 min during market hours, every 30 min outside
  useEffect(() => {
    if (error || !data) return;
    const intervalMs = (isUSMarketHours() ? AUTO_REFRESH_MARKET_MIN : AUTO_REFRESH_OFF_HOURS_MIN) * 60 * 1000;
    const id = setInterval(() => refresh(), intervalMs);
    return () => clearInterval(id);
  }, [data, error, refresh]);

  if (loading && !data) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-emerald-500 border-t-transparent mx-auto mb-4" />
          <p className="text-slate-400">Running analysis... This may take 1-2 minutes.</p>
          <p className="text-slate-500 text-sm mt-1">Fetching signals, portfolio, opportunities...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center p-8 bg-slate-900 rounded-xl border border-red-500/30">
          <p className="text-red-400 font-medium">Error: {error}</p>
          <p className="text-slate-400 text-sm mt-2">Make sure the FastAPI server is running:</p>
          <code className="block mt-2 p-2 bg-slate-800 rounded text-emerald-400 text-sm">cd backend && python -m uvicorn api.main:app --reload --port 8002</code>
          <button
            onClick={refresh}
            className="mt-4 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-medium"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return data ? (
    <Dashboard data={data} onRefresh={refresh} loading={loading} />
  ) : null;
}

export interface CryptoSignal {
  ticker: string;
  close: number | null;
  composite_buy: number | null;
  regime: string | null;
  signal: string | null;
  rsi: number | null;
  error?: string;
}

export interface Best2026Pick {
  ticker: string;
  score: number | null;
  regime: string | null;
  confidence: number;
  reason: string;
  close?: number | null;
}

export interface EconomicCalendarEvent {
  date?: string;
  name?: string;
  event?: string;
  country?: string;
  [key: string]: unknown;
}

export interface FMPPlanStatus {
  has_key: boolean;
  available: { feature: string; plan: string }[];
  unavailable: { feature: string; suggested_plan: string; error: string }[];
}

export interface CrossAssetItem {
  ticker: string;
  label?: string;
  close?: number;
  pct_change: number | null;
  error?: string;
}

export interface BacktestBucketMonth {
  avg_return_pct: number | null;
  hit_rate: number | null;
  count: number;
  margin_of_error_pct?: number | null;
}

export interface BacktestResult {
  ticker: string;
  period: string;
  error?: string;
  buckets?: Record<string, Record<number, BacktestBucketMonth>>;
  by_year?: Record<string, Record<string, Record<number, BacktestBucketMonth>>>;
  by_quarter?: Record<string, Record<string, Record<number, BacktestBucketMonth>>>;
  suggested_buy_min?: string;
  suggested_sell_max?: string;
}

export interface DashboardData {
  signals: Signal[];
  crypto?: CryptoSignal[];
  cross_asset?: CrossAssetItem[];
  best_2026?: Best2026Pick[];
  story_changes: Signal[];
  portfolio: PortfolioReport;
  trim_candidates: PortfolioHolding[];
  opportunities: Opportunity[];
  thesis_check: ThesisCheck[];
  what_changed: WhatChanged[];
  earnings_risk_count?: number;
  economic_calendar?: EconomicCalendarEvent[];
  guidelines?: { text: string; type: "caution" | "info" | "risk" }[];
  macro_regime?: "Risk-On" | "Neutral" | "Risk-Off";
  cot_by_ticker?: Record<string, string>;
  fmp_plan_status?: FMPPlanStatus;
  backtest?: BacktestResult[];
  backtest_years?: number;
  backtest_period?: string;
  config: {
    watchlist: string[];
    score: object;
    regime: object;
    risk_sizing?: { risk_pct: number; stop_pct: number };
    horizons?: { short_term: string; medium_term: string; long_term: string };
  };
}

export interface PriceBand {
  low: number;
  high: number;
}

export interface Signal {
  ticker: string;
  close: number | null;
  composite_buy: number | null;
  regime: string | null;
  signal: string | null;
  rsi: number | null;
  earnings_note?: string | null;
  story_change?: string | null;
  short_suggestion?: string | null;
  medium_suggestion?: string | null;
  long_suggestion?: string | null;
  suggested_buy_price?: number | null;
  suggested_sell_price?: number | null;
  support_level?: number | null;
  risk_sizing?: { size_dollars: number; shares: number; stop_pct: number } | null;
  volume_ratio?: number | null;
  volume_unusual?: boolean;
  drawdown_52w?: number | null;
  atr_14?: number | null;
  st_band?: PriceBand | null;
  mt_band?: PriceBand | null;
  lt_band?: PriceBand | null;
  lt_band_low_confidence?: boolean;
  error?: string;
}

export interface PortfolioReport {
  per_holding: PortfolioHolding[];
  total_value: number;
  avg_score: number;
  regime_counts: { UP: number; NEUTRAL: number; DOWN: number };
  largest_position: { ticker: string; pct: number; value: number; score?: number; regime?: string } | null;
  top3_pct?: number;
  concentration_alert: string[];
  cash_deployment: { ticker: string; score: number; regime: string }[];
  sector_allocation?: { sector: string; pct: number }[];
  correlation_alerts?: string[];
}

export interface PortfolioHolding {
  ticker: string;
  value: number | null;
  pct: number | null;
  score: number | null;
  regime: string | null;
  suggestion: string;
  account?: string;
  cost_basis?: number;
  gain_loss?: number;
  gain_loss_pct?: number | null;
}

export interface Opportunity {
  ticker: string;
  close: number;
  composite_buy: number;
  rsi: number;
  regime: string;
  reason: string;
}

export interface ThesisCheck {
  ticker: string;
  thesis: string;
  exit_condition: string;
  nudge: string | null;
}

export interface WhatChanged {
  ticker: string;
  changes: string[];
  summary?: string;
}
