"use client";

import { useState, useEffect } from "react";
import { AlertTriangle, BarChart3, Calendar, RefreshCw, TrendingUp, Wallet, Target, FileText, Sparkles, HelpCircle } from "lucide-react";
import type { DashboardData } from "@/app/page";
import { clsx } from "clsx";
import {
  AddTickerBar,
  Best2026Section,
  CryptoSection,
  CrossAssetSection,
  StoryAlerts,
  PortfolioSummary,
  SignalsTable,
  PortfolioHoldings,
  TrimCandidates,
  Opportunities,
  ThesisCheck,
  WhatChanged,
  RegimeChart,
  ScoreChart,
  TickerDetailModal,
  ToggleSection,
  BacktestStatus,
  EconomicCalendarSection,
  GuidelinesBanner,
  FMPPlanStatus,
  ChatCopilot,
  AccuracyPriceTargets,
} from "./dashboard/index";

const AUTO_REFRESH_MIN = 30;

function formatLastRefresh(date: Date | null): string {
  if (!date) return "—";
  return date.toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  }) + " ET";
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

interface Props {
  data: DashboardData;
  onRefresh: () => void;
  loading: boolean;
  lastRefreshedAt?: Date | null;
}

export function Dashboard({ data, onRefresh, loading, lastRefreshedAt }: Props) {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [refreshAgo, setRefreshAgo] = useState("");
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
      <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/90 backdrop-blur supports-[backdrop-filter]:bg-slate-950/70">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-8 w-8 text-emerald-500" />
            <h1 className="text-xl font-bold text-slate-100">Thrive Alpha</h1>
          </div>
          <div className="flex items-center gap-3">
            {lastRefreshedAt && (
              <span
                className="text-sm text-slate-500"
                title={`Last refresh: ${formatLastRefresh(lastRefreshedAt)}. Prices and signals update on each refresh (auto every ${AUTO_REFRESH_MIN} min).`}
              >
                Last refresh: {refreshAgo || formatLastRefresh(lastRefreshedAt)}
              </span>
            )}
            <button
              onClick={onRefresh}
              disabled={loading}
              className={clsx(
                "flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition",
                "bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              <RefreshCw className={clsx("h-4 w-4", loading && "animate-spin")} />
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-4">
        <AddTickerBar onAdded={onRefresh} />
      </div>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-4">
        {/* Story Alerts - always visible when present */}
        {data.story_changes.length > 0 && <StoryAlerts items={data.story_changes} onTickerClick={setSelectedTicker} />}

        {/* Event risk - always visible when present */}
        {(data.earnings_risk_count ?? 0) > 0 && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 flex items-center gap-2">
            <Calendar className="h-5 w-5 text-amber-400 shrink-0" />
            <p className="text-amber-200 font-medium">
              {data.earnings_risk_count} holding{data.earnings_risk_count === 1 ? "" : "s"} with earnings in next week – scores may be volatile
            </p>
          </div>
        )}

        {/* Cross-asset guidelines */}
        {data.guidelines && data.guidelines.length > 0 && (
          <GuidelinesBanner guidelines={data.guidelines} />
        )}

        {/* FMP plan status – upgrade path when features unavailable */}
        {data.fmp_plan_status && (
          <FMPPlanStatus status={data.fmp_plan_status} />
        )}

        {/* Backtesting status - lazy load when expanded */}
        <ToggleSection id="backtest" title="Backtesting status" icon={<BarChart3 className="h-5 w-5 text-emerald-500" />} defaultOpen={false}>
          <BacktestStatus />
        </ToggleSection>

        {/* Price target accuracy - model levels vs today close */}
        <ToggleSection id="accuracy" title="Price target accuracy" icon={<Target className="h-5 w-5 text-amber-500" />} defaultOpen={false}>
          <AccuracyPriceTargets />
        </ToggleSection>

        {/* Crypto + Cross-asset + Event calendar + 2026 best - toggle */}
        <ToggleSection id="markets" title="Crypto & Cross-asset" icon={<TrendingUp className="h-5 w-5 text-emerald-500" />} defaultOpen={true}>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6 min-w-0 items-start">
            {data.crypto?.length ? <div className="min-w-0"><CryptoSection items={data.crypto} /></div> : null}
            {data.cross_asset?.length ? <div className="min-w-0"><CrossAssetSection items={data.cross_asset} /></div> : null}
            <div className="min-w-0"><EconomicCalendarSection events={data.economic_calendar ?? []} /></div>
            {data.best_2026?.length ? (
              <div className="min-w-0 xl:col-span-2">
                <Best2026Section items={data.best_2026} onTickerClick={setSelectedTicker} />
              </div>
            ) : null}
          </div>
        </ToggleSection>

        {/* Summary Cards - toggle */}
        <ToggleSection id="summary" title="Portfolio Summary" icon={<Wallet className="h-5 w-5 text-emerald-500" />} defaultOpen={true}>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 min-w-0">
            <PortfolioSummary report={data.portfolio} />
          </div>
        </ToggleSection>

        {/* Charts - toggle */}
        <ToggleSection id="charts" title="Score & Regime Charts" icon={<Target className="h-5 w-5 text-emerald-500" />} defaultOpen={true}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ScoreChart signals={data.signals} onTickerClick={setSelectedTicker} />
            <RegimeChart report={data.portfolio} />
          </div>
        </ToggleSection>

        {/* Daily Signals - toggle */}
        <ToggleSection id="signals" title="Daily Signals" icon={<Target className="h-5 w-5 text-emerald-500" />} badge={data.signals?.length} defaultOpen={true}>
          {data.macro_regime && (
            <p
              className={clsx(
                "text-sm font-medium mb-2 px-3 py-2 rounded-lg border inline-flex items-center gap-2",
                data.macro_regime === "Risk-On" && "text-emerald-400 border-emerald-500/30 bg-emerald-500/5",
                data.macro_regime === "Risk-Off" && "text-red-400 border-red-500/30 bg-red-500/5",
                data.macro_regime === "Neutral" && "text-slate-400 border-slate-600 bg-slate-800/50"
              )}
              title="Risk-On: low VIX, low real yields. Risk-Off: high VIX or high real yields. Affects position sizing and caution."
            >
              <span className="inline-flex items-center gap-1.5">
                Macro regime: {data.macro_regime}
                <HelpCircle className="h-3.5 w-3.5 text-slate-500 cursor-help shrink-0" aria-label="Macro regime explanation" />
              </span>
            </p>
          )}
          {data.market_regime && (data.market_regime.market_breadth || data.market_regime.tech_leadership || data.market_regime.rotation_risk) && (
            <p
              className="text-sm text-slate-300 mb-3 px-3 py-2 rounded-lg border border-slate-600 bg-slate-800/50"
              title="Breadth: participation (e.g. RSP vs SPY). Tech leadership: XLK/QQQ vs SPY trend. Rotation risk High = tighten tech buy zones, favor holds."
            >
              <span className="inline-flex items-center gap-1">
                <span className="text-slate-400">Market breadth:</span> {data.market_regime.market_breadth ?? "—"}
                <HelpCircle className="h-3.5 w-3.5 text-slate-500 cursor-help shrink-0" aria-label="Market regime explanation" />
              </span>
              {" · "}
              <span className="text-slate-400">Tech leadership:</span> {data.market_regime.tech_leadership ?? "—"} &middot;{" "}
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
          {data.pre_market?.message && data.pre_market.rotation_risk_premarket && data.pre_market.rotation_risk_premarket !== "Low" && (
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
          {data.indicator_validation && data.indicator_validation.length > 0 && (
            <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-3 mb-4">
              <p className="text-sm font-medium text-slate-400 mb-0.5">Indicator validation (SPY, QQQ, GLD, SLV)</p>
              <p className="text-sm text-slate-500 mb-1" title="Compares our next-day outlook to Yahoo Finance analyst consensus.">
                Our model vs external consensus; aligned = same direction, divergent = different.
              </p>
              <p className="text-sm text-slate-500 mb-2" title="Yahoo does not provide analyst recommendations for ETFs.">
                ETFs: Yahoo does not provide analyst consensus for SPY/QQQ/GLD/SLV, so external shows &quot;No data&quot; by design.
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
          {data.indicator_comparisons && data.indicator_comparisons.length > 0 && (
            <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-3 mb-4">
              <p className="text-sm font-medium text-slate-400 mb-0.5">Indicator comparison vs Yahoo, Alpha Vantage, Polygon, Finnhub</p>
              <p className="text-sm text-slate-500 mb-1" title="Close, RSI, MA, MACD vs external APIs; margin % for price/MA, absolute for RSI/MACD.">
                All comparable indicators; margin of error per source. See INDICATOR_COMPARISON_MATRIX.md for full coverage.
              </p>
              <p className="text-sm text-slate-500 mb-2" title="Free tier and API coverage limits.">
                Alpha Vantage free tier = 5 req/min, so RSI/MA/MACD are only fetched for SPY. Yahoo close can be missing under load. Finnhub analyst bias is often unavailable for ETFs.
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-600">
                      <th className="py-1.5 pr-2">Ticker</th>
                      <th className="py-1.5 pr-2">Close (margin %)</th>
                      <th className="py-1.5 pr-2">RSI (margin)</th>
                      <th className="py-1.5 pr-2">MA20/MA50 (margin %)</th>
                      <th className="py-1.5 pr-2">MACD (margin)</th>
                      <th className="py-1.5 pr-2">Bias</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.indicator_comparisons.map((c) => (
                      <tr key={c.ticker} className="border-b border-slate-700/50">
                        <td className="py-2 pr-2 font-medium text-slate-300">{c.ticker}</td>
                        <td className="py-2 pr-2 text-slate-400">
                          {c.close.comparisons.length > 0 ? (
                            <>
                              {c.close.comparisons.map((x) => (
                                <span key={x.source} className="mr-1.5 text-sm">
                                  {x.source}: {x.margin_pct != null ? `${x.margin_pct.toFixed(2)}%` : "—"}
                                </span>
                              ))}
                              {c.close.max_margin_pct != null && (
                                <span className="text-amber-400 text-sm"> (max {c.close.max_margin_pct.toFixed(2)}%)</span>
                              )}
                            </>
                          ) : "—"}
                        </td>
                        <td className="py-2 pr-2 text-slate-400">
                          {c.rsi.comparisons.length > 0
                            ? c.rsi.comparisons.map((x) => (
                                <span key={x.source}>{x.source}: {x.margin_abs != null ? `±${x.margin_abs}` : "—"}</span>
                              ))
                            : "—"}
                        </td>
                        <td className="py-2 pr-2 text-slate-400">
                          {c.ma?.comparisons?.length > 0
                            ? c.ma.comparisons.map((m) => (
                                <span key={m.series} className="mr-1.5 text-sm">
                                  {m.series}: {m.margin_pct != null ? `${m.margin_pct.toFixed(2)}%` : "—"}
                                </span>
                              ))
                            : "—"}
                          {c.ma?.max_margin_pct != null && (
                            <span className="text-amber-400 text-sm"> (max {c.ma.max_margin_pct.toFixed(2)}%)</span>
                          )}
                        </td>
                        <td className="py-2 pr-2 text-slate-400">
                          {c.macd?.comparisons?.length > 0
                            ? c.macd.comparisons.map((x) => (
                                <span key={x.source}>{x.source}: {x.margin_abs != null ? `±${x.margin_abs}` : "—"}</span>
                              ))
                            : "—"}
                        </td>
                        <td className="py-2 pr-2">
                          {c.bias.comparisons.length > 0
                            ? c.bias.comparisons.map((b) => (
                                <span
                                  key={b.source}
                                  className={b.status === "aligned" ? "text-emerald-400" : b.status === "divergent" ? "text-amber-400" : "text-slate-500"}
                                >
                                  {b.source}: {b.rating ?? "—"} ({b.status})
                                </span>
                              ))
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {data.model_validation && (data.model_validation.records?.length > 0 || (data.model_validation.summary?.n_records ?? 0) > 0) && (
            <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-3 mb-4">
              <p className="text-sm font-medium text-slate-400 mb-0.5">Model validation: SPY/QQQ predicted vs actual</p>
              <p className="text-sm text-slate-500 mb-2" title="Compares our next-day bias and typical range to the next trading day close. Run run_daily.py daily to accumulate EOD snapshots.">
                Estimated direction and range vs actual close. Direction hit = Bullish and next day up, or Bearish and next day down. Range = actual return within our ±typical_move.
              </p>
              {data.model_validation.summary && (data.model_validation.summary.direction_n > 0 || data.model_validation.summary.range_n > 0) && (
                <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-300 mb-2">
                  {data.model_validation.summary.direction_accuracy_pct != null && (
                    <span>Direction accuracy: <strong className="text-emerald-400">{data.model_validation.summary.direction_accuracy_pct}%</strong> ({data.model_validation.summary.direction_n} days)</span>
                  )}
                  {data.model_validation.summary.range_hit_rate_pct != null && (
                    <span>Range hit rate: <strong className="text-emerald-400">{data.model_validation.summary.range_hit_rate_pct}%</strong> (actual within ±typical_move, n={data.model_validation.summary.range_n})</span>
                  )}
                </div>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-600">
                      <th className="py-1.5 pr-2">As of</th>
                      <th className="py-1.5 pr-2">Ticker</th>
                      <th className="py-1.5 pr-2">Our bias</th>
                      <th className="py-1.5 pr-2">Prior close</th>
                      <th className="py-1.5 pr-2">Actual close</th>
                      <th className="py-1.5 pr-2">Actual %</th>
                      <th className="py-1.5 pr-2">Dir hit</th>
                      <th className="py-1.5 pr-2">In range</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.model_validation.records ?? []).slice(0, 30).map((r) => (
                      <tr key={`${r.as_of_date}-${r.ticker}`} className="border-b border-slate-700/50">
                        <td className="py-2 pr-2 text-slate-400">{r.as_of_date}</td>
                        <td className="py-2 pr-2 font-medium text-slate-300">{r.ticker}</td>
                        <td className="py-2 pr-2 text-slate-400">{r.our_bias ?? "—"}</td>
                        <td className="py-2 pr-2 text-slate-400">${r.prior_close.toFixed(2)}</td>
                        <td className="py-2 pr-2 text-slate-400">${r.actual_close.toFixed(2)}</td>
                        <td className={r.actual_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}>{r.actual_return_pct >= 0 ? "+" : ""}{r.actual_return_pct.toFixed(2)}%</td>
                        <td className="py-2 pr-2">
                          {r.direction_hit === true && <span className="text-emerald-400">Yes</span>}
                          {r.direction_hit === false && <span className="text-red-400">No</span>}
                          {r.direction_hit == null && <span className="text-slate-500">—</span>}
                        </td>
                        <td className="py-2 pr-2">
                          {r.within_range === true && <span className="text-emerald-400">Yes</span>}
                          {r.within_range === false && <span className="text-amber-400">No</span>}
                          {r.within_range == null && <span className="text-slate-500">—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-sm text-slate-500 mt-2">Requires EOD snapshots from <code className="bg-slate-700 px-1 rounded">run_daily.py</code>. See MODEL_VALIDATION.md for metrics and fine-tuning.</p>
            </div>
          )}
          <p className="text-base text-slate-500 mb-4">
            <span className="text-slate-400">Buy:</span> add-on · <span className="text-slate-400">Sell:</span> trim when overbought/weak · <span className="text-slate-400">Support:</span> watch level ·
            <span className="text-slate-400"> Short:</span> ~1 mo · <span className="text-slate-400">Medium:</span> ~3–6 mo · <span className="text-slate-400">Long:</span> 1–2 yr
          </p>
          <SignalsTable signals={data.signals} horizons={data.config?.horizons} onTickerClick={setSelectedTicker} riskSizing={data.config?.risk_sizing} cotByTicker={data.cot_by_ticker} />
        </ToggleSection>

        {/* Portfolio Holdings - toggle */}
        <ToggleSection id="holdings" title="Portfolio Holdings" icon={<Wallet className="h-5 w-5 text-emerald-500" />} badge={data.portfolio?.per_holding?.length} defaultOpen={true}>
          <PortfolioHoldings holdings={data.portfolio.per_holding} onTickerClick={setSelectedTicker} />
        </ToggleSection>

        {/* Consider Trim - toggle */}
        {data.trim_candidates.length > 0 && (
          <ToggleSection id="trim" title="Consider Trim (protect gains)" icon={<AlertTriangle className="h-5 w-5 text-amber-400" />} badge={data.trim_candidates.length} defaultOpen={false}>
            <TrimCandidates items={data.trim_candidates} onTickerClick={setSelectedTicker} />
          </ToggleSection>
        )}

        {/* Opportunities - toggle */}
        <ToggleSection id="opps" title="Daily Opportunities" icon={<Sparkles className="h-5 w-5 text-emerald-500" />} badge={data.opportunities?.length} defaultOpen={false}>
          <Opportunities items={data.opportunities} onTickerClick={setSelectedTicker} />
        </ToggleSection>

        {/* Thesis Check - toggle */}
        {data.thesis_check.length > 0 && (
          <ToggleSection id="thesis" title="Thesis Check" icon={<FileText className="h-5 w-5 text-emerald-500" />} badge={data.thesis_check.length} defaultOpen={false}>
            <ThesisCheck items={data.thesis_check} onTickerClick={setSelectedTicker} />
          </ToggleSection>
        )}

        {/* What Changed - toggle */}
        {data.what_changed.length > 0 && (
          <ToggleSection id="changed" title="What Changed (vs last run)" icon={<RefreshCw className="h-5 w-5 text-emerald-500" />} badge={data.what_changed.length} defaultOpen={true}>
            <WhatChanged items={data.what_changed} onTickerClick={setSelectedTicker} />
          </ToggleSection>
        )}
      </main>

      {selectedTicker && (
        <TickerDetailModal ticker={selectedTicker} onClose={() => setSelectedTicker(null)} />
      )}

      <ChatCopilot data={data} />
    </div>
  );
}
