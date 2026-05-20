"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, BarChart3, Bell, Calendar, Database, Info, RefreshCw, Save, TrendingUp, Wallet, Target, FileText, Sparkles, HelpCircle, Globe, PieChart, Activity, Shield, FlaskConical, Mail } from "lucide-react";
import type {
  DashboardData,
  Signal,
  Opportunity,
  Best2026Pick,
  PortfolioDoctorRecommendation,
} from "@/app/page";
import { LIVE_SCORE_LINE } from "@/lib/modelSemantics";
import { clsx } from "clsx";
import {
  AddTickerBar,
  Best2026Section,
  CryptoSection,
  CrossAssetSection,
  DashboardTabs,
  type TabId,
  StoryAlerts,
  PortfolioSummary,
  PortfolioStressStrip,
  DataFreshnessBar,
  KnownLimitsPanel,
  ModelDisclaimer,
  SignalsTable,
  PortfolioHoldings,
  TrimCandidates,
  Opportunities,
  ThesisCheck,
  WhatChanged,
  RegimeChart,
  ScoreChart,
  AnchorChartPanel,
  TickerDetailModal,
  ToggleSection,
  BacktestStatus,
  EconomicCalendarSection,
  GuidelinesBanner,
  FMPPlanStatus,
  ChatCopilot,
  AccuracyPriceTargetsWithBoundary,
  PortfolioDoctorRecommendations,
  PortfolioRiskMetricsPanel,
  MarketReversalBanner,
  MarketScenarios,
  PerformanceVsBenchmark,
  ForwardTracking,
  ModelHealthStrip,
  MorningNewsletter,
  PaperTradingPanel,
  PaperVsBacktestDrift,
  PreMarketPanel,
  PreMarketStrip,
  type PreMarketData,
  RiskDashboard,
  EodAndSystemPanel,
  InsiderFlowTracker,
  TaxAwareExitPanel,
  AlertsPanel,
  RetailBriefingPanel,
  RoadmapsPanel,
  TrackRecordPanel,
  PortfolioDoctorPanel,
  BrowserPushPanel,
} from "./dashboard/index";
import { SignalTestSuite } from "./dashboard/SignalTestSuite";
import { deriveRegimeBullPctFromDashboard } from "./dashboard/retailActionUX";

const AUTO_REFRESH_MIN = 30;

function formatLastRefresh(date: Date | null): string {
  if (!date) return "—";
  return date.toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  }) + " EST";
}

