"use client";

/**
 * Context tab body — extracted from TickerDetailModal (P4 tab-file split).
 * News rail → options/fin shorts → institutions → thesis → earnings →
 * analyst activity → [collapsible: returns vs peers, bands, zones, data notes].
 */
import React from "react";
import { clsx } from "clsx";
import { Activity, BarChart3, Calendar, ChevronDown, ChevronRight, FileText, HelpCircle, TrendingUp } from "lucide-react";
import { NewsSentimentRail } from "../../tradingPlatformUX";
import { InstitutionalInsightsPanel } from "../../InstitutionalInsightsPanel";
import { ReferenceDetailGrid } from "../ReferenceDetailGrid";
import type { TabCtx } from "./tabCtx";

function fmtUsdCompact(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "–";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toFixed(0)}`;
}

export function ContextTab({ ctx }: { ctx: TabCtx }) {
  const {
    detail,
    decisionMode,
    effectivePrice,
    priceTargets,
    confidence,
    executionVm,
    ltEntryTiersOpen,
    setLtEntryTiersOpen,
    moreContextOpen,
    setMoreContextOpen,
    metricsGuideOpen,
    setMetricsGuideOpen,
    portfolioImpactContext,
    modalNewsRail,
    periods,
    openWhyValuation,
    setModalTab,
    setWhySubTab,
  } = ctx;

  return (
    <div className="space-y-6">
  <NewsSentimentRail
    ticker={detail.ticker}
    mode={decisionMode}
    label={modalNewsRail.label}
    score={modalNewsRail.score}
    headlineCount={modalNewsRail.headlineCount}
    headlines={modalNewsRail.headlines}
    catalystNote={modalNewsRail.catalystNote}
    sentimentCaveat={modalNewsRail.sentimentCaveat}
    catalystCards={modalNewsRail.catalystCards}
  />
  <ReferenceDetailGrid
    only={["options", "shortInterest", "fundamentals"]}
    suppressOpenContext
    detail={detail}
    priceTargets={priceTargets}
    confidence={confidence}
    decisionMode={decisionMode}
    currentPrice={effectivePrice}
    executionVm={executionVm}
    ltEntryTiersOpen={ltEntryTiersOpen}
    onToggleLtTiers={() => setLtEntryTiersOpen((o) => !o)}
    onOpenLevels={() => setModalTab("levels")}
    onOpenValuation={openWhyValuation}
    onOpenProof={() => { setModalTab("why"); setWhySubTab("proof"); }}
    onOpenContext={() => {}}
    portfolioImpactContext={portfolioImpactContext}
  />
  <InstitutionalInsightsPanel
    ticker={detail.ticker}
    enabled
    silentOnError={false}
  />
  {/* ── Story & catalysts ─────── */}
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
          <p className="text-slate-500 italic">No written thesis for this ticker yet.</p>
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
          {detail.earnings_history?.next_consensus && (
            <span className="text-amber-300/70 ml-2 text-xs">
              — Street expects EPS {detail.earnings_history.next_consensus.eps_estimated != null ? `$${detail.earnings_history.next_consensus.eps_estimated.toFixed(2)}` : "–"}
              {detail.earnings_history.next_consensus.revenue_estimated != null && (
                <>, revenue {fmtUsdCompact(detail.earnings_history.next_consensus.revenue_estimated)}</>
              )}
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
              <th className="pr-3 py-1">EPS surprise</th>
              <th className="py-1">Revenue surprise</th>
            </tr>
          </thead>
          <tbody>
            {(detail.earnings_history.history ?? []).map((q, i) => (
              <tr key={i} className="border-t border-slate-700/50 text-slate-300">
                <td className="pr-3 py-1">{q.quarter}</td>
                <td className="pr-3 py-1">{q.actual != null ? q.actual : "–"}</td>
                <td className="pr-3 py-1">{q.estimate != null ? q.estimate : "–"}</td>
                <td className="pr-3 py-1">
                  {q.beat_pct != null ? (
                    <span className={q.status === "Beat" ? "text-emerald-400" : "text-red-400"}>
                      {q.beat_pct > 0 ? "+" : ""}{q.beat_pct}% {q.status}
                    </span>
                  ) : "N/A"}
                </td>
                <td className="py-1">
                  {q.revenue_beat_pct != null ? (
                    <span className={q.revenue_beat_pct > 0 ? "text-emerald-400" : "text-red-400"}>
                      {q.revenue_beat_pct > 0 ? "+" : ""}{q.revenue_beat_pct}%
                    </span>
                  ) : "–"}
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

  {detail.liquidity?.flag === "THIN_FLOAT" && (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-2 text-sm text-amber-200 flex items-center gap-2">
      <Activity className="h-4 w-4 text-amber-400 shrink-0" />
      <span>{detail.liquidity.label || "Thin float — wider spreads, price moves more per dollar traded. Size positions accordingly."}</span>
    </div>
  )}

  {(detail.analyst_actions?.length ?? 0) > 0 && (
    <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-3">
        <Activity className="h-4 w-4 text-emerald-500" />
        Recent analyst activity
      </h3>
      <div className="space-y-2">
        {(detail.analyst_actions ?? []).slice(0, 5).map((a, i) => (
          <div key={i} className="flex items-start justify-between gap-3 text-sm border-t border-slate-700/50 pt-2 first:border-t-0 first:pt-0">
            <div className="text-slate-300">
              <span className="text-slate-200 font-medium">{a.firm || "Analyst"}</span>{" "}
              {a.kind === "price_target" ? (
                <>set a <span className="text-emerald-400">${a.new_target?.toFixed(0)}</span> price target</>
              ) : (
                <>
                  {a.new_grade === a.previous_grade ? "maintained" : "moved to"}{" "}
                  <span className="text-emerald-400">{a.new_grade}</span>
                  {a.new_grade !== a.previous_grade && a.previous_grade && (
                    <span className="text-slate-500"> (from {a.previous_grade})</span>
                  )}
                </>
              )}
            </div>
            <span className="text-slate-500 text-xs whitespace-nowrap">
              {a.published_at ? new Date(a.published_at).toLocaleDateString() : ""}
            </span>
          </div>
        ))}
      </div>
    </section>
  )}

  {/* Denser fundamentals behind one toggle — decision-relevant facts (news, analyst,
      positioning, earnings) stay above it. */}
  <section className="rounded-xl border border-td-line overflow-hidden">
    <button
      type="button"
      onClick={() => setMoreContextOpen((o) => !o)}
      className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-td-surface2/60 transition-colors"
      aria-expanded={moreContextOpen}
    >
      <span className="text-sm font-semibold text-td-text">More fundamentals &amp; data notes</span>
      <span className="flex items-center gap-1 text-[11px] text-td-muted">
        Returns vs peers · price zones · sector &amp; macro · data quality
        {moreContextOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </span>
    </button>
    {moreContextOpen && (
      <div className="border-t border-td-line p-4 space-y-6">
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
            ? " — regime signal confirmed by price action."
            : (diff > 0 && (actionStatus === "BUY" || actionStatus === "STRONG BUY"))
              ? " — price action supports the bullish signal."
              : ".";
        return (
          <p className={`text-sm mt-2 px-3 py-1.5 rounded border leading-snug ${diff < 0 ? "text-red-300/90 border-red-500/25 bg-red-950/30" : "text-emerald-300/90 border-emerald-500/25 bg-emerald-950/30"}`}>
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
            <p className="text-sm text-slate-500 leading-snug">
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
  {(detail.listing_profile?.warnings?.length || (detail.sanity_errors && detail.sanity_errors.length > 0)) && (
    <section className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
      <h3 className="flex items-center gap-2 text-base font-semibold text-amber-400 mb-2">Data quality</h3>
      {detail.listing_profile?.warnings?.length ? (
        <ul className="text-sm text-slate-300 space-y-1 list-disc list-inside">
          {detail.listing_profile.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      ) : null}
      {detail.sanity_errors && detail.sanity_errors.length > 0 && (
        <p className="text-sm text-slate-300 mt-2">
          Additional flags: {detail.sanity_errors.filter((e) => !detail.listing_profile?.warnings?.includes(e)).join(", ") || detail.sanity_errors.join(", ")}
        </p>
      )}
      <p className="text-xs text-slate-500 mt-2">
        Spin-offs and recent listings can distort MA200 and 52-week lows — tiers and structural stops use adjusted levels when flagged.
      </p>
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

      </div>
    )}
  </section>
    </div>
  );
}
