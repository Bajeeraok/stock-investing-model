"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, BarChart3, Bell, Calendar, ClipboardCheck, Database, RefreshCw, Save, Search, TrendingUp, Wallet, Target, FileText, Sparkles, HelpCircle, Globe, PieChart, Activity, Shield, FlaskConical, Mail, Terminal } from "lucide-react";
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
  SubViewSwitch,
  migrateLegacyTab,
  type TabId,
  PortfolioSummary,
  PortfolioStressStrip,
  DataFreshnessBar,
  KnownLimitsPanel,
  ModelDisclaimer,
  SignalsHub,
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
  MarketStatePanel,
  RetailMarketDecisionsPanel,
  TrackRecordPanel,
  PortfolioDoctorPanel,
  BrowserPushPanel,
  EventRiskStrip,
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
import { DecisionModeSelector } from "./dashboard/DecisionModeSelector";
import { AlertsScreen, PriceAlertWatcher, priceAlertTickers } from "./dashboard/AlertsScreen";
import { subscribePriceAlerts } from "@/lib/priceAlerts";
import {
  MarketMapCard,
  MarketWeatherTeaser,
  MyBookCard,
  PortfolioTeaser,
  SinceYesterdayCard,
  ThisWeekCard,
  deriveMarketWeather,
} from "./dashboard/today/TodayFeed";
import {
  NeedsAttentionList,
  PortfolioRegimeStrip,
  PortfolioValueCard,
  RiskManagementCard,
} from "./dashboard/PortfolioOverviewCards";
import { RegimeValidationPanel } from "./dashboard/RegimeValidationPanel";
import { LivePricesProvider } from "@/lib/LivePriceContext";
import { useTickerDetailLayout } from "@/lib/useMediaQuery";

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

type DetailTab = "verdict" | "levels" | "why" | "context" | "track";
const DETAIL_TABS: DetailTab[] = ["verdict", "why", "levels", "context", "track"];

/** Ticker detail lives in the URL (?t=HAL&view=levels) so back closes it and links share. */
function readTickerFromUrl(): { ticker: string | null; view: DetailTab } {
  if (typeof window === "undefined") return { ticker: null, view: "verdict" };
  const q = new URLSearchParams(window.location.search);
  const t = (q.get("t") || "").trim().toUpperCase();
  const v = q.get("view") as DetailTab | null;
  return {
    ticker: /^[A-Z0-9.\-^=]{1,12}$/.test(t) ? t : null,
    view: v && DETAIL_TABS.includes(v) ? v : "verdict",
  };
}

function writeTickerUrl(ticker: string | null, view: DetailTab, mode: "push" | "replace"): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (ticker) {
    url.searchParams.set("t", ticker);
    if (view && view !== "verdict") url.searchParams.set("view", view);
    else url.searchParams.delete("view");
  } else {
    url.searchParams.delete("t");
    url.searchParams.delete("view");
  }
  const state = { ...(window.history.state ?? {}), thriveTicker: ticker ?? null };
  if (mode === "push") window.history.pushState(state, "", url);
  else window.history.replaceState(state, "", url);
}

type PlanSub = "income" | "opportunities";
type MoreSub = "markets" | "admin";
const PLAN_SUB_KEY = "thrive-plan-sub";
const MORE_SUB_KEY = "thrive-more-sub";

