"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, BarChart3, Bell, Calendar, ClipboardCheck, Crosshair, Database, Info, RefreshCw, Save, TrendingUp, Wallet, Target, FileText, Sparkles, HelpCircle, Globe, PieChart, Activity, Shield, FlaskConical, Mail, Terminal } from "lucide-react";
import type {
  DashboardData,
  Signal,
  Opportunity,
  PortfolioDoctorRecommendation,
} from "@/app/page";
import { LIVE_SCORE_LINE } from "@/lib/modelSemantics";
import { formatSnapshotAge, formatSnapshotEt, formatFreshnessLabel, isUsEquityRth } from "@/lib/dashboardCache";
import { clsx } from "clsx";
import {
  AddTickerBar,
  CalibrationCurvePanel,
  CryptoSection,
  PreIpoSection,
  CrossAssetSection,
  DashboardTabs,
  type TabId,
  TodaysMovesPanel,
  buildTodayMoves,
  todayMoveTickers,
  PortfolioSummary,
  PortfolioStressStrip,
  DataFreshnessBar,
  KnownLimitsPanel,
  ModelDisclaimer,
  SignalsTable,
  PortfolioHeatMap,
  PortfolioHoldings,
  TrimCandidates,
  Opportunities,
  IncomeBookPanel,
  ThesisCheck,
  WhatChanged,
  RegimeChart,
  ScoreChart,
  AnchorChartPanel,
  TickerDetailModal,
  ToggleSection,
  BacktestStatus,
  TrackRecordFramework,
  EconomicCalendarSection,
  GuidelinesBanner,
  FMPPlanStatus,
  ChatCopilot,
  AccuracyPriceTargetsWithBoundary,
  PortfolioDoctorRecommendations,
  PortfolioRiskMetricsPanel,
  RiskProfileSelector,
  MarketReversalBanner,
  MarketScenarios,
  PerformanceVsBenchmark,
  ForwardTracking,
  ModelAuditPanel,
  ModelHealthStrip,
  MorningNewsletter,
  PaperTradingPanel,
  PaperVsBacktestDrift,
  AnalysisSectionEmpty,
  ANALYSIS_LOAD_HINTS,
  PreMarketPanel,
  PreMarketStrip,
  type PreMarketData,
  RiskDashboard,
  EodAndSystemPanel,
  ApiEndpointsPanel,
  InsiderFlowTracker,
  TaxAwareExitPanel,
  AlertsPanel,
  OverviewAtAGlance,
  RoadmapsPanel,
  MarketStatePanel,
  RetailMarketDecisionsPanel,
  TrackRecordPanel,
  PortfolioDoctorPanel,
  BrowserPushPanel,
  TacticalBreakoutStrip,
  EventRiskStrip,
  HunterPanel,
  InstitutionalInsightsPanel,
  TradingViewWidget,
  CopyTradePlanButton,
  DecisionJournalPanel,
  LensTrackRecordStrip,
  DegradedDataBanner,
} from "./dashboard/index";
import { SignalTestSuite } from "./dashboard/SignalTestSuite";
import { SignalUniversePanel } from "./dashboard/SignalUniversePanel";
import { deriveRegimeBullPctFromDashboard } from "./dashboard/retailActionUX";
import {
  defaultPresetForLens,
  getTradingLens,
  setTradingLens,
  type TradingLens,
} from "@/lib/tradingLens";
import { saveSignalsPreset } from "@/lib/signalPresets";
import { TradingLensSelector } from "./dashboard/TradingLensSelector";
import { LivePricesProvider } from "@/lib/LivePriceContext";

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
  isRefreshing?: boolean;
  stale?: boolean;
  lastRefreshedAt?: Date | null;
}

const TAB_IDS: TabId[] = ["overview", "signals", "roadmaps", "portfolio", "opportunities", "income", "markets", "analysis"];

function isValidTab(t: string): t is TabId {
  return TAB_IDS.includes(t as TabId);
}

