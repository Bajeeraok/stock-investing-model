"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Dashboard } from "@/components/Dashboard";
import type { PaperVsBacktestDriftPayload } from "@/components/dashboard/PaperVsBacktestDrift";
import { loadCachedDashboard, mergeDashboardData, saveCachedDashboard } from "@/lib/dashboardCache";
import { connectDashboardWs, type DashboardWsConnection } from "@/lib/dashboardWs";

// Use relative /api/* so Next.js rewrites proxy to backend (BACKEND_API_URL). No NEXT_PUBLIC needed for Railway.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
const AUTO_REFRESH_MARKET_MIN = (() => {
  const raw = process.env.NEXT_PUBLIC_AUTO_REFRESH_MARKET_MIN;
  if (raw) {
    const n = parseInt(raw, 10);
    if (!Number.isNaN(n) && n >= 5 && n <= 180) return n;
  }
  // Align with backend signal warm (~2h on Railway); quote ticks still update prices server-side.
  return 120;
})();
// Off-hours: still poll the cheap shell when WebSocket is dead (Railway proxies
// often drop WS). Shell reads Redis only — no FMP. Override with NEXT_PUBLIC_AUTO_REFRESH_OFF_HOURS_MIN.
const AUTO_REFRESH_OFF_HOURS_MIN = (() => {
  const raw = process.env.NEXT_PUBLIC_AUTO_REFRESH_OFF_HOURS_MIN;
  if (raw) {
    const n = parseInt(raw, 10);
    if (!Number.isNaN(n) && n >= 0 && n <= 180) return n;
  }
  return 15;
})();
const DASHBOARD_FETCH_DEBOUNCE_MS = 2000;
/** Min ms between dashboard fetches (avoids loop + duplicate from Strict Mode). */
const DASHBOARD_MIN_INTERVAL_MS = 30_000;
/** Auto-retry once after this delay when 502/503/timeout (shared-use robustness). */
const AUTO_RETRY_DELAY_MS = 8000;
/** Poll while backend recomputes after stale snapshot. */
const STALE_POLL_MS = 5000;

