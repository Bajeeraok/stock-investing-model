"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { X, TrendingUp, FileText, Calendar, BarChart3, HelpCircle, ChevronDown, ChevronRight, Activity, LayoutGrid, Target, Layers, Zap, Ban, Eye, CheckCircle, AlertCircle } from "lucide-react";
import { clsx } from "clsx";
import { ConfidenceBreakdown, type ConfidenceData } from "./ConfidenceBreakdown";
import { PatternSignalCard, type UnifiedSignalData } from "./PatternSignalCard";
import { PriceTargetsPanel, type PriceTargetsData } from "./PriceTargetsPanel";
import { InvestorDecisionSummarySection, type InvestorDecisionSummary } from "./InvestorDecisionSummary";
import { TradeRoadmapCard } from "./TradeRoadmapCard";
import { DataMetricCard } from "./DataMetricCard";

// Lightweight try/catch wrappers so a bad API response never crashes the modal
function ConfidenceBreakdownSafe({ data }: { data: ConfidenceData }) {
  try { return <ConfidenceBreakdown data={data} />; }
  catch { return null; }
}
function PatternSignalCardSafe({ data }: { data: UnifiedSignalData }) {
  try { return <PatternSignalCard data={data} />; }
  catch { return null; }
}

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
      title: "WATCH OR HOLD",
      subtitle:
        "Valuation is attractive, but regime and chart still cautious — research mode; wait for clearer triggers.",
    };
  }

  if (discountPct >= 5 && regime != null && regime < 48) {
    return {
      light: "yellow",
      title: "WATCH OR HOLD",
      subtitle: "Cheap vs fair value, but market regime is not bullish yet — patience or smaller probes only.",
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
          <p className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Action status</p>
          <p className={clsx("text-lg font-bold tracking-tight", styles.accent)}>{status.title}</p>
        </div>
      </div>
      <div className="text-sm text-slate-200/95 leading-snug sm:flex-1 sm:min-w-0 border-t border-white/5 sm:border-0 sm:border-l sm:border-white/10 sm:pl-4 pt-2 sm:pt-0 space-y-1.5">
        <p>{status.subtitle}</p>
        <p
          className="text-[11px] text-slate-400 leading-snug cursor-help"
          title="Fair value compares price to our model anchor. Regime is risk-on vs risk-off from the model. They are allowed to disagree: cheap can stay cheap until the tape improves."
        >
          Quick read: <span className="text-slate-300">Fair value</span> = price vs our estimate of worth.{" "}
          <span className="text-slate-300">Regime / action</span> = whether the model wants full size right now. Yellow often means “good value, wait for better timing.”
        </p>
      </div>
    </div>
  );
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

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
    history: { quarter: string; actual: number | null; estimate: number | null; beat_pct: number | null; status: string }[];
    beat_rate: number;
    summary: string;
  };
  sector_specific?: Record<string, number | string>;
  rate_sensitivity?: {
    correlation_with_tlt: number;
    interpretation: string;
    note: string;
  };
  /** Rolling correlation vs GLD / UUP / VIX — macro sensitivity badges */
  cross_asset?: { badges: string[]; correlations?: Record<string, number | null> } | null;
  investor_summary?: InvestorDecisionSummary | null;
  /** PE/EPS/FMP data are latest vendor snapshot — not point-in-time historical fundamentals. */
  fundamentals_snapshot?: {
    point_in_time: boolean;
    short_label: string;
    detail: string;
  };
}