function formatRefreshAgo(date: Date | null): string {
  if (!date) return "";
  const sec = Math.floor((Date.now() - date.getTime()) / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} min ago`;
  const h = Math.floor(min / 60);
  return `${h}h ago`;
}

function formatEtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return (
    d.toLocaleString("en-US", {
      timeZone: "America/New_York",
      dateStyle: "short",
      timeStyle: "short",
    }) + " EST"
  );
}

function etDateParamFromIso(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(d);
  const y = parts.find((p) => p.type === "year")?.value;
  const m = parts.find((p) => p.type === "month")?.value;
  const day = parts.find((p) => p.type === "day")?.value;
  if (!y || !m || !day) return "";
  return `${y}-${m}-${day}`;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface Props {
  data: DashboardData;
  /** Pass `true` to bypass Redis-backed cache read on the server (full recompute). */
  onRefresh: (forceRefresh?: boolean) => void | Promise<void>;
  loading: boolean;
  lastRefreshedAt?: Date | null;
}

const TAB_IDS: TabId[] = ["overview", "signals", "roadmaps", "portfolio", "opportunities", "markets", "analysis", "testsuite"];

function isValidTab(t: string): t is TabId {
  return TAB_IDS.includes(t as TabId);
}

export function Dashboard({ data, onRefresh, loading, lastRefreshedAt }: Props) {
  const router = useRouter();
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [refreshAgo, setRefreshAgo] = useState("");
  const [eodSaving, setEodSaving] = useState(false);
  const [eodMessage, setEodMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const portfolioNames = data.portfolio_names ?? (data.portfolios ? Object.keys(data.portfolios) : []);
  const defaultPortfolio = portfolioNames[0] ?? "All";
  const [selectedPortfolio, setSelectedPortfolio] = useState(defaultPortfolio);
  const selectedReport = data.portfolios?.[selectedPortfolio] ?? data.portfolio;
  const selectedTrimCandidates = (selectedReport?.per_holding ?? []).filter(
    (h) => (
      (h.action ? (h.action === "REDUCE" || h.action === "AVOID") : false) ||
      (typeof h.suggestion === "string" && h.suggestion.toLowerCase().includes("trim")) ||
      (h.score != null && h.score < 40)
    )
  );
  const preMarketFull: PreMarketData | null = (data.pre_market_full ?? null) as PreMarketData | null;

  const [activeTab, setActiveTabState] = useState<TabId>("overview");
  const [lazySignals, setLazySignals] = useState<Signal[] | null>(null);
  const [signalsFetchErr, setSignalsFetchErr] = useState<string | null>(null);
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [oppBundle, setOppBundle] = useState<{
    opportunities: Opportunity[];
    best_2026: Best2026Pick[];
    portfolio_doctor_recommendations: Record<string, PortfolioDoctorRecommendation>;
  } | null>(null);
  const [oppLoading, setOppLoading] = useState(false);
  const [oppFetchErr, setOppFetchErr] = useState<string | null>(null);

  const setActiveTab = useCallback((id: TabId) => {
    setActiveTabState(id);
    if (typeof window !== "undefined") localStorage.setItem("thrive-tab", id);
    // Keep URL clean: remove only tab param, preserve other query params
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.has("tab")) {
        params.delete("tab");
        const path = window.location.pathname + (params.toString() ? `?${params.toString()}` : "");
        router.replace(path, { scroll: false });
      }
    }
  }, [router]);

  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("thrive-tab") : null;
    const tab = (saved && isValidTab(saved)) ? saved : "overview";
    setActiveTabState(tab);
    // Clear tab from URL on load if present (e.g. shared link with ?tab=)
    if (typeof window !== "undefined" && window.location.search) {
      const params = new URLSearchParams(window.location.search);
      if (params.has("tab")) {
        params.delete("tab");
        const path = window.location.pathname + (params.toString() ? `?${params.toString()}` : "");
        router.replace(path, { scroll: false });
      }
    }
  }, [router]);

  const handleTabChange = setActiveTab;

  useEffect(() => {
    setLazySignals(null);
    setSignalsFetchErr(null);
    setOppBundle(null);
    setOppFetchErr(null);
  }, [data.as_of_date, data.signals_deferred, data.opportunities_deferred]);

  useEffect(() => {
    if (!data.signals_deferred) return;
    if (activeTab !== "signals") return;
    if (lazySignals !== null) return;
    let cancelled = false;
    setSignalsLoading(true);
    setSignalsFetchErr(null);
    const url = API_BASE ? `${API_BASE}/api/dashboard/signals-panel` : "/api/dashboard/signals-panel";
    fetch(url)
      .then((r) => {
        if (!r.ok) {
          throw new Error(
            r.status === 503
              ? "Signals cache unavailable — click Refresh on the dashboard, then open Signals again."
              : `HTTP ${r.status}`
          );
        }
        return r.json();
      })
      .then((j) => {
        if (!cancelled && Array.isArray(j.signals)) setLazySignals(j.signals);
      })
      .catch((e) => {
        if (!cancelled) setSignalsFetchErr(e instanceof Error ? e.message : "Failed to load signals");
      })
      .finally(() => {
        if (!cancelled) setSignalsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [data.signals_deferred, data.as_of_date, activeTab, lazySignals]);

  useEffect(() => {
    if (data.opportunities_deferred !== true) return;
    if (oppBundle !== null) return;
    if (activeTab !== "opportunities" && activeTab !== "portfolio") return;
    let cancelled = false;
    setOppLoading(true);
    setOppFetchErr(null);
    const url = API_BASE ? `${API_BASE}/api/dashboard/opportunities-bundle` : "/api/dashboard/opportunities-bundle";
    fetch(url)
      .then((r) => {
        if (!r.ok) {
          throw new Error(
            r.status === 503
              ? "Opportunities bundle unavailable — load the dashboard or click Refresh, then open Opportunities or Portfolio."
              : `HTTP ${r.status}`
          );
        }
        return r.json();
      })
      .then((j) => {
        if (cancelled || !j || typeof j !== "object") return;
        setOppBundle({
          opportunities: Array.isArray(j.opportunities) ? j.opportunities : [],
          best_2026: Array.isArray(j.best_2026) ? j.best_2026 : [],
          portfolio_doctor_recommendations:
            j.portfolio_doctor_recommendations && typeof j.portfolio_doctor_recommendations === "object"
              ? j.portfolio_doctor_recommendations
              : {},
        });
      })
      .catch((e) => {
        if (!cancelled) setOppFetchErr(e instanceof Error ? e.message : "Failed to load opportunities");
      })
      .finally(() => {
        if (!cancelled) setOppLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [data.opportunities_deferred, data.as_of_date, activeTab, oppBundle]);

  const effectiveSignals = useMemo(() => {
    if (!data.signals_deferred) return data.signals ?? [];
    return lazySignals ?? [];
  }, [data.signals_deferred, data.signals, lazySignals]);

  const scoreChartSignals = useMemo((): Signal[] => {
    if (!data.signals_deferred && (data.signals?.length ?? 0) > 0) return data.signals ?? [];
    if ((lazySignals?.length ?? 0) > 0) return lazySignals ?? [];
    return (data.signal_scores ?? []) as Signal[];
  }, [data.signals_deferred, data.signals, data.signal_scores, lazySignals]);

  const mergedOpportunities = oppBundle?.opportunities ?? data.opportunities ?? [];
  const mergedBest2026 = oppBundle?.best_2026 ?? data.best_2026 ?? [];
  const mergedDoctorRec = oppBundle?.portfolio_doctor_recommendations ?? data.portfolio_doctor_recommendations;

  const dataForCopilot = useMemo(
    () => ({
      ...data,
      signals: effectiveSignals,
      opportunities: mergedOpportunities,
      best_2026: mergedBest2026,
    }),
    [data, effectiveSignals, mergedOpportunities, mergedBest2026]
  );

  const signalListContext = useMemo(
    () => ({
      regimeBullPct: deriveRegimeBullPctFromDashboard({
        globalMarketRegime: data.global_market_regime,
        macroRegime: data.macro_regime,
        hmmBearPct: data.macro_regime_bundle?.hmm_bear_pct_used ?? null,
      }),
    }),
    [data.global_market_regime, data.macro_regime, data.macro_regime_bundle?.hmm_bear_pct_used]
  );

  const signalCountForBadge =
    data.signal_scores?.length ?? data.signals?.length ?? effectiveSignals.length ?? 0;

  const oppCountForBadge = mergedOpportunities.length;

  const tabBadges: Partial<Record<TabId, number>> = {
    signals: signalCountForBadge,
    portfolio: selectedReport?.per_holding?.length ?? 0,
    opportunities: oppCountForBadge,
  };

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.target && (e.target as HTMLElement).closest("input, textarea, select")) return;
      const keyToTab: Partial<Record<string, TabId>> = {
        "1": "overview", "2": "signals", "3": "portfolio", "4": "opportunities",
        "5": "markets", "6": "analysis", "7": "testsuite", "8": "roadmaps",
      };
      const id = e.key in keyToTab ? keyToTab[e.key] : null;
      if (id) {
        e.preventDefault();
        setActiveTab(id);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setActiveTab]);
  // Reset selection when data changes and current selection is no longer valid
  useEffect(() => {
    if (portfolioNames.length > 0 && !portfolioNames.includes(selectedPortfolio)) {
      setSelectedPortfolio(portfolioNames[0]);
    }
  }, [portfolioNames, selectedPortfolio]);
  // Update "X min ago" every minute when we have a last refresh time
  useEffect(() => {
    if (!lastRefreshedAt) return;
    const update = () => setRefreshAgo(formatRefreshAgo(lastRefreshedAt));
    update();
    const id = setInterval(update, 60000);
    return () => clearInterval(id);
  }, [lastRefreshedAt]);

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950">
        <div className="max-w-[min(1600px,95vw)] mx-auto px-3 sm:px-6 lg:px-8 py-3 sm:py-0 sm:h-16 flex flex-wrap items-center justify-between gap-2 sm:gap-4">
          <div className="flex items-center gap-2 min-w-0">
            <TrendingUp className="h-7 w-7 sm:h-8 sm:w-8 shrink-0 text-emerald-500" />
            <h1 className="text-lg sm:text-xl font-bold text-slate-100 truncate">Thrive Alpha</h1>
          </div>
          <div className="flex items-center gap-2 sm:gap-3 flex-wrap justify-end">
            <button
              type="button"
              onClick={() => setActiveTab("markets")}
              className="flex items-center gap-1.5 px-2.5 py-2 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800 hover:text-slate-100 text-xs sm:text-sm min-h-[44px] sm:min-h-0 touch-manipulation"
              title="Open Pre-Market Signal Engine (Markets tab)"
            >
              <Activity className="h-4 w-4 shrink-0" />
              <span className="hidden sm:inline">Pre-market</span>
            </button>
            {lastRefreshedAt && (
              <span
                className="text-xs sm:text-sm text-slate-500 hidden sm:inline"
                title={`Last refresh: ${formatLastRefresh(lastRefreshedAt)}`}
              >
                {refreshAgo || formatLastRefresh(lastRefreshedAt)}
              </span>
            )}
            {data.as_of_date && (
              <span className="text-xs text-slate-600 hidden sm:inline" title="Report timestamp (EST)">As of: {formatEtDateTime(data.as_of_date)}</span>
            )}
            <button
              onClick={() => onRefresh(true)}
              disabled={loading}
              className={clsx(
                "flex items-center gap-2 px-3 py-2.5 sm:px-4 rounded-lg font-medium transition min-h-[44px] sm:min-h-0",
                "bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 disabled:cursor-not-allowed text-sm sm:text-base"
              )}
            >
              <RefreshCw className={clsx("h-4 w-4 shrink-0", loading && "animate-spin")} />
              <span className="hidden sm:inline">{loading ? "Refreshing..." : "Refresh"}</span>
              <span className="sm:hidden">{loading ? "…" : "Refresh"}</span>
            </button>
            <button
              onClick={() => {
                if (!data) return;
                const blob = new Blob([JSON.stringify({ as_of: data.as_of_date, portfolio: data.portfolio, portfolios: data.portfolios, signals_count: signalCountForBadge, opportunities_count: oppCountForBadge }, null, 2)], { type: "application/json" });
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = `thrive-snapshot-${new Date().toISOString().slice(0, 10)}.json`;
                a.click();
                URL.revokeObjectURL(a.href);
              }}
              className="px-3 py-2.5 sm:py-2 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800 text-xs sm:text-sm min-h-[44px] sm:min-h-0 touch-manipulation"
              title="Export snapshot"
            >
              <span className="hidden sm:inline">Export snapshot</span>
              <span className="sm:hidden">Export</span>
            </button>
            <button
              onClick={async () => {
                if (!data || eodSaving) return;
                setEodMessage(null);
                setEodSaving(true);
                try {
                  const asOfEtDate = data.as_of_date ? etDateParamFromIso(data.as_of_date) : "";
                  const dateParam = asOfEtDate ? `?snapshot_date=${asOfEtDate}` : "";
                  const res = await fetch(`/api/eod/save-from-last-run${dateParam}`, { method: "POST" });
                  const json = await res.json().catch(() => ({}));
                  if (!res.ok) {
                    setEodMessage({ type: "err", text: json.detail || json.error || "Save failed" });
                    return;
                  }
                  if (json.skipped) {
                    setEodMessage({ type: "ok", text: `EOD already saved for ${json.snapshot_date}` });
                  } else {
                    setEodMessage({ type: "ok", text: `Saved ${json.snapshot_date} (${json.tickers_count} tickers)` });
                  }
                  setTimeout(() => setEodMessage(null), 4000);
                } catch (e) {
                  setEodMessage({ type: "err", text: e instanceof Error ? e.message : "Request failed" });
                } finally {
                  setEodSaving(false);
                }
              }}
              disabled={eodSaving || loading}
              className={clsx(
                "flex items-center gap-2 px-3 py-2.5 sm:py-2 rounded-lg border text-xs sm:text-sm min-h-[44px] sm:min-h-0 touch-manipulation",
                "border-slate-600 text-slate-300 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed"
              )}
              title="Save current run to data/eod/ (fast, no refresh)"
            >
              <Save className={clsx("h-4 w-4 shrink-0", eodSaving && "animate-pulse")} />
              <span className="hidden sm:inline">{eodSaving ? "Saving…" : "Save as EOD"}</span>
              <span className="sm:hidden">{eodSaving ? "…" : "EOD"}</span>
            </button>
            {eodMessage && (
              <span className={clsx("text-xs px-2 py-1 rounded", eodMessage.type === "ok" ? "text-emerald-300 bg-emerald-900/30" : "text-amber-200 bg-amber-900/30")}>
                {eodMessage.text}
              </span>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-[min(1600px,95vw)] mx-auto px-3 sm:px-6 lg:px-8 pt-3 sm:pt-4">
        <AddTickerBar onAdded={() => onRefresh(true)} />
      </div>

      {/* Compact alert strip - always visible */}
      <div className="max-w-[min(1600px,95vw)] mx-auto px-3 sm:px-6 lg:px-8 pt-3 sm:pt-4 space-y-2">
        {data.story_changes.length > 0 && <StoryAlerts items={data.story_changes} onTickerClick={setSelectedTicker} />}
        {(data.earnings_risk_count ?? 0) > 0 && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-2 flex items-center gap-2">
            <Calendar className="h-4 w-4 text-amber-400 shrink-0" />
            <p className="text-amber-200 text-sm font-medium">
              {data.earnings_risk_count} holding{data.earnings_risk_count === 1 ? "" : "s"} with earnings in next week
            </p>
          </div>
        )}
        <MarketReversalBanner overlay={data.market_reversal_overlay} />
        {data.guidelines && data.guidelines.length > 0 && <GuidelinesBanner guidelines={data.guidelines} />}
      </div>

      {/* Tab bar — desktop / tablet */}
      <div className="hidden md:block max-w-[min(1600px,95vw)] mx-auto px-3 sm:px-6 lg:px-8 pt-4 sm:pt-6">
        <DashboardTabs active={activeTab} onChange={handleTabChange} badges={tabBadges} />
      </div>

      <main className="max-w-[min(1600px,95vw)] mx-auto px-3 sm:px-6 lg:px-8 py-4 sm:py-6 pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:pb-6 overflow-x-hidden">
        <div className="rounded-xl border border-slate-800/80 bg-slate-900">
          {/* Overview tab */}
          {activeTab === "overview" && (
            <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
              {data.retail_briefing && <RetailBriefingPanel data={data} onTickerClick={setSelectedTicker} />}
              <div className="rounded-lg border border-sky-500/25 bg-sky-950/20 px-4 py-3 space-y-1">
                <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-sky-400/90">
                  <Info className="h-4 w-4 shrink-0" aria-hidden />
                  Hold vs take profits
                </h3>
                <p className="text-sm text-slate-300 leading-snug">
                  {data.morning_newsletter?.hold_vs_trade_teaser ??
                    "Unsure trim-and-rebuy vs hold 5–10 years? Tactics (targets, sell roadmap) differ from long-term strategy (tiers, fair value) — open any ticker for the full framework."}
                </p>
                <p className="text-xs text-slate-500 leading-snug">
                  {data.morning_newsletter?.hold_vs_trade_more ??
                    "Signals → pick a ticker → One answer → expand “Hold for years vs take profits”."}
                </p>
              </div>
              <ModelHealthStrip
                model_health={data.model_health}
                summary_by_signal={data.forward_tracking?.summary_by_signal}
                summary_by_horizon={data.forward_tracking?.summary_by_horizon}
                message={data.forward_tracking?.message}
              />
              {data.fmp_plan_status && <FMPPlanStatus status={data.fmp_plan_status} />}
              <ToggleSection id="overview-alerts" title="Alerts" icon={<AlertTriangle />} defaultOpen={false}>
                <AlertsPanel onTickerClick={setSelectedTicker} />
              </ToggleSection>
              {(data.macro_regime || data.macro_analog) && (
                <div className="rounded-lg border border-slate-600 bg-slate-800/30 px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                  {data.macro_regime && (
                    <span className={clsx("text-sm font-medium", data.macro_regime === "Risk-On" && "text-emerald-400", data.macro_regime === "Risk-Off" && "text-red-400", data.macro_regime === "Neutral" && "text-slate-400")}>
                      Macro: {data.macro_regime}
                    </span>
                  )}
                  {data.macro_analog?.one_liner && (
                    <div className="flex flex-col gap-1">
                      <span className="text-sm text-slate-300" title={data.macro_analog.plain_language ?? `State: ${data.macro_analog.state}, n=${data.macro_analog.n_observations}`}>
                        {data.macro_analog.one_liner}
                      </span>
                      {data.macro_analog.plain_language && (
                        <p className="text-xs text-slate-500 max-w-2xl">
                          {data.macro_analog.plain_language}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
              {data.market_forecast && (
                <div className="rounded-lg border border-emerald-500/25 bg-emerald-950/20 px-4 py-3 space-y-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-400/90">Market analysis — near-term backdrop</h3>
                  <p
                    className={clsx(
                      "text-sm font-medium",
                      data.market_forecast.bias === "cautious" && "text-amber-200",
                      data.market_forecast.bias === "constructive" && "text-emerald-200",
                      data.market_forecast.bias === "neutral" && "text-slate-200",
                    )}
                  >
                    {data.market_forecast.headline}
                  </p>
                  <ul className="list-disc list-inside text-xs text-slate-400 space-y-1 max-w-3xl">
                    {data.market_forecast.bullets.map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                  <p className="text-[10px] text-slate-600 leading-snug">{data.market_forecast.disclaimer}</p>
                </div>
              )}
              {portfolioNames.length > 1 && (
                <div className="flex items-center gap-2">
                  <label htmlFor="portfolio-select" className="text-sm text-slate-400">Portfolio:</label>
                  <select
                    id="portfolio-select"
                    value={selectedPortfolio}
                    onChange={(e) => setSelectedPortfolio(e.target.value)}
                    className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  >
                    {portfolioNames.map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                </div>
              )}
              <ToggleSection id="overview-portfolio" title="Portfolio Summary" icon={<PieChart />} defaultOpen>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <PortfolioSummary report={selectedReport} />
                </div>
                {data.portfolio_stress?.scenarios?.length ? (
                  <PortfolioStressStrip stress={data.portfolio_stress} />
                ) : null}
                {data.performance_vs_benchmark?.periods?.length ? (
                  <div className="mt-4">
                    <PerformanceVsBenchmark
                      periods={data.performance_vs_benchmark.periods}
                      message={data.performance_vs_benchmark.message}
                      as_of={data.performance_vs_benchmark.as_of}
                    />
                  </div>
                ) : data.performance_vs_benchmark?.message && (
                  <div className="mt-4">
                    <PerformanceVsBenchmark
                      periods={[]}
                      message={data.performance_vs_benchmark.message}
                    />
                  </div>
                )}
                <ModelDisclaimer className="mt-4 text-[10px] text-slate-600 leading-snug flex items-start gap-1.5 max-w-4xl" />
              </ToggleSection>
              <ToggleSection id="overview-score-regime" title="Confidence & Regime Charts" icon={<Activity />} defaultOpen>
                <AnchorChartPanel
                  title="Portfolio tape"
                  hint="One shared chart surface — click a bar to open the ticker hub. Regime mix is holdings-weighted."
                >
                  <ScoreChart signals={scoreChartSignals} onTickerClick={setSelectedTicker} embedded />
                  <RegimeChart report={selectedReport} embedded />
                </AnchorChartPanel>
              </ToggleSection>
            </div>
          )}

          {/* Signals tab */}
          {activeTab === "signals" && (
            <div className="p-4 sm:p-6 space-y-4">
          {data.data_freshness && <DataFreshnessBar data={data.data_freshness} />}
          {data.macro_regime_bundle?.coaching_note && (
            <div
              className="rounded-lg border border-amber-500/35 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-100"
              role="status"
            >
              <strong className="text-amber-200">Macro vs price:</strong> {data.macro_regime_bundle.coaching_note}
            </div>
          )}
          {data.known_limits && data.known_limits.length > 0 && <KnownLimitsPanel items={data.known_limits} />}
          {data.config?.risk_sizing && (
            <p className="text-xs text-slate-400 rounded-lg border border-slate-700/50 bg-slate-800/30 px-3 py-2">
              <strong className="text-slate-300">Risk-based sizing:</strong> each row uses{" "}
              <strong>{data.config.risk_sizing.risk_pct}%</strong> of total portfolio as the dollar risk budget if your{" "}
              <strong>{data.config.risk_sizing.stop_pct}%</strong> stop is hit. The <strong>Risk (size)</strong> column shows implied shares and notional.
            </p>
          )}
          <ModelDisclaimer className="text-[10px] text-slate-600 leading-snug flex items-start gap-1.5 max-w-4xl" />
          <ToggleSection id="signals-context" title="Context & rules" icon={<HelpCircle className="h-5 w-5" />} defaultOpen={false}>
            <div className="space-y-3">
          {(data.macro_regime === "Risk-Off" || data.market_regime?.rotation_risk === "High") && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200 text-sm">
              <strong>Do nothing guidance:</strong> When macro is Risk-Off or rotation risk is High, consider reducing new buys, stepping down tech adds, and protecting gains. Do not chase; wait for clarity.
            </div>
          )}
          <div
            className="rounded-lg border border-slate-600 bg-slate-800/30 px-4 py-3 text-sm text-slate-400"
            title={`Confidence = 7-layer score (regime, pattern, ML, options, insider, fundamental, NLP). ${LIVE_SCORE_LINE}`}
          >
            <strong className="text-slate-300">Model rules:</strong>{" "}
            Add only when confidence ≥ {data.config?.model_rules?.add_min_confidence ?? 70} and regime {data.config?.model_rules?.add_min_regime ?? "UP"}. Trim when confidence ≤ {data.config?.model_rules?.trim_max_confidence ?? 30} or regime DOWN. When rotation risk High, tech suggestions step down. Rebalance review: quarterly.{" "}
            <span className="text-slate-500" title="Open any ticker to see the 7-layer confidence breakdown.">Confidence = 7-layer score; open a ticker for details.</span>
          </div>
          {(data.macro_regime || data.global_market_regime) && (
            <p
              className={clsx(
                "text-sm font-medium mb-2 px-3 py-2 rounded-lg border inline-flex items-center gap-2 flex-wrap",
                data.macro_regime === "Risk-On" && "text-emerald-400 border-emerald-500/30 bg-emerald-500/5",
                data.macro_regime === "Risk-Off" && "text-red-400 border-red-500/30 bg-red-500/5",
                data.macro_regime === "Neutral" && "text-slate-400 border-slate-600 bg-slate-800/50",
                !data.macro_regime && "text-slate-400 border-slate-600 bg-slate-800/50"
              )}
              title="Macro: VIX/real yields. Market: SPY vs MA200 (BULL/BEAR/NEUTRAL). Affects position sizing."
            >
              <span className="inline-flex items-center gap-1.5 flex-wrap">
                {data.macro_regime && <>Macro regime: {data.macro_regime}</>}
                {data.macro_regime && data.global_market_regime && " · "}
                {data.global_market_regime && (
                  <span className={clsx(
                    data.global_market_regime === "BULL" && "text-emerald-400",
                    data.global_market_regime === "BEAR" && "text-red-400",
                    data.global_market_regime === "NEUTRAL" && "text-slate-400"
                  )}>
                    SPY regime: {data.global_market_regime}
                  </span>
                )}
                <HelpCircle className="h-3.5 w-3.5 text-slate-500 cursor-help shrink-0" aria-label="Macro regime explanation" />
              </span>
            </p>
          )}
          {data.market_regime && (data.market_regime.market_breadth || data.market_regime.tech_leadership || data.market_regime.rotation_risk) && (
            <p
              className="text-sm text-slate-300 mb-3 px-3 py-2 rounded-lg border border-slate-600 bg-slate-800/50"
              title="Breadth: participation (e.g. RSP vs SPY). Tech leadership: XLK/QQQ vs SPY trend. Rotation risk = VIX + real yields + relative strength (tech vs SPY). High = step down tech adds, favor holds."
            >
              <span className="inline-flex items-center gap-1">
                <span className="text-slate-400">Market breadth:</span> {data.market_regime.market_breadth ?? "—"}
                <HelpCircle className="h-3.5 w-3.5 text-slate-500 cursor-help shrink-0" aria-label="Market regime explanation" />
              </span>
              {" · "}
              <span className="text-slate-400">Tech leadership:</span> {data.market_regime.tech_leadership ?? "—"} &middot;{" "}
              {data.market_regime.rs_rsp_spy != null && data.market_regime.rsp_spy_trend && (
                <>
                  <span className="text-slate-400">RSP/SPY:</span>{" "}
                  <span className="text-slate-200">{data.market_regime.rs_rsp_spy.toFixed(3)}</span>{" "}
                  <span className="text-slate-500">({data.market_regime.rsp_spy_trend})</span>
                  {" · "}
                </>
              )}
              <span className={clsx(
                data.market_regime.rotation_risk === "High" && "text-amber-400",
                data.market_regime.rotation_risk === "Medium" && "text-amber-300",
                data.market_regime.rotation_risk === "Low" && "text-emerald-400"
              )}>
                Rotation risk: {data.market_regime.rotation_risk ?? "—"}
              </span>
              {data.market_regime.rotation_risk === "High" && (
                <span className="text-amber-400 text-sm block mt-1">Tech suggestions stepped down (ADD→HOLD, HOLD→CONSIDER TRIM).</span>
              )}
            </p>
          )}
          {data.pre_market?.message && data.pre_market.rotation_risk_premarket && data.pre_market.rotation_risk_premarket !== "Low" && !preMarketFull && (
            <div
              className={clsx(
                "text-sm mb-3 px-3 py-2 rounded-lg border inline-flex items-start gap-2",
                data.pre_market.rotation_risk_premarket === "High" && "text-amber-200 border-amber-500/40 bg-amber-500/10",
                data.pre_market.rotation_risk_premarket === "Medium" && "text-slate-300 border-slate-600 bg-slate-800/50"
              )}
              title="Pre-market: ES/NQ futures and mega-cap tech vs value/cyclicals. Tech red + value flat or green → rotation risk."
            >
              <HelpCircle className="h-3.5 w-3.5 text-slate-500 cursor-help shrink-0 mt-0.5" aria-label="Pre-market explanation" />
              <span>{data.pre_market.message}</span>
            </div>
          )}
          {preMarketFull && (
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <PreMarketStrip data={preMarketFull} />
              <button
                type="button"
                onClick={() => setActiveTab("markets")}
                className="text-xs text-emerald-400 hover:text-emerald-300 underline"
              >
                Open full panel →
              </button>
            </div>
          )}
          {((data.next_day_outlook?.length ?? 0) > 0 || (data.typical_move?.length ?? 0) > 0 || (data.indicator_validation?.length ?? 0) > 0) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
              {data.next_day_outlook && data.next_day_outlook.length > 0 && (
                <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-3">
                  <p className="text-sm font-medium text-slate-400 mb-0.5">Next-day outlook (SPY, QQQ, GLD, SLV)</p>
                  <p className="text-sm text-slate-500 mb-2" title="Backtest: when price/RSI/vol were in a similar state, this was the historical % of next days that closed higher and the typical next-day move range.">
                    Backtest-based: % of next days that were green in similar conditions; ±% = typical next-day move.
                  </p>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                    {data.next_day_outlook.map((o) => (
                      <span key={o.ticker}>
                        <span className="text-slate-300">{o.ticker}</span>{" "}
                        <span className={o.bias === "Bullish" ? "text-emerald-400" : o.bias === "Bearish" ? "text-red-400" : "text-slate-400"}>
                          {o.bias}
                        </span>
                        {o.pct_green != null && <span className="text-slate-500 text-sm"> ({o.pct_green}% green)</span>}
                        {o.typical_range_pct != null && <span className="text-slate-500 text-sm"> ±{o.typical_range_pct}%</span>}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {data.typical_move && data.typical_move.length > 0 && (
                <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-3">
                  <p className="text-sm font-medium text-slate-400 mb-0.5">Typical 1-day range (±1σ)</p>
                  <p className="text-sm text-slate-500 mb-1" title="Uses the last 20 trading days of returns; standard deviation (σ) scaled to one day. About 68% of the time the ETF closes within ± this % of the prior close.">
                    Based on the last 20 days of volatility. On about 2 out of 3 trading days, the ETF closes within ± this percentage of the previous close; bigger moves are less common.
                  </p>
                  <p className="text-sm text-slate-500 mb-2">
                    Example: SPY ±0.66% means most days SPY ends within 0.66% above or below the prior close. High-vol shows the range when recent volatility is elevated.
                  </p>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-base text-slate-300">
                    {data.typical_move.map((m) => (
                      <span key={m.ticker} title={`${m.ticker}: on ~68% of days the closing price is within ±${m.typical_pct_1d}% of the prior close.${m.high_vol_pct != null ? ` When volatility is high, the range widens to ±${m.high_vol_pct}%.` : ""}`}>
                        <span className="font-medium text-slate-200">{m.ticker}:</span> ±{m.typical_pct_1d}%
                        {m.high_vol_pct != null && <span className="text-amber-400 text-sm"> (high-vol: ±{m.high_vol_pct}%)</span>}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          {data.indicator_validation && data.indicator_validation.length > 0 && (
            <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-3 mb-4">
              <p className="text-sm font-medium text-slate-400 mb-0.5">Indicator validation (SPY, QQQ, GLD, SLV)</p>
              <p className="text-sm text-slate-500 mb-1" title="Compares our next-day outlook to Yahoo Finance analyst consensus.">
                Our model vs external consensus; aligned = same direction, divergent = different.
              </p>
              <p className="text-sm text-slate-500 mb-2" title="Yahoo does not provide analyst recommendations for ETFs.">
                ETFs: Yahoo does not provide analyst consensus for SPY/QQQ/GLD/SLV, so external shows "No data" by design.
              </p>
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                {data.indicator_validation.map((v) => (
                  <span key={v.ticker} className="flex items-center gap-2 flex-wrap">
                    <span className="text-slate-300 font-medium">{v.ticker}</span>
                    <span className="text-slate-400">
                      Ours: {v.our_bias ?? "—"} {v.external_rating != null ? `· ${v.source.split(" ")[0]}: ${v.external_rating}` : ""}
                    </span>
                    <span
                      className={v.status === "aligned" ? "text-emerald-400" : v.status === "divergent" ? "text-amber-400" : "text-slate-500"}
                      title={v.message}
                    >
                      {v.status === "aligned" ? "Aligned" : v.status === "divergent" ? "Divergent" : "No data"}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}
          <p className="text-base text-slate-500 mb-0">
            <span className="text-slate-400">Buy:</span> add-on · <span className="text-slate-400">Sell:</span> trim when overbought/weak · <span className="text-slate-400">Support:</span> watch level ·
            <span className="text-slate-400"> Short:</span> ~1 mo · <span className="text-slate-400">Medium:</span> ~3–6 mo · <span className="text-slate-400">Long:</span> ~12–18 mo
          </p>
            </div>
          </ToggleSection>
          {data.signals_deferred && signalsLoading && (
            <div className="rounded-xl border border-slate-700 bg-slate-900/40 px-4 py-8 text-center text-slate-400 text-sm">
              Loading full signals table…
            </div>
          )}
          {data.signals_deferred && signalsFetchErr && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-amber-200 text-sm">
              {signalsFetchErr}
            </div>
          )}
          {(!data.signals_deferred || lazySignals !== null) && (
            <SignalsTable
              signals={effectiveSignals}
              horizons={data.config?.horizons}
              onTickerClick={setSelectedTicker}
              riskSizing={data.config?.risk_sizing}
              cotByTicker={data.cot_by_ticker}
              tickerActions={data.retail_briefing?.ticker_actions}
              listContext={signalListContext}
            />
          )}
            </div>
          )}

          {/* Roadmaps tab */}
          {activeTab === "roadmaps" && (
            <div className="p-4 sm:p-6 space-y-4">
              <RoadmapsPanel
                tickers={
                  data.watchlist ??
                  data.signal_scores?.map((s) => s.ticker).filter(Boolean) ??
                  data.signals?.map((s) => s.ticker) ??
                  []
                }
                onTickerClick={setSelectedTicker}
              />
            </div>
          )}

          {/* Portfolio tab */}
          {activeTab === "portfolio" && (
            <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
              {portfolioNames.length > 1 && (
                <div className="flex items-center gap-2">
                  <label htmlFor="portfolio-select-2" className="text-sm text-slate-400">Portfolio:</label>
                  <select
                    id="portfolio-select-2"
                    value={selectedPortfolio}
                    onChange={(e) => setSelectedPortfolio(e.target.value)}
                    className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  >
                    {portfolioNames.map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                </div>
              )}
              {/* Portfolio Doctor v2 — answers "what do I do this week?" first */}
              <ToggleSection id="portfolio-doctor-v2" title="Portfolio Doctor" icon={<Target />} badge={data.portfolio_doctor_v2?.priority_actions?.total_actions || undefined} defaultOpen>
                <PortfolioDoctorPanel
                  data={data.portfolio_doctor_v2}
                  portfolioRiskMetrics={data.portfolio_risk_metrics}
                  portfolioBeta={data.portfolio_doctor_v2?.portfolio_beta}
                  taxAwareExits={data.tax_aware_exits}
                  totalValue={selectedReport?.total_value}
                  holdingCount={selectedReport?.per_holding?.length}
                  sectorExposure={selectedReport?.sector_allocation}
                  holdings={selectedReport?.per_holding}
                  onTickerClick={setSelectedTicker}
                />
              </ToggleSection>
              <ToggleSection id="portfolio-summary" title="Portfolio Summary" icon={<PieChart />} defaultOpen>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <PortfolioSummary report={selectedReport} />
                </div>
                {data.portfolio_stress?.scenarios?.length ? (
                  <PortfolioStressStrip stress={data.portfolio_stress} />
                ) : null}
              </ToggleSection>
              <ToggleSection id="portfolio-regime" title="Regime Chart" icon={<Activity />} defaultOpen>
                <RegimeChart report={selectedReport} />
              </ToggleSection>
              <ToggleSection id="portfolio-holdings" title="Holdings" icon={<Wallet />} badge={selectedReport?.per_holding?.length ?? 0} defaultOpen>
                {(selectedReport?.per_holding?.length ?? 0) > 0 ? (
                  <PortfolioHoldings
                    holdings={selectedReport?.per_holding ?? []}
                    onTickerClick={setSelectedTicker}
                    hideAccountColumn={selectedPortfolio !== "All"}
                    addMinConfidence={data.config?.model_rules?.add_min_confidence ?? 70}
                    trimMaxConfidence={data.config?.model_rules?.trim_max_confidence ?? 30}
                  />
                ) : (
                  <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-6 text-center">
                    <Wallet className="h-8 w-8 text-slate-500 mx-auto mb-2 opacity-60" />
                    <p className="text-slate-400 text-sm">No holdings</p>
                    <p className="text-slate-500 text-xs mt-1">Add portfolios in config or upload via the bar above.</p>
                  </div>
                )}
              </ToggleSection>
              <ToggleSection id="portfolio-trim" title="Consider Trim" icon={<AlertTriangle />} badge={selectedTrimCandidates.length || undefined} defaultOpen>
                {selectedTrimCandidates.length > 0 ? (
                  <TrimCandidates items={selectedTrimCandidates} onTickerClick={setSelectedTicker} />
                ) : (
                  <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-6 text-center">
                    <AlertTriangle className="h-8 w-8 text-slate-500 mx-auto mb-2 opacity-60" />
                    <p className="text-slate-400 text-sm">No trim candidates</p>
                    <p className="text-slate-500 text-xs mt-1">Positions with action REDUCE/AVOID (or score {'<'} 40 fallback) will appear here.</p>
                  </div>
                )}
              </ToggleSection>
              <ToggleSection id="portfolio-tax-exit" title="Tax-Aware Exit Optimizer" icon={<Calendar />} badge={data.tax_aware_exits?.items?.length ?? 0} defaultOpen>
                <TaxAwareExitPanel data={data.tax_aware_exits} onTickerClick={setSelectedTicker} />
              </ToggleSection>
              <ToggleSection
                id="portfolio-doctor-legacy"
                title="Trim / Add Recommendations"
                icon={<Target />}
                badge={
                  (mergedDoctorRec?.[selectedPortfolio]?.trim?.length ?? 0) +
                    (mergedDoctorRec?.[selectedPortfolio]?.add?.length ?? 0) || undefined
                }
                defaultOpen={false}
              >
                <div className="space-y-6">
                  {data.opportunities_deferred === true && oppLoading && (
                    <p className="text-xs text-slate-500">Loading add ideas (opportunity scan)…</p>
                  )}
                  {data.opportunities_deferred === true && oppFetchErr && (
                    <p className="text-xs text-amber-300/90">{oppFetchErr}</p>
                  )}
                  <div>
                    <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">Portfolio risk (holdings)</p>
                    <PortfolioRiskMetricsPanel metrics={data.portfolio_risk_metrics} />
                  </div>
                  <PortfolioDoctorRecommendations
                    recommendation={mergedDoctorRec?.[selectedPortfolio]}
                    selectedPortfolio={selectedPortfolio}
                    onTickerClick={setSelectedTicker}
                  />
                </div>
              </ToggleSection>
              <ToggleSection id="portfolio-risk" title="Risk Management" icon={<Shield />} defaultOpen={false}>
                <RiskDashboard
                  positionSizing={data.position_sizing}
                  drawdownSim={data.drawdown_sim}
                  exitLevels={data.exit_levels}
                  exitLevelsByHorizon={data.exit_levels_by_horizon}
                  earningsImpacts={data.earnings_impacts}
                  concentration={data.concentration}
                  portfolioValue={selectedReport?.total_value ?? 0}
                />
              </ToggleSection>
            </div>
          )}

          {/* Opportunities tab */}
          {activeTab === "opportunities" && (
            <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
              {data.opportunities_deferred === true && oppLoading && (
                <div className="rounded-lg border border-slate-700 bg-slate-900/40 px-4 py-3 text-slate-400 text-sm">
                  Loading daily opportunities and Best 2026…
                </div>
              )}
              {data.opportunities_deferred === true && oppFetchErr && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-amber-200 text-sm">{oppFetchErr}</div>
              )}
              <ToggleSection id="opps-daily" title="Daily Opportunities" icon={<Sparkles />} badge={mergedOpportunities.length} defaultOpen>
                {mergedOpportunities.length ? (
                  <Opportunities items={mergedOpportunities} onTickerClick={setSelectedTicker} />
                ) : (
                  <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-8 text-center">
                    <Sparkles className="h-10 w-10 text-slate-500 mx-auto mb-2 opacity-60" />
                    <p className="text-slate-400 font-medium">
                      {data.opportunities_deferred === true && oppLoading ? "Loading…" : "No opportunities today"}
                    </p>
                    <p className="text-slate-500 text-sm mt-1">Tickers with score ≥ 70 and UP regime will appear here.</p>
                  </div>
                )}
              </ToggleSection>
              {mergedBest2026.length ? (
                <ToggleSection id="opps-best-2026" title="Best 2026 picks" icon={<Target />} badge={mergedBest2026.length} defaultOpen>
                  <Best2026Section items={mergedBest2026} onTickerClick={setSelectedTicker} />
                </ToggleSection>
              ) : null}
              {data.thesis_check.length > 0 && (
                <ToggleSection id="opps-thesis" title="Thesis check" icon={<FileText />} badge={data.thesis_check.length} defaultOpen>
                  <ThesisCheck items={data.thesis_check} onTickerClick={setSelectedTicker} />
                </ToggleSection>
              )}
              {data.what_changed.length > 0 && (
                <ToggleSection id="opps-what-changed" title="What changed" icon={<RefreshCw />} badge={data.what_changed.length} defaultOpen>
                  <WhatChanged items={data.what_changed} onTickerClick={setSelectedTicker} />
                </ToggleSection>
              )}
              <ToggleSection
                id="opps-insider-flow"
                title="Insider & Institutional Flow"
                icon={<TrendingUp />}
                badge={data.insider_flow?.insider_buys?.length ?? 0}
                defaultOpen
              >
                <InsiderFlowTracker data={data.insider_flow} />
              </ToggleSection>
            </div>
          )}

          {/* Markets tab */}
          {activeTab === "markets" && (
            <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
              <ToggleSection id="markets-newsletter" title="Morning newsletter" icon={<Mail className="h-5 w-5" />} defaultOpen>
                <MorningNewsletter data={data.morning_newsletter ?? undefined} />
              </ToggleSection>
              <ModelHealthStrip
                model_health={data.model_health}
                summary_by_signal={data.forward_tracking?.summary_by_signal}
                summary_by_horizon={data.forward_tracking?.summary_by_horizon}
                message={data.forward_tracking?.message}
              />
              <ToggleSection id="markets-premarket" title="Pre-Market Signal Engine" icon={<Activity />} defaultOpen={false}>
                <PreMarketPanel data={preMarketFull ?? undefined} apiEndpoint="/api/pre-market" />
              </ToggleSection>
              <ToggleSection id="markets-scenarios" title="Market scenarios (what-if)" icon={<Target />} badge={data.market_scenarios?.length ?? 0} defaultOpen>
                <MarketScenarios scenarios={data.market_scenarios ?? []} />
              </ToggleSection>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 min-w-0 items-start">
                {data.crypto?.length ? (
                  <div className="min-w-0">
                    <ToggleSection id="markets-crypto" title="Crypto" icon={<Globe />} badge={data.crypto.length} defaultOpen>
                      <CryptoSection items={data.crypto} />
                    </ToggleSection>
                  </div>
                ) : null}
                {data.cross_asset?.length ? (
                  <div className="min-w-0">
                    <ToggleSection id="markets-cross-asset" title="Cross-asset" icon={<Globe />} badge={data.cross_asset.length} defaultOpen>
                      <CrossAssetSection items={data.cross_asset} />
                    </ToggleSection>
                  </div>
                ) : null}
                <div className="min-w-0">
                  <ToggleSection id="markets-calendar" title="Economic calendar" icon={<Calendar />} badge={data.economic_calendar?.length ?? 0} defaultOpen>
                    <EconomicCalendarSection events={data.economic_calendar ?? []} />
                  </ToggleSection>
                </div>
              </div>
              {(!data.crypto?.length && !data.cross_asset?.length) && (
                <p className="text-slate-500 text-sm">No market data. Check Opportunities tab for Best 2026 picks.</p>
              )}
            </div>
          )}

          {/* Analysis tab */}
          {activeTab === "analysis" && (
            <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
              <ToggleSection id="analysis-eod-system" title="EOD snapshots &amp; system" icon={<Database />} defaultOpen={false}>
                <EodAndSystemPanel
                  eodSnapshots={data.eod_snapshots ?? []}
                  redisStatus={data.redis_status}
                  onRefresh={onRefresh}
                />
              </ToggleSection>
              <ToggleSection id="analysis-backtest" title="Backtesting" icon={<BarChart3 />} defaultOpen={false}>
                <BacktestStatus />
              </ToggleSection>
              <ToggleSection id="analysis-price-target" title="Price target accuracy" icon={<Target />} defaultOpen={false}>
                <AccuracyPriceTargetsWithBoundary />
              </ToggleSection>
              {data.indicator_comparisons && data.indicator_comparisons.length > 0 && (
                <ToggleSection id="analysis-indicator" title="Indicator comparison" icon={<Activity />} badge={data.indicator_comparisons.length} defaultOpen>
                  <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-3">
                    <p className="text-sm text-slate-500 mb-2">Close, RSI, MA, MACD vs external APIs.</p>
                    <div className="overflow-x-auto [-webkit-overflow-scrolling:touch]">
                      <table className="w-full text-sm text-left border-collapse min-w-[480px]">
                        <thead>
                          <tr className="text-slate-500 border-b border-slate-600">
                            <th className="sticky top-0 left-0 z-[30] min-w-[4.5rem] w-24 py-1.5 pr-2 font-medium bg-slate-800 border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]">Ticker</th>
                            <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800">Close</th>
                            <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800">RSI</th>
                            <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800">MA</th>
                            <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800">MACD</th>
                            <th className="sticky top-0 z-[20] py-1.5 pr-2 font-medium bg-slate-800">Bias</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.indicator_comparisons.map((c) => (
                            <tr key={c.ticker} className="group border-b border-slate-700/50 hover:bg-slate-800/30">
                              <td className="sticky left-0 z-[10] min-w-[4.5rem] w-24 py-2 pr-2 font-medium text-slate-300 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30">{c.ticker}</td>
                              <td className="py-2 pr-2 text-slate-400">{c.close.comparisons.length > 0 ? `${c.close.comparisons.map((x) => `${x.source}: ${x.margin_pct != null ? `${x.margin_pct.toFixed(2)}%` : "—"}`).join("; ")}` : "—"}</td>
                              <td className="py-2 pr-2 text-slate-400">{c.rsi.comparisons.length > 0 ? c.rsi.comparisons.map((x) => `${x.source}: ±${x.margin_abs ?? "—"}`).join("; ") : "—"}</td>
                              <td className="py-2 pr-2 text-slate-400">{c.ma?.comparisons?.length ? c.ma.comparisons.map((m) => `${m.series}: ${m.margin_pct != null ? `${m.margin_pct.toFixed(2)}%` : "—"}`).join("; ") : "—"}</td>
                              <td className="py-2 pr-2 text-slate-400">{c.macd?.comparisons?.length ? c.macd.comparisons.map((x) => `${x.source}: ±${x.margin_abs ?? "—"}`).join("; ") : "—"}</td>
                              <td className="py-2 pr-2">{c.bias.comparisons.map((b) => <span key={b.source} className={b.status === "aligned" ? "text-emerald-400" : b.status === "divergent" ? "text-amber-400" : "text-slate-500"}>{b.source}: {b.rating ?? "—"}</span>)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </ToggleSection>
              )}
              {(data.forward_tracking?.records?.length ?? 0) > 0 && (
                <ToggleSection id="analysis-forward" title="Forward tracking" icon={<RefreshCw />} badge={data.forward_tracking?.records?.length ?? 0} defaultOpen>
                  <ForwardTracking
                    records={data.forward_tracking!.records}
                    summary_by_horizon={data.forward_tracking!.summary_by_horizon ?? {}}
                    summary_by_signal={data.forward_tracking!.summary_by_signal ?? {}}
                    message={data.forward_tracking?.message}
                  />
                </ToggleSection>
              )}
              <ToggleSection id="analysis-track-record" title="Track record" icon={<Target />} defaultOpen>
                <TrackRecordPanel
                  calibration={(data as any).confidence_calibration ?? null}
                  paperTrading={data.paper_trading?.summary ?? null}
                  forwardSummary={data.forward_tracking?.summary_by_signal ?? null}
                  modelHealth={data.model_health ?? null}
                  equityCurve={data.paper_trading?.equity_curve ?? null}
                />
              </ToggleSection>
              <ToggleSection id="analysis-browser-push" title="Browser push" icon={<Bell />} defaultOpen={false}>
                <BrowserPushPanel />
              </ToggleSection>
              {(data.paper_trading || data.paper_vs_backtest_drift) && (
                <ToggleSection
                  id="analysis-paper"
                  title="Paper trading"
                  icon={<FlaskConical />}
                  badge={data.paper_trading?.summary?.completed ?? undefined}
                  defaultOpen={false}
                >
                  {data.paper_vs_backtest_drift && (
                    <PaperVsBacktestDrift drift={data.paper_vs_backtest_drift} />
                  )}
                  {data.paper_trading && <PaperTradingPanel data={data} />}
                </ToggleSection>
              )}
              {data.forward_tracking?.message && !data.forward_tracking?.records?.length && (
                <ToggleSection id="analysis-forward-msg" title="Forward tracking" icon={<RefreshCw />} defaultOpen>
                  <ForwardTracking
                    records={[]}
                    summary_by_horizon={{}}
                    summary_by_signal={{}}
                    message={data.forward_tracking.message}
                  />
                </ToggleSection>
              )}
              {data.model_validation && (data.model_validation.records?.length ?? 0) > 0 && (
                <ToggleSection id="analysis-model" title="Model validation" icon={<Activity />} badge={data.model_validation?.records?.length ?? 0} defaultOpen>
                  <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-3">
                    {data.model_validation.summary && (
                      <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-300 mb-2">
                        {data.model_validation.summary.direction_accuracy_pct != null && (
                          <span>Direction: <strong className="text-emerald-400">{data.model_validation.summary.direction_accuracy_pct}%</strong></span>
                        )}
                        {data.model_validation.summary.range_hit_rate_pct != null && (
                          <span>Range: <strong className="text-emerald-400">{data.model_validation.summary.range_hit_rate_pct}%</strong></span>
                        )}
                      </div>
                    )}
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm text-left">
                        <thead>
                          <tr className="text-slate-500 border-b border-slate-600">
                            <th className="py-1.5 pr-2">As of</th>
                            <th className="py-1.5 pr-2">Ticker</th>
                            <th className="py-1.5 pr-2">Bias</th>
                            <th className="py-1.5 pr-2">Actual %</th>
                            <th className="py-1.5 pr-2">Hit</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(data.model_validation.records ?? []).slice(0, 20).map((r) => (
                            <tr key={`${r.as_of_date}-${r.ticker}`} className="border-b border-slate-700/50">
                              <td className="py-2 pr-2 text-slate-400">{r.as_of_date}</td>
                              <td className="py-2 pr-2 font-medium text-slate-300">{r.ticker}</td>
                              <td className="py-2 pr-2 text-slate-400">{r.our_bias ?? "—"}</td>
                              <td className={r.actual_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}>{r.actual_return_pct >= 0 ? "+" : ""}{r.actual_return_pct.toFixed(2)}%</td>
                              <td className="py-2 pr-2">{r.direction_hit === true ? "Yes" : r.direction_hit === false ? "No" : "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </ToggleSection>
              )}
            </div>
          )}

          {/* ── Test Suite tab ── */}
          {activeTab === "testsuite" && (
            <div className="p-4 sm:p-6">
              <SignalTestSuite />
            </div>
          )}
        </div>
      </main>

      {selectedTicker && (
        <TickerDetailModal ticker={selectedTicker} onClose={() => setSelectedTicker(null)} />
      )}

      <div className="md:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-slate-800 shadow-[0_-8px_24px_rgba(0,0,0,0.35)]">
        <DashboardTabs active={activeTab} onChange={handleTabChange} badges={tabBadges} variant="bottom" />
      </div>

      <ChatCopilot data={dataForCopilot} />
    </div>
  );
}