// Module-level guards so they survive Strict Mode unmount/remount and prevent duplicate requests
let dashboardFetchInProgress = false;
let lastDashboardFetchStart = 0;
let pendingForceRefresh = false;
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
  // SSR + first client paint must match; hydrate localStorage cache in useEffect only.
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [wsLive, setWsLive] = useState(false);

  const lastFetchRef = useRef<number>(0);
  const stalePollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const cached = loadCachedDashboard();
    if (cached) {
      setData(cached);
      setLoading(false);
      setStale(Boolean(cached.stale));
    }
  }, []);

  const applyDashboardJson = useCallback((json: DashboardData, fromNetwork = true) => {
    setData((prev) => (prev ? mergeDashboardData(prev, json) : json));
    if (fromNetwork) {
      saveCachedDashboard(json);
      setLastRefreshedAt(new Date());
    }
    setStale(Boolean(json.stale) || Boolean(json.warming));
    if (fromNetwork && !json.warming && json.refresh_status !== "running") {
      setIsRefreshing(false);
    }
  }, []);

  const refresh = useCallback(async (isAutoRetry = false, forceRefresh = false, silentBackground = false) => {
    const now = Date.now();
    if (!forceRefresh && !silentBackground && now - lastFetchRef.current < DASHBOARD_FETCH_DEBOUNCE_MS) return;
    lastFetchRef.current = now;

    if (dashboardFetchInProgress) {
      if (forceRefresh) pendingForceRefresh = true;
      return;
    }
    if (
      !forceRefresh &&
      !silentBackground &&
      lastDashboardFetchStart !== 0 &&
      now - lastDashboardFetchStart < DASHBOARD_MIN_INTERVAL_MS
    ) {
      return;
    }

    dashboardFetchInProgress = true;
    lastDashboardFetchStart = now;
    const hasCached = !!loadCachedDashboard();
    if (!hasCached && !data) setLoading(true);
    else if (forceRefresh) setIsRefreshing(true);
    if (!isAutoRetry) setError(null);
    let succeeded = false;
    let keepRefreshing = false;
    try {
      const shellBase = API_BASE ? `${API_BASE}/api/dashboard/shell` : "/api/dashboard/shell";
      const refreshUrl = API_BASE ? `${API_BASE}/api/dashboard?refresh=true` : "/api/dashboard?refresh=true";
      const url = forceRefresh ? refreshUrl : shellBase;
      const res = await fetch(url, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        let errMsg = res.status === 503
          ? "Dashboard warming up — retry in a moment."
          : res.status === 502
            ? "Backend didn't respond in time (502). The app will retry automatically."
            : `HTTP ${res.status}`;
        try {
          const errBody = await res.json();
          if (errBody && typeof errBody.detail === "string") errMsg = errBody.detail;
          else if (errBody && typeof errBody.error === "string") errMsg = errBody.error;
        } catch {
          // ignore
        }
        throw new Error(errMsg);
      }
      const json = (await res.json()) as DashboardData;
      applyDashboardJson(json);
      retryCountRef.current = 0;
      succeeded = true;
      if (forceRefresh && (json.refresh_coalesced || json.refresh_status === "running")) {
        keepRefreshing = true;
      }
    } catch (e) {
      const raw = e instanceof Error ? e.message : "Failed to load";
      const msg =
        raw === "Failed to fetch" || raw.includes("Load failed") || raw.includes("NetworkError")
          ? "Connection failed or timed out. Retrying automatically…"
          : raw;
      console.error("[Dashboard] Fetch error:", raw, e);
      if (!loadCachedDashboard() && !data) setError(msg);
      lastDashboardFetchStart = 0;
    } finally {
      setLoading(false);
      setIsRefreshing(keepRefreshing);
      dashboardFetchInProgress = false;
      if (pendingForceRefresh) {
        pendingForceRefresh = false;
        if (succeeded) {
          window.setTimeout(() => {
            void refresh(false, true);
          }, 500);
        }
      }
    }
  }, [applyDashboardJson, data]);

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

  // WebSocket push: backend notifies when Redis cache is updated (quote tick / signal warm / full run).
  useEffect(() => {
    let conn: DashboardWsConnection | null = null;
    let wsCheckTimer: ReturnType<typeof setInterval> | null = null;
    let cancelled = false;

    void connectDashboardWs(() => {
      void refresh(false, false, true);
    }).then((c) => {
      if (cancelled) {
        c?.close();
        return;
      }
      conn = c;
      if (!c) {
        setWsLive(false);
        return;
      }
      const sync = () => setWsLive(c.isConnected());
      sync();
      wsCheckTimer = setInterval(sync, 3000);
    });

    return () => {
      cancelled = true;
      setWsLive(false);
      if (wsCheckTimer) clearInterval(wsCheckTimer);
      conn?.close();
    };
  }, [refresh]);

  // Mobile: refetch when tab becomes visible (Safari suspends WebSocket / stale localStorage).
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        void refresh(false, false, true);
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [refresh]);

  // Auto-refresh: market hours on a long cadence; off-hours still refresh the shell
  // when WebSocket is down so desktop/mobile don't stick on yesterday's localStorage.
  useEffect(() => {
    if (error || !data) return;
    const minutes = isUSMarketHours()
      ? AUTO_REFRESH_MARKET_MIN
      : wsLive
        ? 0
        : AUTO_REFRESH_OFF_HOURS_MIN;
    if (!minutes || minutes <= 0) return;
    const intervalMs = minutes * 60 * 1000;
    const id = setInterval(() => refresh(false, false, true), intervalMs);
    return () => clearInterval(id);
  }, [data, error, refresh, wsLive]);

  // HTTP poll fallback when WebSocket unavailable (cold start / proxy) or first-load warming.
  useEffect(() => {
    const jobRunning =
      data?.warming === true ||
      data?.refresh_status === "running" ||
      data?.refresh_coalesced === true;
    const shouldPoll =
      !error &&
      (jobRunning || !wsLive) &&
      (!wsLive || data?.warming === true || jobRunning);
    if (!shouldPoll) {
      if (stalePollRef.current) {
        clearInterval(stalePollRef.current);
        stalePollRef.current = null;
      }
      return;
    }
    const pollMs = jobRunning ? STALE_POLL_MS : Math.max(60_000, (AUTO_REFRESH_OFF_HOURS_MIN || 15) * 60_000);
    const poll = async () => {
      try {
        if (jobRunning) {
          const statusUrl = API_BASE ? `${API_BASE}/api/dashboard/status` : "/api/dashboard/status";
          const st = await fetch(statusUrl, { cache: "no-store" }).then((r) => r.json());
          const ready =
            st?.ready === true ||
            (st?.cache_fresh === true && st?.is_running === false && st?.status !== "running");
          if (ready) {
            await refresh(false, false, true);
            setIsRefreshing(false);
          }
        } else {
          await refresh(false, false, true);
        }
      } catch {
        // ignore poll errors
      }
    };
    void poll();
    stalePollRef.current = setInterval(poll, pollMs);
    return () => {
      if (stalePollRef.current) clearInterval(stalePollRef.current);
    };
  }, [data?.warming, data?.refresh_status, data?.refresh_coalesced, error, refresh, wsLive]);

  if (loading && !data && !retrying) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center max-w-sm">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-emerald-500 border-t-transparent mx-auto mb-4" />
          <p className="text-slate-400">Loading dashboard…</p>
          <p className="text-slate-500 text-sm mt-1">First visit may take a minute if cache is cold.</p>
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
      <Dashboard
        data={data}
        onRefresh={(force?: boolean) => {
          void refresh(false, !!force);
        }}
        loading={loading}
        isRefreshing={isRefreshing}
        stale={stale}
        lastRefreshedAt={lastRefreshedAt}
      />
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