export function Dashboard({ data, onRefresh, loading, isRefreshing = false, stale = false, lastRefreshedAt }: Props) {
  const router = useRouter();
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [modalInitialTab, setModalInitialTab] = useState<"today" | "levels" | "why">("today");
  const openTickerDetail = useCallback((ticker: string, tab?: "today" | "levels" | "why") => {
    setModalInitialTab(tab ?? "today");
    setSelectedTicker(ticker);
  }, []);
  const [refreshAgo, setRefreshAgo] = useState("");
  const [eodSaving, setEodSaving] = useState(false);
  const [eodMessage, setEodMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const portfolioNames = data.portfolio_names ?? (data.portfolios ? Object.keys(data.portfolios) : []);
  const defaultPortfolio = portfolioNames[0] ?? "All";
  const [selectedPortfolio, setSelectedPortfolio] = useState(defaultPortfolio);
  const selectedReport = data.portfolios?.[selectedPortfolio] ?? data.portfolio;
  const selectedTrimCandidates = (selectedReport?.per_holding ?? []).filter((h) => {
    if (h.is_trim_candidate === true) return true;
    if (h.is_trim_candidate === false) return false;
    return (
      (h.action ? h.action === "REDUCE" || h.action === "AVOID" : false) ||
      (typeof h.suggestion === "string" && h.suggestion.toLowerCase().includes("trim")) ||
      (h.score != null && h.score < 40)
    );
  });
  const preMarketFull: PreMarketData | null = (data.pre_market_full ?? null) as PreMarketData | null;

  const [activeTab, setActiveTabState] = useState<TabId>("overview");
  const [overviewAlertCount, setOverviewAlertCount] = useState<number | null>(null);
  const [overviewAlertActionCount, setOverviewAlertActionCount] = useState(0);
  const marketQuadrant = data.retail_market_decisions?.market_context?.quadrant;
  const [lazySignals, setLazySignals] = useState<Signal[] | null>(null);
  const [tradingLens, setTradingLensState] = useState<TradingLens>("scout");

  const todayMovesCoveredTickers = useMemo(() => {
    const signals = lazySignals ?? data.signals ?? [];
    const earningsSignals = signals.filter(
      (s) => s.earnings_caution || (s.earnings_days_until != null && s.earnings_days_until <= 7)
    );
    const moves = buildTodayMoves({
      storyChanges: data.story_changes,
      trimCandidates: selectedTrimCandidates.map((h) => ({
        ticker: h.ticker,
        label: h.action || h.suggestion || (h.score != null && h.score < 40 ? `Score ${Math.round(h.score)} — below trim threshold` : "Review sizing"),
        trim_source: h.trim_source,
        trim_primary_driver: h.trim_primary_driver,
        trim_triggers: h.trim_triggers,
        trim_detail: h.trim_detail,
      })),
      earningsSignals,
      afterHours: data.after_hours_earnings?.skipped
        ? undefined
        : data.after_hours_earnings?.items?.map((i) => ({
            ticker: i.ticker,
            change_pct: i.change_pct,
            post_earnings: i.post_earnings,
          })),
      macroHeadline:
        data.retail_market_decisions?.market_context?.primary_message
        ?? data.macro_analog?.one_liner
        ?? data.market_forecast?.headline
        ?? null,
      max: 3,
      lens: tradingLens,
    });
    return todayMoveTickers(moves);
  }, [
    data.story_changes,
    data.signals,
    data.after_hours_earnings,
    data.retail_market_decisions,
    data.macro_analog,
    data.market_forecast,
    lazySignals,
    selectedTrimCandidates,
    tradingLens,
  ]);

  const [signalsFetchErr, setSignalsFetchErr] = useState<string | null>(null);
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [oppBundle, setOppBundle] = useState<{
    opportunities: Opportunity[];
    portfolio_doctor_recommendations: Record<string, PortfolioDoctorRecommendation>;
  } | null>(null);
  const [oppLoading, setOppLoading] = useState(false);
  const [oppFetchErr, setOppFetchErr] = useState<string | null>(null);
  const [analysisBundle, setAnalysisBundle] = useState<Partial<DashboardData> | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisFetchErr, setAnalysisFetchErr] = useState<string | null>(null);
  const [forwardTrackingErr, setForwardTrackingErr] = useState<string | null>(null);
  const [modelAuditErr, setModelAuditErr] = useState<string | null>(null);
  const [paperTradingErr, setPaperTradingErr] = useState<string | null>(null);
  const [analysisRetryKey, setAnalysisRetryKey] = useState(0);
  const [analysisWarmingMessage, setAnalysisWarmingMessage] = useState<string | null>(null);
  const [advancedMode, setAdvancedMode] = useState(false);

  useEffect(() => {
    try {
      if (localStorage.getItem("thrive-advanced-mode") === "1") setAdvancedMode(true);
    } catch {
      /* ignore */
    }
    setTradingLensState(getTradingLens());
  }, []);

  const handleTradingLensChange = useCallback((lens: TradingLens) => {
    setTradingLensState(lens);
    setTradingLens(lens);
    saveSignalsPreset(defaultPresetForLens(lens));
  }, []);

  useEffect(() => {
    if (!advancedMode && activeTab === "analysis") {
      setActiveTabState("overview");
    }
  }, [advancedMode, activeTab]);

  const toggleAdvancedMode = () => {
    setAdvancedMode((v) => {
      const next = !v;
      try {
        localStorage.setItem("thrive-advanced-mode", next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  };

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
    const savedTab = saved === "testsuite" ? "analysis" : saved;
    const tab = (savedTab && isValidTab(savedTab)) ? savedTab : "overview";
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

  // Use refresh_ts (per-run ISO timestamp) as the primary cache-bust key; fall back to
  // as_of_date for older cache payloads that predate the refresh_ts field.
  const refreshCacheKey = (data as unknown as Record<string, unknown>).refresh_ts as string | undefined ?? data.as_of_date;

  useEffect(() => {
    setLazySignals(null);
    setSignalsFetchErr(null);
    setOppBundle(null);
    setOppFetchErr(null);
    setAnalysisBundle(null);
    setAnalysisFetchErr(null);
    setAnalysisWarmingMessage(null);
    setForwardTrackingErr(null);
    setModelAuditErr(null);
    setPaperTradingErr(null);
  }, [refreshCacheKey, data.signals_deferred, data.opportunities_deferred, data.analysis_deferred]);

  useEffect(() => {
    if (data.warming) return;
    if (!data.signals_deferred) return;
    if (activeTab !== "signals") return;
    if (lazySignals !== null) return;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    const url = API_BASE ? `${API_BASE}/api/dashboard/signals-panel` : "/api/dashboard/signals-panel";
    const SIGNALS_PANEL_TIMEOUT_MS = 45_000;
    const MAX_WARMING_RETRIES = 24; // ~2 min of 5s polls while backend recomputes

    const load = (attempt: number) => {
      if (cancelled) return;
      setSignalsLoading(true);
      setSignalsFetchErr(null);
      const ac = new AbortController();
      const kill = setTimeout(() => ac.abort(), SIGNALS_PANEL_TIMEOUT_MS);
      fetch(url, { signal: ac.signal })
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
          if (cancelled || !j || typeof j !== "object") return;
          if (j.warming) {
            if (attempt < MAX_WARMING_RETRIES) {
              retryTimer = setTimeout(() => load(attempt + 1), 5000);
              return;
            }
            setSignalsFetchErr("Signals still warming — wait a moment, then open Signals again or click Refresh.");
            return;
          }
          if (Array.isArray(j.signals) && j.signals.length === 0 && (j as unknown as Record<string, unknown>).message) {
            setSignalsFetchErr((j as unknown as Record<string, unknown>).message as string);
            return;
          }
          if (Array.isArray(j.signals) && j.signals.length > 0) {
            setLazySignals(j.signals);
            return;
          }
          if (attempt < MAX_WARMING_RETRIES) {
            retryTimer = setTimeout(() => load(attempt + 1), 5000);
            return;
          }
          setSignalsFetchErr("No signals rows yet — click Refresh, then reopen Signals.");
        })
        .catch((e) => {
          if (cancelled) return;
          const aborted = e instanceof Error && e.name === "AbortError";
          if (aborted && attempt < MAX_WARMING_RETRIES) {
            retryTimer = setTimeout(() => load(attempt + 1), 5000);
            return;
          }
          setSignalsFetchErr(
            aborted
              ? "Signals request timed out — backend may be busy. Retry in a moment or click Refresh."
              : e instanceof Error
                ? e.message
                : "Failed to load signals"
          );
        })
        .finally(() => {
          clearTimeout(kill);
          if (!cancelled && !retryTimer) setSignalsLoading(false);
        });
    };

    load(0);
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [data.warming, data.signals_deferred, refreshCacheKey, activeTab, lazySignals]);

  useEffect(() => {
    if (data.warming) return;
    if (data.opportunities_bundle_enabled === false) return;
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
        if (j.warming) return;
        setOppBundle({
          opportunities: Array.isArray(j.opportunities) ? j.opportunities : [],
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
  }, [data.warming, data.opportunities_bundle_enabled, data.opportunities_deferred, data.as_of_date, activeTab, oppBundle]);

  const analysisInShell = useMemo(() => {
    if (data.model_audit != null) return true;
    const ft = data.forward_tracking;
    if (ft == null) return false;
    return (ft.records?.length ?? 0) > 0 || Boolean(ft.message);
  }, [data.model_audit, data.forward_tracking]);

  useEffect(() => {
    if (data.warming) return;
    if (analysisBundle !== null) return;
    if (analysisInShell) return;
    if (activeTab !== "overview" && activeTab !== "analysis" && activeTab !== "markets") return;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let awaitingWarm = false;
    setAnalysisLoading(true);
    setAnalysisFetchErr(null);
    setAnalysisWarmingMessage(null);
    const url = API_BASE ? `${API_BASE}/api/dashboard/analysis-bundle` : "/api/dashboard/analysis-bundle";
    fetch(url)
      .then((r) => {
        if (!r.ok) {
          throw new Error(
            r.status === 503
              ? "Analysis data unavailable — refresh the dashboard, then open Analysis again."
              : `HTTP ${r.status}`
          );
        }
        return r.json();
      })
      .then((j) => {
        if (cancelled || !j || typeof j !== "object") return;
        if (j.warming) {
          awaitingWarm = true;
          setAnalysisWarmingMessage(
            typeof j.message === "string"
              ? j.message
              : "Analysis sections are computing in the background (usually 1–3 min)…"
          );
          retryTimer = setTimeout(() => setAnalysisRetryKey((k) => k + 1), 5_000);
          return;
        }
        setAnalysisWarmingMessage(null);
        setAnalysisBundle(j as Partial<DashboardData>);
      })
      .catch((e) => {
        if (!cancelled) setAnalysisFetchErr(e instanceof Error ? e.message : "Failed to load analysis");
      })
      .finally(() => {
        if (!cancelled) setAnalysisLoading(false);
      });
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [data.warming, data.analysis_deferred, refreshCacheKey, activeTab, analysisBundle, analysisRetryKey, analysisInShell]);

  // Heavy Analysis panels — separate lightweight endpoints (avoid monolithic bundle 502).
  useEffect(() => {
    if (data.warming) return;
    if (activeTab !== "analysis") return;

    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let awaitingWarm = false;

    const slices: Array<{
      path: string;
      key: keyof DashboardData;
      setErr: (msg: string | null) => void;
    }> = [
      { path: "analysis/forward-tracking", key: "forward_tracking", setErr: setForwardTrackingErr },
      { path: "analysis/model-audit", key: "model_audit", setErr: setModelAuditErr },
      { path: "analysis/paper-trading", key: "paper_trading", setErr: setPaperTradingErr },
    ];

    void (async () => {
      await Promise.all(
        slices.map(async ({ path, key, setErr }) => {
          try {
            const url = API_BASE ? `${API_BASE}/api/dashboard/${path}` : `/api/dashboard/${path}`;
            const r = await fetch(url);
            if (!r.ok) {
              throw new Error(
                r.status === 503
                  ? "Analysis data unavailable — refresh the dashboard, then open Analysis again."
                  : `HTTP ${r.status}`
              );
            }
            const j = (await r.json()) as Record<string, unknown>;
            if (cancelled) return;
            if (j.warming) {
              awaitingWarm = true;
              setAnalysisWarmingMessage(
                typeof j.message === "string"
                  ? j.message
                  : "Still computing analysis sections in the background…"
              );
              return;
            }
            setAnalysisWarmingMessage(null);
            if (j[key] != null) {
              setAnalysisBundle((prev) => ({ ...(prev ?? {}), [key]: j[key] }));
              setErr(null);
            }
          } catch (e) {
            if (!cancelled) {
              setErr(e instanceof Error ? e.message : "Failed to load section");
            }
          }
        })
      );
      if (!cancelled && awaitingWarm) {
        retryTimer = setTimeout(() => setAnalysisRetryKey((k) => k + 1), 5_000);
      }
    })();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [data.warming, refreshCacheKey, activeTab, analysisRetryKey]);

  const analysisNeedsFetch =
    analysisBundle === null && !analysisInShell && !analysisFetchErr;
  const analysisBundlePending = analysisNeedsFetch && !analysisLoading;
  const analysisSectionLoading = analysisNeedsFetch && analysisLoading;

  const effectiveSignals = useMemo(() => {
    if (!data.signals_deferred) return data.signals ?? [];
    return lazySignals ?? [];
  }, [data.signals_deferred, data.signals, lazySignals]);

  const scoreChartSignals = useMemo((): Signal[] => {
    if (!data.signals_deferred && (data.signals?.length ?? 0) > 0) return data.signals ?? [];
    if ((lazySignals?.length ?? 0) > 0) return lazySignals ?? [];
    return (data.signal_scores ?? []) as Signal[];
  }, [data.signals_deferred, data.signals, data.signal_scores, lazySignals]);

  const oppBundleEnabled = data.opportunities_bundle_enabled !== false;
  const mergedOpportunities = oppBundleEnabled ? (oppBundle?.opportunities ?? data.opportunities ?? []) : [];
  const mergedDoctorRec = oppBundle?.portfolio_doctor_recommendations ?? data.portfolio_doctor_recommendations;

  const insiderFlow = analysisBundle?.insider_flow ?? data.insider_flow;
  const forwardTracking = analysisBundle?.forward_tracking ?? data.forward_tracking;
  const paperTrading = analysisBundle?.paper_trading ?? data.paper_trading;
  const paperVsBacktestDrift = analysisBundle?.paper_vs_backtest_drift ?? data.paper_vs_backtest_drift;
  const regimeValidation = analysisBundle?.regime_validation ?? data.regime_validation;
  const confidenceCalibration = analysisBundle?.confidence_calibration ?? data.confidence_calibration;
  const indicatorValidation = analysisBundle?.indicator_validation ?? data.indicator_validation;
  const indicatorComparisons = analysisBundle?.indicator_comparisons ?? data.indicator_comparisons;
  const fmpPlanStatus = analysisBundle?.fmp_plan_status ?? data.fmp_plan_status;
  const modelAudit = analysisBundle?.model_audit ?? data.model_audit;

  const summaryByLens = forwardTracking?.summary_by_lens;
  const degradedSources = useMemo(() => {
    const base = data.data_freshness?.degraded_sources ?? [];
    if (!fmpPlanStatus?.unavailable?.length) return base;
    const fmpFailed = fmpPlanStatus.unavailable
      .map((u) => u.feature)
      .filter(Boolean)
      .slice(0, 3)
      .join(", ");
    const merged = [...base];
    const idx = merged.findIndex((d) => d.source === "FMP");
    const fmpEntry = {
      source: "FMP",
      status: "degraded" as const,
      message: `Probe failed: ${fmpFailed || "plan limit"}`,
    };
    if (idx >= 0) merged[idx] = fmpEntry;
    else merged.push(fmpEntry);
    return merged;
  }, [data.data_freshness?.degraded_sources, fmpPlanStatus]);
  const degradedMode =
    Boolean(data.data_freshness?.degraded_mode) || degradedSources.some((d) => d.status !== "ok");

  const analysisPanelData = useMemo(
    (): DashboardData => ({
      ...data,
      insider_flow: insiderFlow,
      forward_tracking: forwardTracking,
      paper_trading: paperTrading,
      paper_vs_backtest_drift: paperVsBacktestDrift,
      regime_validation: regimeValidation,
      confidence_calibration: confidenceCalibration,
      indicator_validation: indicatorValidation,
      indicator_comparisons: indicatorComparisons,
      fmp_plan_status: fmpPlanStatus,
      model_audit: modelAudit,
    }),
    [
      data,
      insiderFlow,
      forwardTracking,
      paperTrading,
      paperVsBacktestDrift,
      regimeValidation,
      confidenceCalibration,
      indicatorValidation,
      indicatorComparisons,
      fmpPlanStatus,
      modelAudit,
    ]
  );

  const dataForCopilot = useMemo(
    () => ({
      ...data,
      signals: effectiveSignals,
      opportunities: mergedOpportunities,
    }),
    [data, effectiveSignals, mergedOpportunities]
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

  /** Portfolio holdings first, then watchlist-only — matches backend signal_universe. */
  const roadmapTickers = useMemo(() => {
    const universe = data.signal_universe ?? data.watchlist ?? [];
    const holdingTickers = (selectedReport?.per_holding ?? data.portfolio?.per_holding ?? [])
      .map((h) => h.ticker)
      .filter(Boolean) as string[];
    const seen = new Set<string>();
    const ordered: string[] = [];
    for (const t of holdingTickers) {
      const u = String(t).toUpperCase();
      if (!seen.has(u)) {
        ordered.push(u);
        seen.add(u);
      }
    }
    for (const t of universe) {
      const u = String(t).toUpperCase();
      if (!seen.has(u)) {
        ordered.push(u);
        seen.add(u);
      }
    }
    return ordered;
  }, [
    data.signal_universe,
    data.watchlist,
    selectedReport?.per_holding,
    data.portfolio?.per_holding,
  ]);

  const portfolioTickerList = useMemo(
    () =>
      (selectedReport?.per_holding ?? data.portfolio?.per_holding ?? [])
        .map((h) => h.ticker)
        .filter(Boolean) as string[],
    [selectedReport?.per_holding, data.portfolio?.per_holding],
  );

  const watchlistTickerList = useMemo(() => data.watchlist ?? [], [data.watchlist]);

  // All tickers visible in the current dashboard session — deduped for live-price polling
  const livePriceTickers = useMemo(() => {
    const seen: Record<string, true> = {};
    const out: string[] = [];
    const add = (t: string) => { if (t && !seen[t]) { seen[t] = true; out.push(t); } };
    for (const s of effectiveSignals) s.ticker && add(String(s.ticker).toUpperCase());
    for (const t of portfolioTickerList) t && add(t.toUpperCase());
    for (const o of mergedOpportunities) o.ticker && add(String(o.ticker).toUpperCase());
    return out;
  }, [effectiveSignals, portfolioTickerList, mergedOpportunities]);

  const signalsByTicker = useMemo(() => {
    const m = new Map<string, (typeof effectiveSignals)[number]>();
    for (const s of effectiveSignals) {
      if (s.ticker) m.set(String(s.ticker).toUpperCase(), s);
    }
    return m;
  }, [effectiveSignals]);

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
        "5": "markets", "6": "analysis", "7": "roadmaps", "8": "income",
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

  const snapshotIso = data.data_freshness?.snapshot_updated_at ?? data.as_of_date ?? null;
  const [snapshotAge, setSnapshotAge] = useState(() => formatSnapshotAge(snapshotIso));
  useEffect(() => {
    const tick = () => setSnapshotAge(formatSnapshotAge(snapshotIso));
    tick();
    const id = setInterval(tick, 60000);
    return () => clearInterval(id);
  }, [snapshotIso]);

  return (
    <LivePricesProvider tickers={livePriceTickers}>
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
                className="text-xs sm:text-sm text-slate-500 hidden md:inline"
                title={`Browser fetched: ${formatLastRefresh(lastRefreshedAt)}`}
              >
                Fetched {refreshAgo || formatLastRefresh(lastRefreshedAt)}
              </span>
            )}
            {snapshotIso && (
              <span
                className="text-xs hidden lg:inline font-mono text-slate-500"
                title={
                  data.data_freshness?.quotes_updated_at || data.data_freshness?.signals_updated_at
                    ? `Prices ${formatSnapshotEt(data.data_freshness?.quotes_updated_at ?? undefined) ?? "—"} · Signals ${formatSnapshotEt(data.data_freshness?.signals_updated_at ?? undefined) ?? "—"}`
                    : `Server snapshot saved ${formatSnapshotEt(snapshotIso)}`
                }
              >
                {data.data_freshness?.quotes_updated_at || data.data_freshness?.signals_updated_at
                  ? `${isUsEquityRth() ? "" : "After close · "}Prices ${formatFreshnessLabel(data.data_freshness?.quotes_updated_at ?? undefined) || "—"} · Signals ${formatFreshnessLabel(data.data_freshness?.signals_updated_at ?? undefined) || "—"}`
                  : `${isUsEquityRth() ? "Snapshot" : "After close"} ${formatFreshnessLabel(snapshotIso) || snapshotAge || "—"}`}
              </span>
            )}
            <TradingLensSelector
              lens={tradingLens}
              onChange={handleTradingLensChange}
              compact
              className="hidden lg:flex"
            />
            <button
              type="button"
              onClick={toggleAdvancedMode}
              className={clsx(
                "flex items-center gap-1.5 px-2.5 py-2 rounded-lg border text-xs sm:text-sm min-h-[44px] sm:min-h-0 touch-manipulation",
                advancedMode
                  ? "border-violet-500/40 bg-violet-500/10 text-violet-200"
                  : "border-slate-600 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              )}
              title="Show Analysis and Test Suite tabs"
            >
              <FlaskConical className="h-4 w-4 shrink-0" />
              <span className="hidden sm:inline">{advancedMode ? "Advanced on" : "Advanced"}</span>
            </button>
            {advancedMode && (
              <button
                onClick={() => onRefresh(true)}
                disabled={loading || isRefreshing}
                className={clsx(
                  "flex items-center gap-2 px-3 py-2.5 sm:px-4 rounded-lg font-medium transition min-h-[44px] sm:min-h-0",
                  "border border-slate-600 text-slate-300 hover:bg-slate-800 hover:text-slate-100 disabled:opacity-50 disabled:cursor-not-allowed text-sm sm:text-base"
                )}
                title="Force full signal recompute (usually unnecessary — data updates automatically)"
              >
                <RefreshCw className={clsx("h-4 w-4 shrink-0", (loading || isRefreshing) && "animate-spin")} />
                <span className="hidden sm:inline">{loading || isRefreshing ? "Refreshing…" : "Force refresh"}</span>
                <span className="sm:hidden">{loading || isRefreshing ? "…" : "↻"}</span>
              </button>
            )}
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
        {data.warming && (
          <div className="rounded-lg border border-slate-600/60 bg-slate-800/50 px-3 py-2 text-slate-300 text-sm flex items-center gap-2">
            <RefreshCw className="h-4 w-4 shrink-0 animate-spin" />
            <span>First load in progress — usually 1–3 minutes. Data will appear automatically.</span>
          </div>
        )}
        {isRefreshing && !data.warming && (
          <div className="rounded-lg border border-slate-600/60 bg-slate-800/50 px-3 py-2 text-slate-400 text-sm flex items-center gap-2">
            <RefreshCw className="h-4 w-4 shrink-0 animate-spin" />
            <span>Running full refresh…</span>
          </div>
        )}
        {data.data_freshness && !data.warming && (
          <DataFreshnessBar data={data.data_freshness} compact />
        )}
        <TodaysMovesPanel
          storyChanges={data.story_changes}
          trimCandidates={selectedTrimCandidates.map((h) => ({
            ticker: h.ticker,
            label: h.action || h.suggestion || (h.score != null && h.score < 40 ? `Score ${Math.round(h.score)} — below trim threshold` : "Review sizing"),
            trim_source: h.trim_source,
            trim_primary_driver: h.trim_primary_driver,
            trim_triggers: h.trim_triggers,
            trim_detail: h.trim_detail,
          }))}
          signals={lazySignals ?? data.signals ?? []}
          afterHours={
            data.after_hours_earnings?.skipped
              ? undefined
              : data.after_hours_earnings?.items?.map((i) => ({
                  ticker: i.ticker,
                  change_pct: i.change_pct,
                  post_earnings: i.post_earnings,
                }))
          }
          macroHeadline={
            data.retail_market_decisions?.market_context?.primary_message
            ?? data.macro_analog?.one_liner
            ?? data.market_forecast?.headline
            ?? null
          }
          tradingLens={tradingLens}
          onTickerClick={openTickerDetail}
          onViewAll={() => setActiveTab("signals")}
        />
        <div className="lg:hidden px-1">
          <TradingLensSelector lens={tradingLens} onChange={handleTradingLensChange} />
        </div>
        <MarketReversalBanner overlay={data.market_reversal_overlay} />
        {data.guidelines && data.guidelines.length > 0 && <GuidelinesBanner guidelines={data.guidelines} />}
      </div>

      {/* Tab bar — desktop / tablet */}
      <div className="hidden md:block max-w-[min(1600px,95vw)] mx-auto px-3 sm:px-6 lg:px-8 pt-4 sm:pt-6">
        <DashboardTabs active={activeTab} onChange={handleTabChange} badges={tabBadges} advancedMode={advancedMode} />
      </div>

      <main className="max-w-[min(1600px,95vw)] mx-auto px-3 sm:px-6 lg:px-8 py-4 sm:py-6 pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:pb-6 overflow-x-hidden">
        <div className="rounded-xl border border-slate-800/80 bg-slate-900">
          {/* Overview tab */}
          {activeTab === "overview" && (
            <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
              {(data.retail_briefing || data.retail_market_decisions) && (
                <OverviewAtAGlance
                  briefing={data.retail_briefing}
                  market={data.retail_market_decisions}
                  marketQuadrant={marketQuadrant}
                  macroBackdrop={
                    data.market_forecast
                      ? { bullets: data.market_forecast.bullets, disclaimer: data.market_forecast.disclaimer }
                      : null
                  }
                  preMarketFull={preMarketFull}
                  preMarket={data.pre_market}
                  todayMoveTickers={todayMovesCoveredTickers}
                  tradingLens={tradingLens}
                  forwardTracking={data.forward_tracking}
                  modelHealth={data.model_health}

                  paperTrading={data.paper_trading}
                  guestUniverseNote={data.universe_meta?.note ?? null}
                  tacticalSlot={
                    tradingLens === "scout" &&
                    ((data.event_risk_strip?.rows?.length ?? 0) > 0 ||
                      (data.tactical_breakouts?.length ?? 0) > 0) ? (
                      <div className="space-y-3">
                        {(data.event_risk_strip?.rows?.length ?? 0) > 0 && (
                          <EventRiskStrip
                            payload={data.event_risk_strip}
                            onTickerClick={openTickerDetail}
                          />
                        )}
                        {(data.tactical_breakouts?.length ?? 0) > 0 && (
                          <TacticalBreakoutStrip
                            rows={data.tactical_breakouts}
                            onTickerClick={openTickerDetail}
                          />
                        )}
                      </div>
                    ) : null
                  }
                  onTickerClick={openTickerDetail}
                />
              )}
              {tradingLens !== "scout" && (data.tactical_breakouts?.length ?? 0) > 0 && (
                <TacticalBreakoutStrip
                  rows={data.tactical_breakouts}
                  onTickerClick={openTickerDetail}
                />
              )}
              <ToggleSection
                id="overview-hunter"
                title="Hunter panel"
                icon={<Crosshair />}
                badge={data.hunter_panel?.candidate_count ?? 0}
                defaultOpen={(data.hunter_panel?.candidate_count ?? 0) > 0}
              >
                <HunterPanel
                  panel={data.hunter_panel}
                  portfolioTickers={portfolioTickerList}
                  watchlistTickers={watchlistTickerList}
                  onTickerClick={openTickerDetail}
                />
              </ToggleSection>
              <ToggleSection
                id="overview-alerts"
                title="Alerts"
                icon={<AlertTriangle />}
                keepMounted
                badge={
                  overviewAlertCount != null && overviewAlertCount > 0
                    ? overviewAlertActionCount > 0
                      ? overviewAlertActionCount
                      : overviewAlertCount
                    : undefined
                }
                defaultOpen={overviewAlertActionCount > 0}
              >
                <AlertsPanel
                  onTickerClick={openTickerDetail}
                  dashboardRefreshedAt={
                    lastRefreshedAt?.toISOString() ?? data.as_of_date ?? data.data_freshness?.snapshot_updated_at ?? null
                  }
                  onLoaded={(total, actionRequired) => {
                    setOverviewAlertCount(total);
                    setOverviewAlertActionCount(actionRequired);
                  }}
                />
              </ToggleSection>
              <ToggleSection
                id="overview-market-tape"
                title="Live market tape"
                icon={<Globe className="h-5 w-5" />}
                defaultOpen={false}
              >
                <MarketStatePanel compactHeader />
              </ToggleSection>
              <ModelHealthStrip
                model_health={data.model_health}
                summary_by_signal={forwardTracking?.summary_by_signal}
                summary_by_horizon={forwardTracking?.summary_by_horizon}
                message={forwardTracking?.message}
              />
              <LensTrackRecordStrip
                activeLens={tradingLens}
                summaryByLens={summaryByLens}
                loading={analysisLoading && !forwardTracking}
              />
              {degradedMode && (
                <DegradedDataBanner degradedMode={degradedMode} sources={degradedSources} compact />
              )}
              <DecisionJournalPanel />
              {fmpPlanStatus && <FMPPlanStatus status={fmpPlanStatus} />}
              {!data.retail_market_decisions?.market_context && (data.macro_regime || data.macro_analog) && (
                <div className="rounded-lg border border-slate-600 bg-slate-800/30 px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                  {data.macro_regime && (
                    <span className={clsx("text-sm font-medium", data.macro_regime === "Risk-On" && "text-emerald-400", data.macro_regime === "Risk-Off" && "text-red-400", data.macro_regime === "Neutral" && "text-slate-400")}>
                      Macro overlay (ST): {data.macro_regime}
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
              {!data.retail_market_decisions?.market_context && data.market_forecast && (
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
              <PortfolioHeatMap
                holdings={selectedReport?.per_holding ?? []}
                regimeCounts={selectedReport?.regime_counts}
                onTickerClick={openTickerDetail}
              />
              <ToggleSection id="overview-portfolio" title="Portfolio summary" icon={<PieChart />} defaultOpen>
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
              <ToggleSection id="overview-score-regime" title="Score & regime charts" icon={<Activity />} defaultOpen={false}>
                <AnchorChartPanel
                  title="Portfolio tape"
                  hint="One shared chart surface — click a bar to open the ticker hub. Regime mix is holdings-weighted."
                >
                  <ScoreChart signals={scoreChartSignals} onTickerClick={openTickerDetail} embedded />
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
          {(data.macro_regime === "Risk-Off" || data.market_regime?.rotation_risk === "High") && marketQuadrant !== "best_buy_zone" && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200 text-sm">
              <strong>Do nothing guidance:</strong> When macro is Risk-Off or rotation risk is High, consider reducing new buys, stepping down tech adds, and protecting gains. Do not chase; wait for clarity.
            </div>
          )}
          {marketQuadrant === "best_buy_zone" && (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 px-4 py-3 text-emerald-200 text-sm">
              <strong>Fear in a bull market:</strong> Short-term Risk-Off/fear can coexist with a strong bull regime — unified context above says accumulate dips, not blanket REDUCE.
            </div>
          )}
          <div
            className="rounded-lg border border-slate-600 bg-slate-800/30 px-4 py-3 text-sm text-slate-400"
            title={`Confidence = 7-layer score (regime, pattern, ML, options, insider, fundamental, NLP). ${LIVE_SCORE_LINE}`}
          >
            <strong className="text-slate-300">Model rules:</strong>{" "}
            Add when model confidence ≥ {data.config?.model_rules?.add_min_confidence ?? 70} and regime {data.config?.model_rules?.add_min_regime ?? "UP"}. Trim when confidence ≤ {data.config?.model_rules?.trim_max_confidence ?? 30} or regime DOWN. Portfolio heat map: tile color = composite chart score; ring = fused confidence (can disagree).{" "}
            <span className="text-slate-500" title="Open any ticker to see the 7-layer confidence breakdown.">Open a ticker for confidence layers vs chart score.</span>
          </div>
          {(data.macro_regime || data.global_market_regime) && (
            <p
              className={clsx(
                "text-sm font-medium mb-2 px-3 py-2 rounded-lg border inline-flex items-center gap-2 flex-wrap",
                data.macro_regime === "Risk-On" && "text-emerald-400 border-emerald-500/30 bg-emerald-500/5",
                data.macro_regime === "Risk-Off" && marketQuadrant === "best_buy_zone" && "text-sky-300 border-sky-500/30 bg-sky-950/20",
                data.macro_regime === "Risk-Off" && marketQuadrant !== "best_buy_zone" && "text-red-400 border-red-500/30 bg-red-500/5",
                data.macro_regime === "Neutral" && "text-slate-400 border-slate-600 bg-slate-800/50",
                !data.macro_regime && "text-slate-400 border-slate-600 bg-slate-800/50"
              )}
              title="Macro overlay (short-term) vs SPY regime (long-term) — see What should I do today? for unified read."
            >
              <span className="inline-flex items-center gap-1.5 flex-wrap">
                {data.macro_regime && <>Macro overlay (ST): {data.macro_regime}</>}
                {data.macro_regime && data.global_market_regime && " · "}
                {data.global_market_regime && (
                  <span className={clsx(
                    String(data.global_market_regime).includes("BULL") && "text-emerald-400",
                    String(data.global_market_regime).includes("BEAR") && "text-red-400",
                    data.global_market_regime === "NEUTRAL" && "text-slate-400"
                  )}>
                    SPY regime (LT): {String(data.global_market_regime).replace(/_/g, " ")}
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
          {(data.warming || (data.signals_deferred && signalsLoading && lazySignals === null)) && (
            <div className="rounded-xl border border-slate-700 bg-slate-900/40 px-4 py-8 text-center text-slate-400 text-sm">
              {data.warming
                ? "Waiting for first dashboard load…"
                : "Loading full signals table… (backend may still be recomputing — usually 1–5 min)"}
            </div>
          )}
          {data.signals_deferred && signalsFetchErr && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-amber-200 text-sm">
              {signalsFetchErr}
            </div>
          )}
          {(!data.signals_deferred || lazySignals !== null) && (
            <>
              {tradingLens === "scout" && (data.event_risk_strip?.rows?.length ?? 0) > 0 && (
                <EventRiskStrip payload={data.event_risk_strip} onTickerClick={openTickerDetail} />
              )}
            <SignalsTable
              signals={effectiveSignals}
              horizons={data.config?.horizons}
              onTickerClick={openTickerDetail}
              riskSizing={data.config?.risk_sizing}
              cotByTicker={data.cot_by_ticker}
              tickerActions={data.retail_briefing?.ticker_actions}
              listContext={signalListContext}
              portfolioTickers={portfolioTickerList}
              watchlistTickers={watchlistTickerList}
              tradingLens={tradingLens}
            />
            </>
          )}
          {/* EOD Universe panel — folded into SignalsTable audit columns (Jun 2026). Re-enable if cohort table needed again.
          <ToggleSection
            id="signals-eod-universe"
            title="EOD Universe — all tickers"
            icon={<Database className="h-5 w-5" />}
            defaultOpen={false}
          >
            <SignalUniversePanel onTickerClick={openTickerDetail} />
          </ToggleSection>
          */}
            </div>
          )}

          {/* Roadmaps tab */}
          {activeTab === "roadmaps" && (
            <div className="p-4 sm:p-6 space-y-4">
              <RoadmapsPanel
                warming={Boolean(data.warming)}
                tickers={roadmapTickers}
                onTickerClick={openTickerDetail}
                portfolioTickers={portfolioTickerList}
                watchlistTickers={watchlistTickerList}
                signalsByTicker={signalsByTicker}
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
              <PortfolioHeatMap
                holdings={selectedReport?.per_holding ?? []}
                regimeCounts={selectedReport?.regime_counts}
                onTickerClick={openTickerDetail}
              />
              {/* Portfolio Doctor v2 — answers "what do I do this week?" first.
                  Risk profile governs everything below it: health score context,
                  trim/add sizing, and (cross-referenced) the Tier1 Kelly engine in
                  Risk Management — one persisted setting, not three disconnected ones. */}
              <ToggleSection id="portfolio-doctor-v2" title="Portfolio Doctor" icon={<Target />} badge={data.portfolio_doctor_v2?.priority_actions?.total_actions || undefined} defaultOpen>
                <div className="mb-4">
                  <RiskProfileSelector value={data.risk_profile} onChanged={() => onRefresh(true)} />
                </div>
                <PortfolioDoctorPanel
                  data={data.portfolio_doctor_v2}
                  portfolioRiskMetrics={data.portfolio_risk_metrics}
                  portfolioBeta={data.portfolio_doctor_v2?.portfolio_beta}
                  taxAwareExits={data.tax_aware_exits}
                  totalValue={selectedReport?.total_value}
                  holdingCount={selectedReport?.per_holding?.length}
                  sectorExposure={selectedReport?.sector_allocation}
                  holdings={selectedReport?.per_holding}
                  onTickerClick={openTickerDetail}
                />
                <div className="mt-6 space-y-6">
                  {oppBundleEnabled && data.opportunities_deferred === true && oppLoading && (
                    <p className="text-xs text-slate-500">Loading add ideas (opportunity scan)…</p>
                  )}
                  {oppBundleEnabled && data.opportunities_deferred === true && oppFetchErr && (
                    <p className="text-xs text-amber-300/90">{oppFetchErr}</p>
                  )}
                  <div>
                    <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">Portfolio risk (holdings)</p>
                    <PortfolioRiskMetricsPanel metrics={data.portfolio_risk_metrics} />
                  </div>
                  <PortfolioDoctorRecommendations
                    recommendation={mergedDoctorRec?.[selectedPortfolio]}
                    selectedPortfolio={selectedPortfolio}
                    onTickerClick={openTickerDetail}
                  />
                </div>
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
                    onTickerClick={openTickerDetail}
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
                  <TrimCandidates items={selectedTrimCandidates} onTickerClick={openTickerDetail} />
                ) : (
                  <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-6 text-center">
                    <AlertTriangle className="h-8 w-8 text-slate-500 mx-auto mb-2 opacity-60" />
                    <p className="text-slate-400 text-sm">No trim candidates</p>
                    <p className="text-slate-500 text-xs mt-1">Positions with action REDUCE/AVOID (or score {'<'} 40 fallback) will appear here.</p>
                  </div>
                )}
              </ToggleSection>
              <ToggleSection id="portfolio-tax-exit" title="Tax-Aware Exit Optimizer" icon={<Calendar />} badge={data.tax_aware_exits?.items?.length ?? 0} defaultOpen>
                <TaxAwareExitPanel data={data.tax_aware_exits} onTickerClick={openTickerDetail} />
              </ToggleSection>
              <ToggleSection id="portfolio-risk" title="Risk Management" icon={<Shield />} defaultOpen={false}>
                <RiskDashboard
                  riskProfile={data.risk_profile}
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
              {oppBundleEnabled && data.opportunities_deferred === true && oppLoading && (
                <div className="rounded-lg border border-slate-700 bg-slate-900/40 px-4 py-3 text-slate-400 text-sm">
                  Loading daily opportunities…
                </div>
              )}
              {oppBundleEnabled && data.opportunities_deferred === true && oppFetchErr && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-amber-200 text-sm">{oppFetchErr}</div>
              )}
              {oppBundleEnabled ? (
                <ToggleSection id="opps-daily" title="Daily Opportunities" icon={<Sparkles />} badge={mergedOpportunities.length} defaultOpen>
                  {mergedOpportunities.length ? (
                    <Opportunities items={mergedOpportunities} onTickerClick={openTickerDetail} />
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
              ) : null}
              {data.thesis_check.length > 0 && (
                <ToggleSection id="opps-thesis" title="Thesis check" icon={<FileText />} badge={data.thesis_check.length} defaultOpen>
                  <ThesisCheck items={data.thesis_check} onTickerClick={openTickerDetail} />
                </ToggleSection>
              )}
              {data.what_changed.length > 0 && (
                <ToggleSection id="opps-what-changed" title="What changed" icon={<RefreshCw />} badge={data.what_changed.length} defaultOpen>
                  <WhatChanged items={data.what_changed} onTickerClick={openTickerDetail} />
                </ToggleSection>
              )}
              <ToggleSection
                id="opps-insider-flow"
                title="Insider & Institutional Flow"
                icon={<TrendingUp />}
                badge={insiderFlow?.insider_buys?.length ?? 0}
                defaultOpen
              >
                {data.analysis_deferred === true && analysisLoading && (
                  <p className="text-slate-500 text-sm py-4">Loading insider flow…</p>
                )}
                {data.analysis_deferred === true && analysisFetchErr && (
                  <p className="text-amber-200 text-sm py-2">{analysisFetchErr}</p>
                )}
                <InsiderFlowTracker data={insiderFlow} />
              </ToggleSection>
            </div>
          )}

          {/* Income Book tab — ad-hoc swing sleeve (separate from long-term portfolio) */}
          {activeTab === "income" && (
            <div className="p-4 sm:p-6 space-y-4">
              <ModelDisclaimer className="text-[10px] text-slate-600 leading-snug flex items-start gap-1.5 max-w-4xl" />
              <IncomeBookPanel onTickerClick={openTickerDetail} />
            </div>
          )}

          {/* Markets tab */}
          {activeTab === "markets" && (
            <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
              {data.retail_market_decisions && (
                <RetailMarketDecisionsPanel data={data.retail_market_decisions} />
              )}
              <ToggleSection id="markets-newsletter" title="Morning newsletter" icon={<Mail className="h-5 w-5" />} defaultOpen>
                <MorningNewsletter data={data.morning_newsletter ?? undefined} />
              </ToggleSection>
              <ModelHealthStrip
                model_health={data.model_health}
                summary_by_signal={forwardTracking?.summary_by_signal}
                summary_by_horizon={forwardTracking?.summary_by_horizon}
                message={forwardTracking?.message}
              />
              <ToggleSection id="markets-premarket" title="Pre-Market Signal Engine" icon={<Activity />} defaultOpen={false}>
                <PreMarketPanel data={preMarketFull ?? undefined} apiEndpoint="/api/pre-market" />
              </ToggleSection>
              <ToggleSection id="markets-scenarios" title="Market scenarios (what-if)" icon={<Target />} badge={data.market_scenarios?.length ?? 0} defaultOpen>
                <MarketScenarios scenarios={data.market_scenarios ?? []} />
              </ToggleSection>
              {data.pre_ipo?.enabled && (data.pre_ipo.items?.length ?? 0) > 0 ? (
                <ToggleSection
                  id="markets-pre-ipo"
                  title="Pre-IPO watch"
                  icon={<Sparkles />}
                  badge={data.pre_ipo.items!.length}
                  defaultOpen
                >
                  <PreIpoSection panel={data.pre_ipo} onTickerClick={openTickerDetail} />
                </ToggleSection>
              ) : null}
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
                <p className="text-slate-500 text-sm">No market data available for crypto or cross-asset panels.</p>
              )}
            </div>
          )}

          {/* Analysis tab */}
          {activeTab === "analysis" && (
            <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
              {analysisWarmingMessage && (
                <div className="rounded-lg border border-slate-600 bg-slate-900/50 px-4 py-3 text-slate-400 text-sm animate-pulse">
                  {analysisWarmingMessage}
                </div>
              )}
              {data.analysis_deferred === true && analysisLoading && (
                <div className="rounded-lg border border-slate-700 bg-slate-900/50 px-4 py-3 text-slate-400 text-sm animate-pulse">
                  Loading analysis sections…
                </div>
              )}
              {data.analysis_deferred === true && analysisFetchErr && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-amber-200 text-sm space-y-2">
                  <p>{analysisFetchErr}</p>
                  <button
                    type="button"
                    onClick={() => {
                      setAnalysisBundle(null);
                      setAnalysisFetchErr(null);
                      setAnalysisRetryKey((k) => k + 1);
                    }}
                    className="text-xs px-3 py-1.5 rounded border border-amber-500/40 text-amber-100 hover:bg-amber-500/10"
                  >
                    Retry analysis load
                  </button>
                </div>
              )}
              <TrackRecordFramework />
              <ToggleSection id="analysis-api-endpoints" title="API endpoints (ad-hoc runner)" icon={<Terminal className="h-5 w-5" />} defaultOpen={false}>
                <ApiEndpointsPanel />
              </ToggleSection>
              <ToggleSection id="analysis-eod-system" title="EOD snapshots &amp; system" icon={<Database />} defaultOpen={false}>
                <EodAndSystemPanel
                  eodSnapshots={data.eod_snapshots ?? []}
                  redisStatus={data.redis_status}
                  dataRoot={data.data_root}
                  onRefresh={onRefresh}
                />
              </ToggleSection>
              <ToggleSection id="analysis-backtest" title="(A) Historical dip edge — backtest" icon={<BarChart3 />} defaultOpen={false}>
                <BacktestStatus />
              </ToggleSection>
              <ToggleSection id="analysis-price-target" title="Price target accuracy" icon={<Target />} defaultOpen={false}>
                <AccuracyPriceTargetsWithBoundary />
              </ToggleSection>
              {indicatorComparisons && indicatorComparisons.length > 0 && (
                <ToggleSection id="analysis-indicator" title="Indicator comparison" icon={<Activity />} badge={indicatorComparisons.length} defaultOpen>
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
                          {indicatorComparisons.map((c) => (
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
              <ToggleSection
                id="analysis-model-audit"
                title="(B) 100-ticker gate audit"
                icon={<ClipboardCheck />}
                badge={
                  modelAudit?.pilot?.total_events ??
                  modelAudit?.cohort_size ??
                  (analysisSectionLoading ? "…" : undefined)
                }
                defaultOpen
              >
                {modelAudit == null && !modelAuditErr ? (
                  <AnalysisSectionEmpty loading message="Loading 100-ticker audit (background compute may take 1–3 min)…" />
                ) : modelAuditErr ? (
                  <AnalysisSectionEmpty
                    title="Could not load audit data"
                    message={modelAuditErr}
                    hints={[...ANALYSIS_LOAD_HINTS.bundle, ...ANALYSIS_LOAD_HINTS.audit100]}
                  />
                ) : (
                  <ModelAuditPanel audit={modelAudit ?? null} />
                )}
              </ToggleSection>
              <ToggleSection
                id="analysis-forward"
                title="(C) Forward outcomes — tracking"
                icon={<RefreshCw />}
                badge={
                  (forwardTracking?.records?.length ?? 0) > 0
                    ? forwardTracking!.records!.length
                    : analysisSectionLoading
                      ? "…"
                      : undefined
                }
                defaultOpen
              >
                {forwardTracking == null && !forwardTrackingErr ? (
                  <AnalysisSectionEmpty loading message="Loading forward tracking…" />
                ) : forwardTrackingErr ? (
                  <AnalysisSectionEmpty
                    title="Could not load forward tracking"
                    message={forwardTrackingErr}
                    hints={[...ANALYSIS_LOAD_HINTS.bundle, ...ANALYSIS_LOAD_HINTS.forward]}
                  />
                ) : (
                  <ForwardTracking
                    records={forwardTracking?.records ?? []}
                    summary_by_horizon={forwardTracking?.summary_by_horizon ?? {}}
                    summary_by_signal={forwardTracking?.summary_by_signal ?? {}}
                    summary_by_go_no_go={forwardTracking?.summary_by_go_no_go ?? {}}
                    summary_by_gates={forwardTracking?.summary_by_gates ?? {}}
                    summary_actionable_buy={forwardTracking?.summary_actionable_buy ?? undefined}
                    summary_by_entry_mode={forwardTracking?.summary_by_entry_mode ?? {}}
                    summary_by_model_version={forwardTracking?.summary_by_model_version ?? {}}
                    data_source_note={forwardTracking?.data_source_note ?? null}
                    message={forwardTracking?.message ?? undefined}
                    meta={forwardTracking?.meta ?? null}
                  />
                )}
              </ToggleSection>
              <ToggleSection id="analysis-calibration" title="Calibration curve" icon={<Activity />} defaultOpen>
                <CalibrationCurvePanel
                  calibration={(confidenceCalibration ?? null) as Parameters<typeof CalibrationCurvePanel>[0]["calibration"]}
                />
              </ToggleSection>
              <ToggleSection id="analysis-track-record" title="Track record" icon={<Target />} defaultOpen={false}>
                <TrackRecordPanel
                  calibration={(confidenceCalibration ?? null) as Parameters<typeof TrackRecordPanel>[0]["calibration"]}
                  paperTrading={paperTrading?.summary ?? null}
                  forwardSummary={forwardTracking?.summary_by_signal ?? null}
                  summaryByLens={summaryByLens}
                  activeLens={tradingLens}
                  modelHealth={data.model_health ?? null}
                  equityCurve={paperTrading?.equity_curve ?? null}
                  auditOutcomeSummary={modelAudit?.outcome_summary ?? null}
                />
              </ToggleSection>
              <ToggleSection id="analysis-browser-push" title="Browser push" icon={<Bell />} defaultOpen={false}>
                <BrowserPushPanel />
              </ToggleSection>
              <ToggleSection
                id="analysis-paper"
                title="(C) Paper trading — forward outcomes"
                icon={<FlaskConical />}
                badge={
                  paperTrading?.summary?.completed ??
                  (analysisSectionLoading ? "…" : undefined)
                }
                defaultOpen={false}
              >
                {paperTrading == null && !paperTradingErr ? (
                  <AnalysisSectionEmpty loading message="Loading paper trading stats…" />
                ) : paperTradingErr ? (
                  <AnalysisSectionEmpty
                    title="Could not load paper trading"
                    message={paperTradingErr}
                    hints={[...ANALYSIS_LOAD_HINTS.bundle, ...ANALYSIS_LOAD_HINTS.paper]}
                  />
                ) : (
                  <>
                    {paperVsBacktestDrift && <PaperVsBacktestDrift drift={paperVsBacktestDrift} />}
                    <PaperTradingPanel data={analysisPanelData} />
                  </>
                )}
              </ToggleSection>
              <ToggleSection id="analysis-test-suite" title="Signal test suite" icon={<FlaskConical />} defaultOpen={false}>
                <SignalTestSuite />
              </ToggleSection>
            </div>
          )}
        </div>
      </main>

      {selectedTicker && (
        <TickerDetailModal
          ticker={selectedTicker}
          initialTab={modalInitialTab}
          onClose={() => setSelectedTicker(null)}
        />
      )}

      <div className="md:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-slate-800 shadow-[0_-8px_24px_rgba(0,0,0,0.35)]">
        <DashboardTabs active={activeTab} onChange={handleTabChange} badges={tabBadges} advancedMode={advancedMode} variant="bottom" />
      </div>

      <ChatCopilot data={dataForCopilot} />
    </div>
    </LivePricesProvider>
  );
}
