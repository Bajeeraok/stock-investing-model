"use client";

import { useEffect, useState } from "react";
import { Dashboard } from "@/components/Dashboard";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(API_BASE ? `${API_BASE}/api/dashboard` : "/api/dashboard");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  if (loading && !data) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-emerald-500 border-t-transparent mx-auto mb-4" />
          <p className="text-slate-400">Running analysis... This may take 1-2 minutes.</p>
          <p className="text-slate-500 text-sm mt-1">Fetching signals, portfolio, opportunities...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center p-8 bg-slate-900 rounded-xl border border-red-500/30">
          <p className="text-red-400 font-medium">Error: {error}</p>
          <p className="text-slate-400 text-sm mt-2">Make sure the FastAPI server is running:</p>
          <code className="block mt-2 p-2 bg-slate-800 rounded text-emerald-400 text-sm">cd backend && python -m uvicorn api.main:app --reload --port 8002</code>
          <button
            onClick={refresh}
            className="mt-4 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-medium"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return data ? (
    <Dashboard data={data} onRefresh={refresh} loading={loading} />
  ) : null;
}

export interface DashboardData {
  signals: Signal[];
  story_changes: Signal[];
  portfolio: PortfolioReport;
  trim_candidates: PortfolioHolding[];
  opportunities: Opportunity[];
  thesis_check: ThesisCheck[];
  what_changed: WhatChanged[];
  config: { watchlist: string[]; score: object; regime: object };
}

export interface Signal {
  ticker: string;
  close: number | null;
  composite_buy: number | null;
  regime: string | null;
  signal: string | null;
  rsi: number | null;
  earnings_note?: string | null;
  story_change?: string | null;
  short_suggestion?: string | null;
  medium_suggestion?: string | null;
  long_suggestion?: string | null;
  error?: string;
}

export interface PortfolioReport {
  per_holding: PortfolioHolding[];
  total_value: number;
  avg_score: number;
  regime_counts: { UP: number; NEUTRAL: number; DOWN: number };
  largest_position: { ticker: string; pct: number; value: number } | null;
  concentration_alert: string[];
  cash_deployment: { ticker: string; score: number; regime: string }[];
}

export interface PortfolioHolding {
  ticker: string;
  value: number | null;
  pct: number | null;
  score: number | null;
  regime: string | null;
  suggestion: string;
}

export interface Opportunity {
  ticker: string;
  close: number;
  composite_buy: number;
  rsi: number;
  regime: string;
  reason: string;
}

export interface ThesisCheck {
  ticker: string;
  thesis: string;
  exit_condition: string;
  nudge: string | null;
}

export interface WhatChanged {
  ticker: string;
  changes: string[];
}