export interface PreIpoProxySignal {
  ticker: string;
  close?: number | null;
  composite_buy?: number | null;
  regime?: string | null;
  signal?: string | null;
}

export interface PreIpoHeadline {
  title: string;
  url?: string | null;
  published_at?: string | null;
  source?: string | null;
}

export interface PreIpoNewsBlock {
  available?: boolean;
  headline_count?: number;
  sentiment_label?: string | null;
  sentiment_score_avg?: number | null;
  sentiment_method?: string | null;
  latest?: PreIpoHeadline | null;
  headlines?: PreIpoHeadline[];
  themes?: string[];
  catalyst?: {
    headline_summary?: string | null;
    top_event_type?: string | null;
    top_impact?: number | null;
    hours_since_catalyst?: number | null;
  } | null;
  sources_note?: string | null;
  message?: string | null;
}

export interface PreIpoItem {
  id: string;
  name: string;
  sector?: string | null;
  last_valuation_usd_b?: number | null;
  valuation_as_of?: string | null;
  status?: string | null;
  note?: string | null;
  public_proxies?: string[];
  proxy_signals?: PreIpoProxySignal[];
  news?: PreIpoNewsBlock | null;
}

export interface PreIpoPanel {
  enabled?: boolean;
  disclaimer?: string | null;
  items?: PreIpoItem[];
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
  avg_excess_vs_benchmark_pct?: number | null;
}

export interface BacktestScoreParity {
  apply_live_adjustments?: boolean;
  live_ctx_active?: boolean;
  question?: string;
  question_label?: string;
  note?: string;
}

export interface WalkForwardConsistency {
  avg_hit_rate_pct?: number;
  std_hit_rate_pct?: number;
  avg_net_return_pct?: number | null;
  consistent?: boolean;
  window_count?: number;
}

