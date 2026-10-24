"use client";

/**
 * Levels tab body — extracted from TickerDetailModal (P4 tab-file split).
 * Chart-first ordering: band overlay → playbook banner → at-a-glance →
 * intraday chart → anchors → [collapsible reference grid] → playbooks.
 */
import React, { useState } from "react";
import { ChevronDown, ChevronRight, Zap } from "lucide-react";
import { DensityProvider, DensityToggle, Comfort } from "../../levels/DensityToggle";
import { LevelsPageHeader } from "../../levels/LevelsPageHeader";
import { AnchorBentoGrid, anchorsFromTechnicalLevels } from "../../levels/AnchorBentoGrid";
import { IntradayChart } from "../../IntradayChart";
import { EntryBandsChart, bandsFromHorizons } from "../EntryBandsChart";
import { ReferenceDetailGrid } from "../ReferenceDetailGrid";
import { RoadmapSummaries } from "../../RoadmapSummaries";
import { HorizonPlaybooksPanel } from "../../HorizonPlaybooksPanel";
import { TradeRoadmapCard } from "../../TradeRoadmapCard";
import { setPositionIntent } from "@/lib/positionIntent";
import { modeFromIntent, setDecisionMode } from "@/lib/decisionMode";
import type { TabCtx } from "./tabCtx";

