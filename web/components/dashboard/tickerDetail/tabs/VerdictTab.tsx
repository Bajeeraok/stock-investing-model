"use client";

/**
 * Verdict tab body — extracted from TickerDetailModal (P4 tab-file split).
 * Plain sentence → unlocks → R:R / catalyst → hit rate → actions.
 */
import React from "react";
import { clsx } from "clsx";
import { AlertCircle, ChevronDown, ChevronRight, HelpCircle, Zap } from "lucide-react";
import { VerdictPanel } from "../VerdictPanel";
import { TickerDecisionHero } from "../TickerDecisionHero";
import { NarrativeWaterfallCard } from "../NarrativeWaterfallCard";
import { HorizonProjectionChart } from "../../HorizonProjectionChart";
import { ReferenceDetailGrid } from "../ReferenceDetailGrid";
import { CopyTradePlanButton } from "../../CopyTradePlanButton";
import { WatchZoneCallout } from "../../zoneContextUX";
import { ProtectModeCard } from "../../ProtectModeCard";
import type { TabCtx } from "./tabCtx";

export function VerdictTab({ ctx }: { ctx: TabCtx }) {
  const {
    ticker,
    detail,
    wide,
    decisionMode,
    effectivePrice,
    quoteDailyMovePct,
    headerActionStatus,
    tradingGates,
    gatesPassedCount,
    gatesTotal,
    confidence,
    priceTargets,
    executionVm,
    ltEntryTiersOpen,
    setLtEntryTiersOpen,
    quickRefOpen,
    setQuickRefOpen,
    portfolioImpactContext,
    playbookStage3,
    openWhyValuation,
    setModalTab,
    setWhySubTab,
  } = ctx;

  return (
    <div className={clsx("space-y-4", wide && "xl:grid xl:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)] xl:gap-5 xl:items-start xl:space-y-0")}>
    <div className="min-w-0 space-y-4">
  {detail.investor_summary ? (
    <VerdictPanel
      ticker={detail.ticker}
      summary={detail.investor_summary}
      mode={decisionMode}
      actionStatus={headerActionStatus}
      gates={tradingGates}
      gatesPassed={gatesPassedCount}
      gatesTotal={gatesTotal}
      currentPrice={effectivePrice}
      earnings={detail.earnings}
      catalystLabel={detail.catalyst?.active ? detail.catalyst.top_event_type?.replace(/_/g, " ") : null}
      held={!!(portfolioImpactContext as any)?.heldTickers?.has(detail.ticker.toUpperCase())}
      onOpenWhy={() => setModalTab("why")}
      onOpenTrack={() => setModalTab("track")}
      actionExtra={
        <CopyTradePlanButton
          ticker={detail.ticker}
          summary={detail.investor_summary}
          currentPrice={effectivePrice ?? 0}
          mode={decisionMode}
        />
      }
    />
  ) : (
    <section className="rounded-xl border border-slate-700 bg-slate-800/50 p-6 text-center">
      <AlertCircle className="h-8 w-8 text-slate-500 mx-auto mb-2" />
      <p className="text-sm text-slate-400">Signal summary is still loading or unavailable for this ticker.</p>
      <p className="text-xs text-slate-500 mt-1">Try refreshing the dashboard or check if the ticker is in your watchlist.</p>
    </section>
  )}
  <ProtectModeCard data={detail.investor_summary?.protect_mode} />

  {confidence && playbookStage3 && (
    <button
      type="button"
      onClick={() => setModalTab("levels")}
      className="w-full text-left rounded-xl border border-td-warn/40 bg-td-warn-weak/60 px-4 py-3 flex items-center gap-3 hover:bg-td-warn-weak transition-colors"
    >
      <Zap className="h-5 w-5 text-td-warn shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-td-text">Possible change in market mood</p>
        <p className="text-[12.5px] text-td-muted mt-0.5">
          {playbookStage3.name} — {playbookStage3.action}
        </p>
      </div>
      <ChevronRight className="h-5 w-5 text-td-warn/80 shrink-0" aria-hidden />
    </button>
  )}

  {detail.investor_summary?.retail_action?.zone_context?.in_watch_zone && (
    <WatchZoneCallout
      zone={detail.investor_summary.retail_action.zone_context}
      currentPrice={effectivePrice}
      regimeBullPct={detail.investor_summary.regime_bull_pct}
    />
  )}

  {detail.investor_summary && (
    <TickerDecisionHero
      ticker={detail.ticker}
      companyName={detail.company_name}
      sector={detail.sector}
      currentPrice={effectivePrice}
      dailyMovePct={quoteDailyMovePct}
      summary={detail.investor_summary}
      mode={decisionMode}
      actionStatus={headerActionStatus}
      gates={tradingGates}
      gatesPassed={gatesPassedCount}
      gatesTotal={gatesTotal}
      onOpenWhy={() => setModalTab("why")}
      compact
    />
  )}

  {detail.investor_summary && detail.price_history && detail.price_history.length >= 3 && (
    <HorizonProjectionChart
      ticker={detail.ticker}
      currentPrice={effectivePrice ?? 0}
      priceHistory={detail.price_history}
      short={detail.investor_summary.horizons.short}
      medium={detail.investor_summary.horizons.medium}
      long={detail.investor_summary.horizons.long}
      fairValue={detail.investor_summary.fair_value}
      ma20={detail.ma20}
      ma50={detail.ma50}
      variant="sparkline"
      planMode={detail.investor_summary.plan_mode}
      chaseBanner={detail.investor_summary.chase_banner}
      chaseDetail={detail.investor_summary.chase_detail}
    />
  )}

  {detail.cross_asset && (detail.cross_asset.badges?.length ?? 0) > 0 && (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-td-muted">Tends to move with:</span>
      {detail.cross_asset.badges.map((b) => (
        <span
          key={b}
          className="text-[12px] px-2 py-0.5 rounded-md bg-td-surface2 border border-td-line text-td-text/85"
          title="How this stock has tended to move with gold, the U.S. dollar, and the fear gauge (VIX) over the last ~60 trading days"
        >
          {b}
        </span>
      ))}
    </div>
  )}

  <ReferenceDetailGrid
    only={["whyMoved"]}
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
    onOpenContext={() => setModalTab("context")}
    portfolioImpactContext={portfolioImpactContext}
  />

  {detail.fundamentals_snapshot && !detail.fundamentals_snapshot.point_in_time && (
    <p
      className="text-[11px] text-td-muted leading-snug"
      title={detail.fundamentals_snapshot.detail}
    >
      Fair value and valuation numbers reflect the latest available data, not a historical snapshot — treat them as context, not a precise calculation.
    </p>
  )}

  {/* Quick reference — collapsed by default */}
  <section className="border border-td-line rounded-xl overflow-hidden">
    <button
      type="button"
      onClick={() => setQuickRefOpen((o) => !o)}
      className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-td-surface2/60 transition-colors"
    >
      <h3 className="flex items-center gap-2 text-sm font-semibold text-td-muted">
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
      <div className="px-4 pb-4 pt-3 border-t border-td-line">
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
    </div>
    <aside className={clsx("space-y-3 self-start", wide && "xl:sticky xl:top-44")}>
      <NarrativeWaterfallCard ticker={detail.ticker} mode={decisionMode} />
    </aside>
    </div>
  );
}
