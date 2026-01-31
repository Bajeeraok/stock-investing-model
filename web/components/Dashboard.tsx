"use client";

import { AlertTriangle, RefreshCw, TrendingUp, Wallet, Target, FileText, Sparkles } from "lucide-react";
import type { DashboardData } from "@/app/page";
import { clsx } from "clsx";
import {
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
} from "./dashboard";

interface Props {
  data: DashboardData;
  onRefresh: () => void;
  loading: boolean;
}

export function Dashboard({ data, onRefresh, loading }: Props) {
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

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Story Alerts */}
        {data.story_changes.length > 0 && <StoryAlerts items={data.story_changes} />}

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <PortfolioSummary report={data.portfolio} />
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ScoreChart signals={data.signals} />
          <RegimeChart report={data.portfolio} />
        </div>

        {/* Signals Table */}
        <section>
          <h2 className="flex items-center gap-2 text-lg font-semibold mb-4">
            <Target className="h-5 w-5 text-emerald-500" />
            Daily Signals
          </h2>
          <SignalsTable signals={data.signals} />
        </section>

        {/* Portfolio Holdings */}
        <section>
          <h2 className="flex items-center gap-2 text-lg font-semibold mb-4">
            <Wallet className="h-5 w-5 text-emerald-500" />
            Portfolio Holdings
          </h2>
          <PortfolioHoldings holdings={data.portfolio.per_holding} />
        </section>

        {/* Consider Trim */}
        {data.trim_candidates.length > 0 && (
          <section>
            <h2 className="flex items-center gap-2 text-lg font-semibold mb-4 text-amber-400">
              <AlertTriangle className="h-5 w-5" />
              Consider Trim (protect gains)
            </h2>
            <TrimCandidates items={data.trim_candidates} />
          </section>
        )}

        {/* Opportunities */}
        <section>
          <h2 className="flex items-center gap-2 text-lg font-semibold mb-4">
            <Sparkles className="h-5 w-5 text-emerald-500" />
            Daily Opportunities (long-term potential)
          </h2>
          <Opportunities items={data.opportunities} />
        </section>

        {/* Thesis Check */}
        {data.thesis_check.length > 0 && (
          <section>
            <h2 className="flex items-center gap-2 text-lg font-semibold mb-4">
              <FileText className="h-5 w-5 text-emerald-500" />
              Thesis Check
            </h2>
            <ThesisCheck items={data.thesis_check} />
          </section>
        )}

        {/* What Changed */}
        {data.what_changed.length > 0 && (
          <section>
            <h2 className="flex items-center gap-2 text-lg font-semibold mb-4">
              <RefreshCw className="h-5 w-5 text-emerald-500" />
              What Changed (vs last run)
            </h2>
            <WhatChanged items={data.what_changed} />
          </section>
        )}
      </main>
    </div>
  );
}
