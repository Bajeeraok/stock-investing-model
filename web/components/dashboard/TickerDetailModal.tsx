"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X, FileText, ChevronLeft, Maximize2, Minimize2, Activity, LayoutGrid, Target, Layers, Ban, Eye, CheckCircle } from "lucide-react";
import { clsx } from "clsx";
import type { ConfidenceData } from "./ConfidenceBreakdown";
import type { UnifiedSignalData } from "./PatternSignalCard";
import type { PriceTargetsData } from "./PriceTargetsPanel";
import type { InvestorDecisionSummary } from "./InvestorDecisionSummary";
import type { WhySubTab } from "./TickerDetailWhyNav";
import type { HorizonPlaybooksBundle } from "./HorizonPlaybookCard";
import { type TickerMarketContext } from "./TickerMarketContextCard";
import { getPositionIntent, setPositionIntent, type PositionIntent } from "@/lib/positionIntent";
import {
  getDecisionMode,
  setDecisionMode,
  intentFromMode,
  type DecisionMode,
} from "@/lib/decisionMode";
import { DecisionModeSelector } from "./DecisionModeSelector";
import { buildExecutionPlanViewModel } from "./executionPlanModel";
import {
  buildGatesFromInvestorSummary,
  mapApiGateToRow,
  resolvePrimaryGatesCount,
} from "./retailActionUX";
import { isUsEquityRth } from "@/lib/dashboardCache";
import TrackRecordPanel from "./tickerDetail/TrackRecordPanel";
import { VerdictTab } from "./tickerDetail/tabs/VerdictTab";
import { LevelsTab } from "./tickerDetail/tabs/LevelsTab";
import { WhyTab } from "./tickerDetail/tabs/WhyTab";
import { ContextTab } from "./tickerDetail/tabs/ContextTab";
import type { TabCtx } from "./tickerDetail/tabs/tabCtx";
import { apiUrl, fetchJsonWithRetry, formatFetchError, isMobileLikeBrowser } from "@/lib/apiBase";
import { pctPriceVsFairValue } from "@/lib/valuationPct";
import { computeActionableScore } from "@/lib/actionableScore";

/** Traffic-light headline for retail: execution vs research vs avoid (aligned with FV + regime + pattern + optional news). */
export type RetailActionLight = "red" | "yellow" | "green" | "neutral";

export interface RetailActionStatus {
  light: RetailActionLight;
  title: string;
  subtitle: string;
}

function computeRetailActionStatus(input: {
  currentPrice: number | null | undefined;
  fairValue: number | null | undefined;
  regimeBullPct: number | null | undefined;
  patternScore: number | null | undefined;
  newsScore0to1: number | null | undefined;
  newsLayerAvailable: boolean;
}): RetailActionStatus | null {
  const cp = input.currentPrice;
  const fv = input.fairValue;
  if (cp == null || !(cp > 0) || fv == null || !(fv > 0)) return null;

  const premiumPct = ((cp - fv) / fv) * 100;
  const discountPct = ((fv - cp) / fv) * 100;

  const regime = input.regimeBullPct;
  const pattern = input.patternScore;

  const newsScore = input.newsScore0to1;
  const newsBearish =
    input.newsLayerAvailable &&
    newsScore != null &&
    !Number.isNaN(newsScore) &&
    newsScore < 0.38;

  /** Paying clearly above model fair value → avoid (tiny tolerance for rounding). */
  const overvalued = premiumPct > 0.12;

  /**
   * Catastrophic backdrop only when there is little valuation cushion — avoids labeling
   * deep-value + risk-off (e.g. META) as red; those stay yellow.
   */
  const regimeSevereRiskOff =
    regime != null &&
    regime < 22 &&
    discountPct < 10;

  if (overvalued || newsBearish || regimeSevereRiskOff) {
    const parts: string[] = [];
    if (overvalued) parts.push("price is above model fair value");
    if (newsBearish) parts.push("news flow skews negative");
    if (regimeSevereRiskOff && !overvalued && !newsBearish) {
      parts.push("risk-off backdrop without much margin of safety");
    }
    return {
      light: "red",
      title: "AVOID",
      subtitle:
        parts.length > 0
          ? `Why: ${parts.join(" · ")}.`
          : "Elevated risk versus reward at today’s prices.",
    };
  }

  const undervaluedEnough = discountPct >= 5;
  const bullishRegime = regime != null && regime >= 48;
  const positiveTechnical = pattern != null && pattern >= 55;

  if (undervaluedEnough && bullishRegime && positiveTechnical) {
    return {
      light: "green",
      title: "ENTRY OPPORTUNITY",
      subtitle:
        "Undervalued vs model, bullish regime, and technical setup supportive — confirm sizing on Roadmaps.",
    };
  }

  if (discountPct >= 5 && regime != null && regime < 48 && pattern != null && pattern < 55) {
    return {
      light: "yellow",
      title: "DO NOT CHASE",
      subtitle:
        "Valuation is attractive, but regime and chart still cautious — sit on your hands until gates clear.",
    };
  }

  if (discountPct >= 5 && regime != null && regime < 48) {
    return {
      light: "yellow",
      title: "WATCH OR HOLD",
      subtitle: "Cheap vs fair value, but stormy tape — wait for a cleaner dip before sizing.",
    };
  }

  if (discountPct >= 5 && pattern != null && pattern < 55) {
    return {
      light: "yellow",
      title: "WATCH OR HOLD",
      subtitle: "Undervalued on fundamentals; technical score still weak — wait for momentum to improve.",
    };
  }

  if (discountPct < 5 && discountPct >= -2) {
    return {
      light: "yellow",
      title: "WATCH OR HOLD",
      subtitle: "Little margin of safety vs model fair value — mixed setup; see Roadmaps for levels.",
    };
  }

  return {
    light: "yellow",
    title: "WATCH OR HOLD",
    subtitle: "Mixed signals — use Roadmaps for entry zones and stops before sizing.",
  };
}