export interface WalkForwardBacktest {
  ticker?: string;
  train_years?: number;
  test_months?: number;
  buy_threshold?: number;
  transaction_cost_pct?: number;
  windows?: Array<{
    train_start: string;
    train_end: string;
    test_start: string;
    test_end: string;
    spy_regime?: string;
    results: Record<number, BacktestBucketMonth>;
  }>;
  consistency?: Record<number, WalkForwardConsistency>;
  regime_breakdown?: Record<string, { window_count?: number; avg_hit_rate_pct?: number; avg_net_return_pct?: number | null }>;
  regime_note?: string;
  score_parity?: BacktestScoreParity;
  error?: string;
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
  mr_spread_3m?: {
    edge_pct?: number;
    dip_avg_return_pct?: number | null;
    momentum_avg_return_pct?: number | null;
    dip_n?: number;
    momentum_n?: number;
  } | null;
  mr_spread_6m?: {
    edge_pct?: number;
    dip_avg_return_pct?: number | null;
    momentum_avg_return_pct?: number | null;
    dip_n?: number;
    momentum_n?: number;
  } | null;
  /** FMP-based earnings window exclusion when enabled in config (see docs/backend/BACKTEST_DATA.md). */
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
  benchmark?: string;
  score_parity?: BacktestScoreParity;
  walk_forward?: WalkForwardBacktest;
  /** Tier 1–3: gates, rule sim, exit, regime, thresholds (see docs/signals/BACKTEST_CONFIDENCE.md). */
  tier_enhancements?: BacktestTierEnhancements | null;
  primary_kpis?: BacktestPrimaryKpis | null;
}

export interface BacktestPrimaryKpis {
  headline?: string;
  recommended_horizon_months?: number;
  mr_spread_6m_edge_pct?: number | null;
  walk_forward_6m_avg_return_pct?: number | null;
  walk_forward_6m_consistent?: boolean | null;
  dip_bucket_6m_hit_rate_pct?: number | null;
  pct_mean_reverting?: number | null;
  confidence_band?: "good" | "moderate" | "review" | string;
  calibration_note?: string;
}

export interface BacktestTierEnhancements {
  error?: string;
  gate_backtest?: {
    n_rows?: number;
    by_horizon_trading_days?: Record<
      string,
      Record<string, { n?: number; mean_fwd_pct?: number | null; hit_rate_pct?: number | null }>
    >;
    notes?: string[];
  };
  exit_backtest?: {
    sell_max?: number;
    sell_avg_fwd_3m_pct?: number | null;
    unconditional_avg_fwd_3m_pct?: number | null;
    sell_precision_3m_pct?: number | null;
    notes?: string[];
  };
  rule_strategy?: {
    entry_rule?: string;
    non_overlapping?: {
      n?: number;
      avg_return_pct?: number | null;
      hit_rate_pct?: number | null;
      strategy_cagr_pct?: number | null;
      buy_hold_cagr_pct?: number | null;
      alpha_vs_buy_hold_cagr_pct?: number | null;
    };
  };
  by_regime?: Record<
    string,
    {
      dip_bucket_6m?: { avg_return_pct?: number | null };
      momentum_bucket_6m?: { avg_return_pct?: number | null };
      mr_spread_6m_edge_pct?: number | null;
    }
  >;
  per_ticker_threshold?: {
    suggested_buy_min?: number;
    suggested_sell_max?: number;
    notes?: string[];
  };
  forward_tracking?: { note?: string };
  regime_gate_proxy_note?: string;
}

