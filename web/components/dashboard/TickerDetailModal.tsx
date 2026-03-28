"use client";

import { useEffect, useState } from "react";
import { X, TrendingUp, FileText, Calendar, BarChart3, HelpCircle, ChevronDown, ChevronRight, Activity, LayoutGrid, Target, Layers } from "lucide-react";
import { clsx } from "clsx";
import { ConfidenceBreakdown, type ConfidenceData } from "./ConfidenceBreakdown";
import { PatternSignalCard, type UnifiedSignalData } from "./PatternSignalCard";
import { PriceTargetsPanel, type PriceTargetsData } from "./PriceTargetsPanel";
import { InvestorDecisionSummarySection, type InvestorDecisionSummary } from "./InvestorDecisionSummary";
import { TradeRoadmapCard } from "./TradeRoadmapCard";

// Lightweight try/catch wrappers so a bad API response never crashes the modal
function ConfidenceBreakdownSafe({ data }: { data: ConfidenceData }) {
  try { return <ConfidenceBreakdown data={data} />; }
  catch { return null; }
}
function PatternSignalCardSafe({ data }: { data: UnifiedSignalData }) {
  try { return <PatternSignalCard data={data} />; }
  catch { return null; }
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
  investor_summary?: InvestorDecisionSummary | null;
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

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  useEffect(() => {
    if (!ticker) return;
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        className="bg-slate-900 border border-slate-700 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-slate-900 border-b border-slate-700 px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2 flex-wrap">
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

        {/* Tab bar: Overview | Roadmaps | Details — keeps modal from feeling crowded */}
        {detail && !loading && (
          <div className="border-b border-slate-700 bg-slate-900/90 sticky top-0 z-10">
            <div className="flex">
            {(
              [
                { id: "overview" as const, label: "Overview", icon: Target },
                { id: "roadmaps" as const, label: "Roadmaps", icon: LayoutGrid },
                { id: "details" as const, label: "Details", icon: Layers },
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
              Overview = decision &amp; bands · Roadmaps = timeline · Details = ML, scenarios &amp; fundamentals
            </p>
          </div>
        )}

        <div className="p-6 space-y-6">
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
              {/* Quick reference – collapsible so modal has less vertical scroll */}
              <section className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl overflow-hidden mb-4">
                <button
                  type="button"
                  onClick={() => setQuickRefOpen((o) => !o)}
                  className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-emerald-500/10 transition-colors"
                >
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
                    <HelpCircle className="h-4 w-4 shrink-0" />
                    Quick reference – What each metric means
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
                      <li><span className="font-medium text-slate-200">Price vs MAs:</span> Price {'>'} MA50 {'>'} MA200 = uptrend; below = downtrend.</li>
                      <li><span className="font-medium text-slate-200">MA20/50/200:</span> Short/medium/long trend. Above = bullish.</li>
                      <li><span className="font-medium text-emerald-400">Buy:</span> Suggested add level (e.g. pullback to MA50).</li>
                      <li><span className="font-medium text-red-400">Sell:</span> Trim/exit when overbought or score weak.</li>
                      <li><span className="font-medium text-amber-400">Support:</span> MA20; break below = caution.</li>
                      <li><span className="font-medium text-slate-200">Position size:</span> Reduce when guidelines show elevated risk.</li>
                      <li><span className="font-medium text-amber-400">Crowded Long/Short:</span> CFTC specs extreme; reversal risk.</li>
                      <li><span className="font-medium text-slate-200">Macro regime:</span> Risk-On vs Risk-Off; affects sizing.</li>
                      <li><span className="font-medium text-slate-200">Rotation risk:</span> High = tech stepped down (ADD→HOLD).</li>
                      <li><span className="font-medium text-slate-200">Short/Med/Long:</span> ~1 mo / ~3–6 mo / 1–2 yr view.</li>
                      <li><span className="font-medium text-slate-200">Vol, Drawdown 52w, 52w range:</span> Volume vs avg; % off high; low–high.</li>
                      <li><span className="font-medium text-slate-200">Dividend, Beta, vs Market:</span> Yield; volatility vs SPY; outperformance.</li>
                    </ul>
                  </div>
                )}
              </section>

              {/* ── Investor Decision Summary (horizon entry + tiers) ───── */}
              {detail.investor_summary && (
                <InvestorDecisionSummarySection
                  summary={detail.investor_summary}
                  currentPrice={detail.current_price ?? 0}
                  ma200={detail.ma200}
                  sector={detail.sector}
                  companyName={detail.company_name}
                  ltEntryTiersOpen={ltEntryTiersOpen}
                  onToggleLtTiers={() => setLtEntryTiersOpen((o) => !o)}
                />
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
              {/* Rule-based technical scores (Details only — Overview focuses on investor summary) */}
              {detail.score_breakdown && (detail.score_breakdown.trend != null || detail.score_breakdown.composite != null) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-1">
                    <BarChart3 className="h-4 w-4 text-emerald-500" />
                    Technical signal strength
                  </h3>
                  <p className="text-slate-500 text-xs mb-3">
                    Rule-based (0–100 strength, not probability). Composite = 50% trend + 30% RSI + 20% MACD.
                    For calibrated probability use 7-layer confidence below.
                  </p>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
                    {detail.score_breakdown.trend != null && (
                      <div className="bg-slate-800 rounded-lg p-2 text-center">
                        <p className="text-slate-500 text-xs">Trend</p>
                        <p className={clsx("font-mono font-semibold", detail.score_breakdown.trend >= 80 ? "text-emerald-400" : detail.score_breakdown.trend <= 30 ? "text-red-400" : "text-slate-200")}>
                          {detail.score_breakdown.trend.toFixed(0)}<span className="text-slate-600 text-xs">/100</span>
                        </p>
                      </div>
                    )}
                    {detail.score_breakdown.rsi != null && (
                      <div className="bg-slate-800 rounded-lg p-2 text-center">
                        <p className="text-slate-500 text-xs">RSI</p>
                        <p className={clsx("font-mono font-semibold", detail.score_breakdown.rsi >= 80 ? "text-emerald-400" : detail.score_breakdown.rsi <= 30 ? "text-red-400" : "text-slate-200")}>
                          {detail.score_breakdown.rsi.toFixed(0)}<span className="text-slate-600 text-xs">/100</span>
                        </p>
                      </div>
                    )}
                    {detail.score_breakdown.macd != null && (
                      <div className="bg-slate-800 rounded-lg p-2 text-center">
                        <p className="text-slate-500 text-xs">MACD</p>
                        <p className={clsx("font-mono font-semibold", detail.score_breakdown.macd >= 80 ? "text-emerald-400" : detail.score_breakdown.macd <= 30 ? "text-red-400" : "text-slate-200")}>
                          {detail.score_breakdown.macd.toFixed(0)}<span className="text-slate-600 text-xs">/100</span>
                        </p>
                      </div>
                    )}
                    {detail.score_breakdown.composite != null && (
                      <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-2 text-center">
                        <p className="text-slate-500 text-xs">Composite</p>
                        <p className="font-mono font-semibold text-emerald-400">
                          {detail.score_breakdown.composite.toFixed(0)}<span className="text-slate-600 text-xs">/100</span>
                        </p>
                      </div>
                    )}
                  </div>
                </section>
              )}

              {/* ── 7-Layer Confidence Engine ──────────────────────────── */}
              {confidence ? (
                <ConfidenceBreakdownSafe data={confidence} />
              ) : (
                <div className="rounded-xl border border-slate-700/50 bg-slate-800/20 px-4 py-3 flex items-center gap-3 text-slate-500 text-xs animate-pulse">
                  <Activity className="h-4 w-4 shrink-0" />
                  <span>Loading ML confidence breakdown…</span>
                </div>
              )}

              {/* ── Unified Signal Engine (regime + pattern + momentum) ─ */}
              {unified ? (
                <PatternSignalCardSafe data={unified} />
              ) : (
                <div className="rounded-xl border border-slate-700/50 bg-slate-800/20 px-4 py-3 flex items-center gap-3 text-slate-500 text-xs animate-pulse">
                  <Activity className="h-4 w-4 shrink-0" />
                  <span>Loading pattern signal engine…</span>
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
                  <span>Computing price targets &amp; scenarios…</span>
                </div>
              )}

              {/* Price vs MAs — one line (grid was redundant with Overview bands) */}
              {(detail.current_price != null || detail.ma20 != null || detail.ma50 != null || detail.ma200 != null) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-2">
                    <BarChart3 className="h-4 w-4 text-emerald-500" />
                    Price vs moving averages
                  </h3>
                  <p className="text-sm text-slate-200 font-mono flex flex-wrap gap-x-3 gap-y-1">
                    {detail.current_price != null && (
                      <span><span className="text-slate-500 font-sans text-xs mr-1">Spot</span>${detail.current_price.toFixed(2)}</span>
                    )}
                    {detail.ma20 != null && (
                      <span><span className="text-slate-500 font-sans text-xs mr-1">MA20</span>${detail.ma20.toFixed(2)}</span>
                    )}
                    {detail.ma50 != null && (
                      <span><span className="text-slate-500 font-sans text-xs mr-1">MA50</span>${detail.ma50.toFixed(2)}</span>
                    )}
                    {detail.ma200 != null && (
                      <span><span className="text-slate-500 font-sans text-xs mr-1">MA200</span>${detail.ma200.toFixed(2)}</span>
                    )}
                  </p>
                  <p className="text-xs text-slate-500 mt-2">
                    Price above MA50 &amp; MA200 → stronger uptrend; below → weaker. Same context as Overview entry zones.
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
                              <span className="text-slate-500 text-sm ml-1">(conf: {detail.st_target_confidence_pct}% over 20d)</span>
                            )}
                          </p>
                        )}
                        <p className="text-sm text-slate-500 mt-0.5">ATR-based; MA20/swing context. Confidence from historical hit rates under similar conditions; not a guarantee.</p>
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
                              <span className="text-slate-500 text-sm ml-1">(conf: {detail.mt_target_confidence_pct}% over 6mo)</span>
                            )}
                          </p>
                        )}
                        <p className="text-sm text-slate-500 mt-0.5">Regime + 6m volatility band</p>
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
                                Street: ${detail.street_vs_model.street_low.toFixed(1)}–${detail.street_vs_model.street_high.toFixed(1)}
                                {" · "}
                                Model vs Street: low {detail.street_vs_model.delta_low_pct >= 0 ? "+" : ""}{detail.street_vs_model.delta_low_pct}%, high {detail.street_vs_model.delta_high_pct >= 0 ? "+" : ""}{detail.street_vs_model.delta_high_pct}%
                                {detail.street_vs_model.model_more_bullish && (
                                  <span className="text-emerald-400"> · model more bullish</span>
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
                    Use ST band for trades up to ~1 month, MT band for 3–6 months; LT is 1–3+ years.
                  </p>
                </section>
              )}

              {/* Price-level hints + horizon suggestions (single section — was two) */}
              {((detail.price_reasoning && (detail.price_reasoning.buy || detail.price_reasoning.sell || detail.price_reasoning.support)) ||
                detail.short_suggestion || detail.medium_suggestion || detail.long_suggestion) && (
                <section className="bg-slate-800/40 border border-slate-700/80 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-3">
                    <TrendingUp className="h-4 w-4 text-emerald-500" />
                    Actions &amp; reasoning
                  </h3>
                  {detail.price_reasoning && (detail.price_reasoning.buy || detail.price_reasoning.sell || detail.price_reasoning.support) && (
                    <div className="space-y-2 text-sm border-b border-slate-700/50 pb-3 mb-3">
                      <p className="text-xs text-slate-500 uppercase tracking-wide">Buy / sell / support labels</p>
                      {detail.price_reasoning.buy && (
                        <p className="text-slate-300">
                          <span className="text-emerald-400 font-medium">Buy:</span> {detail.price_reasoning.buy}
                        </p>
                      )}
                      {detail.price_reasoning.sell && (
                        <p className="text-slate-300">
                          <span className="text-red-400 font-medium">Sell:</span> {detail.price_reasoning.sell}
                        </p>
                      )}
                      {detail.price_reasoning.support && (
                        <p className="text-slate-300">
                          <span className="text-amber-400 font-medium">Support:</span> {detail.price_reasoning.support}
                        </p>
                      )}
                    </div>
                  )}
                  {(detail.short_suggestion || detail.medium_suggestion || detail.long_suggestion) && (
                    <div className="space-y-3">
                      <p className="text-xs text-slate-500 uppercase tracking-wide">Horizon signals</p>
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
                          Long (1–2 yr): {detail.long_suggestion}
                        </span>
                        {detail.long_reason && (
                          <p className="text-sm text-slate-400 mt-1">{detail.long_reason}</p>
                        )}
                      </div>
                    )}
                    </div>
                  )}
                </section>
              )}

              {/* Thesis */}
              {(detail.thesis || detail.exit_condition) && (
                <section>
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-2">
                    <FileText className="h-4 w-4" />
                    Thesis
                  </h3>
                  <div className="bg-slate-800/50 rounded-lg p-4 text-base text-slate-300 space-y-2">
                    {detail.thesis && <p>{detail.thesis}</p>}
                    {detail.exit_condition && (
                      <p className="text-amber-400/90">
                        <span className="text-slate-400">Exit when:</span> {detail.exit_condition}
                      </p>
                    )}
                    {!detail.thesis && !detail.exit_condition && (
                      <p className="text-slate-500 italic">No thesis. Add in data/theses.yaml or via add_thesis.py</p>
                    )}
                  </div>
                </section>
              )}

              {/* Earnings: next report + history in one place */}
              {(detail.earnings || (detail.earnings_history?.history?.length ?? 0) > 0) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-3">
                    <Calendar className="h-4 w-4 text-emerald-500" />
                    Earnings
                  </h3>
                  {detail.earnings && (
                    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-2 text-sm text-amber-200 mb-3">
                      <span className="text-slate-400 text-xs uppercase tracking-wide mr-2">Next</span>
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
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Recent quarters</p>
                  <p className="text-slate-400 text-xs mb-2">{detail.earnings_history.summary}</p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-slate-500">
                          <th className="pr-3 py-1">Quarter</th>
                          <th className="pr-3 py-1">Actual</th>
                          <th className="pr-3 py-1">Estimate</th>
                          <th className="py-1">Beat/Miss</th>
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

              {/* Benchmark comparison */}
              <section>
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-1">
                  <BarChart3 className="h-4 w-4" />
                  Performance vs Benchmarks
                </h3>
                <p className="text-xs text-slate-500 mb-3">SPY = market; sector column = {detail.sector_etf}. Peers table follows.</p>
                <div className="rounded-lg border border-slate-700 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-800/80 text-left text-slate-400">
                        <th className="px-4 py-2 font-medium">Period</th>
                        <th className="px-4 py-2 font-medium text-emerald-400">{detail.ticker}</th>
                        <th className="px-4 py-2 font-medium">SPY (Market)</th>
                        <th className="px-4 py-2 font-medium">{detail.sector_etf_name}</th>
                        <th className="px-4 py-2 font-medium text-slate-500">vs Market</th>
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
              </section>

              {/* Peer comparison */}
              {(detail.peer_returns?.length ?? 0) > 0 && (
                <section>
                  <h3 className="text-sm font-semibold text-slate-300 mb-2">Top Peers ({detail.industry || detail.sector || "same sector"})</h3>
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
                        <tr className="border-t border-slate-700/50 bg-emerald-500/5">
                          <td className="px-4 py-2 font-mono font-medium text-emerald-400">{detail.ticker}</td>
                          {periods.map((p) => (
                            <td key={p} className="px-4 py-2">
                              <span className={detail.returns[p] != null ? (detail.returns[p]! >= 0 ? "text-emerald-400" : "text-red-400") : "text-slate-500"}>
                                {detail.returns[p] != null ? `${detail.returns[p]! >= 0 ? "+" : ""}${detail.returns[p]}%` : "-"}
                              </span>
                            </td>
                          ))}
                        </tr>
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
                  <p className="text-sm text-slate-500 mt-2">
                    Compare vs industry ETF ({detail.sector_etf}) and peers to gauge relative strength.
                  </p>
                </section>
              )}

              {/* Sector-specific (Fix 5): AUM, P/B, ROE for financials; P/S, margins for tech */}
              {detail.sector_specific && Object.keys(detail.sector_specific).length > 0 && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-2">Sector metrics</h3>
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
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-2">Rate sensitivity</h3>
                  <p className="text-slate-300 text-sm">
                    Corr with TLT: <span className="font-mono text-slate-100">{detail.rate_sensitivity.correlation_with_tlt}</span>
                    {" · "}{detail.rate_sensitivity.interpretation}
                  </p>
                  <p className="text-slate-500 text-xs mt-1">{detail.rate_sensitivity.note}</p>
                </section>
              )}

              {/* Sanity errors badge */}
              {detail.sanity_errors && detail.sanity_errors.length > 0 && (
                <section className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-base font-semibold text-amber-400 mb-2">Data quality</h3>
                  <p className="text-sm text-slate-300">Some metrics flagged: {detail.sanity_errors.join(", ")}</p>
                  <p className="text-xs text-slate-500 mt-1">yield = dividend out of 0–15% range; range_drawdown = price outside 52w; drawdown_extreme = |drawdown| {'>'} 80%; bb_band_order = bear/base/bull inconsistent.</p>
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
                        <p className="font-medium text-slate-200">Beta vs SPY: {detail.beta}</p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">β {'>'} 1 = more volatile than market; β {'<'} 1 = less. Gold (GLD) often has low/negative beta.</p>
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
    </div>
  );
}
