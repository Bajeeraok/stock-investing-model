"use client";

/**
 * Why tab body — extracted from TickerDetailModal (P4 tab-file split).
 * P3 gate-first: the single blocking gate (first fail + how it flips) leads,
 * then the full gate cards, then valuation/proof sub-tabs.
 */
import React from "react";
import { clsx } from "clsx";
import { Activity, BarChart3, Ban, ChevronDown, ChevronRight } from "lucide-react";
import { WhyGateCards } from "../WhyGateCards";
import { TickerDetailWhyNav } from "../../TickerDetailWhyNav";
import { ReferenceDetailGrid } from "../ReferenceDetailGrid";
import { HorizonProjectionChart } from "../../HorizonProjectionChart";
import { UnifiedValuationSummary } from "../../UnifiedValuationSummary";
import { FairValueDebugPanel } from "../../FairValueDebugPanel";
import { PriceTargetsPanel } from "../../PriceTargetsPanel";
import { ConfidenceBreakdown, type ConfidenceData } from "../../ConfidenceBreakdown";
import { PatternSignalCard, type UnifiedSignalData } from "../../PatternSignalCard";
import type { TabCtx } from "./tabCtx";

// Lightweight try/catch wrappers so a bad API response never crashes the tab
function ConfidenceBreakdownSafe({ data }: { data: ConfidenceData }) {
  try { return <ConfidenceBreakdown data={data} />; }
  catch { return null; }
}
function PatternSignalCardSafe({ data }: { data: UnifiedSignalData }) {
  try { return <PatternSignalCard data={data} />; }
  catch { return null; }
}

/** The one gate standing between WAIT and GO — first failing primary gate
 * plus the backend's unlock hint. Leads the Why tab (P3 gate-first). */