/** Backend `portfolio_risk_metrics` — optional fields when data is insufficient */
export interface PortfolioRiskMetrics {
  beta?: {
    benchmark?: string;
    portfolio_beta?: number | null;
    coverage_pct?: number;
    headline?: string;
    band?: string;
    band_tone?: string;
    lookback_days?: number;
    error?: string;
    holdings?: Array<{
      ticker: string;
      beta?: number | null;
      weight_pct: number;
      sector?: string;
      contribution?: number;
    }>;
    sectors?: Array<{
      sector: string;
      beta?: number | null;
      weight_pct: number;
    }>;
  } | null;
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

/** SPY/VIX stress + bounce-setup overlay; optional ML bounce probability */
export interface MarketReversalOverlay {
  enabled?: boolean;
  error?: string;
  stress_score?: number | null;
  bounce_setup_score?: number | null;
  bounce_rule_score?: number | null;
  composite_buy_delta?: number | null;
  label?: string;
  headline?: string;
  bullets?: string[];
  ml_bounce_prob?: number | null;
  ml_error?: string | null;
  features?: Record<string, number> | null;
  vix?: number | null;
  real_yield?: number | null;
}

export interface DashboardData {
  signals: Signal[];
  /** Lite rows for Overview chart when full `signals` is deferred (smaller first payload). */
  signal_scores?: Array<
    Pick<Signal, "ticker" | "composite_buy" | "regime"> & { error?: string }
  >;
  /** When true, full per-ticker rows load via GET /api/dashboard/signals-panel (Redis). */
  signals_deferred?: boolean;
  /** When true, opportunities + doctor adds load via GET /api/dashboard/opportunities-bundle. */
  opportunities_deferred?: boolean;
  /** When false, skip opportunity scan and hide Daily Opportunities in UI. */
  opportunities_bundle_enabled?: boolean;
  /** When true, Analysis tab sections load via GET /api/dashboard/analysis-bundle. */
  analysis_deferred?: boolean;
  /** Snapshot is older than fresh Redis cache; background refresh may be running. */
  stale?: boolean;
  /** First cold start: empty shell while background compute runs. */
  warming?: boolean;
  refresh_status?: string;
  /** True when Refresh was coalesced because a full compute was already running. */
  refresh_coalesced?: boolean;
  /** After-hours marks for tickers reporting earnings today (4:30 PM / 6 PM ET job). */
  after_hours_earnings?: {
    as_of_et?: string;
    session_date_et?: string;
    slot?: string;
    skipped?: boolean;
    skip_reason?: string;
    items?: Array<{
      ticker: string;
      earnings_date?: string;
      previous_close?: number | null;
      mark_price?: number | null;
      change_pct?: number | null;
      price_source?: string;
      post_earnings?: {
        beat_or_miss?: string | null;
        transition_note?: string | null;
        signal_direction?: string | null;
      };
    }>;
    disclaimer?: string;
  };
  /** Top-level watchlist from API (config.watchlist). */
  watchlist?: string[];
  /** Watchlist ∪ portfolio holdings — tickers with signals / roadmaps. */
  signal_universe?: string[];
  /** Guest vs linked portfolio; public demo universe until auth ships. */
  universe_meta?: {
    guest_mode?: boolean;
    has_config_portfolio?: boolean;
    public_demo_universe?: string[];
    portfolio_ticker_count?: number;
    note?: string;
  };
  crypto?: CryptoSignal[];
  pre_ipo?: PreIpoPanel;
  cross_asset?: CrossAssetItem[];
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
  market_reversal_overlay?: MarketReversalOverlay | null;
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
    /** RSP/SPY ratio trend: Rising | Flat | Falling — equal-weight participation */
    rsp_spy_trend?: string | null;
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
    records: {
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
      gates_frozen?: boolean | null;
      hit_st_target?: number | null;
      hit_st_stop?: number | null;
      trim_net_score_pct?: number | null;
      trim_outcome_label?: string | null;
      max_drawdown_pct?: number | null;
    }[];
    summary_by_horizon?: Record<
      number,
      {
        avg_return_pct?: number;
        n_observations?: number;
        win_rate_pct?: number;
        st_target_hit_rate_pct?: number;
        st_stop_hit_rate_pct?: number;
        trim_avg_net_score_pct?: number;
        trim_helped_pct?: number;
        trim_n?: number;
      }
    >;
    summary_by_signal?: Record<
      string,
      {
        avg_return_20d_pct?: number;
        avg_return_pct?: number;
        n_observations?: number;
        hit_rate_pct?: number;
        trim_avg_net_score_pct?: number;
        trim_helped_pct?: number;
        metric_note?: string;
      }
    >;
    summary_by_gates?: Record<
      string,
      {
        avg_return_pct?: number;
        n_observations?: number;
        win_rate_pct?: number;
        st_target_hit_rate_pct?: number;
        st_stop_hit_rate_pct?: number;
      }
    >;
    summary_by_go_no_go?: Record<string, { avg_return_20d_pct?: number; n_observations?: number; hit_rate_pct?: number }>;
    summary_by_entry_mode?: Record<
      string,
      {
        avg_return_pct?: number;
        avg_return_20d_pct?: number;
        n_observations?: number;
        win_rate_pct?: number;
        hit_rate_pct?: number;
      }
    >;
    summary_actionable_buy?: {
      label?: string;
      avg_return_pct?: number;
      avg_return_20d_pct?: number;
      n_observations?: number;
      win_rate_pct?: number;
      hit_rate_pct?: number;
    } | null;
    data_source_note?: string | null;
    meta?: {
      eod_date_first?: string | null;
      eod_date_last?: string | null;
      eod_snapshot_count?: number;
      records_total?: number;
      records_returned?: number;
      as_of_date_min?: string | null;
      as_of_date_max?: string | null;
      newest_completed_as_of?: string | null;
      ticker_count?: number;
    };
    message?: string | null;
    summary_by_lens?: import("@/lib/forwardTrackingLens").SummaryByLens;
  };
  model_audit?: import("@/components/dashboard/index").ModelAuditPayload;
  tactical_breakouts?: import("@/components/dashboard/index").TacticalBreakoutRow[];
  event_risk_strip?: import("@/components/dashboard/index").EventRiskStripPayload;
  hunter_panel?: import("@/components/dashboard/index").HunterPanelPayload;
  /** Paper realized returns vs forward-tracking 20d population mean (smoke test; Analysis tab) */
  paper_vs_backtest_drift?: PaperVsBacktestDriftPayload | null;
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
    fill?: { updated: number; message?: string | null; entry_synced?: number | null } | null;
    backfill?: {
      appended: number;
      skipped_no_fill?: number | null;
      skipped_no_reference?: number | null;
      skipped_gate?: number | null;
      signals_scanned?: number | null;
      dates_scanned?: number | null;
      skipped_existing?: number | null;
      eod_dates_total?: number | null;
      entry_mode?: string | null;
      message?: string | null;
    } | null;
    mtm_history_sync?: { appended?: number; message?: string | null; as_of?: string | null } | null;
    sync_targets?: { updated?: number; message?: string | null } | null;
    summary?: {
      status: string;
      /** Which cohort drives headline win rate / avg return */
      headline_track?: "accumulate" | "accumulate_thin" | "no_accumulate" | null;
      completed?: number;
      min_required?: number;
      horizon_note?: string | null;
      benchmark_ticker?: string | null;
      win_rate_pct?: number | null;
      avg_return_pct?: number | null;
      avg_win_pct?: number | null;
      avg_loss_pct?: number | null;
      avg_excess_vs_spy_pct?: number | null;
      n_benchmarked?: number | null;
      message?: string | null;
      buy_signals_summary?: {
        completed_n: number;
        win_rate_pct?: number | null;
        avg_return_pct?: number | null;
        avg_excess_vs_spy_pct?: number | null;
        label: string;
      } | null;
      accumulate_summary?: {
        completed_n: number;
        win_rate_pct?: number | null;
        avg_return_pct?: number | null;
        label: string;
      } | null;
      tactical_summary?: {
        completed_n: number;
        win_rate_pct?: number | null;
        avg_return_pct?: number | null;
        label: string;
      } | null;
      by_gate_mode?: Record<string, {
        n: number;
        win_rate_pct?: number | null;
        avg_return_pct?: number | null;
      }> | null;
      marketing_note?: string | null;
    } | null;
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
      effective_entry_date?: string | null;
      effective_entry_price?: number | null;
      /** signal_entry_provisional | next_session_close | signal_entry */
      effective_entry_source?: string | null;
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
      benchmark_ticker?: string | null;
      benchmark_return_pct?: number | null;
      excess_return_pct?: number | null;
      gate_cleared?: boolean | null;
      go_no_go?: string | null;
      gates_passed?: number | null;
      gates_total?: number | null;
      track?: string | null;
      reference_entry_price?: number | null;
      limit_fill_date?: string | null;
      entry_mode?: string | null;
      gate_mode?: "full_go" | "starter_only" | "hard_lock" | null;
    }>;
    /** Cumulative equity index from completed paper trades (for track record chart) */
    equity_curve?: Array<{
      date: string;
      ticker?: string;
      signal?: string;
      outcome?: string;
      return_pct?: number;
      equity_index?: number;
      cumulative_return_pct?: number;
      trade_n?: number;
    }>;
  };
  regime_validation?: {
    validated?: unknown;
    summary?: string;
    error?: boolean;
  };
  confidence_calibration?: {
    buckets?: unknown[];
    note?: string;
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
  /** Retail decision framework — five questions, matrix, IF/THEN */
  retail_market_decisions?: import("@/components/dashboard/RetailMarketDecisionsPanel").RetailMarketDecisions | null;
  /** As-of timestamp + data limitation copy for retail trust */
  data_freshness?: {
    as_of_et?: string;
    snapshot_updated_at?: string | null;
    snapshot_updated_et?: string | null;
    eod_snapshot_saved_at?: string | null;
    serving_stale?: boolean;
    snapshot_source?: string;
    refresh_status?: string;
    status?: string;
    message?: string;
    prices?: string;
    fundamentals?: string;
    macro?: string;
    disclaimer?: string;
    price_last_bar_date?: string | null;
    eod_snapshot_latest_date?: string | null;
    quotes_updated_at?: string | null;
    signals_updated_at?: string | null;
    precision_note?: string | null;
    degraded_mode?: boolean;
    degraded_sources?: import("@/components/dashboard/index").DegradedSource[];
  };
  /** Parallel shock scenarios to total portfolio value (illustrative) */
  portfolio_stress?: {
    base_value: number;
    scenarios: { name: string; shock_pct: number; portfolio_value_after: number; loss_dollars: number }[];
    disclaimer?: string;
  };
  /** Holdings-based correlation, VaR/CVaR, correlation-adjusted sizing (dashboard API) */
  portfolio_risk_metrics?: PortfolioRiskMetrics;
  /** Portfolio Doctor v2: health score, MCTR, stress tests, earnings calendar, priority actions */
  portfolio_doctor_v2?: {
    health?: {
      score: number;
      sub_scores: { concentration: number; correlation: number; regime_alignment: number; drawdown_risk: number; tax_efficiency: number };
      biggest_drag?: string | null;
      improvement_note?: string | null;
    };
    mctr?: {
      positions: { ticker: string; value_pct: number; risk_pct: number; risk_ratio: number }[];
      portfolio_vol_annual_pct?: number;
      portfolio_beta?: number | null;
      note?: string | null;
    };
    stress_tests?: { name: string; portfolio_impact_pct: number; spy_drawdown_pct: number; survivors?: string[] }[];
    earnings_calendar?: {
      items: { ticker: string; earnings_date?: string; days_until: number; portfolio_pct: number }[];
      total_at_risk_pct: number;
      count: number;
      note?: string | null;
    };
    priority_actions?: {
      this_week: { ticker: string; action: string; reason: string; tags?: string[]; urgency?: string }[];
      this_month: { ticker: string; action: string; reason: string; tags?: string[]; urgency?: string }[];
      total_actions: number;
    };
    portfolio_beta?: number | null;
    attribution?: {
      periods?: Record<string, { ticker: string; weight_pct: number; return_pct: number | null; contribution_pct: number | null }[]>;
      top_contributor?: { ticker: string; contribution_pct: number; period: string } | null;
      top_detractor?: { ticker: string; contribution_pct: number; period: string } | null;
    };
    liquidity?: {
      items?: { ticker: string; avg_daily_volume?: number | null; days_to_exit?: number | null; liquidity_score?: number | null; flag?: string | null; portfolio_pct?: number }[];
      illiquid_count?: number;
      note?: string | null;
    };
    factor_exposure?: {
      portfolio_factors?: Record<string, number>;
      per_holding?: { ticker: string; weight_pct: number; factors: Record<string, number> }[];
      dominant_factor?: string | null;
      note?: string | null;
    };
  };
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
  /** Resolved DATA_ROOT on the backend (e.g. /data or /app/data) */
  data_root?: string | null;
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
  /** Prior close → last close % move (EOD snapshot). */
  daily_move_pct?: number | null;
  /** Last ~30 EOD closes for list sparklines. */
  sparkline_closes?: number[] | null;
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
  story_change_source?: string | null;
  story_change_trigger?: string | null;
  story_change_horizon?: string | null;
  story_change_horizon_flips?: string[] | null;
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
  /** 7-layer model action — aligned with Roadmaps / ticker detail */
  plan_action?: string | null;
  plan_confidence?: number | null;
  /** Backend retail tokens + audit cohort fields (gates, entry mode). */
  retail_status?: import("@/components/dashboard/retailActionUX").RetailActionPayload | null;
  entry_mode?: string | null;
  gates_passed?: number | null;
  gates_total?: number | null;
  model_confidence_pct?: number | null;
  confidence_mid?: number | null;
  rsi_status?: string | null;
  gate_cleared?: boolean | null;
  /** ADV-based days to exit at 20% participation (risk-sized or $5k probe). */
  liquidity_days_to_exit?: number | null;
  liquidity_score?: number | null;
  liquidity_flag?: string | null;
  /** FMP news catalyst (48h) when detected on dashboard enrich */
  catalyst?: {
    active?: boolean;
    top_event_type?: string | null;
    top_impact?: number | null;
    headline_summary?: string | null;
    override_note?: string | null;
    hours_since_catalyst?: number | null;
  } | null;
  catalyst_modifier?: {
    active?: boolean;
    event_type?: string | null;
    headline?: string | null;
    override_note?: string | null;
  } | null;
  post_earnings_transition?: {
    active?: boolean;
    beat_or_miss?: string | null;
    signal_direction?: string | null;
    transition_note?: string | null;
    eps_surprise_pct?: number | null;
    days_since?: number | null;
  } | null;
  stress_label?: string | null;
  error?: string;
}

export interface PortfolioReport {
  per_holding: PortfolioHolding[];
  total_value: number;
  avg_score: number;
  /** Weighted avg of 7-layer confidence when available on holdings */
  avg_confidence?: number | null;
  /** Holdings where chart score and model confidence materially disagree */
  score_confidence_mismatch_count?: number;
  regime_counts: { UP: number; NEUTRAL: number; DOWN: number };
  largest_position: {
    ticker: string;
    pct: number;
    value: number;
    score?: number;
    confidence?: number | null;
    regime?: string;
  } | null;
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
  trim_source?: string | null;
  trim_primary_driver?: string | null;
  trim_triggers?: string[] | null;
  trim_horizon?: string | null;
  trim_detail?: string | null;
  /** Trim gate stack (hybrid v1: score trigger + 2/4 gates) */
  trim_gates_passed?: number | null;
  trim_gates_total?: number | null;
  trim_gate_cleared?: boolean | null;
  trim_recommendation?: string | null;
  trim_gates?: Array<{ id: string; label: string; detail: string; pass: boolean }> | null;
  is_trim_candidate?: boolean | null;
  trim_gates_pending?: boolean | null;
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
