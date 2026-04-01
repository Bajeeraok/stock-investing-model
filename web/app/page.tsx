"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Dashboard } from "@/components/Dashboard";

// Use relative /api/* so Next.js rewrites proxy to backend (BACKEND_API_URL). No NEXT_PUBLIC needed for Railway.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
const AUTO_REFRESH_MARKET_MIN = 30;
// Off-hours auto-refresh is disabled to reduce API usage (FMP calls) and noise.
// You can still manually refresh anytime.
const AUTO_REFRESH_OFF_HOURS_MIN = 0;
const DASHBOARD_FETCH_DEBOUNCE_MS = 2000;
/** Min ms between dashboard fetches (avoids loop + duplicate from Strict Mode). */
const DASHBOARD_MIN_INTERVAL_MS = 30_000;
/** Auto-retry once after this delay when 502/503/timeout (shared-use robustness). */
const AUTO_RETRY_DELAY_MS = 8000;

// Module-level guards so they survive Strict Mode unmount/remount and prevent duplicate requests
let dashboardFetchInProgress = false;
let lastDashboardFetchStart = 0;
/** Time of last initial effect run; used to skip duplicate run from React Strict Mode (same ~tick). */
let lastInitialEffectRun = 0;

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
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [retrying, setRetrying] = useState(false);

  const lastFetchRef = useRef<number>(0);

  const refresh = useCallback(async (isAutoRetry = false) => {
    const now = Date.now();
    // Per-call debounce (same as before)
    if (now - lastFetchRef.current < DASHBOARD_FETCH_DEBOUNCE_MS) return;
    lastFetchRef.current = now;

    // Single-flight: don't start another fetch while one is in progress (avoids Strict Mode double-mount)
    if (dashboardFetchInProgress) return;
    // Min interval between fetches after we've started one (avoids loop; uses module-level so it survives remount)
    if (lastDashboardFetchStart !== 0 && now - lastDashboardFetchStart < DASHBOARD_MIN_INTERVAL_MS) return;

    dashboardFetchInProgress = true;
    lastDashboardFetchStart = now;
    setLoading(true);
    if (!isAutoRetry) setError(null);
    try {
      const res = await fetch(API_BASE ? `${API_BASE}/api/dashboard` : "/api/dashboard");
      if (!res.ok) {
        let errMsg = res.status === 503
          ? "Service temporarily unavailable (503)"
          : res.status === 502
            ? "Backend didn't respond in time (502). The app will retry automatically."
            : `HTTP ${res.status}`;
        try {
          const errBody = await res.json();
          if (errBody && typeof errBody.error === "string") errMsg = errBody.error;
        } catch {
          // ignore JSON parse for error body
        }
        throw new Error(errMsg);
      }
      const json = await res.json();
      setData(json);
      setLastRefreshedAt(new Date());
      retryCountRef.current = 0; // allow auto-retry again on future 502
    } catch (e) {
      const raw = e instanceof Error ? e.message : "Failed to load";
      const msg =
        raw === "Failed to fetch" || raw.includes("Load failed") || raw.includes("NetworkError")
          ? "Connection failed or timed out. Retrying automatically…"
          : raw;
      console.error("[Dashboard] Fetch error:", raw, e);
      setError(msg);
      lastDashboardFetchStart = 0; // allow immediate retry from error screen
    } finally {
      setLoading(false);
      dashboardFetchInProgress = false;
    }
  }, []);

  // Auto-retry once after 502/503/timeout (robustness for shared links / cold start)
  const retryCountRef = useRef(0);
  useEffect(() => {
    if (!error || retryCountRef.current >= 1) return;
    const isRetryable =
      error.includes("502") ||
      error.includes("503") ||
      error.includes("timed out") ||
      error.includes("Timeout") ||
      error.includes("Retrying") ||
      error.includes("Connection failed");
    if (!isRetryable) return;
    retryCountRef.current += 1;
    setRetrying(true);
    const t = setTimeout(() => {
      setRetrying(false);
      refresh(true);
    }, AUTO_RETRY_DELAY_MS);
    return () => clearTimeout(t);
  }, [error, refresh]);

  useEffect(() => {
    const now = Date.now();
    if (now - lastInitialEffectRun < DASHBOARD_FETCH_DEBOUNCE_MS) return;
    lastInitialEffectRun = now;
    refresh();
  }, [refresh]);

  // Auto-refresh: only during US market hours on weekdays (ET).
  useEffect(() => {
    if (error || !data) return;
    const minutes = isUSMarketHours() ? AUTO_REFRESH_MARKET_MIN : AUTO_REFRESH_OFF_HOURS_MIN;
    if (!minutes || minutes <= 0) return;
    const intervalMs = minutes * 60 * 1000;
    const id = setInterval(() => refresh(), intervalMs);
    return () => clearInterval(id);
  }, [data, error, refresh]);

  if (loading && !data && !retrying) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center max-w-sm">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-emerald-500 border-t-transparent mx-auto mb-4" />
          <p className="text-slate-400">Running analysis… First load can take 2–3 minutes.</p>
          <p className="text-slate-500 text-sm mt-1">Fetching signals, portfolio, opportunities...</p>
          <p className="text-slate-600 text-xs mt-2">If you shared this link, the app will keep trying — no need to refresh.</p>
        </div>
      </div>
    );
  }

  if (retrying) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center max-w-sm">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-amber-500 border-t-transparent mx-auto mb-4" />
          <p className="text-slate-400">First load didn’t respond in time. Retrying in a few seconds…</p>
          <p className="text-slate-500 text-sm mt-1">This often works on the second try (e.g. backend cold start).</p>
        </div>
      </div>
    );
  }

  if (error) {
    const isBackendBusy =
      error.includes("timed out") ||
      error.includes("Timeout") ||
      error.includes("502") ||
      error.includes("503") ||
      error.includes("Retrying") ||
      error.includes("Connection failed");
    const hint = isBackendBusy
      ? "First load can take 2–3 minutes; the app retries automatically. If it still fails, click Retry. When sharing with others, they’ll see the same retry — no action needed."
      : typeof window !== "undefined" && !/^localhost|127\.0\.0\.1$/.test(window.location.hostname)
        ? "Backend may be starting or unreachable. Check Railway logs and BACKEND_API_URL on the web service."
        : "Local: ensure FastAPI is running — cd backend && python -m uvicorn api.main:app --reload --port 8002";
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center p-8 bg-slate-900 rounded-xl border border-red-500/30 max-w-md">
          <p className="text-red-400 font-medium">Error: {error}</p>
          <p className="text-slate-400 text-sm mt-2">{hint}</p>
          <button
            onClick={() => refresh()}
            className="mt-4 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-medium"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return data ? (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="animate-pulse text-slate-500">Loading…</div></div>}>
      <Dashboard data={data} onRefresh={refresh} loading={loading} lastRefreshedAt={lastRefreshedAt} />
    </Suspense>
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

export interface BacktestValidation {
  valid: boolean;
  issues: string[];
  fixes: string[];
  data_quality_score: number;
}

export interface BacktestResult {
  ticker: string;
  period: string;
  /** 2 = MR-aware bucket mapping + relaxed ACF for backtest (see config score.interpretation). */
  schema_version?: number;
  /** How score → bucket assignment works (MR tape uses 100−score for buckets when enabled). */
  bucket_assignment_note?: string;
  /** Share of backtest rows where bucket used MR (100−score) vs trending (raw score). */
  bucket_assignment_stats?: {
    n_bars_scored: number;
    mean_reverting_bar_count: number;
    trending_bar_count: number;
    pct_mean_reverting: number | null;
    pct_trending: number | null;
  };
  /** When middle-bin avg returns reorder (e.g. 30–50 > 50–70 at 3m under MR mapping). */
  bucket_return_ordering_notes?: string[];
  /** FMP-based earnings window exclusion when enabled in config (see backend/docs/BACKTEST_DATA.md). */
  earnings_exclusion?: {
    enabled: boolean;
    days_before: number;
    bars_skipped?: number;
    dates_loaded?: number;
    source?: string | null;
    error?: string | null;
    note?: string | null;
  };
  /** SPY (or configured benchmark) vs SMA: share of bull/bear/neutral days on scored bars — context only. */
  spy_regime_summary?: {
    benchmark: string;
    ma_days: number;
    pct_trading_days_bull?: number | null;
    pct_trading_days_bear?: number | null;
    pct_trading_days_neutral?: number | null;
    bars_counted?: number;
    note?: string;
  } | null;
  error?: string;
  buckets?: Record<string, Record<number, BacktestBucketMonth>>;
  by_year?: Record<string, Record<string, Record<number, BacktestBucketMonth>>>;
  by_quarter?: Record<string, Record<string, Record<number, BacktestBucketMonth>>>;
  suggested_buy_min?: string;
  suggested_sell_max?: string;
  validation?: BacktestValidation;
}

/** Backend `portfolio_risk_metrics` — optional fields when data is insufficient */
export interface PortfolioRiskMetrics {
  correlation_matrix?: Record<string, Record<string, number>>;
  correlation_error?: string | null;
  var_cvar?: {
    var_95_10day_pct?: number;
    cvar_95_10day_pct?: number;
    confidence?: number;
    horizon_days?: number;
    interpretation?: string;
    error?: string;
  } | null;
  correlation_adjusted_sizes?: Record<string, number>;
  note?: string;
}

export interface DashboardData {
  signals: Signal[];
  /** Top-level watchlist from API (config.watchlist). */
  watchlist?: string[];
  crypto?: CryptoSignal[];
  cross_asset?: CrossAssetItem[];
  best_2026?: Best2026Pick[];
  story_changes: Signal[];
  portfolio: PortfolioReport;
  portfolios?: Record<string, PortfolioReport>;
  portfolio_names?: string[];
  portfolio_doctor_recommendations?: Record<string, PortfolioDoctorRecommendation>;
  performance_vs_benchmark?: {
    periods: { period: string; portfolio_pct: number | null; spy_pct: number | null; qqq_pct: number | null; vs_spy: number | null; vs_qqq: number | null }[];
    as_of?: string | null;
    message?: string | null;
  };
  trim_candidates: PortfolioHolding[];
  opportunities: Opportunity[];
  thesis_check: ThesisCheck[];
  what_changed: WhatChanged[];
  earnings_risk_count?: number;
  economic_calendar?: EconomicCalendarEvent[];
  guidelines?: { text: string; type: "caution" | "info" | "risk" }[];
  macro_regime?: "Risk-On" | "Neutral" | "Risk-Off";
  global_market_regime?: "BULL" | "BEAR" | "NEUTRAL" | null;
  market_regime?: {
    market_breadth?: string;
    tech_leadership?: string;
    rotation_risk?: string;
    participation_narrow?: boolean | null;
    rs_xlk_spy?: number | null;
    rs_qqq_spy?: number | null;
    rs_rsp_spy?: number | null;
  };
  next_day_outlook?: { ticker: string; bias: string; pct_green: number | null; avg_return_pct: number | null; typical_range_pct: number | null; state_key?: string | null }[];
  typical_move?: { ticker: string; typical_pct_1d: number; typical_pct_60d?: number; high_vol_pct?: number | null; vol_regime?: string }[];
  indicator_validation?: { ticker: string; our_bias: string | null; source: string; external_rating: string | null; status: "aligned" | "divergent" | "no_data"; message: string }[];
  indicator_comparisons?: {
    ticker: string;
    close: { ours: number | null; comparisons: { source: string; value: number; margin_pct: number | null }[]; max_margin_pct: number | null };
    rsi: { ours: number | null; comparisons: { source: string; value: number; margin_abs: number | null }[]; max_margin_abs: number | null };
    ma: { comparisons: { series: string; ours: number; source: string; value: number; margin_pct: number | null }[]; max_margin_pct: number | null };
    macd: { ours: number | null; comparisons: { source: string; value: number; margin_abs: number | null }[]; max_margin_abs: number | null };
    bias: { ours: string | null; comparisons: { source: string; rating: string | null; status: string }[] };
  }[];
  forward_tracking?: {
    records: { as_of_date: string; next_date: string; ticker: string; horizon_days: number; our_signal: string; actual_return_pct: number }[];
    summary_by_horizon?: Record<number, { avg_return_pct: number; n_observations: number }>;
    summary_by_signal?: Record<string, { avg_return_20d_pct?: number; n_observations?: number; hit_rate_pct?: number }>;
    message?: string | null;
  };
  /** EOD freshness, accuracy report, forward ADD hit rate, optional weekly backtest (data/model_health.json) */
  model_health?: import("@/components/dashboard/index").ModelHealthData;
  /** Morning brief (Markets tab): market pulse, key levels, today's focus, action items */
  morning_newsletter?: {
    headline: string;
    date: string;
    three_line_brief?: string[];
    sections: Array<{ title: string; items: string[] }>;
    action_items: string[];
    hold_vs_trade_teaser?: string;
    hold_vs_trade_more?: string;
  } | null;
  paper_trading?: {
    log?: { date: string; seen: number; appended: number } | null;
    mtm?: { updated: number; message?: string | null; as_of?: string } | null;
    mtm_history_log?: { appended: number; message?: string | null; as_of?: string } | null;
    fill?: { updated: number; message?: string | null } | null;
    summary?: { status: string; completed?: number; win_rate_pct?: number | null; avg_return_pct?: number | null; avg_win_pct?: number | null; avg_loss_pct?: number | null; message?: string } | null;
    mtm_history?: Record<string, Array<{ mtm_date: string; mtm_return_pct: number | null; mtm_price: number | null }>> | null;
    data_root?: string | null;
    persistence_note?: string | null;
    recent?: Array<{
      trade_id?: string | null;
      date: string;
      ticker: string;
      signal: string;
      ml_confidence?: number | null;
      regime?: string | null;
      entry_price?: number | null;
      /** ohlcv_last_bar | fmp_batch | yfinance_latest */
      entry_price_source?: string | null;
      target_1?: number | null;
      hard_stop?: number | null;
      atr_14?: number | null;
      model_score?: number | null;
      horizon_trading_days?: number | null;
      next_date?: string | null;
      actual_price?: number | null;
      return_pct?: number | null;
      mtm_date?: string | null;
      mtm_price?: number | null;
      mtm_return_pct?: number | null;
      rolling_entry_price?: number | null;
      rolling_pnl?: number | null;
      rolling_return_pct?: number | null;
      hit_target?: number | null;
      outcome?: string | null;
    }>;
  };
  model_validation?: {
    records: {
      as_of_date: string;
      next_date: string;
      ticker: string;
      prior_close: number;
      actual_close: number;
      actual_return_pct: number;
      our_bias: string | null;
      our_pct_green: number | null;
      our_typical_range_pct: number | null;
      direction_hit: boolean | null;
      within_range: boolean | null;
    }[];
    summary: {
      n_records: number;
      direction_accuracy_pct: number | null;
      direction_n: number;
      range_hit_rate_pct: number | null;
      range_n: number;
    };
  };
  pre_market?: {
    es_pct?: number | null;
    nq_pct?: number | null;
    tech_avg_pct?: number | null;
    value_avg_pct?: number | null;
    rotation_risk_premarket?: string;
    message?: string | null;
  } | null;
  /** Full pre-market engine (6 categories, 15 sources); from scheduler file or /api/pre-market */
  pre_market_full?: {
    timestamp: string;
    composite_score: number;
    bias: string;
    confidence: number;
    minutes_to_open: number;
    top_bullish: string[];
    top_bearish: string[];
    key_risks: string[];
    sector_plays: Record<string, string[]>;
    signals: { name: string; category: string; score: number; weight: number; raw_value: string; direction: string; confidence: number; note?: string }[];
    message?: string;
    rotation_risk_premarket?: string;
  } | null;
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
    model_rules?: { add_min_confidence?: number; trim_max_confidence?: number; add_min_regime?: string };
    horizons?: { short_term: string; medium_term: string; long_term: string };
  };
  as_of_date?: string;
  /** As-of UTC + data limitation copy for retail trust */
  data_freshness?: {
    as_of_utc: string;
    prices?: string;
    fundamentals?: string;
    macro?: string;
    disclaimer?: string;
  };
  /** Parallel shock scenarios to total portfolio value (illustrative) */
  portfolio_stress?: {
    base_value: number;
    scenarios: { name: string; shock_pct: number; portfolio_value_after: number; loss_dollars: number }[];
    disclaimer?: string;
  };
  /** Holdings-based correlation, VaR/CVaR, correlation-adjusted sizing (dashboard API) */
  portfolio_risk_metrics?: PortfolioRiskMetrics;
  /** Methodology bullets for the Known limits panel (config or API defaults) */
  known_limits?: string[];
  /** FRED+VIX macro + optional SPY HMM fusion; coaching_note when views diverge */
  macro_regime_bundle?: {
    macro_regime?: string;
    macro_score?: number;
    combined_regime?: string;
    combined_score?: number;
    coaching_note?: string | null;
    hmm_bear_pct_used?: number | null;
    factors?: Record<string, unknown>;
  } | null;
  market_scenarios?: MarketScenarioItem[];
  macro_analog?: {
    state: string;
    n_observations: number;
    avg_return_3m: number;
    pct_positive: number;
    one_liner: string;
    /** Plain-language interpretation of the historical analog stat */
    plain_language?: string;
  } | null;
  /** Rules-based near-term bias + bullets (FRED + FMP calendar + cross-asset) */
  market_forecast?: {
    headline: string;
    bias: "cautious" | "neutral" | "constructive";
    bullets: string[];
    disclaimer: string;
  } | null;
  /** Tier 1 risk engine: position sizing, drawdown sim, exit levels, earnings impacts, concentration */
  position_sizing?: import("@/components/dashboard/index").PositionSizingData[];
  drawdown_sim?: import("@/components/dashboard/index").DrawdownSimData[];
  exit_levels?: import("@/components/dashboard/index").ExitLevelsData[];
  /** Exit levels by time horizon (short 20d / medium 60d / long 180d) */
  exit_levels_by_horizon?: {
    short?: import("@/components/dashboard/index").ExitLevelsData[];
    medium?: import("@/components/dashboard/index").ExitLevelsData[];
    long?: import("@/components/dashboard/index").ExitLevelsData[];
  };
  earnings_impacts?: import("@/components/dashboard/index").EarningsImpactData[];
  concentration?: import("@/components/dashboard/index").ConcentrationData;
  /** EOD snapshot files in data/eod/ (date, size_bytes, run_date) */
  eod_snapshots?: { date: string; size_bytes: number; run_date?: string | null }[];
  /** Redis: configured (REDIS_URL set) and connected (ping ok) */
  redis_status?: { configured: boolean; connected: boolean };
  /** SEC EDGAR Form 4 insider buys/sells (free data) */
  insider_flow?: {
    insider_buys: { ticker: string; filing_date: string; shares: number; edgar_url: string }[];
    insider_sells: { ticker: string; filing_date: string; shares: number; edgar_url: string }[];
    ticker_activities?: { ticker: string; filing_date: string; edgar_url: string; buys_shares: number; sells_shares: number }[];
    message?: string | null;
  };
  /** Tax-aware exit: positions approaching 1-year LTCG (add purchase_date to holdings) */
  tax_aware_exits?: {
    items: { ticker: string; days_held: number; days_to_ltcg: number; gain: number; tax_savings_if_hold: number; recommendation: string; account?: string; score?: number; regime?: string }[];
    message?: string | null;
  };
  /** Retail value-add: daily briefing, heat, one-liners, badges */
  retail_briefing?: {
    daily_briefing?: {
      summary_sentence?: string;
      regime_plain_english?: string;
      in_entry_zone?: { ticker: string; price: number; entry_low: number; entry_high: number }[];
      earnings_soon?: { ticker: string; days: number }[];
      stops_near?: { ticker: string; price: number; stop_loss: number }[];
      targets_hit?: { ticker: string; price: number; target: number }[];
      suggested_actions?: { ticker: string; action: string; reason: string }[];
      earnings_risk_count?: number;
      tax_approaching_ltcg?: { ticker: string; days_to_ltcg: number }[];
    };
    portfolio_heat_pct?: number;
    concentration?: { top_positions: { ticker: string; pct: number }[]; message?: string | null; concentration_pct?: number };
    regime_plain_english?: string;
    ticker_actions?: Record<string, { action: string; one_liner: string }>;
    tax_approaching_ltcg?: { ticker: string; days_to_ltcg: number }[];
    win_loss_recap?: { total_trades?: number; wins?: number; losses?: number; win_rate_pct?: number; net_pnl_pct?: number };
    overtrading_nudge?: string | null;
    sector_gap?: string | null;
    drawdown_guard?: string | null;
  };
}