function RetailActionStatusBanner({ status }: { status: RetailActionStatus | null }) {
  if (!status) {
    return (
      <div
        className="border-b border-slate-700 bg-slate-800 px-4 py-3 sm:px-6"
        role="status"
        aria-live="polite"
      >
        <p className="text-sm text-slate-400">
          Action status appears when fair value and price are available from the summary.
        </p>
      </div>
    );
  }

  const styles =
    status.light === "green"
      ? {
          wrap: "border-emerald-600/50 bg-emerald-950",
          accent: "text-emerald-300",
          icon: CheckCircle,
        }
      : status.light === "yellow"
        ? {
            wrap: "border-amber-500/50 bg-amber-950",
            accent: "text-amber-200",
            icon: Eye,
          }
        : status.light === "red"
          ? {
              wrap: "border-red-500/55 bg-red-950",
              accent: "text-red-100",
              icon: Ban,
            }
          : {
              wrap: "border-slate-600 bg-slate-800",
              accent: "text-slate-200",
              icon: Activity,
            };

  const Icon = styles.icon;

  return (
    <div
      className={clsx(
        "border-b px-4 py-3 sm:px-6 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4",
        styles.wrap
      )}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-3 min-w-0">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-black/25 border border-white/10">
          <Icon className={clsx("h-5 w-5", styles.accent)} aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="text-sm uppercase tracking-wider text-slate-400 font-semibold">Action status</p>
          <p className={clsx("text-lg font-bold tracking-tight", styles.accent)}>{status.title}</p>
        </div>
      </div>
      <div className="text-sm text-slate-200/95 leading-snug sm:flex-1 sm:min-w-0 border-t border-white/5 sm:border-0 sm:border-l sm:border-white/10 sm:pl-4 pt-2 sm:pt-0 space-y-1.5">
        <p>{status.subtitle}</p>
        <p
          className="text-sm text-slate-400 leading-snug cursor-help"
          title="Fair value compares price to our model anchor. Regime is risk-on vs risk-off from the model. They are allowed to disagree: cheap can stay cheap until the tape improves."
        >
          Quick read: <span className="text-slate-300">Fair value</span> = price vs our estimate of worth.{" "}
          <span className="text-slate-300">Regime / action</span> = whether the model wants full size right now. Yellow often means “good value, wait for better timing.”
        </p>
      </div>
    </div>
  );
}

export interface TickerDetail {
  ticker: string;
  company_name?: string | null;
  thesis: string;
  exit_condition: string;
  short_suggestion?: string;
  medium_suggestion?: string;
  long_suggestion?: string;
  short_reason?: string;
  medium_reason?: string;
  long_reason?: string;
  price_reasoning?: { buy?: string; sell?: string; support?: string };
  ma20?: number | null;
  ma50?: number | null;
  ma200?: number | null;
  earnings: { date: string; days_until: number } | null;
  sector: string | null;
  industry: string | null;
  sector_etf: string;
  sector_etf_name: string;
  peers: string[];
  current_price: number | null;
  daily_move_pct?: number | null;
  price_history?: { date: string; close: number }[];
  returns: Record<string, number>;
  benchmark_spy: Record<string, number>;
  benchmark_industry: Record<string, number>;
  peer_returns: { ticker: string; returns: Record<string, number>; data_quality_warning?: string }[];
  volume_ratio?: number | null;
  volume_unusual?: boolean;
  drawdown_52w?: number | null;
  dividend_yield?: number | null;
  dividend_yield_explanation?: string | null;
  dividend_yield_error?: string | null;
  sanity_errors?: string[];
  listing_profile?: {
    young_listing?: boolean;
    extreme_52w_range?: boolean;
    listing_bars?: number;
    raw_52w_low?: number;
    effective_52w_low?: number;
    raw_ma200?: number;
    effective_ma200?: number;
    warnings?: string[];
    listing_event?: { event?: string; note?: string; parent?: string };
  } | null;
  catalyst?: {
    active: boolean;
    top_event_type: string;
    top_impact: number;
    headline_summary: string;
    override_note: string;
    hours_since_catalyst: number;
    event_count: number;
  } | null;
  post_earnings_transition?: {
    active: boolean;
    beat_or_miss: string;
    eps_surprise_pct: number | null;
    earnings_date: string | null;
    days_since: number | null;
    price_reaction_pct: number | null;
    transition_note: string;
    signal_direction: string;
  } | null;
  high_52w?: number | null;
  low_52w?: number | null;
  /** Real single-session VWAP (free, yfinance 5-min bars) — null outside market hours or
   * when intraday data isn't available for this ticker. Distinct from any internal `vwap`
   * band-math input used elsewhere in the pipeline. */
  session_vwap?: { vwap: number; close_vs_vwap_pct: number; bars_used: number } | null;
  beta?: number | null;
  st_band?: { low: number; high: number } | null;
  mt_band?: { low: number; high: number } | null;
  lt_band?: { low: number; high: number } | null;
  lt_band_low_confidence?: boolean;
  st_checkpoints?: number[] | null;
  mt_checkpoints?: number[] | null;
  lt_checkpoints?: number[] | null;
  lt_scenarios?: { bear: number; base: number; bull: number } | null;
  st_level_hit?: "target" | "stop" | null;
  st_target_confidence_pct?: number | null;
  mt_target_confidence_pct?: number | null;
  score_breakdown?: { trend?: number; rsi?: number; macd?: number; composite?: number };
  street_vs_model?: {
    street_low: number;
    street_high: number;
    model_lt_low: number;
    model_lt_high: number;
    delta_low_pct: number;
    delta_high_pct: number;
    model_more_bullish: boolean;
    divergence_pct?: number;
  };
  long_horizon_risk?: {
    max_drawdown_pct: number;
    worst_3y_return_pct?: number | null;
    stress_bear_pct: number;
    period_years: number;
  };
  earnings_history?: {
    history: { quarter: string; actual: number | null; estimate: number | null; beat_pct: number | null; status: string; revenue_beat_pct?: number | null }[];
    beat_rate: number;
    summary: string;
    next_consensus?: { date: string; eps_estimated: number | null; revenue_estimated: number | null };
  };
  liquidity?: {
    flag: "NORMAL" | "THIN_FLOAT" | "UNKNOWN";
    label?: string;
    free_float_pct?: number | null;
    float_shares?: number | null;
  };
  analyst_actions?: {
    kind: "price_target" | "grade";
    firm: string | null;
    new_target?: number | null;
    price_when_posted?: number | null;
    new_grade?: string | null;
    previous_grade?: string | null;
    published_at: string | null;
    headline: string | null;
  }[];
  sector_specific?: Record<string, number | string>;
  rate_sensitivity?: {
    correlation_with_tlt: number;
    interpretation: string;
    note: string;
  };
  /** Rolling correlation vs GLD / UUP / VIX — macro sensitivity badges */
  cross_asset?: { badges: string[]; correlations?: Record<string, number | null> } | null;
  market_context?: TickerMarketContext | null;
  investor_summary?: InvestorDecisionSummary | null;
  /** Full 7-layer confidence — included in ticker detail to avoid a second API round-trip. */
  confidence?: ConfidenceData | null;
  /** PE/EPS/FMP data are latest vendor snapshot — not point-in-time historical fundamentals. */
  fundamentals_snapshot?: {
    point_in_time: boolean;
    short_label: string;
    detail: string;
  };
}