export function Dashboard({ data, onRefresh, loading, isRefreshing = false, stale = false, lastRefreshedAt }: Props) {
  const router = useRouter();
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [modalInitialTab, setModalInitialTab] = useState<DetailTab>("verdict");
  /** Desktop pane → full-width drawer ("Expand"). Reset whenever the detail closes. */
  const [detailExpanded, setDetailExpanded] = useState(false);
  const detailLayout = useTickerDetailLayout();
  const selectedTickerRef = useRef<string | null>(null);
  selectedTickerRef.current = selectedTicker;
  /** True when this session pushed the ?t= history entry — then close = history.back(). */
  const pushedDetailRef = useRef(false);

  const openTickerDetail = useCallback((ticker: string, tab?: DetailTab) => {
    const t = ticker.toUpperCase();
    const view = tab ?? "verdict";
    const alreadyOpen = selectedTickerRef.current != null;
    setModalInitialTab(view);
    setSelectedTicker(t);
    // First open pushes a history entry (back closes it); switching tickers while open
    // replaces it, so stepping through a list doesn't stack 20 back-presses.
    writeTickerUrl(t, view, alreadyOpen ? "replace" : "push");
    if (!alreadyOpen) pushedDetailRef.current = true;
  }, []);

  const closeTickerDetail = useCallback(() => {
    setDetailExpanded(false);
    if (pushedDetailRef.current && window.history.state?.thriveTicker) {
      pushedDetailRef.current = false;
      window.history.back(); // popstate clears selectedTicker
      return;
    }
    pushedDetailRef.current = false;
    setSelectedTicker(null);
    writeTickerUrl(null, "verdict", "replace");
  }, []);

  const handleDetailTabChange = useCallback((tab: DetailTab) => {
    const t = selectedTickerRef.current;
    if (t) writeTickerUrl(t, tab, "replace");
  }, []);

  // Deep link on load + browser back/forward.
  useEffect(() => {
    const syncFromUrl = () => {
      const { ticker, view } = readTickerFromUrl();
      if (!ticker) {
        pushedDetailRef.current = false;
        setDetailExpanded(false);
        setSelectedTicker(null);
        return;
      }
      setModalInitialTab(view);
      setSelectedTicker(ticker);
    };
    syncFromUrl();
    window.addEventListener("popstate", syncFromUrl);
    return () => window.removeEventListener("popstate", syncFromUrl);
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

  const [activeTab, setActiveTabState] = useState<TabId>("today");
  const [planSub, setPlanSub] = useState<PlanSub>("income");
  const [moreSub, setMoreSub] = useState<MoreSub>("markets");
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [riskReportKey, setRiskReportKey] = useState(0);
  const [overviewAlertCount, setOverviewAlertCount] = useState<number | null>(null);
  const [overviewAlertActionCount, setOverviewAlertActionCount] = useState(0);
  const marketQuadrant = data.retail_market_decisions?.market_context?.quadrant;
  const [lazySignals, setLazySignals] = useState<Signal[] | null>(null);
  const [tradingLens, setTradingLensState] = useState<TradingLens>("scout");

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
    let saved: string | null = null;
    let urlTab: string | null = null;
    try {
      saved = localStorage.getItem("thrive-tab");
      urlTab = new URLSearchParams(window.location.search).get("tab");
      const ps = localStorage.getItem(PLAN_SUB_KEY);
      if (ps === "income" || ps === "opportunities") setPlanSub(ps);
      const ms = localStorage.getItem(MORE_SUB_KEY);
      if (ms === "markets" || ms === "admin") setMoreSub(ms);
    } catch {
      /* ignore */
    }
    // Old 7-tab ids (Overview/Opportunities/Income/Markets/Analysis) map onto the 5-tab IA.
    const migrated = migrateLegacyTab(urlTab) ?? migrateLegacyTab(saved) ?? { tab: "today" as TabId };
    setActiveTabState(migrated.tab);
    if (migrated.sub === "income" || migrated.sub === "opportunities") setPlanSub(migrated.sub);
    if (migrated.sub === "markets" || migrated.sub === "admin") setMoreSub(migrated.sub);
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

  const handleTabChange = useCallback(
    (id: TabId) => {
      // Mobile: the ticker page sits over the content — a bottom-nav tap means "go there".
      if (detailLayout === "page" && selectedTickerRef.current) closeTickerDetail();
      setActiveTab(id);
    },
    [detailLayout, closeTickerDetail, setActiveTab],
  );

  const setPlanSubPersist = useCallback((v: PlanSub) => {
    setPlanSub(v);
    try {
      localStorage.setItem(PLAN_SUB_KEY, v);
    } catch {
      /* ignore */
    }
  }, []);
  const setMoreSubPersist = useCallback((v: MoreSub) => {
    setMoreSub(v);
    try {
      localStorage.setItem(MORE_SUB_KEY, v);
    } catch {
      /* ignore */
    }
  }, []);
  const openMore = useCallback(
    (sub: MoreSub) => {
      setMoreSubPersist(sub);
      setActiveTab("more");
    },
    [setActiveTab, setMoreSubPersist],
  );

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
    if (!(activeTab === "plan" && planSub === "opportunities") && activeTab !== "portfolio") return;
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
  }, [data.warming, data.opportunities_bundle_enabled, data.opportunities_deferred, data.as_of_date, activeTab, planSub, oppBundle]);

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
    if (activeTab !== "today" && activeTab !== "more" && !(activeTab === "plan" && planSub === "opportunities")) return;
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
  }, [data.warming, data.analysis_deferred, refreshCacheKey, activeTab, planSub, analysisBundle, analysisRetryKey, analysisInShell]);

  // Heavy Analysis panels — separate lightweight endpoints (avoid monolithic bundle 502).
  useEffect(() => {
    if (data.warming) return;
    if (activeTab !== "more" || moreSub !== "admin") return;

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
  }, [data.warming, refreshCacheKey, activeTab, moreSub, analysisRetryKey]);

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

  // Pre-trade portfolio-impact context for the ticker detail modal — top holdings by
  // value (for a correlation-to-holdings check) + sector allocation/total value (for a
  // client-side "what would adding here do to my {sector} weight" estimate). All already
  // computed by the selected portfolio's report; no extra fetch needed for this part.
  const portfolioImpactContext = useMemo(() => {
    const perHolding = selectedReport?.per_holding ?? [];
    const totalValue = selectedReport?.total_value ?? 0;
    if (!perHolding.length || totalValue <= 0) return null;
    const topHoldings = perHolding
      .filter((h) => h.value != null && h.ticker)
      .map((h) => ({ ticker: h.ticker, value: h.value as number }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 5);
    const heldTickers = new Set(
      perHolding.map((h) => h.ticker?.toUpperCase()).filter(Boolean) as string[],
    );
    return { totalValue, sectorAllocation: selectedReport?.sector_allocation ?? [], topHoldings, heldTickers };
  }, [selectedReport]);

  // Price alerts set from ticker Verdict tabs must be polled even when off-screen.
  const [alertTickers, setAlertTickers] = useState<string[]>([]);
  useEffect(() => {
    const sync = () => setAlertTickers(priceAlertTickers());
    sync();
    return subscribePriceAlerts(sync);
  }, []);

  // All tickers visible in the current dashboard session — deduped for live-price polling
  const livePriceTickers = useMemo(() => {
    const seen: Record<string, true> = {};
    const out: string[] = [];
    const add = (t: string) => { if (t && !seen[t]) { seen[t] = true; out.push(t); } };
    for (const s of effectiveSignals) s.ticker && add(String(s.ticker).toUpperCase());
    for (const t of portfolioTickerList) t && add(t.toUpperCase());
    for (const o of mergedOpportunities) o.ticker && add(String(o.ticker).toUpperCase());
    for (const t of alertTickers) add(t);
    return out;
  }, [effectiveSignals, portfolioTickerList, mergedOpportunities, alertTickers]);

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
    plan: oppCountForBadge,
  };
  const bellCount =
    overviewAlertCount != null && overviewAlertCount > 0
      ? overviewAlertActionCount > 0
        ? overviewAlertActionCount
        : overviewAlertCount
      : 0;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.target && (e.target as HTMLElement).closest("input, textarea, select")) return;
      const keyToTab: Partial<Record<string, TabId>> = {
        "1": "today", "2": "signals", "3": "plan", "4": "portfolio", "5": "more",
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

  const concentrationLimitPct = data.config?.concentration_alert_pct ?? 20;

  const marketWeather = useMemo(
    () =>
      deriveMarketWeather({
        regimeBullPct: signalListContext.regimeBullPct,
        macroRegime: data.macro_regime,
        rotationRisk: data.market_regime?.rotation_risk,
        primaryMessage: data.retail_market_decisions?.market_context?.primary_message,
        temperatureLabel: data.retail_market_decisions?.market_temperature?.label,
        vix: data.retail_market_decisions?.market_temperature?.vix,
        forecastHeadline: data.market_forecast?.headline,
        quadrant: marketQuadrant,
      }),
    [
      signalListContext.regimeBullPct,
      data.macro_regime,
      data.market_regime?.rotation_risk,
      data.retail_market_decisions,
      data.market_forecast?.headline,
      marketQuadrant,
    ],
  );

  const heldTickerSet = useMemo(
    () => new Set(portfolioTickerList.map((t) => t.toUpperCase())),
    [portfolioTickerList],
  );

  /** Score direction since the last saved run, parsed from what_changed's "T: a → b" summary. */
  const scoreDeltaByTicker = useMemo(() => {
    const m = new Map<string, number>();
    for (const w of data.what_changed ?? []) {
      const mm = (w.summary ?? "").match(/:\s*(\d+)\s*→\s*(\d+)/);
      if (mm) m.set(w.ticker.toUpperCase(), Number(mm[2]) - Number(mm[1]));
    }
    return m;
  }, [data.what_changed]);

  const heldEarnings = useMemo(() => {
    const out = new Map<string, number>();
    for (const it of data.retail_market_decisions?.personal_earnings_calendar?.items ?? []) {
      if (it.ticker && it.days_until != null) out.set(it.ticker.toUpperCase(), it.days_until);
    }
    for (const sig of effectiveSignals) {
      const t = String(sig.ticker || "").toUpperCase();
      if (heldTickerSet.has(t) && sig.earnings_days_until != null && !out.has(t)) out.set(t, sig.earnings_days_until);
    }
    return Array.from(out, ([ticker, days_until]) => ({ ticker, days_until }));
  }, [data.retail_market_decisions?.personal_earnings_calendar, effectiveSignals, heldTickerSet]);

  const nextHeldEarnings = useMemo(
    () =>
      heldEarnings
        .filter((e) => e.days_until >= 0 && e.days_until <= 21)
        .sort((a, b) => a.days_until - b.days_until)[0] ?? null,
    [heldEarnings],
  );

  const openFullRiskReport = useCallback(() => {
    setRiskReportKey((k) => k + 1);
    window.setTimeout(() => {
      document.getElementById("portfolio-risk-report")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  }, []);

  const exportSnapshot = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify({ as_of: data.as_of_date, portfolio: data.portfolio, portfolios: data.portfolios, signals_count: signalCountForBadge, opportunities_count: oppCountForBadge }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `thrive-snapshot-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const saveAsEod = async () => {
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
  };

  /** Desktop (≥1280px) list + detail split: the detail renders inline as the right pane. */
  const showPane = detailLayout === "pane" && !!selectedTicker;

  return (
    <LivePricesProvider tickers={livePriceTickers}>
    <PriceAlertWatcher />
    <div className="min-h-screen bg-td-bg">
      {/* Header — logo · ticker search · freshness · alerts bell */}
      <header className="sticky top-0 z-50 border-b border-td-line bg-td-surface/95 backdrop-blur">
        <div className="max-w-[min(1600px,96vw)] mx-auto px-3 sm:px-6 h-14 sm:h-16 flex items-center gap-3">
          <button type="button" onClick={() => setActiveTab("today")} className="flex items-center gap-2 min-w-0 shrink-0">
            <TrendingUp className="h-6 w-6 sm:h-7 sm:w-7 shrink-0 text-emerald-500" />
            <h1 className="text-base sm:text-lg font-bold text-slate-100 truncate">Thrive Alpha</h1>
          </button>
          <form
            className="ml-auto sm:ml-4 flex-1 max-w-xs"
            onSubmit={(e) => {
              e.preventDefault();
              const t = searchQuery.trim().toUpperCase();
              if (/^[A-Z0-9.\-^=]{1,12}$/.test(t)) {
                openTickerDetail(t);
                setSearchQuery("");
              }
            }}
            role="search"
          >
            <label className="relative block">
              <span className="sr-only">Open a ticker</span>
              <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-td-muted" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Ticker…"
                autoCapitalize="characters"
                spellCheck={false}
                className="w-full rounded-lg border border-td-line bg-td-bg pl-8 pr-2 py-1.5 text-sm text-td-text placeholder:text-td-muted/70 focus:border-emerald-500 focus:outline-none"
              />
            </label>
          </form>
          {snapshotIso && (
            <span
              className="text-[11px] hidden lg:inline font-mono text-td-muted whitespace-nowrap"
              title={
                data.data_freshness?.quotes_updated_at || data.data_freshness?.signals_updated_at
                  ? `Prices ${formatSnapshotEt(data.data_freshness?.quotes_updated_at ?? undefined) ?? "—"} · Signals ${formatSnapshotEt(data.data_freshness?.signals_updated_at ?? undefined) ?? "—"}${lastRefreshedAt ? ` · fetched ${formatLastRefresh(lastRefreshedAt)}` : ""}`
                  : `Server snapshot saved ${formatSnapshotEt(snapshotIso)}`
              }
            >
              {data.data_freshness?.quotes_updated_at || data.data_freshness?.signals_updated_at
                ? `${isUsEquityRth() ? "" : "After close · "}Prices ${formatFreshnessLabel(data.data_freshness?.quotes_updated_at ?? undefined) || "—"} · Signals ${formatFreshnessLabel(data.data_freshness?.signals_updated_at ?? undefined) || "—"}`
                : `${isUsEquityRth() ? "Snapshot" : "After close"} ${formatFreshnessLabel(snapshotIso) || snapshotAge || "—"}`}
              {refreshAgo ? ` · fetched ${refreshAgo}` : ""}
            </span>
          )}
          <button
            type="button"
            onClick={() => setAlertsOpen(true)}
            className="relative p-2 rounded-lg text-td-muted hover:text-td-text hover:bg-td-surface2 shrink-0"
            aria-label={`Alerts${bellCount ? `, ${bellCount} need action` : ""}`}
            title="Alerts"
          >
            <Bell className="h-5 w-5" />
            {bellCount > 0 && (
              <span className="absolute top-0.5 right-0.5 min-w-[1.05rem] h-4 px-1 rounded-full bg-red-500 text-[10px] font-bold text-white flex items-center justify-center leading-none">
                {bellCount > 99 ? "99+" : bellCount}
              </span>
            )}
          </button>
        </div>
      </header>

      <div
        className={clsx(
          "mx-auto px-3 sm:px-6 md:flex md:gap-6",
          showPane ? "max-w-none sm:pr-0 md:gap-5" : "max-w-[min(1600px,96vw)]",
        )}
      >
        {/* Desktop: persistent left rail — the 5 tabs + mode switcher, always visible.
            Collapses to icons while the detail pane is open so the list keeps its width. */}
        <aside
          className={clsx(
            "hidden md:flex md:flex-col shrink-0 sticky top-16 self-start h-[calc(100vh-4rem)] py-5 gap-5",
            showPane ? "md:w-12" : "md:w-52 lg:w-56",
          )}
        >
          {!showPane && (
            <div>
              <p className="px-1 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-td-muted">Deciding as</p>
              <DecisionModeSelector mode={tradingLens} onChange={handleTradingLensChange} variant="segmented" />
            </div>
          )}
          <DashboardTabs active={activeTab} onChange={handleTabChange} badges={tabBadges} variant="rail" compact={showPane} />
          {!showPane && (
            <div className="mt-auto px-1 text-[10.5px] text-td-muted leading-snug">
              <ModelDisclaimer className="text-[10px] text-td-muted/80 leading-snug flex items-start gap-1.5" />
            </div>
          )}
        </aside>

        <main className="flex-1 min-w-0 py-4 sm:py-5 pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:pb-8 overflow-x-hidden space-y-4">
          {/* Mobile mode switch — the rail holds it on desktop */}
          <div className="md:hidden">
            <DecisionModeSelector mode={tradingLens} onChange={handleTradingLensChange} variant="segmented" />
          </div>

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

          {/* ── Today ─────────────────────────────────────────────────── */}
          {activeTab === "today" && (
            <div className="space-y-4">
              <MarketWeatherTeaser
                weather={marketWeather}
                onOpen={() => openMore("markets")}
                cautions={(data.guidelines ?? []).map((g) => g.text)}
              />
              <MarketReversalBanner overlay={data.market_reversal_overlay} />
              {degradedMode && <DegradedDataBanner degradedMode={degradedMode} sources={degradedSources} compact />}
              <div className="grid gap-4 xl:grid-cols-2 items-start">
                <div className="space-y-4 min-w-0">
                  <SinceYesterdayCard
                    items={data.what_changed ?? []}
                    lens={tradingLens}
                    heldTickers={heldTickerSet}
                    onTickerClick={openTickerDetail}
                  />
                  <MyBookCard
                    holdings={selectedReport?.per_holding ?? []}
                    scoreDelta={scoreDeltaByTicker}
                    onTickerClick={openTickerDetail}
                    onOpenPortfolio={() => setActiveTab("portfolio")}
                  />
                </div>
                <div className="space-y-4 min-w-0">
                  <MarketMapCard />
                  <ThisWeekCard
                    events={data.economic_calendar ?? []}
                    heldEarnings={heldEarnings}
                    onOpenCalendar={() => openMore("markets")}
                  />
                  <PortfolioTeaser
                    totalValue={selectedReport?.total_value}
                    holdingCount={heldTickerSet.size}
                    largest={selectedReport?.largest_position ?? null}
                    onOpen={() => setActiveTab("portfolio")}
                  />
                </div>
              </div>
            </div>
          )}

          {/* ── Signals ───────────────────────────────────────────────── */}
          {activeTab === "signals" && (
            <div className="space-y-4">
              <AddTickerBar onAdded={() => onRefresh(true)} />
              {data.macro_regime_bundle?.coaching_note && (
                <div
                  className="rounded-lg border border-amber-500/35 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-100"
                  role="status"
                >
                  <strong className="text-amber-200">Macro vs price:</strong> {data.macro_regime_bundle.coaching_note}
                </div>
              )}
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
                  <div className="rounded-xl border border-slate-800/80 bg-slate-900 p-3 sm:p-4">
                    <SignalsHub
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
                      hunterPanel={data.hunter_panel}
                      roadmapTickers={roadmapTickers}
                      roadmapsWarming={Boolean(data.warming)}
                      signalsByTicker={signalsByTicker}
                      splitPane={detailLayout === "pane"}
                      activeTicker={selectedTicker}
                    />
                  </div>
                </>
              )}
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
                  {data.config?.risk_sizing && (
                    <p className="text-xs text-slate-400 rounded-lg border border-slate-700/50 bg-slate-800/30 px-3 py-2">
                      <strong className="text-slate-300">Risk-based sizing:</strong> each row uses{" "}
                      <strong>{data.config.risk_sizing.risk_pct}%</strong> of total portfolio as the dollar risk budget if your{" "}
                      <strong>{data.config.risk_sizing.stop_pct}%</strong> stop is hit. The <strong>Risk (size)</strong> column shows implied shares and notional.
                    </p>
                  )}
                  {data.known_limits && data.known_limits.length > 0 && <KnownLimitsPanel items={data.known_limits} />}
                  <p className="text-sm text-slate-500 mb-0">
                    <span className="text-slate-400">Buy:</span> add-on · <span className="text-slate-400">Sell:</span> trim when overbought/weak · <span className="text-slate-400">Support:</span> watch level ·
                    <span className="text-slate-400"> Short:</span> ~1 mo · <span className="text-slate-400">Medium:</span> ~3–6 mo · <span className="text-slate-400">Long:</span> ~12–18 mo
                  </p>
                  <p className="text-xs text-slate-500">
                    Macro, breadth, pre-market and next-day outlook now live under{" "}
                    <button type="button" onClick={() => openMore("markets")} className="text-emerald-400 hover:text-emerald-300 underline">
                      More → Markets
                    </button>
                    .
                  </p>
                </div>
              </ToggleSection>
              <ModelDisclaimer className="text-[10px] text-slate-600 leading-snug flex items-start gap-1.5 max-w-4xl" />
            </div>
          )}

          {/* ── Plan: Income sleeve + Opportunities ───────────────────── */}
          {activeTab === "plan" && (
            <div className="space-y-4">
              <SubViewSwitch
                value={planSub}
                onChange={setPlanSubPersist}
                options={[
                  { id: "income", label: "Income sleeve" },
                  { id: "opportunities", label: "Opportunities", badge: oppCountForBadge },
                ]}
              />
              {planSub === "income" && (
                <div className="space-y-4">
                  <IncomeBookPanel onTickerClick={openTickerDetail} />
                  <ModelDisclaimer className="text-[10px] text-slate-600 leading-snug flex items-start gap-1.5 max-w-4xl" />
                </div>
              )}
              {planSub === "opportunities" && (
                <div className="space-y-4">
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
            </div>
          )}

          {/* ── Portfolio ─────────────────────────────────────────────── */}
          {activeTab === "portfolio" && (
            <div className="space-y-4">
              {portfolioNames.length > 1 && (
                <div className="flex items-center gap-2">
                  <label htmlFor="portfolio-select-2" className="text-sm text-td-muted">Portfolio:</label>
                  <select
                    id="portfolio-select-2"
                    value={selectedPortfolio}
                    onChange={(e) => setSelectedPortfolio(e.target.value)}
                    className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-1.5 text-slate-100 text-sm focus:border-emerald-500 focus:outline-none"
                  >
                    {portfolioNames.map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="grid gap-4 xl:grid-cols-2 items-start">
                <div className="space-y-4 min-w-0">
                  <PortfolioValueCard report={selectedReport} limitPct={concentrationLimitPct} />
                  <NeedsAttentionList
                    report={selectedReport}
                    trimCandidates={selectedTrimCandidates}
                    limitPct={concentrationLimitPct}
                    onTickerClick={openTickerDetail}
                  />
                </div>
                <div className="space-y-4 min-w-0">
                  <RiskManagementCard
                    totalValue={selectedReport?.total_value}
                    metrics={data.portfolio_risk_metrics}
                    stress={data.portfolio_stress}
                    onOpenFull={openFullRiskReport}
                  />
                  <PortfolioRegimeStrip counts={selectedReport?.regime_counts} />
                </div>
              </div>
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
                    <p className="text-slate-500 text-xs mt-1">Add portfolios in config or upload via Signals → add ticker.</p>
                  </div>
                )}
              </ToggleSection>
              <div id="portfolio-risk-report" className="scroll-mt-20">
                <ToggleSection key={`risk-${riskReportKey}`} id="portfolio-risk" title="Risk management — full report" icon={<Shield />} defaultOpen={riskReportKey > 0}>
                  <div className="space-y-6">
                    {data.portfolio_stress?.scenarios?.length ? <PortfolioStressStrip stress={data.portfolio_stress} /> : null}
                    <div>
                      <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">VaR / CVaR & correlation (holdings)</p>
                      <PortfolioRiskMetricsPanel metrics={data.portfolio_risk_metrics} />
                    </div>
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
                  </div>
                </ToggleSection>
              </div>
              <ToggleSection id="portfolio-tax-exit" title="Tax-Aware Exit Optimizer" icon={<Calendar />} badge={data.tax_aware_exits?.items?.length ?? 0} defaultOpen>
                <TaxAwareExitPanel data={data.tax_aware_exits} onTickerClick={openTickerDetail} />
              </ToggleSection>
              <DecisionJournalPanel defaultOpen />
              <ToggleSection id="portfolio-doctor-v2" title="Portfolio Doctor — this week's actions" icon={<Target />} badge={data.portfolio_doctor_v2?.priority_actions?.total_actions || undefined} defaultOpen={false}>
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
                  <PortfolioDoctorRecommendations
                    recommendation={mergedDoctorRec?.[selectedPortfolio]}
                    selectedPortfolio={selectedPortfolio}
                    onTickerClick={openTickerDetail}
                  />
                </div>
              </ToggleSection>
              <ToggleSection id="portfolio-heatmap" title="Heat map" icon={<Activity />} defaultOpen={false}>
                <PortfolioHeatMap
                  holdings={selectedReport?.per_holding ?? []}
                  regimeCounts={selectedReport?.regime_counts}
                  onTickerClick={openTickerDetail}
                />
              </ToggleSection>
              <ToggleSection id="portfolio-summary" title="Summary & regime mix" icon={<PieChart />} defaultOpen={false}>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <PortfolioSummary report={selectedReport} />
                </div>
                <div className="mt-4">
                  <RegimeChart report={selectedReport} />
                </div>
              </ToggleSection>
              <ToggleSection id="portfolio-trim" title="Consider Trim — detail" icon={<AlertTriangle />} badge={selectedTrimCandidates.length || undefined} defaultOpen={false}>
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
              <ToggleSection id="portfolio-score-chart" title="Score chart" icon={<BarChart3 />} defaultOpen={false}>
                <AnchorChartPanel
                  title="Portfolio tape"
                  hint="One shared chart surface — click a bar to open the ticker hub."
                >
                  <ScoreChart signals={scoreChartSignals} onTickerClick={openTickerDetail} embedded />
                </AnchorChartPanel>
              </ToggleSection>
              {(data.performance_vs_benchmark?.periods?.length || data.performance_vs_benchmark?.message) && (
                <ToggleSection id="portfolio-performance" title="Performance vs benchmark" icon={<PieChart />} defaultOpen={false}>
                  <PerformanceVsBenchmark
                    periods={data.performance_vs_benchmark?.periods ?? []}
                    message={data.performance_vs_benchmark?.message}
                    as_of={data.performance_vs_benchmark?.as_of}
                  />
                  <ModelDisclaimer className="mt-4 text-[10px] text-slate-600 leading-snug flex items-start gap-1.5 max-w-4xl" />
                </ToggleSection>
              )}
            </div>
          )}

          {/* ── More: Markets + Admin ─────────────────────────────────── */}
          {activeTab === "more" && (
            <div className="space-y-4">
              <SubViewSwitch
                value={moreSub}
                onChange={setMoreSubPersist}
                options={[
                  { id: "markets", label: "Markets" },
                  { id: "admin", label: "Admin" },
                ]}
              />
              {moreSub === "markets" && (
                <div className="space-y-4 sm:space-y-6">
                  {data.retail_market_decisions && (
                    <RetailMarketDecisionsPanel data={data.retail_market_decisions} collapsible />
                  )}
                  <ToggleSection id="markets-outlook" title="Breadth, rotation & next-day outlook" icon={<Globe className="h-5 w-5" />} defaultOpen>
                    <div className="space-y-3">
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
                    </div>
                  </ToggleSection>
                  <ToggleSection id="markets-tape" title="Live market tape" icon={<Globe className="h-5 w-5" />} defaultOpen={false}>
                    <MarketStatePanel compactHeader />
                  </ToggleSection>
                  <ToggleSection id="markets-premarket" title="Pre-Market Signal Engine" icon={<Activity />} defaultOpen={false}>
                    <PreMarketPanel data={preMarketFull ?? undefined} apiEndpoint="/api/pre-market" />
                  </ToggleSection>
                  <ToggleSection id="markets-newsletter" title="Morning newsletter" icon={<Mail className="h-5 w-5" />} defaultOpen={false}>
                    <MorningNewsletter data={data.morning_newsletter ?? undefined} />
                  </ToggleSection>
                  <ToggleSection id="markets-scenarios" title="Market scenarios (what-if)" icon={<Target />} badge={data.market_scenarios?.length ?? 0} defaultOpen={false}>
                    <MarketScenarios scenarios={data.market_scenarios ?? []} />
                  </ToggleSection>
                  {data.pre_ipo?.enabled && (data.pre_ipo.items?.length ?? 0) > 0 ? (
                    <ToggleSection
                      id="markets-pre-ipo"
                      title="Pre-IPO watch"
                      icon={<Sparkles />}
                      badge={data.pre_ipo.items!.length}
                      defaultOpen={false}
                    >
                      <PreIpoSection panel={data.pre_ipo} onTickerClick={openTickerDetail} />
                    </ToggleSection>
                  ) : null}
                  <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-6 min-w-0 items-start">
                    {data.crypto?.length ? (
                      <div className="min-w-0">
                        <ToggleSection id="markets-crypto" title="Crypto" icon={<Globe />} badge={data.crypto.length} defaultOpen={false}>
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
                </div>
              )}
              {moreSub === "admin" && (
                <div className="space-y-4 sm:space-y-6">
                  <p className="text-xs text-td-muted">
                    Model validation and data health — not decision inputs. Read-only on mobile.
                  </p>
                  <div className="hidden md:flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => onRefresh(true)}
                      disabled={loading || isRefreshing}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800 disabled:opacity-50 text-sm"
                      title="Force full signal recompute (usually unnecessary — data updates automatically)"
                    >
                      <RefreshCw className={clsx("h-4 w-4 shrink-0", (loading || isRefreshing) && "animate-spin")} />
                      {loading || isRefreshing ? "Refreshing…" : "Force refresh"}
                    </button>
                    <button
                      type="button"
                      onClick={exportSnapshot}
                      className="px-3 py-2 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800 text-sm"
                    >
                      Export snapshot
                    </button>
                    <button
                      type="button"
                      onClick={saveAsEod}
                      disabled={eodSaving || loading}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800 disabled:opacity-50 text-sm"
                      title="Save current run to data/eod/ (fast, no refresh)"
                    >
                      <Save className={clsx("h-4 w-4 shrink-0", eodSaving && "animate-pulse")} />
                      {eodSaving ? "Saving…" : "Save as EOD"}
                    </button>
                    <button
                      type="button"
                      onClick={toggleAdvancedMode}
                      className={clsx(
                        "flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm",
                        advancedMode
                          ? "border-violet-500/40 bg-violet-500/10 text-violet-200"
                          : "border-slate-600 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                      )}
                      title="Show the API runner and signal test suite"
                    >
                      <FlaskConical className="h-4 w-4 shrink-0" />
                      {advancedMode ? "Dev tools on" : "Dev tools"}
                    </button>
                    {eodMessage && (
                      <span className={clsx("text-xs px-2 py-1 rounded", eodMessage.type === "ok" ? "text-emerald-300 bg-emerald-900/30" : "text-amber-200 bg-amber-900/30")}>
                        {eodMessage.text}
                      </span>
                    )}
                  </div>
                  {data.data_freshness && <DataFreshnessBar data={data.data_freshness} />}
                  {degradedMode && <DegradedDataBanner degradedMode={degradedMode} sources={degradedSources} />}
                  {fmpPlanStatus && <FMPPlanStatus status={fmpPlanStatus} />}
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
                  <RegimeValidationPanel data={regimeValidation} />
                  {data.known_limits && data.known_limits.length > 0 && <KnownLimitsPanel items={data.known_limits} />}
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
              {advancedMode && (
              <ToggleSection id="analysis-api-endpoints" title="API endpoints (ad-hoc runner)" icon={<Terminal className="h-5 w-5" />} defaultOpen={false}>
                <ApiEndpointsPanel />
              </ToggleSection>
              )}
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
              {advancedMode && (
              <ToggleSection id="analysis-test-suite" title="Signal test suite" icon={<FlaskConical />} defaultOpen={false}>
                <SignalTestSuite />
              </ToggleSection>
              )}
                </div>
              )}
            </div>
          )}
        </main>

        {showPane && selectedTicker && detailExpanded && (
          <div
            className="hidden xl:block fixed inset-0 z-[99] bg-black/60 backdrop-blur-[2px]"
            onClick={() => setDetailExpanded(false)}
            aria-hidden
          />
        )}
        {showPane && selectedTicker && (
          <aside
            className={clsx(
              "hidden xl:block border-l border-td-line",
              detailExpanded
                ? "td-slide-in fixed inset-y-0 right-0 z-[100] w-[min(96vw,1280px)] shadow-2xl shadow-black/50"
                : "w-[46%] 2xl:w-[48%] max-w-[60rem] shrink-0 sticky top-16 self-start h-[calc(100vh-4rem)]",
            )}
            aria-label={`${selectedTicker} detail`}
          >
            <TickerDetailModal
              ticker={selectedTicker}
              initialTab={modalInitialTab}
              onClose={closeTickerDetail}
              portfolioImpactContext={portfolioImpactContext}
              layout="pane"
              expanded={detailExpanded}
              onExpand={() => setDetailExpanded((v) => !v)}
              onTabChange={handleDetailTabChange}
            />
          </aside>
        )}
      </div>

      {selectedTicker && !showPane && (
        <TickerDetailModal
          ticker={selectedTicker}
          initialTab={modalInitialTab}
          onClose={closeTickerDetail}
          portfolioImpactContext={portfolioImpactContext}
          layout={detailLayout === "page" ? "page" : "drawer"}
          onTabChange={handleDetailTabChange}
        />
      )}

      <AlertsScreen
        open={alertsOpen}
        onClose={() => setAlertsOpen(false)}
        onTickerClick={(t) => {
          setAlertsOpen(false);
          openTickerDetail(t);
        }}
        dashboardRefreshedAt={
          lastRefreshedAt?.toISOString() ?? data.as_of_date ?? data.data_freshness?.snapshot_updated_at ?? null
        }
        onCounts={(total, actionRequired) => {
          setOverviewAlertCount(total);
          setOverviewAlertActionCount(actionRequired);
        }}
      />

      <div className="md:hidden fixed bottom-0 left-0 right-0 z-40 shadow-[0_-8px_24px_rgba(0,0,0,0.35)]">
        <DashboardTabs active={activeTab} onChange={handleTabChange} badges={tabBadges} variant="bottom" />
      </div>

      <ChatCopilot data={dataForCopilot} />
    </div>
    </LivePricesProvider>
  );
}