function BlockingGateStrip({ ctx }: { ctx: TabCtx }) {
  const { tradingGates, detail } = ctx;
  const failing = tradingGates.find((g) => !g.pass);
  const unlock = detail.investor_summary?.retail_action?.unlock_sequence;
  if (!failing) return null;
  return (
    <section className="rounded-xl border border-amber-500/35 bg-amber-950/20 px-4 py-3">
      <div className="flex items-start gap-2.5">
        <Ban className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-amber-200">
            Blocking now: {failing.label}
          </p>
          {failing.detail && (
            <p className="text-xs text-amber-100/80 leading-snug mt-0.5">{failing.detail}</p>
          )}
          {unlock && (
            <p className="text-xs text-slate-400 leading-snug mt-1.5 pt-1.5 border-t border-amber-500/15">
              {unlock}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

export function WhyTab({ ctx }: { ctx: TabCtx }) {
  const {
    detail,
    decisionMode,
    effectivePrice,
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
    debugPanelOpen,
    setDebugPanelOpen,
    portfolioImpactContext,
    overviewVerdict,
    patternVerdict,
    hasVerdictConflict,
    whySubTab,
    setWhySubTab,
    openWhyValuation,
    setModalTab,
  } = ctx;

  return (
    <>
    <BlockingGateStrip ctx={ctx} />
    <WhyGateCards
      verdictWord={(() => {
        const t = headerActionStatus.title.toUpperCase();
        if (headerActionStatus.light === "green") return "Buy";
        if (/TRIM|REDUCE|SELL|EXIT|AVOID/.test(t)) return "Trim";
        if (headerActionStatus.light === "red") return "Wait";
        return "Wait";
      })()}
      gates={tradingGates}
      gatesPassed={gatesPassedCount}
      gatesTotal={gatesTotal}
      currentPrice={effectivePrice}
      fairValue={detail.investor_summary?.fair_value}
    />
    <TickerDetailWhyNav active={whySubTab} onChange={setWhySubTab} />

    {whySubTab === "valuation" && (
      <div className="space-y-4">
        <ReferenceDetailGrid
          only={["valuation"]}
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
        {detail.investor_summary && detail.price_history && detail.price_history.length > 0 && (
          <section className="rounded-xl border border-slate-700/50 bg-slate-900/60 overflow-hidden">
            <HorizonProjectionChart
              ticker={detail.ticker}
              currentPrice={detail.current_price ?? 0}
              priceHistory={detail.price_history}
              short={detail.investor_summary.horizons.short}
              medium={detail.investor_summary.horizons.medium}
              long={detail.investor_summary.horizons.long}
              fairValue={detail.investor_summary.fair_value}
              ma20={detail.ma20}
              ma50={detail.ma50}
              planMode={detail.investor_summary.plan_mode}
              chaseBanner={detail.investor_summary.chase_banner}
              chaseDetail={detail.investor_summary.chase_detail}
            />
          </section>
        )}
        {detail.investor_summary && (
          <UnifiedValuationSummary
            deck={detail.investor_summary.valuation_deck}
            analystTargets={priceTargets?.analyst_targets}
            currentPrice={detail.current_price ?? 0}
            fairValue={detail.investor_summary.fair_value}
            external={detail.investor_summary.fair_value_vs_external}
            decisionMode={decisionMode}
            showFullDeck
          />
        )}
        {detail.investor_summary && (detail.current_price ?? 0) > 0 && (
          <section className="rounded-xl border border-slate-700/50 bg-slate-900/40 overflow-hidden">
            <button
              type="button"
              onClick={() => setDebugPanelOpen((o) => !o)}
              className="w-full flex items-center justify-between gap-2 px-4 py-2.5 text-left hover:bg-slate-800/40 transition-colors"
              aria-expanded={debugPanelOpen}
            >
              <span className="text-[11px] font-mono uppercase tracking-wider text-slate-500">
                Show model internals
              </span>
              {debugPanelOpen ? (
                <ChevronDown className="h-4 w-4 text-slate-500 shrink-0" aria-hidden />
              ) : (
                <ChevronRight className="h-4 w-4 text-slate-500 shrink-0" aria-hidden />
              )}
            </button>
            {debugPanelOpen && (
              <div className="border-t border-slate-800 px-4 py-3">
                <FairValueDebugPanel
                  currentPrice={detail.current_price ?? 0}
                  displayFairValue={detail.investor_summary.fair_value}
                  ttmPeUsed={detail.investor_summary.ttm_pe_used}
                  forwardPeUsed={detail.investor_summary.forward_pe_used}
                  metadata={detail.investor_summary.fair_value_metadata}
                  external={detail.investor_summary.fair_value_vs_external}
                />
              </div>
            )}
          </section>
        )}
        {priceTargets ? (
          <div className="rounded-xl border border-slate-700/50 bg-slate-900/60 px-4 py-4">
            <PriceTargetsPanel
              data={priceTargets}
              hideHorizonZones={!!detail.investor_summary}
              hideTechnicalLevels
              hideAnalystStrip={!!detail.investor_summary}
              scenariosDefaultOpen
              valuationDeck={detail.investor_summary?.valuation_deck}
              fairValue={detail.investor_summary?.fair_value ?? 0}
              fairValueExternal={detail.investor_summary?.fair_value_vs_external}
              decisionMode={decisionMode}
            />
          </div>
        ) : (
          <div className="rounded-xl border border-slate-700/50 bg-slate-800/20 px-4 py-3 flex items-center gap-3 text-slate-500 text-xs animate-pulse">
            <Activity className="h-4 w-4 shrink-0" />
            <span>Computing price ranges &amp; scenarios…</span>
          </div>
        )}
      </div>
    )}

    {whySubTab === "proof" && (
      <div className="space-y-4">
        <ReferenceDetailGrid
          only={["confidence"]}
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

    {confidence ? (
      <section className="space-y-2">
        <div className="rounded-lg border border-slate-700/70 bg-slate-900/40 px-3 py-2">
          <p className="text-xs font-semibold text-slate-200 uppercase tracking-wide">7-Layer model signal</p>
          <p className="text-sm text-slate-400">Regime + ML + options + fundamentals fused.</p>
        </div>
        <ConfidenceBreakdownSafe data={confidence} />
      </section>
    ) : (
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/20 px-4 py-3 flex items-center gap-3 text-slate-500 text-xs animate-pulse">
        <Activity className="h-4 w-4 shrink-0" />
        <span>Loading full confidence model…</span>
      </div>
    )}

    {unified ? (
      <section className="space-y-2">
        <div className="rounded-lg border border-slate-700/70 bg-slate-900/20 px-3 py-2">
          <p className="text-xs font-semibold text-slate-300 uppercase tracking-wide">Technical pattern only</p>
          <p className="text-sm text-slate-500">Chart-pattern context only; not the full fused model verdict.</p>
        </div>
        {hasVerdictConflict && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2">
            <p className="text-sm text-amber-200 leading-snug">
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

    {detail.score_breakdown && (detail.score_breakdown.trend != null || detail.score_breakdown.composite != null) && (
      <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-1">
          <BarChart3 className="h-4 w-4 text-emerald-500" />
          Quick momentum check (rules, not odds)
        </h3>
        <p className="text-slate-500 text-xs mb-3">
          These are 0–100 rule scores (not win probabilities). For odds and sizing, rely on the confidence block above.
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
      </div>
    )}
    </>
  );
}