export interface PortfolioImpactContext {
  totalValue: number;
  sectorAllocation: { sector: string; pct: number }[];
  /** Top holdings by value, already capped (e.g. top 5) — used for a correlation-to-holdings check. */
  topHoldings: { ticker: string; value: number }[];
  heldTickers: Set<string>;
}

export type ModalTab = "verdict" | "levels" | "why" | "context" | "track";

/** One decision record, five views — order and copy from the Thrive Alpha redesign. */
const MODAL_TABS: { id: ModalTab; label: string; hint: string; icon: typeof Target }[] = [
  { id: "verdict", label: "Verdict", hint: "What to do", icon: Target },
  { id: "why", label: "Why", hint: "Gates & proof", icon: Layers },
  { id: "levels", label: "Levels", hint: "Prices & plan", icon: LayoutGrid },
  { id: "context", label: "Context", hint: "News & data", icon: FileText },
  { id: "track", label: "Track", hint: "Our history here", icon: Activity },
];

export function TickerDetailModal({
  ticker,
  onClose,
  initialTab = "verdict",
  portfolioImpactContext = null,
  layout = "drawer",
  onExpand,
  expanded = false,
  onTabChange,
}: {
  ticker: string;
  onClose: () => void;
  /**
   * drawer — overlay panel over the list (tablet, or desktop "expanded")
   * pane   — inline right pane of the desktop split view (no portal / backdrop)
   * page   — full-screen mobile page; bottom nav stays visible below it
   */
  layout?: "drawer" | "pane" | "page";
  /** Pane only: open the same ticker in the full-width drawer (sidebar tabs). */
  onExpand?: () => void;
  /** Pane shown as a full-width overlay (same mounted instance — no refetch on expand). */
  expanded?: boolean;
  /** Fires when the visible tab changes — Dashboard mirrors it into ?view= */
  onTabChange?: (tab: ModalTab) => void;
  /** Which hub tab to show first (e.g. Levels when opening from roadmap expand). */
  initialTab?: "verdict" | "levels" | "why" | "context" | "track";
  /** Current portfolio's holdings context, for the pre-trade impact card. Null when no portfolio is configured/selected. */
  portfolioImpactContext?: PortfolioImpactContext | null;
}) {
  const [detail, setDetail]               = useState<TickerDetail | null>(null);
  const [confidence, setConfidence]        = useState<ConfidenceData | null>(null);
  const [unified, setUnified]              = useState<UnifiedSignalData | null>(null);
  const [priceTargets, setPriceTargets]    = useState<PriceTargetsData | null>(null);
  const [loading, setLoading]              = useState(true);
  const [error, setError]                  = useState<string | null>(null);
  const [reloadKey, setReloadKey]          = useState(0);
  /** Live price lifted from IntradayChart (1-min cadence on 1D view) */
  const [livePrice, setLivePrice]          = useState<number | null>(null);
  const [liveChangePct, setLiveChangePct]  = useState<number | null>(null);
  const [quickRefOpen, setQuickRefOpen]    = useState(false);
  const [ltEntryTiersOpen, setLtEntryTiersOpen] = useState(true);
  const [metricsGuideOpen, setMetricsGuideOpen] = useState(false);
  const [debugPanelOpen, setDebugPanelOpen] = useState(false);
  const [modalTab, setModalTab] = useState<"verdict" | "levels" | "why" | "context" | "track">(initialTab);
  const [whySubTab, setWhySubTab] = useState<WhySubTab>("valuation");

  const openWhyValuation = () => {
    setModalTab("why");
    setWhySubTab("valuation");
  };
  const [catalystExpanded, setCatalystExpanded] = useState(false);
  const [moreContextOpen, setMoreContextOpen] = useState(false);
  const [positionIntent, setPositionIntentLocal] = useState<PositionIntent | null>(null);
  const [decisionMode, setDecisionModeLocal] = useState<DecisionMode>("scout");

  useEffect(() => {
    const intent = getPositionIntent(ticker);
    setPositionIntentLocal(intent);
    setDecisionModeLocal(getDecisionMode(ticker, intent));
  }, [ticker]);

  const handleDecisionMode = (mode: DecisionMode) => {
    setDecisionModeLocal(mode);
    setDecisionMode(ticker, mode);
    const mapped = intentFromMode(mode);
    if (mapped) {
      setPositionIntent(ticker, mapped);
      setPositionIntentLocal(mapped);
    }
  };

  useEffect(() => {
    if (layout === "pane") {
      if (!expanded) return;
      const onKey = (e: KeyboardEvent) => {
        if (e.key === "Escape") onExpand?.();
      };
      window.addEventListener("keydown", onKey);
      return () => window.removeEventListener("keydown", onKey);
    }
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [layout, onClose, expanded, onExpand]);

  useEffect(() => {
    onTabChange?.(modalTab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modalTab]);

  // Tab reset is separate from the fetch so a ?view= change doesn't refetch the ticker.
  useEffect(() => {
    setModalTab(initialTab);
  }, [ticker, initialTab]);

  useEffect(() => {
    if (!ticker) return;
    setWhySubTab("valuation");
    setCatalystExpanded(false);
    setLoading(true);
    setError(null);
    setDetail(null);
    setConfidence(null);
    setUnified(null);
    setPriceTargets(null);
    setLivePrice(null);
    setLiveChangePct(null);

    const ac = new AbortController();
    let cancelled = false;

    (async () => {
      try {
        const d = await fetchJsonWithRetry<TickerDetail>(`/api/ticker/${ticker}`, {
          signal: ac.signal,
          retries: 2,
        });
        if (cancelled) return;
        setDetail(d);
        if (d.confidence) {
          setConfidence(d.confidence);
        } else {
          fetch(apiUrl(`/api/confidence/${ticker}`), { signal: ac.signal, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((c) => c && setConfidence(c as ConfidenceData))
            .catch(() => {/* optional — older backend without embedded confidence */});
        }
      } catch (e) {
        if (cancelled || (e instanceof DOMException && e.name === "AbortError")) return;
        setError(formatFetchError(e, "Ticker detail"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      ac.abort();
    };
  }, [ticker, reloadKey]);

  /** Unified signal + price targets are heavy — load only when Why/Levels tabs are opened. */
  const unifiedFetchStarted = useRef(false);
  const targetsFetchStarted = useRef(false);

  useEffect(() => {
    unifiedFetchStarted.current = false;
    targetsFetchStarted.current = false;
  }, [ticker, reloadKey, detail?.investor_summary?.fair_value]);

  useEffect(() => {
    if (!ticker || !detail) return;
    if (modalTab !== "why" && modalTab !== "levels") return;

    const ac = new AbortController();
    const delay = isMobileLikeBrowser() ? 400 : 0;
    const fv = detail.investor_summary?.fair_value;
    const targetsQs =
      fv != null && fv > 0 ? `?fair_value=${encodeURIComponent(String(fv))}` : "";

    const loadUnified = () => {
      if (unifiedFetchStarted.current) return;
      unifiedFetchStarted.current = true;
      fetch(apiUrl(`/api/unified-signal/${ticker}`), { signal: ac.signal, cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => d && setUnified(d as UnifiedSignalData))
        .catch(() => {
          unifiedFetchStarted.current = false;
        });
    };

    const loadPriceTargets = () => {
      if (targetsFetchStarted.current) return;
      targetsFetchStarted.current = true;
      fetch(apiUrl(`/api/price-targets/${ticker}${targetsQs}`), { signal: ac.signal, cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          const pt = d as PriceTargetsData & { error?: string };
          if (pt && !pt.error) setPriceTargets(pt);
          else targetsFetchStarted.current = false;
        })
        .catch(() => {
          targetsFetchStarted.current = false;
        });
    };

    const t1 = window.setTimeout(loadUnified, delay);
    const t2 = window.setTimeout(loadPriceTargets, delay + (isMobileLikeBrowser() ? 800 : 300));

    return () => {
      ac.abort();
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [ticker, detail, detail?.investor_summary?.fair_value, modalTab, reloadKey]);

  /** Scenario teaser on Today tab — prefetch after paint (non-blocking). */
  useEffect(() => {
    if (!ticker || !detail || priceTargets) return;
    const ac = new AbortController();
    const fv = detail.investor_summary?.fair_value;
    const targetsQs =
      fv != null && fv > 0 ? `?fair_value=${encodeURIComponent(String(fv))}` : "";
    const t = window.setTimeout(() => {
      fetch(apiUrl(`/api/price-targets/${ticker}${targetsQs}`), { signal: ac.signal, cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          const pt = d as PriceTargetsData & { error?: string };
          if (pt && !pt.error) setPriceTargets(pt);
        })
        .catch(() => {});
    }, isMobileLikeBrowser() ? 2500 : 1200);
    return () => {
      ac.abort();
      window.clearTimeout(t);
    };
  }, [ticker, detail, detail?.investor_summary?.fair_value, priceTargets, reloadKey]);

  const periods = ["1m", "3m", "6m", "1y"];

  const playbookStage3 =
    confidence?.pre_flight?.playbook?.find((s) => s.condition_met && s.scenario_id === 3) ?? null;
  const regimeShift = confidence?.pre_flight?.regime_transition ?? null;

  const normalizeActionClass = (v?: string | null): "constructive" | "neutral" | "cautionary" => {
    const s = (v || "").toUpperCase();
    if (s.includes("STRONG BUY") || s.includes("BUY") || s.includes("ADD")) return "constructive";
    if (s.includes("AVOID") || s.includes("REDUCE") || s.includes("TRIM") || s.includes("SELL")) return "cautionary";
    return "neutral";
  };
  const overviewVerdict = detail?.investor_summary?.one_answer?.verdict ?? detail?.investor_summary?.overall_verdict ?? null;
  const patternVerdict = unified?.action ?? null;
  const hasVerdictConflict =
    !!overviewVerdict &&
    !!patternVerdict &&
    normalizeActionClass(overviewVerdict) !== normalizeActionClass(patternVerdict);

  const retailActionStatus = useMemo(() => {
    const inv = detail?.investor_summary;
    if (!inv) return null;
    const roadmapNews = inv.trade_roadmap?.news_sentiment_layer;
    let newsScore = roadmapNews?.score_0_1 ?? null;
    let newsAvail =
      roadmapNews != null &&
      roadmapNews.layer_available !== false &&
      (roadmapNews.headline_count ?? 0) > 0 &&
      newsScore != null;
    const confNlp = confidence?.breakdown?.nlp_sentiment;
    if (confNlp?.available && confNlp.score != null) {
      newsScore = confNlp.score;
      newsAvail = true;
    }
    return computeRetailActionStatus({
      currentPrice: detail?.current_price,
      fairValue: inv.fair_value,
      regimeBullPct: inv.regime_bull_pct,
      patternScore: inv.pattern_score,
      newsScore0to1: newsScore,
      newsLayerAvailable: newsAvail,
    });
  }, [detail, confidence]);

  const headerActionStatus = useMemo((): RetailActionStatus => {
    const ra = detail?.investor_summary?.retail_action;
    // action_title_by_mode gives each persona its own horizon's zone (scout=short,
    // swing=medium, owner=long) — the flat action_title/action_light below always
    // prefers the long-term tier zone when one exists, which showed owner-only
    // "T1/T2/T3 IN RANGE" language in Scout/Swing mode. Prefer the mode-keyed
    // variant; fall back to the flat field for older cached responses.
    const byMode = ra?.action_title_by_mode?.[decisionMode];
    if (byMode?.title && byMode?.light) {
      return {
        light: byMode.light as RetailActionLight,
        title: byMode.title,
        subtitle: ra?.dynamic_subtitle ?? "",
      };
    }
    if (ra?.action_title && ra?.action_light) {
      return {
        light: ra.action_light as RetailActionLight,
        title: ra.action_title,
        subtitle: ra.dynamic_subtitle ?? "",
      };
    }
    if (retailActionStatus) return retailActionStatus;
    const v = String(detail?.investor_summary?.overall_verdict || "WATCH").toUpperCase();
    if (v === "STRONG BUY" || v === "BUY") {
      return { light: "green", title: "TACTICAL ENTRY", subtitle: "Horizons align — confirm gates and sizing." };
    }
    if (v === "WAIT") {
      return { light: "red", title: "DO NOT CHASE", subtitle: "Gates are blocking new entries — see checklist below." };
    }
    return { light: "yellow", title: "WATCH OR HOLD", subtitle: "Mixed setup — wait for locked gates to clear." };
  }, [retailActionStatus, detail?.investor_summary?.retail_action, detail?.investor_summary?.overall_verdict, decisionMode]);

  // Live price from IntradayChart (1-min cadence) overrides the detail snapshot price.
  // Falls back to detail.current_price when the chart hasn't emitted yet.
  const effectivePrice = livePrice ?? detail?.current_price ?? null;

  const tradingGates = useMemo(() => {
    const inv = detail?.investor_summary;
    const cp = effectivePrice;
    if (!inv || cp == null || !(cp > 0)) return [];
    // The ML gate inside retail_action.gates always scores the short (1-month) horizon —
    // fine for Scout, misleading for Swing/Owner (e.g. GOOGL: 32% short vs 68% long ML prob,
    // same "ML PROBABILITY: Marginal pass" label either way). gates_by_mode carries a variant
    // per persona with only that gate swapped to the matching horizon; prefer it when present.
    const byMode = inv.retail_action?.gates_by_mode?.[decisionMode];
    if (byMode?.length) return byMode.map(mapApiGateToRow);
    return buildGatesFromInvestorSummary(inv, cp);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail, effectivePrice, decisionMode]);

  const { passed: gatesPassedCount, total: gatesTotal } = useMemo(
    () => resolvePrimaryGatesCount(tradingGates),
    [tradingGates],
  );

  const headlineScore = useMemo(() => {
    const inv = detail?.investor_summary as
      | (InvestorDecisionSummary & {
          actionable_score?: {
            setup_quality?: number | null;
            actionable?: number | null;
            stale?: boolean;
            note?: string;
          };
        })
      | null
      | undefined;
    const fromApi = inv?.actionable_score;
    const setup =
      detail?.score_breakdown?.composite ?? inv?.pattern_score ?? null;
    const conf =
      inv?.model_confidence_pct ??
      inv?.trade_roadmap?.tldr?.model_confidence_pct ??
      null;
    if (fromApi && (fromApi.actionable != null || fromApi.stale || fromApi.setup_quality != null)) {
      return {
        actionable: fromApi.actionable ?? null,
        setup: fromApi.setup_quality ?? (setup != null ? Number(setup) : null),
        stale: !!fromApi.stale,
        note: fromApi.note ?? null,
        confidencePct: conf != null ? Number(conf) : null,
      };
    }
    const computed = computeActionableScore({
      setupQuality: setup != null ? Number(setup) : null,
      gatesPassed: tradingGates.length ? gatesPassedCount : null,
      gatesTotal,
      fusedConfidencePct: conf != null ? Number(conf) : null,
    });
    return {
      actionable: computed.actionable,
      setup: computed.setup_quality,
      stale: computed.stale,
      note: computed.note,
      confidencePct: conf != null ? Number(conf) : null,
    };
  }, [detail, tradingGates.length, gatesPassedCount, gatesTotal]);

  const quoteDailyMovePct = useMemo(() => {
    // Prefer live intraday change pct (1D chart, from open) when available
    if (liveChangePct != null) return liveChangePct;
    if (detail?.daily_move_pct != null) return detail.daily_move_pct;
    const hist = detail?.price_history;
    if (!hist || hist.length < 2) return null;
    const c0 = hist[hist.length - 2]?.close;
    const c1 = hist[hist.length - 1]?.close;
    if (c0 == null || c1 == null || c0 <= 0) return null;
    return ((c1 - c0) / c0) * 100;
  }, [liveChangePct, detail?.daily_move_pct, detail?.price_history]);

  const headerRegime = useMemo((): "UP" | "DOWN" | "NEUTRAL" | "EXTENDED" => {
    const inv = detail?.investor_summary;
    if (inv?.regime_momentum_extended) return "EXTENDED";
    const rb = inv?.regime_bull_pct;
    if (rb != null && rb >= 60) return "UP";
    if (rb != null && rb <= 40) return "DOWN";
    return "NEUTRAL";
  }, [detail?.investor_summary]);

  const modalNewsRail = useMemo(() => {
    const roadmapNews = detail?.investor_summary?.trade_roadmap?.news_sentiment_layer;
    const catalyst = detail?.catalyst?.headline_summary;
    return {
      label: roadmapNews?.display_label ?? roadmapNews?.sentiment_label ?? null,
      score: roadmapNews?.score_0_1 ?? null,
      headlineCount: roadmapNews?.headline_count ?? null,
      headlines: (roadmapNews?.headlines ?? []).map((h) => ({ title: h.title, url: h.url })),
      catalystNote: catalyst ?? detail?.catalyst?.override_note ?? null,
      sentimentCaveat: roadmapNews?.sentiment_caveat ?? null,
      catalystCards: roadmapNews?.catalyst_cards ?? [],
    };
  }, [detail]);

  // Header "vs FV" must be (price−FV)/FV — NOT (FV−price)/price (upside-to-FV),
  // which was misread as MOS surplus (AVGO +42% badge vs true −30% discount).
  // Header "vs FV" = (price-FV)/FV. Not (FV-price)/price (upside-to-FV / false MOS).
  const assessmentPctForHeader = useMemo(() => {
    const inv = detail?.investor_summary;
    const cp = effectivePrice;
    if (!inv || !cp || !(inv.fair_value > 0)) return 0;
    return pctPriceVsFairValue(cp, inv.fair_value);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail, effectivePrice]);

  const executionVm = useMemo(() => {
    const inv = detail?.investor_summary;
    const cp = effectivePrice ?? 0;
    if (!inv || cp <= 0) return null;
    return buildExecutionPlanViewModel(inv, cp, decisionMode);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.investor_summary, effectivePrice, decisionMode]);

  const horizonPlaybooksBundle = useMemo((): HorizonPlaybooksBundle | null => {
    const inv = detail?.investor_summary;
    if (!inv) return null;
    const bundle = inv.horizon_playbooks as HorizonPlaybooksBundle | null | undefined;
    if (bundle && (bundle.swing?.active || bundle.medium?.active || bundle.long?.active)) {
      return bundle;
    }
    if (inv.swing_setup?.active) {
      return {
        default_primary: "short",
        intent_map: { trade: "short", invest: "long", unset: "short" },
        swing: inv.swing_setup,
      };
    }
    return null;
  }, [detail]);

  if (typeof window === "undefined") return null;

  /** Sidebar tabs + two-column Verdict only when the detail has the full overlay width. */
  const wide = layout === "drawer" || (layout === "pane" && expanded);

  // Shared prop bag for the extracted tab bodies (P4). detail is non-null
  // whenever any tab renders — every tab block sits inside {detail && !loading}.
  const tabCtx: TabCtx = {
    ticker,
    detail: detail!,
    wide,
    decisionMode,
    positionIntent,
    effectivePrice,
    quoteDailyMovePct,
    headerActionStatus,
    tradingGates,
    gatesPassedCount,
    gatesTotal,
    confidence,
    unified,
    priceTargets,
    executionVm,
    ltEntryTiersOpen,
    setLtEntryTiersOpen,
    quickRefOpen,
    setQuickRefOpen,
    debugPanelOpen,
    setDebugPanelOpen,
    moreContextOpen,
    setMoreContextOpen,
    metricsGuideOpen,
    setMetricsGuideOpen,
    portfolioImpactContext,
    playbookStage3,
    regimeShift,
    horizonPlaybooksBundle,
    modalNewsRail,
    overviewVerdict,
    patternVerdict,
    hasVerdictConflict,
    periods,
    whySubTab,
    setWhySubTab,
    setModalTab,
    openWhyValuation,
    setLivePrice,
    setLiveChangePct,
    setPositionIntentLocal,
    setDecisionModeLocal,
  };

  const body = (
      <>
        {/* Header — ticker · price · market status, then the mode switch and (mobile) tab strip,
            all in one sticky block so they never scroll apart. */}
        <div className="sticky top-0 z-20 bg-td-surface/95 backdrop-blur border-b border-td-line">
          <div className="px-4 sm:px-6 pt-3 pb-2 flex items-start gap-2">
            <button
              type="button"
              onClick={onClose}
              className={clsx(
                "mt-0.5 p-1.5 -ml-1.5 rounded-lg text-td-muted hover:text-td-text hover:bg-td-surface2",
                layout !== "page" && "hidden",
              )}
              aria-label="Back"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <div className="min-w-0 flex-1">
              <p id="ticker-detail-title" className="flex items-baseline gap-2 min-w-0">
                <span className="font-mono text-lg font-bold text-td-text tracking-tight">{ticker}</span>
                {detail && !loading && (
                  <span className="text-[12px] text-td-muted truncate">
                    {detail.company_name ?? ""}
                    {detail.sector ? ` · ${detail.sector}` : ""}
                  </span>
                )}
              </p>
              {detail && !loading && effectivePrice != null && (
                <div className="mt-0.5 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="font-mono text-2xl font-bold text-td-text tabular-nums">${effectivePrice.toFixed(2)}</span>
                  {quoteDailyMovePct != null && (
                    <span className={clsx("font-mono text-[13px] tabular-nums", quoteDailyMovePct >= 0 ? "text-td-accent" : "text-td-crit")}>
                      {quoteDailyMovePct >= 0 ? "+" : "−"}
                      {Math.abs(quoteDailyMovePct).toFixed(2)}%
                    </span>
                  )}
                  <span className="inline-flex items-center gap-1.5 text-[11px] text-td-muted">
                    {livePrice != null ? (
                      <>
                        <span className="h-1.5 w-1.5 rounded-full bg-td-accent animate-pulse" />
                        Live
                      </>
                    ) : isUsEquityRth() ? (
                      "Delayed quote"
                    ) : (
                      "Market closed · last close"
                    )}
                  </span>
                </div>
              )}
              {detail && !loading && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10.5px] font-mono">
                  {headlineScore.actionable != null && (
                    <span
                      className="px-1.5 py-0.5 rounded border border-td-line bg-td-surface2 text-td-text"
                      title={headlineScore.note || "Confidence-adjusted — gates × fused confidence applied to setup quality"}
                    >
                      Score {Math.round(headlineScore.actionable)}
                      {headlineScore.setup != null && <span className="text-td-muted"> · setup {Math.round(headlineScore.setup)}</span>}
                    </span>
                  )}
                  <span
                    className={clsx(
                      "px-1.5 py-0.5 rounded border",
                      headerRegime === "UP" && "border-td-accent/40 text-td-accent",
                      headerRegime === "DOWN" && "border-td-crit/40 text-td-crit",
                      headerRegime === "EXTENDED" && "border-td-warn/40 text-td-warn",
                      headerRegime === "NEUTRAL" && "border-td-line text-td-muted",
                    )}
                  >
                    {headerRegime}
                  </span>
                  {headlineScore.confidencePct != null && (
                    <span className="px-1.5 py-0.5 rounded border border-td-line text-td-muted" title="Fused 7-layer model confidence">
                      Confidence {Math.round(headlineScore.confidencePct)}%
                    </span>
                  )}
                  {detail.investor_summary && (
                    <span
                      className={clsx(
                        "px-1.5 py-0.5 rounded border border-td-line",
                        // (price-FV)/FV: negative = discount (constructive), positive = premium
                        assessmentPctForHeader <= 0 ? "text-td-info" : "text-td-warn",
                      )}
                    >
                      {assessmentPctForHeader >= 0 ? "+" : "−"}
                      {Math.abs(assessmentPctForHeader).toFixed(1)}% vs FV
                    </span>
                  )}
                </div>
              )}
            </div>
            {layout === "pane" && onExpand && (
              <button
                type="button"
                onClick={onExpand}
                className="p-2 rounded-lg hover:bg-td-surface2 text-td-muted hover:text-td-text"
                aria-label={expanded ? "Back to split view" : "Expand ticker detail"}
                title={expanded ? "Back to split view" : "Expand — full width with section sidebar"}
              >
                {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </button>
            )}
            {layout !== "page" && (
              <button
                onClick={onClose}
                className="p-2 rounded-lg hover:bg-td-surface2 text-td-muted hover:text-td-text"
                aria-label="Close ticker detail"
              >
                <X className="h-5 w-5" />
              </button>
            )}
          </div>
          {detail && !loading && detail.investor_summary && (
            <div className="px-4 sm:px-6 pb-2.5">
              <DecisionModeSelector mode={decisionMode} onChange={handleDecisionMode} variant="segmented" className="max-w-md" />
            </div>
          )}
          {/* Mobile / tablet tab strip — desktop gets the left sidebar below */}
          {detail && !loading && (
            <div className={clsx("flex overflow-x-auto border-t border-td-line px-2", wide && "lg:hidden")} role="tablist" aria-label="Ticker sections">
              {MODAL_TABS.map(({ id, label }) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={modalTab === id}
                  onClick={() => setModalTab(id)}
                  className={clsx(
                    "shrink-0 px-3 py-2.5 text-[13px] font-semibold border-b-2 -mb-px transition-colors",
                    modalTab === id ? "text-td-text border-td-accent" : "text-td-muted border-transparent hover:text-td-text",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Catalyst — summary first, full note on expand */}
        {detail && !loading && detail.catalyst?.active && (
          <div className="border-b border-td-warn/30 bg-td-warn-weak px-3 py-2 sm:px-6">
            <button
              type="button"
              onClick={() => setCatalystExpanded((e) => !e)}
              className="w-full flex items-start gap-2 text-left touch-manipulation"
              aria-expanded={catalystExpanded}
            >
              <span className="shrink-0 mt-0.5 inline-flex items-center rounded-full bg-td-warn/20 px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-td-warn ring-1 ring-td-warn/40">
                {detail.catalyst.top_event_type?.replace(/_/g, " ") ?? "CATALYST"}
              </span>
              <span className="text-xs text-td-text/85 leading-relaxed flex-1 min-w-0">
                {catalystExpanded
                  ? detail.catalyst.override_note
                  : `${(detail.catalyst.override_note || "").slice(0, 140)}${(detail.catalyst.override_note || "").length > 140 ? "…" : ""}`}
              </span>
              <span className="shrink-0 text-td-warn/80 text-xs font-semibold pt-0.5">{catalystExpanded ? "Hide" : "More"}</span>
            </button>
          </div>
        )}

        {/* Post-earnings transition banner */}
        {detail && !loading && detail.post_earnings_transition?.active && (
          <div className={`border-b px-4 py-2.5 sm:px-6 flex items-start gap-2 ${
            detail.post_earnings_transition.signal_direction === "bullish"
              ? "border-emerald-500/30 bg-emerald-950/80"
              : detail.post_earnings_transition.signal_direction === "bearish"
                ? "border-red-500/30 bg-red-950/80"
                : "border-slate-600 bg-slate-800/80"
          }`}>
            <span className={`shrink-0 mt-0.5 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-bold uppercase tracking-wider ring-1 ${
              detail.post_earnings_transition.beat_or_miss === "beat"
                ? "bg-emerald-500/20 text-emerald-300 ring-emerald-500/40"
                : detail.post_earnings_transition.beat_or_miss === "miss"
                  ? "bg-red-500/20 text-red-300 ring-red-500/40"
                  : "bg-slate-500/20 text-slate-300 ring-slate-500/40"
            }`}>
              {detail.post_earnings_transition.beat_or_miss === "beat" ? "EARNINGS BEAT" :
               detail.post_earnings_transition.beat_or_miss === "miss" ? "EARNINGS MISS" : "EARNINGS INLINE"}
            </span>
            <p className="text-xs text-slate-200/90 leading-relaxed">
              {detail.post_earnings_transition.transition_note}
            </p>
          </div>
        )}

        <div className={clsx(wide && "lg:grid lg:grid-cols-[11.5rem_minmax(0,1fr)]")}>
        {/* Desktop: tabs become a left sidebar list — each section one click away, no swipe */}
        {wide && detail && !loading && (
          <nav
            className="hidden lg:block border-r border-td-line bg-td-bg/40 px-3 py-5"
            role="tablist"
            aria-label="Ticker sections"
          >
            <div className="sticky top-44 space-y-1">
              {MODAL_TABS.map(({ id, label, hint, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={modalTab === id}
                  onClick={() => setModalTab(id)}
                  className={clsx(
                    "w-full text-left rounded-lg px-3 py-2 transition-colors border",
                    modalTab === id
                      ? "bg-td-accent-weak/60 border-td-accent/35 text-td-text"
                      : "border-transparent text-td-muted hover:text-td-text hover:bg-td-surface2/60",
                  )}
                >
                  <span className="flex items-center gap-2 text-[13px] font-semibold">
                    <Icon className={clsx("h-4 w-4 shrink-0", modalTab === id ? "text-td-accent" : "")} />
                    {label}
                  </span>
                  <span className="block pl-6 text-[10.5px] text-td-muted leading-tight">{hint}</span>
                </button>
              ))}
            </div>
          </nav>
        )}

        <div className="min-w-0 p-4 sm:p-6 space-y-6">
          {loading && (
            <div className="flex flex-col items-center justify-center py-12 gap-3 px-4">
              <div className="animate-spin rounded-full h-10 w-10 border-2 border-emerald-500 border-t-transparent" />
              <p className="text-sm text-slate-400 text-center max-w-sm leading-snug">
                Loading {ticker}… first open builds the full decision deck (usually 20–60s).
              </p>
            </div>
          )}
          {error && (
            <div className="py-4 space-y-3">
              <p className="text-red-400 text-sm leading-snug">Failed to load: {error}</p>
              <button
                type="button"
                onClick={() => setReloadKey((k) => k + 1)}
                className="text-sm px-4 py-2 rounded-lg bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-600/30"
              >
                Retry
              </button>
            </div>
          )}
          {detail && !loading && (
            <>
              {/* ── Tab bodies extracted to tickerDetail/tabs/* (P4 split) ── */}
              {modalTab === "verdict" && <VerdictTab ctx={tabCtx} />}
              {modalTab === "levels" && <LevelsTab ctx={tabCtx} />}
              {modalTab === "why" && <WhyTab ctx={tabCtx} />}
              {modalTab === "context" && <ContextTab ctx={tabCtx} />}

              {modalTab === "track" && <TrackRecordPanel ticker={detail.ticker} />}
            </>
          )}
        </div>
        </div>
      </>
  );

  if (layout === "pane") {
    return (
      <div
        className="td-skin font-td-sans h-full overflow-y-auto overscroll-contain bg-slate-900"
        role="region"
        aria-labelledby="ticker-detail-title"
      >
        {body}
      </div>
    );
  }

  if (layout === "page") {
    /** Full-screen page above the app header; stops above the mobile bottom nav so
     * Today / Signals / Plan stay one tap away. */
    return createPortal(
      <div
        className="td-skin font-td-sans td-slide-in fixed inset-x-0 top-0 z-[60] overflow-y-auto overscroll-contain bg-slate-900"
        style={{ bottom: "calc(55px + max(0.5rem, env(safe-area-inset-bottom)))" }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ticker-detail-title"
      >
        {body}
      </div>,
      document.body,
    );
  }

  /** Portal + high z-index: avoids clipping under sticky dashboard header (also z-50). */
  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex justify-end bg-black/60 backdrop-blur-[2px]"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="td-skin font-td-sans td-slide-in bg-slate-900 border-l border-slate-700/90 h-full w-[min(96vw,1280px)] overflow-y-auto overscroll-contain shadow-2xl shadow-black/50"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ticker-detail-title"
      >
        {body}
      </div>
    </div>,
    document.body
  );
}
