"use client";

import { useState } from "react";
import { AlertTriangle, BarChart3, Calendar, RefreshCw, TrendingUp, Wallet, Target, FileText, Sparkles } from "lucide-react";
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
} from "./dashboard/index";

interface Props {
  data: DashboardData;
  onRefresh: () => void;
  loading: boolean;
}

export function Dashboard({ data, onRefresh, loading }: Props) {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/90 backdrop-blur supports-[backdrop-filter]:bg-slate-950/70">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-8 w-8 text-emerald-500" />
            <h1 className="text-xl font-bold text-slate-100">Stock Investing Model</h1>
          </div>
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

        {/* Crypto + Cross-asset + Event calendar + 2026 best - toggle */}
        <ToggleSection id="markets" title="Crypto & Cross-asset" icon={<TrendingUp className="h-5 w-5 text-emerald-500" />} defaultOpen={true}>
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 gap-6">
            {data.crypto?.length ? <CryptoSection items={data.crypto} /> : null}
            {data.cross_asset?.length ? <CrossAssetSection items={data.cross_asset} /> : null}
            <EconomicCalendarSection events={data.economic_calendar ?? []} />
            {data.best_2026?.length ? <Best2026Section items={data.best_2026} onTickerClick={setSelectedTicker} /> : null}
          </div>
        </ToggleSection>

        {/* Summary Cards - toggle */}
        <ToggleSection id="summary" title="Portfolio Summary" icon={<Wallet className="h-5 w-5 text-emerald-500" />} defaultOpen={true}>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
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
            <p className={clsx(
              "text-sm font-medium mb-3 px-3 py-2 rounded-lg border",
              data.macro_regime === "Risk-On" && "text-emerald-400 border-emerald-500/30 bg-emerald-500/5",
              data.macro_regime === "Risk-Off" && "text-red-400 border-red-500/30 bg-red-500/5",
              data.macro_regime === "Neutral" && "text-slate-400 border-slate-600 bg-slate-800/50"
            )}>
              Macro regime: {data.macro_regime}
            </p>
          )}
          <p className="text-sm text-slate-500 mb-4">
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
    </div>
  );
}