export interface MarketScenarioItem {
  date: string;
  name: string;
  event_type: string;
  scenario: {
    avg_return_pct: number;
    std_pct: number;
    pct_positive: number;
    n_events: number;
    rationale: string;
  } | null;
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
  /** Days until next earnings when known from pipeline */
  earnings_days_until?: number | null;
  /** True when within `earnings.caution_days` — extra score reduction applied */
  earnings_caution?: boolean;
  /** Dashboard-only FMP quality hint */
  earnings_quality?: {
    grade?: string | null;
    quality_score?: number | null;
    flags?: string[];
    error?: string | null;
  } | null;
  story_change?: string | null;
  short_suggestion?: string | null;
  medium_suggestion?: string | null;
  long_suggestion?: string | null;
  suggested_buy_price?: number | null;
  suggested_sell_price?: number | null;
  support_level?: number | null;
  buy_target_confidence_pct?: number | null;
  sell_target_confidence_pct?: number | null;
  risk_sizing?: {
    size_dollars: number;
    shares: number;
    shares_1pct_risk?: number;
    stop_pct: number;
    risk_budget_dollars?: number;
    risk_pct?: number;
  } | null;
  /** Band widths + narrative hints — not statistical confidence intervals */
  uncertainty?: {
    st_band_width_pct?: number | null;
    atr_pct_of_price?: number | null;
    typical_range_label?: string | null;
    mt_band_width_pct?: number | null;
    mt_narrative?: string | null;
    lt_band_width_pct?: number | null;
    lt_narrative?: string | null;
  } | null;
  volume_ratio?: number | null;
  volume_unusual?: boolean;
  drawdown_52w?: number | null;
  atr_14?: number | null;
  st_band?: PriceBand | null;
  mt_band?: PriceBand | null;
  lt_band?: PriceBand | null;
  lt_band_low_confidence?: boolean;
  rotation_stepped_down?: boolean;
  st_target_confidence_pct?: number | null;
  mt_target_confidence_pct?: number | null;
  score_label?: string | null;
  confidence_tag?: string | null;
  confluence_score?: number | null;
  trend_signal?: string | null;   // "UP" | "NEUTRAL" | "DOWN"
  rsi_signal?: string | null;
  macd_signal?: string | null;
  ml_short_prob?: number | null;  // P(threshold gain in 20d) from LightGBM, 0-1
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
  cash_deployment: { ticker: string; score?: number | null; confidence?: number | null; action?: string | null; regime: string }[];
  sector_allocation?: { sector: string; pct: number }[];
  correlation_alerts?: string[];
  mega_cap_pct?: number;
}