export function LevelsTab({ ctx }: { ctx: TabCtx }) {
  const {
    ticker,
    detail,
    decisionMode,
    effectivePrice,
    priceTargets,
    confidence,
    executionVm,
    ltEntryTiersOpen,
    setLtEntryTiersOpen,
    portfolioImpactContext,
    playbookStage3,
    regimeShift,
    horizonPlaybooksBundle,
    positionIntent,
    setPositionIntentLocal,
    setDecisionModeLocal,
    openWhyValuation,
    setModalTab,
    setWhySubTab,
    setLivePrice,
    setLiveChangePct,
  } = ctx;

  // P2 chart-first: the dense reference grid starts collapsed — the band chart
  // and anchors carry the at-a-glance answer; the grid is on demand.
  const [gridOpen, setGridOpen] = useState(false);

  return (
    <DensityProvider>
    <>
    {/* Top bar: at-a-glance + density toggle */}
    <div className="flex items-center justify-between gap-2 -mt-2 mb-3">
      <p className="text-xs text-slate-400 leading-snug">
        Staged entries · playbooks · anchors · roadmaps
      </p>
      <DensityToggle />
    </div>

    {/* Chart-first: all entry bands painted vs spot on one price axis */}
    <EntryBandsChart
      currentPrice={effectivePrice}
      bands={bandsFromHorizons(
        {
          ...(detail?.investor_summary?.horizons || {}),
          fair_value: detail?.investor_summary?.fair_value,
        },
        effectivePrice,
      )}
      className="mb-3"
    />

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
            <p className="text-sm text-slate-400 leading-snug pt-1 border-t border-amber-500/20">
              Chance the market backdrop changes meaningfully in about {regimeShift.days_estimate}:{" "}
              <span className="font-mono font-semibold text-amber-300/95">
                {regimeShift.shift_probability.toFixed(0)}%
              </span>
              {regimeShift.label === "WATCH_CLOSELY" && (
                <span className="text-amber-400/90"> — worth watching closely</span>
              )}
              .
            </p>
          )}
        </div>
      </div>
    </section>
  )}


    {/* ── At-a-glance summary header ─── */}
    {detail.investor_summary && detail.current_price != null && (() => {
      const ra = detail.investor_summary.retail_action;
      const long = detail.investor_summary.horizons?.long;
      // Use backend-computed next_add_tier_id as primary — avoids
      // disagreeing with LongTermTierLadder which uses the same field.
      const nextAddTierId = long?.entry_tiers?.spot_position?.next_add_tier_id;
      const nextTier = nextAddTierId
        ? long?.entry_tiers?.tiers?.find((t: { id?: string }) => t.id === nextAddTierId)
        : long?.entry_tiers?.tiers?.find((t: { high: number }) => detail.current_price! > t.high);
      const nextLevel = nextTier?.low ?? long?.entry_zone?.low ?? null;
      return (
        <LevelsPageHeader
          action={ra?.action_title ?? detail.investor_summary.overall_verdict ?? null}
          nextLevel={nextLevel}
          fairValue={detail.investor_summary.fair_value}
          entryMode={ra?.entry_mode ?? null}
          unlockSequence={ra?.unlock_sequence ?? null}
        />
      );
    })()}

    {/* ── Intraday price chart (lazy, auto-refreshes every 15 min) ── */}
    {(() => {
      // Build level reference lines from available data
      const levelLines: Array<{ label: string; value: number; color?: string }> = [];
      const tl = priceTargets?.technical_levels;
      if (tl?.ma200 != null) levelLines.push({ label: "MA200", value: tl.ma200, color: "#f59e0b" });
      if (tl?.ma50  != null) levelLines.push({ label: "MA50",  value: tl.ma50,  color: "#818cf8" });
      const long = detail.investor_summary?.horizons?.long;
      const tiers = long?.entry_tiers?.tiers ?? [];
      const t1 = tiers.find((t: { id?: string }) => t.id === "t1");
      if (t1?.low  != null) levelLines.push({ label: "T1",  value: t1.low,  color: "#34d399" });
      if (long?.entry_zone?.low != null) levelLines.push({ label: "Entry", value: long.entry_zone.low, color: "#22d3ee" });
      return (
        <IntradayChart
          ticker={ticker}
          levelLines={levelLines}
          className="mb-3"
          onLivePrice={(p, pct) => {
            setLivePrice(p);
            setLiveChangePct(pct);
          }}
        />
      );
    })()}

    {/* ── Technical Level Anchors — Bento grid ─── */}
    {priceTargets?.technical_levels && detail.current_price != null && (() => {
      const anchors = anchorsFromTechnicalLevels(
        priceTargets.technical_levels,
        detail.current_price,
      );
      return (
        <div>
          <div className="flex items-center gap-2 flex-wrap mb-0.5">
            <span className="text-[9px] font-semibold text-slate-600 uppercase tracking-widest shrink-0">
              Anchors
            </span>
            <AnchorBentoGrid anchors={anchors} />
          </div>
          <Comfort>
            {priceTargets.technical_levels.note && (
              <p className="text-[10px] text-slate-500 leading-snug mt-1 px-0.5">
                {priceTargets.technical_levels.note}
              </p>
            )}
          </Comfort>
        </div>
      );
    })()}

    {/* ── Chart & levels / near-bottom read / pre-trade portfolio impact —
        chart-first: collapsed by default, expand for the dense read ─── */}
    <section className="rounded-xl border border-td-line overflow-hidden">
      <button
        type="button"
        onClick={() => setGridOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 px-4 py-2.5 text-left hover:bg-td-surface2/60 transition-colors"
        aria-expanded={gridOpen}
      >
        <span className="text-sm font-semibold text-td-text">Levels detail &amp; sizing read</span>
        <span className="flex items-center gap-1 text-[11px] text-td-muted">
          Charts · near-bottom · portfolio impact
          {gridOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </span>
      </button>
      {gridOpen && (
        <div className="border-t border-td-line p-3 pt-2">
          <ReferenceDetailGrid
            only={["chartLevels", "nearBottom", "preTradeImpact"]}
            suppressOpenLevels
            detail={detail}
            priceTargets={priceTargets}
            confidence={confidence}
            decisionMode={decisionMode}
            currentPrice={effectivePrice}
            executionVm={executionVm}
            ltEntryTiersOpen={ltEntryTiersOpen}
            onToggleLtTiers={() => setLtEntryTiersOpen((o) => !o)}
            onOpenLevels={() => {}}
            onOpenValuation={openWhyValuation}
            onOpenProof={() => { setModalTab("why"); setWhySubTab("proof"); }}
            onOpenContext={() => setModalTab("context")}
            portfolioImpactContext={portfolioImpactContext}
          />
        </div>
      )}
    </section>

    {/* ── Roadmap summaries (fallback only — hidden when horizon playbooks
        are present because playbooks show the same short/medium/long data
        in a richer format from the same horizons.* source) ─── */}
    {!horizonPlaybooksBundle && (
      <RoadmapSummaries
        traderRoadmap={detail.investor_summary?.trader_roadmap}
        investorRoadmap={detail.investor_summary?.investor_roadmap}
      />
    )}

    {/* ── Horizon playbooks (Thesis & Tiers tab embeds the Price Thermometer
        + tier ladder — single canonical place these render, see HorizonPlaybookCard) ─── */}
    {horizonPlaybooksBundle && (
      <HorizonPlaybooksPanel
        ticker={detail.ticker}
        playbooks={horizonPlaybooksBundle}
        intent={positionIntent}
        onIntentChange={(intent) => {
          setPositionIntentLocal(intent);
          if (intent) {
            setPositionIntent(detail.ticker, intent);
            const m = modeFromIntent(intent);
            if (m) {
              setDecisionModeLocal(m);
              setDecisionMode(detail.ticker, m);
            }
          }
        }}
        decisionMode={decisionMode}
        entryTiers={detail.investor_summary?.horizons?.long?.entry_tiers ?? null}
        currentPrice={detail.current_price}
        structuralStop={detail.investor_summary?.horizons?.long?.entry_tiers?.structural_invalidation?.price ?? null}
        ma200={priceTargets?.technical_levels?.ma200 ?? null}
      />
    )}

    {/* ── Trade roadmap card — tablesOnly when playbooks are present (the
        playbook above already carries verdict/action/trigger/why narrative;
        this card then renders only its unique content: staged tranche
        tables + news layer). Full card renders when no playbook exists or
        on the Roadmaps dashboard view. ─── */}
    {detail.investor_summary?.trade_roadmap ? (
      <TradeRoadmapCard
        data={detail.investor_summary.trade_roadmap}
        ticker={detail.ticker}
        decisionMode={decisionMode}
        tablesOnly={Boolean(horizonPlaybooksBundle)}
      />
    ) : !horizonPlaybooksBundle && !detail.investor_summary?.horizons?.long?.entry_tiers ? (
      <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-6 text-center text-slate-400">
        <p className="text-sm">Levels not available for this ticker.</p>
        <button
          type="button"
          onClick={() => setModalTab("verdict")}
          className="mt-2 text-sm text-emerald-400 hover:text-emerald-300"
        >
          Back to Verdict
        </button>
      </div>
    ) : null}
    </>
    </DensityProvider>
  );
}