export function TickerDetailModal({
  ticker,
  onClose,
}: {
  ticker: string;
  onClose: () => void;
}) {
  const [detail, setDetail]               = useState<TickerDetail | null>(null);
  const [confidence, setConfidence]        = useState<ConfidenceData | null>(null);
  const [unified, setUnified]              = useState<UnifiedSignalData | null>(null);
  const [priceTargets, setPriceTargets]    = useState<PriceTargetsData | null>(null);
  const [loading, setLoading]              = useState(true);
  const [error, setError]                  = useState<string | null>(null);
  const [quickRefOpen, setQuickRefOpen]    = useState(false);
  const [ltEntryTiersOpen, setLtEntryTiersOpen] = useState(false);
  const [metricsGuideOpen, setMetricsGuideOpen] = useState(false);
  const [modalTab, setModalTab] = useState<"overview" | "roadmaps" | "details">("overview");
  const [catalystExpanded, setCatalystExpanded] = useState(false);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  useEffect(() => {
    if (!ticker) return;
    setModalTab("overview");
    setCatalystExpanded(false);
    setLoading(true);
    setError(null);
    setConfidence(null);
    setUnified(null);
    setPriceTargets(null);

    const base = (path: string) => API_BASE ? `${API_BASE}${path}` : path;

    // Main ticker detail (required)
    fetch(base(`/api/ticker/${ticker}`))
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setDetail)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

    // Confidence engine (optional — runs in background, shows when ready)
    fetch(base(`/api/confidence/${ticker}`))
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setConfidence(d))
      .catch(() => {/* graceful — confidence unavailable */});

    // Unified signal engine (optional — runs in background)
    fetch(base(`/api/unified-signal/${ticker}`))
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setUnified(d))
      .catch(() => {/* graceful — unified signal unavailable */});

    // Price targets + scenario analysis (optional — runs in background)
    fetch(base(`/api/price-targets/${ticker}`))
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && !d.error && setPriceTargets(d))
      .catch(() => {/* graceful — price targets unavailable */});
  }, [ticker]);

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

  /** Portal + high z-index: avoids clipping under sticky dashboard header (also z-50) and parent overflow on mobile. */
  if (typeof window === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center overflow-y-auto overscroll-y-contain bg-black/80 backdrop-blur-sm px-3 pt-[max(12px,env(safe-area-inset-top))] pb-[max(12px,env(safe-area-inset-bottom))] sm:items-center sm:p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="bg-slate-900 border border-slate-700/90 rounded-2xl w-[min(96vw,1280px)] max-w-full max-h-[calc(100dvh-env(safe-area-inset-top)-env(safe-area-inset-bottom)-1.5rem)] sm:max-h-[92vh] my-2 sm:my-0 overflow-y-auto overscroll-contain shadow-2xl shadow-black/50"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ticker-detail-title"
      >
        <div className="sticky top-0 bg-slate-900 border-b border-slate-700/80 px-5 sm:px-6 py-4 flex items-center justify-between z-20">
          <h2 id="ticker-detail-title" className="text-xl font-bold text-slate-100 flex items-center gap-2 flex-wrap">
            <TrendingUp className="h-6 w-6 text-emerald-500 shrink-0" />
            <span className="font-mono text-emerald-400">{ticker}</span>
            {detail?.company_name && (
              <span className="text-base font-normal text-slate-300">· {detail.company_name}</span>
            )}
            {detail?.sector && (
              <span className="text-base font-normal text-slate-400">· {detail.sector}</span>
            )}
          </h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {detail && !loading && detail.investor_summary && (
          <RetailActionStatusBanner status={retailActionStatus} />
        )}

        {/* Catalyst — summary first, full note on expand */}
        {detail && !loading && detail.catalyst?.active && (
          <div className="border-b border-amber-500/30 bg-amber-950/80 px-3 py-2 sm:px-6">
            <button
              type="button"
              onClick={() => setCatalystExpanded((e) => !e)}
              className="w-full flex items-start gap-2 text-left touch-manipulation"
              aria-expanded={catalystExpanded}
            >
              <span className="shrink-0 mt-0.5 inline-flex items-center rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300 ring-1 ring-amber-500/40">
                {detail.catalyst.top_event_type?.replace(/_/g, " ") ?? "CATALYST"}
              </span>
              <span className="text-xs text-amber-200/90 leading-relaxed flex-1 min-w-0">
                {catalystExpanded
                  ? detail.catalyst.override_note
                  : `${(detail.catalyst.override_note || "").slice(0, 140)}${(detail.catalyst.override_note || "").length > 140 ? "…" : ""}`}
              </span>
              <span className="shrink-0 text-amber-400/80 text-[10px] font-semibold pt-0.5">{catalystExpanded ? "Hide" : "More"}</span>
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
            <span className={`shrink-0 mt-0.5 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ring-1 ${
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

        {/* Ticker hub — quick read strip */}
        {detail && !loading && (
          <div className="border-b border-slate-700 bg-slate-900/90 px-3 sm:px-5 py-3">
            <p className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Ticker hub</p>
            <div className="flex gap-2 overflow-x-auto [-webkit-overflow-scrolling:touch] pb-0.5">
              <DataMetricCard
                dense
                className="shrink-0 min-w-[7rem]"
                title="Last"
                primary={detail.current_price != null ? `$${detail.current_price.toFixed(2)}` : "—"}
                secondary={detail.sector ?? undefined}
              />
              <DataMetricCard
                dense
                className="shrink-0 min-w-[7.5rem]"
                title="Plan"
                primary={detail.investor_summary?.one_answer?.verdict ?? detail.investor_summary?.overall_verdict ?? "—"}
                secondary={unified?.action ? `Pattern: ${unified.action}` : undefined}
              />
              <DataMetricCard
                dense
                className="shrink-0 min-w-[8rem]"
                title="Next earnings"
                primary={
                  detail.earnings?.date
                    ? detail.earnings.days_until > 0
                      ? `T+${detail.earnings.days_until}d`
                      : "Soon"
                    : "—"
                }
                secondary={detail.earnings?.date ?? undefined}
              />
            </div>
          </div>
        )}

        {/* Tab bar: hub sections */}
        {detail && !loading && (
          <div className="border-b border-slate-700 bg-slate-900 sticky top-0 z-[15]">
            <div className="flex">
            {(
              [
                { id: "overview" as const, label: "One answer", icon: Target },
                { id: "roadmaps" as const, label: "Roadmaps", icon: LayoutGrid },
                { id: "details" as const, label: "Deep dive", icon: Layers },
              ] as const
            ).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setModalTab(id)}
                className={clsx(
                  "flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors",
                  modalTab === id
                    ? "text-emerald-400 border-b-2 border-emerald-500 bg-slate-800/50"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/30"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </button>
            ))}
            </div>
            <p className="text-center text-[11px] text-slate-500 px-2 py-1.5 border-t border-slate-800">
              One answer: today&apos;s takeaway · Roadmaps: prices &amp; steps · Deep dive: models, thesis, and history
            </p>
          </div>
        )}

        <div className="p-4 sm:p-6 space-y-6">
          {loading && (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-10 w-10 border-2 border-emerald-500 border-t-transparent" />
            </div>
          )}
          {error && (
            <p className="text-red-400 py-4">Failed to load: {error}</p>
          )}
          {detail && !loading && (
            <>
              {/* ── Overview tab: One Answer + horizons + CTA to Roadmaps ───── */}
              {modalTab === "overview" && (
                <>
              {detail.fundamentals_snapshot && !detail.fundamentals_snapshot.point_in_time && (
                <p
                  className="text-xs text-slate-500 border border-slate-600/80 bg-slate-800/40 rounded-lg px-3 py-2 mb-3 leading-snug"
                  title={detail.fundamentals_snapshot.detail}
                >
                  <span className="text-amber-400/90 font-medium">Note:</span>{" "}
                  Fair value and valuation numbers reflect the latest available data, not a historical snapshot. Treat them as helpful context, not a precise calculation.
                </p>
              )}
              {detail.cross_asset && (detail.cross_asset.badges?.length ?? 0) > 0 && (
                <div className="flex flex-wrap items-center gap-2 mb-4">
                  <span className="text-xs text-slate-500">Tends to move with:</span>
                  {detail.cross_asset.badges.map((b) => (
                    <span
                      key={b}
                      className="text-[11px] px-2 py-0.5 rounded-md bg-slate-800 border border-slate-600 text-slate-300"
                      title="How this stock has tended to move with gold, the U.S. dollar, and the fear gauge (VIX) over the last ~60 trading days"
                    >
                      {b}
                    </span>
                  ))}
                </div>
              )}

              {confidence && playbookStage3 && (
                <button
                  type="button"
                  onClick={() => setModalTab("details")}
                  className="w-full text-left rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 mb-4 flex items-center gap-3 hover:bg-amber-500/15 transition-colors"
                >
                  <Zap className="h-5 w-5 text-amber-300 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-amber-100">Possible change in market mood</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Our read suggests the backdrop for stocks may be shifting. Open Details for the full breakdown.
                    </p>
                  </div>
                  <ChevronRight className="h-5 w-5 text-amber-400/80 shrink-0" aria-hidden />
                </button>
              )}

              {/* ── Investor Decision Summary (horizon entry + tiers) ───── */}
              {detail.investor_summary ? (
                <InvestorDecisionSummarySection
                  summary={detail.investor_summary}
                  currentPrice={detail.current_price ?? 0}
                  ma200={detail.ma200}
                  sector={detail.sector}
                  companyName={detail.company_name}
                  ltEntryTiersOpen={ltEntryTiersOpen}
                  onToggleLtTiers={() => setLtEntryTiersOpen((o) => !o)}
                />
              ) : (
                <section className="rounded-xl border border-slate-700 bg-slate-800/50 p-6 text-center">
                  <AlertCircle className="h-8 w-8 text-slate-500 mx-auto mb-2" />
                  <p className="text-sm text-slate-400">Signal data is still loading or unavailable for this ticker.</p>
                  <p className="text-xs text-slate-500 mt-1">Try refreshing the dashboard or check if the ticker is in your watchlist.</p>
                </section>
              )}

              {/* CTA: jump to Roadmaps tab for full buy/sell tables */}
              {detail.investor_summary?.trade_roadmap && (
                <section className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
                  <p className="text-sm text-slate-300 mb-2">Full buy/sell roadmap with timeline, trader type, and price zones.</p>
                  <button
                    type="button"
                    onClick={() => setModalTab("roadmaps")}
                    className="text-sm font-medium text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
                  >
                    See full Roadmaps <ChevronRight className="h-4 w-4" />
                  </button>
                </section>
              )}

              {/* Quick reference – at bottom so it doesn't clutter the primary decision view */}
              <section className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl overflow-hidden">
                <button
                  type="button"
                  onClick={() => setQuickRefOpen((o) => !o)}
                  className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-emerald-500/10 transition-colors"
                >
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
                    <HelpCircle className="h-4 w-4 shrink-0" />
                    Terms explained
                  </h3>
                  {quickRefOpen ? (
                    <ChevronDown className="h-4 w-4 text-slate-400 shrink-0" aria-hidden />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-slate-400 shrink-0" aria-hidden />
                  )}
                </button>
                {quickRefOpen && (
                  <div className="px-4 pb-4 pt-0 border-t border-emerald-500/20">
                    <ul className="space-y-1.5 text-sm text-slate-300 list-disc list-inside columns-1 sm:columns-2 gap-x-4">
                      <li><span className="font-medium text-slate-200">Price vs averages:</span> Above the 50- and 200-day lines usually means a stronger uptrend; below usually means weaker.</li>
                      <li><span className="font-medium text-slate-200">20 / 50 / 200-day lines:</span> Short-, medium-, and long-term average price—often used as support or resistance.</li>
                      <li><span className="font-medium text-emerald-400">Add / buy zone:</span> A price area where adding shares may make sense (for example after a dip to an average).</li>
                      <li><span className="font-medium text-red-400">Trim / take profits:</span> A zone where taking some profit or cutting size may make sense.</li>
                      <li><span className="font-medium text-amber-400">Support:</span> A level where price has tended to hold; a clean break below can mean extra caution.</li>
                      <li><span className="font-medium text-slate-200">Position size:</span> Smaller size when risk flags show up.</li>
                      <li><span className="font-medium text-amber-400">Crowded bets:</span> When many traders are leaning the same way, reversals can happen.</li>
                      <li><span className="font-medium text-slate-200">Risk-on vs risk-off:</span> Whether markets broadly favor stocks vs safer assets—helps with how much to invest.</li>
                      <li><span className="font-medium text-slate-200">Sector rotation risk:</span> When money is moving out of a group (e.g. tech), ratings can soften.</li>
                      <li><span className="font-medium text-slate-200">Near term / medium / long:</span> About the next month · about 3–6 months · about a year or more.</li>
                      <li><span className="font-medium text-slate-200">Volume, drop from high, yearly range:</span> Trading activity vs normal; how far price is under the 52-week high; high–low of the past year.</li>
                      <li><span className="font-medium text-slate-200">Dividend, volatility vs market, vs S&amp;P:</span> Income from dividends; how jumpy the stock is vs the S&amp;P 500; return vs the index.</li>
                    </ul>
                  </div>
                )}
              </section>
                </>
              )}

              {/* ── Roadmaps tab: only Trade Roadmap card ──────────────────── */}
              {modalTab === "roadmaps" && (
                detail.investor_summary?.trade_roadmap ? (
                  <TradeRoadmapCard data={detail.investor_summary.trade_roadmap} ticker={detail.ticker} />
                ) : (
                  <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-6 text-center text-slate-400">
                    <p className="text-sm">Roadmap not available for this ticker.</p>
                    <button
                      type="button"
                      onClick={() => setModalTab("overview")}
                      className="mt-2 text-sm text-emerald-400 hover:text-emerald-300"
                    >
                      Back to Overview
                    </button>
                  </div>
                )
              )}

              {/* ── Details tab: Confidence, signals, targets, thesis, etc. ── */}
              {modalTab === "details" && (
                <>
              {/* ── 1. Story & catalysts (plain context before models) ─────── */}
              {(detail.thesis || detail.exit_condition) && (
                <section>
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-2">
                    <FileText className="h-4 w-4" />
                    Why we&apos;re watching this name
                  </h3>
                  <div className="bg-slate-800/50 rounded-lg p-4 text-base text-slate-300 space-y-2">
                    {detail.thesis && <p>{detail.thesis}</p>}
                    {detail.exit_condition && (
                      <p className="text-amber-400/90">
                        <span className="text-slate-400">Sell or rethink if:</span> {detail.exit_condition}
                      </p>
                    )}
                    {!detail.thesis && !detail.exit_condition && (
                      <p className="text-slate-500 italic">No written thesis yet. Add in data/theses.yaml or via add_thesis.py</p>
                    )}
                  </div>
                </section>
              )}

              {(detail.earnings || (detail.earnings_history?.history?.length ?? 0) > 0) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-3">
                    <Calendar className="h-4 w-4 text-emerald-500" />
                    Earnings calendar
                  </h3>
                  {detail.earnings && (
                    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-2 text-sm text-amber-200 mb-3">
                      <span className="text-slate-400 text-xs mr-2">Next report</span>
                      {detail.earnings.date}
                      {detail.earnings.days_until != null && (
                        <span className="text-amber-400/80 ml-2">
                          ({detail.earnings.days_until > 0 ? `in ${detail.earnings.days_until} days` : "recent"})
                        </span>
                      )}
                    </div>
                  )}
                  {detail.earnings_history && (detail.earnings_history.history?.length ?? 0) > 0 && (
                    <>
                  <p className="text-xs text-slate-500 mb-1">Recent quarters vs expectations</p>
                  <p className="text-slate-400 text-xs mb-2">{detail.earnings_history.summary}</p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-slate-500">
                          <th className="pr-3 py-1">Quarter</th>
                          <th className="pr-3 py-1">Reported</th>
                          <th className="pr-3 py-1">Expected</th>
                          <th className="py-1">Surprise</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(detail.earnings_history.history ?? []).map((q, i) => (
                          <tr key={i} className="border-t border-slate-700/50 text-slate-300">
                            <td className="pr-3 py-1">{q.quarter}</td>
                            <td className="pr-3 py-1">{q.actual != null ? q.actual : "–"}</td>
                            <td className="pr-3 py-1">{q.estimate != null ? q.estimate : "–"}</td>
                            <td className="py-1">
                              {q.beat_pct != null ? (
                                <span className={q.status === "Beat" ? "text-emerald-400" : "text-red-400"}>
                                  {q.beat_pct > 0 ? "+" : ""}{q.beat_pct}% {q.status}
                                </span>
                              ) : "N/A"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                    </>
                  )}
                </section>
              )}

              {/* Returns: market + sector + peers in one narrative block */}
              <section className="space-y-4">
                <div>
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-1">
                    <BarChart3 className="h-4 w-4" />
                    How the stock has performed
                  </h3>
                  <p className="text-xs text-slate-500 mb-3">
                    &ldquo;Market&rdquo; is the broad U.S. market (S&amp;P 500, ticker SPY). &ldquo;Sector&rdquo; is {detail.sector_etf_name || "the sector ETF"} ({detail.sector_etf}). &ldquo;Extra vs market&rdquo; is this stock&apos;s return minus the market for the same period.
                  </p>
                  <div className="rounded-lg border border-slate-700 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-800/80 text-left text-slate-400">
                        <th className="px-4 py-2 font-medium">Period</th>
                        <th className="px-4 py-2 font-medium text-emerald-400">{detail.ticker}</th>
                        <th className="px-4 py-2 font-medium">Market (SPY)</th>
                        <th className="px-4 py-2 font-medium">Sector</th>
                        <th className="px-4 py-2 font-medium text-slate-500">Extra vs market</th>
                      </tr>
                    </thead>
                    <tbody>
                      {periods.map((p) => {
                        const r = detail.returns[p];
                        const spy = detail.benchmark_spy[p];
                        const ind = detail.benchmark_industry[p];
                        const vsSpy = r != null && spy != null ? r - spy : null;
                        return (
                          <tr key={p} className="border-t border-slate-700/50">
                            <td className="px-4 py-2 text-slate-400">{p}</td>
                            <td className="px-4 py-2">
                              <span className={r != null ? (r >= 0 ? "text-emerald-400" : "text-red-400") : "text-slate-500"}>
                                {r != null ? `${r >= 0 ? "+" : ""}${r}%` : "-"}
                              </span>
                            </td>
                            <td className="px-4 py-2">
                              <span className={spy != null ? (spy >= 0 ? "text-emerald-400" : "text-red-400") : "text-slate-500"}>
                                {spy != null ? `${spy >= 0 ? "+" : ""}${spy}%` : "-"}
                              </span>
                            </td>
                            <td className="px-4 py-2">
                              <span className={ind != null ? (ind >= 0 ? "text-emerald-400" : "text-red-400") : "text-slate-500"}>
                                {ind != null ? `${ind >= 0 ? "+" : ""}${ind}%` : "-"}
                              </span>
                            </td>
                            <td className="px-4 py-2">
                              {vsSpy != null ? (
                                <span className={vsSpy >= 0 ? "text-emerald-400" : "text-red-400"}>
                                  {vsSpy >= 0 ? "+" : ""}{vsSpy.toFixed(1)}%
                                </span>
                              ) : (
                                "-"
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  </div>
                  {(() => {
                    const bestPeriod = (["3m", "6m", "1m"] as const).find((p) => {
                      const r = detail.returns[p];
                      const s = detail.benchmark_spy[p];
                      return r != null && s != null && Math.abs(r - s) >= 5;
                    });
                    if (!bestPeriod) return null;
                    const r = detail.returns[bestPeriod]!;
                    const s = detail.benchmark_spy[bestPeriod]!;
                    const diff = r - s;
                    const absDiff = Math.abs(diff);
                    const word = diff < 0 ? "underperformed" : "outperformed";
                    const actionStatus = detail.investor_summary?.overall_verdict;
                    const confirmMsg =
                      (diff < 0 && (actionStatus === "WAIT" || actionStatus === "WATCH"))
                        ? " \u2014 regime signal confirmed by price action."
                        : (diff > 0 && (actionStatus === "BUY" || actionStatus === "STRONG BUY"))
                          ? " \u2014 price action supports the bullish signal."
                          : ".";
                    return (
                      <p className={`text-[11px] mt-2 px-3 py-1.5 rounded border leading-snug ${diff < 0 ? "text-red-300/90 border-red-500/25 bg-red-950/30" : "text-emerald-300/90 border-emerald-500/25 bg-emerald-950/30"}`}>
                        {detail.ticker} has {word} SPY by {absDiff.toFixed(1)}% over {bestPeriod}{confirmMsg}
                      </p>
                    );
                  })()}
                </div>

                {(detail.peer_returns?.length ?? 0) > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-slate-300 mb-2">Similar companies (for context)</h4>
                    <p className="text-xs text-slate-500 mb-2">{detail.industry || detail.sector || "Peers in the same area"} — returns over the same windows. Your ticker is in the table above.</p>
                    <div className="rounded-lg border border-slate-700 overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-slate-800/80 text-left text-slate-400">
                          <th className="px-4 py-2 font-medium">Ticker</th>
                          {periods.map((p) => (
                            <th key={p} className="px-4 py-2 font-medium">{p}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {detail.peer_returns.map((pr) => (
                          <tr key={pr.ticker} className="border-t border-slate-700/50">
                            <td className="px-4 py-2 font-mono text-slate-300">
                              {pr.ticker}
                              {pr.data_quality_warning && (
                                <span className="text-amber-400 text-xs ml-1" title={pr.data_quality_warning}>⚠</span>
                              )}
                            </td>
                            {periods.map((p) => (
                              <td key={p} className="px-4 py-2">
                                {pr.returns[p] != null ? (
                                  <span className={pr.returns[p]! >= 0 ? "text-emerald-400" : "text-red-400"}>
                                    {pr.returns[p]! >= 0 ? "+" : ""}{pr.returns[p]}%
                                  </span>
                                ) : (
                                  <span className="text-slate-500">-</span>
                                )}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    </div>
                  </div>
                )}
              </section>

              {confidence && playbookStage3 && (
                <section
                  className="rounded-xl border border-amber-500/45 bg-gradient-to-br from-amber-500/12 to-slate-900/40 p-4 space-y-2"
                  aria-label="Special playbook step active"
                >
                  <div className="flex items-start gap-2.5">
                    <div className="mt-0.5 rounded-lg bg-amber-500/20 p-1.5 border border-amber-500/35">
                      <Zap className="h-4 w-4 text-amber-300 shrink-0" />
                    </div>
                    <div className="min-w-0 space-y-1">
                      <p className="text-sm font-semibold text-amber-100">
                        Special playbook step is active
                      </p>
                      <p className="text-xs text-amber-200/90 leading-snug">
                        <span className="font-medium text-amber-100">{playbookStage3.name}</span>
                        {" — "}
                        {playbookStage3.action}
                      </p>
                      {regimeShift && (
                        <p className="text-[11px] text-slate-400 leading-snug pt-1 border-t border-amber-500/20">
                          Chance the market backdrop changes meaningfully in about {regimeShift.days_estimate}:{" "}
                          <span className="font-mono font-semibold text-amber-300/95">
                            {regimeShift.shift_probability.toFixed(0)}%
                          </span>
                          {regimeShift.label === "WATCH_CLOSELY" && (
                            <span className="text-amber-400/90"> — worth watching closely</span>
                          )}
                          . Use the confidence section below as supporting context, not the only thing you read.
                        </p>
                      )}
                      {!regimeShift && (
                        <p className="text-[11px] text-slate-500 pt-1">
                          Full scenario list is in the confidence card below under the playbook section.
                        </p>
                      )}
                    </div>
                  </div>
                </section>
              )}

              {/* ── 7-Layer Confidence Engine ──────────────────────────── */}
              {confidence ? (
                <section className="space-y-2">
                  <div className="rounded-lg border border-slate-700/70 bg-slate-900/40 px-3 py-2">
                    <p className="text-xs font-semibold text-slate-200 uppercase tracking-wide">7-Layer model signal</p>
                    <p className="text-[11px] text-slate-400">Regime + ML + options + fundamentals fused.</p>
                  </div>
                  <ConfidenceBreakdownSafe data={confidence} />
                </section>
              ) : (
                <div className="rounded-xl border border-slate-700/50 bg-slate-800/20 px-4 py-3 flex items-center gap-3 text-slate-500 text-xs animate-pulse">
                  <Activity className="h-4 w-4 shrink-0" />
                  <span>Loading full confidence model…</span>
                </div>
              )}

              {/* ── Unified Signal Engine (regime + pattern + momentum) ─ */}
              {unified ? (
                <section className="space-y-2">
                  <div className="rounded-lg border border-slate-700/70 bg-slate-900/20 px-3 py-2">
                    <p className="text-xs font-semibold text-slate-300 uppercase tracking-wide">Technical pattern only</p>
                    <p className="text-[11px] text-slate-500">Chart-pattern context only; not the full fused model verdict.</p>
                  </div>
                  {hasVerdictConflict && (
                    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2">
                      <p className="text-[11px] text-amber-200 leading-snug">
                        Overview says <span className="font-semibold">{overviewVerdict}</span> (fused multi-layer model),
                        while Technical Pattern says <span className="font-semibold">{patternVerdict}</span> (chart-only).
                        This is expected when structural thesis and tactical timing diverge.
                      </p>
                    </div>
                  )}
                  <PatternSignalCardSafe data={unified} />
                </section>
              ) : (
                <div className="rounded-xl border border-slate-700/50 bg-slate-800/20 px-4 py-3 flex items-center gap-3 text-slate-500 text-xs animate-pulse">
                  <Activity className="h-4 w-4 shrink-0" />
                  <span>Loading chart-pattern readout…</span>
                </div>
              )}

              {/* ── Price Targets & Scenario Analysis ──────────────────── */}
              {priceTargets ? (
                <div className="rounded-xl border border-slate-700/50 bg-slate-900/60 px-4 py-4">
                  <PriceTargetsPanel data={priceTargets} hideHorizonZones={!!detail.investor_summary} />
                </div>
              ) : (
                <div className="rounded-xl border border-slate-700/50 bg-slate-800/20 px-4 py-3 flex items-center gap-3 text-slate-500 text-xs animate-pulse">
                  <Activity className="h-4 w-4 shrink-0" />
                  <span>Computing price ranges &amp; scenarios…</span>
                </div>
              )}

              {/* Simple rule-based momentum (secondary to ML confidence above) */}
              {detail.score_breakdown && (detail.score_breakdown.trend != null || detail.score_breakdown.composite != null) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-1">
                    <BarChart3 className="h-4 w-4 text-emerald-500" />
                    Quick momentum check (rules, not odds)
                  </h3>
                  <p className="text-slate-500 text-xs mb-3">
                    These are 0–100 rule scores (not win probabilities). For odds and sizing, rely on the confidence block above.
                    The blended number is about 50% trend, 30% how &ldquo;stretched&rdquo; the move is, and 20% momentum shift.
                  </p>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
                    {detail.score_breakdown.trend != null && (
                      <div className="bg-slate-800 rounded-lg p-2 text-center">
                        <p className="text-slate-500 text-xs">Trend strength</p>
                        <p className={clsx("font-mono font-semibold", detail.score_breakdown.trend >= 80 ? "text-emerald-400" : detail.score_breakdown.trend <= 30 ? "text-red-400" : "text-slate-200")}>
                          {detail.score_breakdown.trend.toFixed(0)}<span className="text-slate-600 text-xs">/100</span>
                        </p>
                      </div>
                    )}
                    {detail.score_breakdown.rsi != null && (
                      <div className="bg-slate-800 rounded-lg p-2 text-center">
                        <p className="text-slate-500 text-xs">Stretched vs normal</p>
                        <p className={clsx("font-mono font-semibold", detail.score_breakdown.rsi >= 80 ? "text-emerald-400" : detail.score_breakdown.rsi <= 30 ? "text-red-400" : "text-slate-200")}>
                          {detail.score_breakdown.rsi.toFixed(0)}<span className="text-slate-600 text-xs">/100</span>
                        </p>
                      </div>
                    )}
                    {detail.score_breakdown.macd != null && (
                      <div className="bg-slate-800 rounded-lg p-2 text-center">
                        <p className="text-slate-500 text-xs">Momentum shift</p>
                        <p className={clsx("font-mono font-semibold", detail.score_breakdown.macd >= 80 ? "text-emerald-400" : detail.score_breakdown.macd <= 30 ? "text-red-400" : "text-slate-200")}>
                          {detail.score_breakdown.macd.toFixed(0)}<span className="text-slate-600 text-xs">/100</span>
                        </p>
                      </div>
                    )}
                    {detail.score_breakdown.composite != null && (
                      <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-2 text-center">
                        <p className="text-slate-500 text-xs">Blended</p>
                        <p className="font-mono font-semibold text-emerald-400">
                          {detail.score_breakdown.composite.toFixed(0)}<span className="text-slate-600 text-xs">/100</span>
                        </p>
                      </div>
                    )}
                  </div>
                </section>
              )}

              {/* Spot vs averages — skip when price-targets panel already shows MA lines */}
              {!priceTargets && (detail.current_price != null || detail.ma20 != null || detail.ma50 != null || detail.ma200 != null) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-2">
                    <BarChart3 className="h-4 w-4 text-emerald-500" />
                    Price vs key averages
                  </h3>
                  <p className="text-sm text-slate-200 font-mono flex flex-wrap gap-x-3 gap-y-1">
                    {detail.current_price != null && (
                      <span><span className="text-slate-500 font-sans text-xs mr-1">Last price</span>${detail.current_price.toFixed(2)}</span>
                    )}
                    {detail.ma20 != null && (
                      <span><span className="text-slate-500 font-sans text-xs mr-1">20-day avg</span>${detail.ma20.toFixed(2)}</span>
                    )}
                    {detail.ma50 != null && (
                      <span><span className="text-slate-500 font-sans text-xs mr-1">50-day avg</span>${detail.ma50.toFixed(2)}</span>
                    )}
                    {detail.ma200 != null && (
                      <span><span className="text-slate-500 font-sans text-xs mr-1">200-day avg</span>${detail.ma200.toFixed(2)}</span>
                    )}
                  </p>
                  <p className="text-xs text-slate-500 mt-2">
                    When price sits above the 50- and 200-day averages, the trend is usually stronger; below both often means a weaker setup. (Also covered in Overview when entry zones are shown.)
                  </p>
                </section>
              )}

              {/* Target bands — only when no investor summary (otherwise ST/MT/LT are in Overview + scenarios below) */}
              {!detail.investor_summary && (detail.st_band || detail.mt_band || detail.lt_band) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-3">
                    <TrendingUp className="h-4 w-4 text-emerald-500" />
                    Target price bands (context, not promises)
                  </h3>
                  <div className="space-y-4 text-sm">
                    {detail.st_band && (
                      <div>
                        <p className="font-medium text-slate-300 mb-1">Short-term (days–weeks)</p>
                        {detail.st_checkpoints && detail.st_checkpoints.length > 0 ? (
                          <p className="text-slate-400 flex flex-wrap gap-x-2 gap-y-0.5">
                            {detail.st_checkpoints.map((p, i) => (
                              <span key={i} className={i === 0 ? "text-amber-400" : i === detail.st_checkpoints!.length - 1 ? "text-emerald-400" : "text-slate-500"}>
                                ${p.toFixed(2)}{i < (detail.st_checkpoints!.length - 1) ? " ·" : ""}
                              </span>
                            ))}
                          </p>
                        ) : (
                          <p className="text-slate-400">
                            Stop: ${detail.st_band.low.toFixed(2)} – Target: ${detail.st_band.high.toFixed(2)}
                            {detail.st_target_confidence_pct != null && (
                              <span className="text-slate-500 text-sm ml-1">(roughly {detail.st_target_confidence_pct}% historical hit rate in similar ~20-day setups)</span>
                            )}
                          </p>
                        )}
                        <p className="text-sm text-slate-500 mt-0.5">Based on recent volatility and short-term averages—not a price promise. The hit-rate note is from similar past periods.</p>
                        {detail.st_level_hit === "target" && (
                          <p className="text-xs text-emerald-400 mt-0.5">Target hit — bands trailed up (stop locked at prior target)</p>
                        )}
                        {detail.st_level_hit === "stop" && (
                          <p className="text-sm text-amber-400 mt-0.5">Stop hit — bands recomputed from current price</p>
                        )}
                      </div>
                    )}
                    {detail.mt_band && (
                      <div>
                        <p className="font-medium text-slate-300 mb-1">Medium-term (months)</p>
                        {detail.mt_checkpoints && detail.mt_checkpoints.length > 0 ? (
                          <p className="text-slate-400 flex flex-wrap gap-x-2 gap-y-0.5">
                            {detail.mt_checkpoints.map((p, i) => (
                              <span key={i} className={i === 0 ? "text-amber-400" : i === detail.mt_checkpoints!.length - 1 ? "text-emerald-400" : "text-slate-500"}>
                                ${p.toFixed(2)}{i < (detail.mt_checkpoints!.length - 1) ? " ·" : ""}
                              </span>
                            ))}
                          </p>
                        ) : (
                          <p className="text-slate-400">
                            Low: ${detail.mt_band.low.toFixed(2)} – High: ${detail.mt_band.high.toFixed(2)}
                            {detail.mt_target_confidence_pct != null && (
                              <span className="text-slate-500 text-sm ml-1">(roughly {detail.mt_target_confidence_pct}% historical hit rate in similar ~6-month setups)</span>
                            )}
                          </p>
                        )}
                        <p className="text-sm text-slate-500 mt-0.5">Blends the market backdrop with a six-month volatility range.</p>
                      </div>
                    )}
                    {(detail.lt_band || detail.st_band || detail.mt_band) && (
                      <div>
                        <p className="font-medium text-slate-300 mb-1">Long-term (1–3+ yr)</p>
                        {detail.lt_band ? (
                          <>
                            {detail.lt_scenarios && (
                              <p className="text-slate-400 mb-1">
                                <span className="text-red-400">Bear</span> ${detail.lt_scenarios.bear.toFixed(2)}
                                {" · "}
                                <span className="text-slate-300">Base</span> ${detail.lt_scenarios.base.toFixed(2)}
                                {" · "}
                                <span className="text-emerald-400">Bull</span> ${detail.lt_scenarios.bull.toFixed(2)}
                              </p>
                            )}
                            {detail.lt_checkpoints && detail.lt_checkpoints.length > 0 ? (
                              <p className="text-slate-400 flex flex-wrap gap-x-2 gap-y-0.5">
                                {detail.lt_checkpoints.map((p, i) => (
                                  <span key={i} className={i === 0 ? "text-amber-400" : i === detail.lt_checkpoints!.length - 1 ? "text-emerald-400" : "text-slate-500"}>
                                    ${p.toFixed(2)}{i < (detail.lt_checkpoints!.length - 1) ? " ·" : ""}
                                  </span>
                                ))}
                              </p>
                            ) : (
                              <p className="text-slate-400">
                                Low: ${detail.lt_band.low.toFixed(2)} – High: ${detail.lt_band.high.toFixed(2)}
                              </p>
                            )}
                            {detail.lt_band_low_confidence && (
                              <span className="text-amber-400 text-sm">(low confidence – high analyst dispersion)</span>
                            )}
                            {detail.street_vs_model && (
                              <p className="text-sm text-slate-400 mt-2">
                                Analysts (sell-side range): ${detail.street_vs_model.street_low.toFixed(1)}–${detail.street_vs_model.street_high.toFixed(1)}
                                {" · "}
                                Our range vs theirs: low end {detail.street_vs_model.delta_low_pct >= 0 ? "+" : ""}{detail.street_vs_model.delta_low_pct}%, high end {detail.street_vs_model.delta_high_pct >= 0 ? "+" : ""}{detail.street_vs_model.delta_high_pct}%
                                {detail.street_vs_model.model_more_bullish && (
                                  <span className="text-emerald-400"> · our model is more optimistic</span>
                                )}
                              </p>
                            )}
                            <p className="text-sm text-slate-500 mt-0.5">
                              {["GLD", "SLV", "IAU", "USO", "GDX", "GDXJ"].includes(detail.ticker) || detail.sector === "Commodities"
                                ? "Price band from analyst consensus and volatility (no P/E — commodity ETF). Bear level uses 10+yr stress when available."
                                : "Fair value (EPS × P/E) blended with analyst consensus. Bear level uses 10+yr stress drawdown when available."}
                            </p>
                          </>
                        ) : (
                          <p className="text-slate-500 text-base">Not available — requires analyst consensus or forward EPS (FMP)</p>
                        )}
                      </div>
                    )}
                  </div>
                  <p className="text-sm text-slate-400 mt-3 border-t border-slate-700/50 pt-3">
                    Use the short band for trades up to about a month, the middle band for a few months, and the long band for multi-year planning—not for timing next week&apos;s move.
                  </p>
                </section>
              )}

              {/* Technical price levels + horizon signals (horizon signals hidden when investor_summary covers them) */}
              {(() => {
                const hasPriceReasoning = detail.price_reasoning && (detail.price_reasoning.buy || detail.price_reasoning.sell || detail.price_reasoning.support);
                const showHorizonSignals = !detail.investor_summary && (detail.short_suggestion || detail.medium_suggestion || detail.long_suggestion);
                if (!hasPriceReasoning && !showHorizonSignals) return null;
                return (
                  <section className="bg-slate-800/40 border border-slate-700/80 rounded-xl p-4">
                    <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-3">
                      <TrendingUp className="h-4 w-4 text-emerald-500" />
                      {hasPriceReasoning && !showHorizonSignals ? "Rule-based price zones" : "Simple actions by timeframe"}
                    </h3>
                    {hasPriceReasoning && (
                      <div className={clsx("space-y-2 text-sm", showHorizonSignals && "border-b border-slate-700/50 pb-3 mb-3")}>
                        <p className="text-xs text-slate-500">From chart rules (not the full confidence model)</p>
                        <p className="text-[11px] text-slate-500 leading-snug">
                          These add/trim zones follow momentum and average-price rules. Prefer the <span className="text-slate-400">confidence section</span> above for the main buy/sell read—they can disagree on purpose.
                        </p>
                        {detail.price_reasoning!.buy && (
                          <p className="text-slate-300">
                            <span className="text-emerald-400 font-medium">Where buys often make sense:</span> {detail.price_reasoning!.buy}
                          </p>
                        )}
                        {detail.price_reasoning!.sell && (
                          <p className="text-slate-300">
                            <span className="text-red-400 font-medium">Where taking profits often makes sense:</span> {detail.price_reasoning!.sell}
                          </p>
                        )}
                        {detail.price_reasoning!.support && (
                          <p className="text-slate-300">
                            <span className="text-amber-400 font-medium">Support to watch:</span> {detail.price_reasoning!.support}
                          </p>
                        )}
                      </div>
                    )}
                    {showHorizonSignals && (
                      <div className="space-y-3">
                        <p className="text-xs text-slate-500">By holding period</p>
                        {detail.short_suggestion && (
                          <div className="bg-slate-800/50 rounded-lg p-3">
                            <span className={clsx(
                              "font-medium",
                              detail.short_suggestion.includes("ADD") && "text-emerald-400",
                              detail.short_suggestion.includes("TRIM") && "text-red-400",
                              detail.short_suggestion === "HOLD" && "text-slate-300"
                            )}>
                              Short (~1 mo): {detail.short_suggestion}
                            </span>
                            {detail.short_reason && (
                              <p className="text-sm text-slate-400 mt-1">{detail.short_reason}</p>
                            )}
                          </div>
                        )}
                        {detail.medium_suggestion && (
                          <div className="bg-slate-800/50 rounded-lg p-3">
                            <span className={clsx(
                              "font-medium",
                              detail.medium_suggestion.includes("ADD") && "text-emerald-400",
                              detail.medium_suggestion.includes("TRIM") && "text-red-400",
                              detail.medium_suggestion === "HOLD" && "text-slate-300"
                            )}>
                              Medium (~3–6 mo): {detail.medium_suggestion}
                            </span>
                            {detail.medium_reason && (
                              <p className="text-sm text-slate-400 mt-1">{detail.medium_reason}</p>
                            )}
                          </div>
                        )}
                        {detail.long_suggestion && (
                          <div className="bg-slate-800/50 rounded-lg p-3">
                            <span className={clsx(
                              "font-medium",
                              detail.long_suggestion.includes("ADD") && "text-emerald-400",
                              detail.long_suggestion.includes("TRIM") && "text-red-400",
                              detail.long_suggestion === "HOLD" && "text-slate-300"
                            )}>
                              Long (~12–18 mo): {detail.long_suggestion}
                            </span>
                            {detail.long_reason && (
                              <p className="text-sm text-slate-400 mt-1">{detail.long_reason}</p>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </section>
                );
              })()}

              {/* Sector-specific (Fix 5): AUM, P/B, ROE for financials; P/S, margins for tech */}
              {detail.sector_specific && Object.keys(detail.sector_specific).length > 0 && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-2">Extra numbers for this sector</h3>
                  <div className="flex flex-wrap gap-3 text-sm">
                    {Object.entries(detail.sector_specific).map(([k, v]) => (
                      v != null && (
                        <span key={k} className="text-slate-300">
                          <span className="text-slate-500">{k.replace(/_/g, " ")}:</span>{" "}
                          <span className="text-slate-100">{typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(2)) : v}</span>
                        </span>
                      )
                    ))}
                  </div>
                </section>
              )}

              {/* Rate sensitivity (Fix 5): correlation with TLT */}
              {detail.rate_sensitivity && !("error" in detail.rate_sensitivity) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-2">Sensitivity to bond prices (long-term Treasuries)</h3>
                  <p className="text-slate-300 text-sm">
                    Tendency to move with the Treasury bond ETF (TLT): <span className="font-mono text-slate-100">{detail.rate_sensitivity.correlation_with_tlt}</span>
                    {" · "}{detail.rate_sensitivity.interpretation}
                  </p>
                  <p className="text-slate-500 text-xs mt-1">{detail.rate_sensitivity.note}</p>
                </section>
              )}

              {/* Sanity errors badge */}
              {detail.sanity_errors && detail.sanity_errors.length > 0 && (
                <section className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-base font-semibold text-amber-400 mb-2">Data quality</h3>
                  <p className="text-sm text-slate-300">Some numbers looked odd and were flagged: {detail.sanity_errors.join(", ")}</p>
                  <p className="text-xs text-slate-500 mt-1">Examples: dividend yield outside a normal band; price outside its 52-week range; an extreme drawdown; or bear/base/bull levels that don&apos;t line up.</p>
                </section>
              )}

              {/* Volume, drawdown, long-horizon risk — collapsed by default to reduce scroll */}
              {(detail.volume_ratio != null || detail.drawdown_52w != null || detail.long_horizon_risk) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setMetricsGuideOpen((o) => !o)}
                    className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-800/50 transition-colors"
                  >
                    <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                      <HelpCircle className="h-4 w-4 shrink-0" />
                      Volume, drawdown &amp; risk (explainers)
                    </h3>
                    {metricsGuideOpen ? (
                      <ChevronDown className="h-4 w-4 text-slate-400 shrink-0" aria-hidden />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-slate-400 shrink-0" aria-hidden />
                    )}
                  </button>
                  {metricsGuideOpen && (
                  <div className="px-4 pb-4 pt-0 border-t border-slate-700/80 space-y-4 text-sm">
                    {detail.volume_ratio != null && (
                      <div className={detail.volume_unusual ? "bg-amber-500/10 border border-amber-500/30 rounded-lg p-4" : ""}>
                        <p className="font-medium text-slate-200">
                          Vol vs 20d avg: <span className={detail.volume_unusual ? "text-amber-400 font-bold" : "text-slate-300"}>{detail.volume_ratio}x</span>
                          {detail.volume_unusual && " (unusual)"}
                        </p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">
                          Today&apos;s volume is {detail.volume_ratio}× the 20-day average. {detail.volume_unusual ? "Orange = unusual (≥2×). High volume often signals news, institutional activity, or a potential breakout—interpret with price direction (up = buying interest, down = selling pressure)." : "Normal range. Volume < 2× avg is typical."}
                        </p>
                        {detail.volume_unusual && (
                          <p className="text-amber-200 mt-2 text-sm font-medium leading-relaxed">
                            Recommended: Check if price moved up (buying interest) or down (selling pressure). If up on high volume, consider it confirmation; if down, watch for follow-through before adding. Look for news or catalysts before sizing in.
                          </p>
                        )}
                      </div>
                    )}
                    {detail.drawdown_52w != null && (
                      <div>
                        <p className="font-medium text-slate-200">
                          Drawdown (52w): <span className={detail.drawdown_52w < -10 ? "text-red-400" : "text-slate-300"}>{detail.drawdown_52w}%</span>
                        </p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">
                          Price is {detail.drawdown_52w >= 0 ? "at or above" : `${Math.abs(detail.drawdown_52w)}% below`} the 52-week high. Larger drawdowns = more distance from peak; can signal consolidation or weakness.
                        </p>
                      </div>
                    )}
                    {(detail.high_52w != null || detail.low_52w != null) && (
                      <div>
                        <p className="font-medium text-slate-200">
                          52w range: {detail.low_52w != null && `$${Number(detail.low_52w).toFixed(2)}`} – {detail.high_52w != null && `$${Number(detail.high_52w).toFixed(2)}`}
                        </p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">
                          Where price sits in the yearly range. Near high = extended; near low = potential value or weakness.
                        </p>
                      </div>
                    )}
                    {(detail.dividend_yield != null && detail.dividend_yield > 0 && !detail.sanity_errors?.includes("yield")) && (
                      <div>
                        <p className="font-medium text-slate-200">Dividend yield: {detail.dividend_yield}%</p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">{detail.dividend_yield_explanation ?? "Dividend yield = last 12-month dividends / current price."}</p>
                      </div>
                    )}
                    {detail.dividend_yield_explanation && detail.sanity_errors?.includes("yield") && (
                      <div>
                        <p className="font-medium text-amber-400">Dividend yield: N/A (out of range)</p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">{detail.dividend_yield_explanation}</p>
                      </div>
                    )}
                    {detail.dividend_yield_explanation && (detail.dividend_yield == null || detail.dividend_yield === 0) && !detail.sanity_errors?.includes("yield") && detail.dividend_yield_explanation.includes("Gold ETFs") && (
                      <div>
                        <p className="font-medium text-slate-200">Dividend yield: ~0%</p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">{detail.dividend_yield_explanation}</p>
                      </div>
                    )}
                    {detail.beta != null && (
                      <div>
                        <p className="font-medium text-slate-200">Moves vs the market (beta): {detail.beta}</p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">Above 1 usually means more jumpy than the S&amp;P 500; below 1 calmer. Gold funds often sit near zero or negative.</p>
                      </div>
                    )}
                    {detail.long_horizon_risk && (
                      <div>
                        <p className="font-medium text-slate-200">
                          Long-horizon risk ({detail.long_horizon_risk.period_years}y monthly)
                        </p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">
                          Max drawdown: {detail.long_horizon_risk.max_drawdown_pct}%. Worst 3y return: {detail.long_horizon_risk.worst_3y_return_pct != null ? `${detail.long_horizon_risk.worst_3y_return_pct}%` : "n/a"}. Stress bear: {detail.long_horizon_risk.stress_bear_pct}% (20th pct drawdown – stress tail). Used to ground bear/base/bull levels in tail events.
                        </p>
                      </div>
                    )}
                  </div>
                  )}
                </section>
              )}

                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