export interface PortfolioHolding {
  ticker: string;
  value: number | null;
  pct: number | null;
  score: number | null;
  /** 7-layer calibrated confidence (0-100), when available */
  confidence?: number | null;
  /** 7-layer action label (STRONG BUY/BUY/HOLD/REDUCE/AVOID), when available */
  action?: string | null;
  regime: string | null;
  suggestion: string;
  /** One-line “do this today” from portfolio doctor */
  action_today?: string | null;
  earnings_note?: string | null;
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

export interface PortfolioDoctorTrim {
  ticker: string;
  current_pct: number;
  current_value: number;
  suggest_trim_pct: number;
  suggest_trim_dollars: number;
  sell_price: number | null;
  reason: string;
  score: number | null;
  confidence?: number | null;
  action?: string | null;
  regime: string | null;
}

export interface PortfolioDoctorAdd {
  ticker: string;
  score: number | null;
  confidence?: number | null;
  action?: string | null;
  regime: string;
  suggest_add_pct: number;
  suggest_add_dollars: number;
  buy_price: number | null;
  source: string;
}

export interface PortfolioDoctorRecommendation {
  inputs: { risk_appetite: string; goal: string; target_portfolio_value: number | null; time_period_years: number };
  implied_cagr_pct: number | null;
  profile: string;
  trim: PortfolioDoctorTrim[];
  add: PortfolioDoctorAdd[];
}
