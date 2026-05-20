"use client";

import React, { useEffect, useState } from "react";
import { ChevronRight, LayoutGrid } from "lucide-react";
import { clsx } from "clsx";
import type { TradeRoadmapData } from "./TradeRoadmapCard";
import { TradeRoadmapCard } from "./TradeRoadmapCard";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
const MAX_TICKERS = 12;

export interface RoadmapItem {
  ticker: string;
  one_answer: { headline: string; subline?: string | null; verdict: string; action_today: string } | null;
  trade_roadmap: TradeRoadmapData | null;
}

interface Props {
  /** Tickers to load (e.g. watchlist or signals). */
  tickers: string[];
  onTickerClick: (ticker: string) => void;
  /** Skip fetch while dashboard background compute is running. */
  warming?: boolean;
}

export function RoadmapsPanel({ tickers, onTickerClick, warming = false }: Props) {
  const [items, setItems] = useState<RoadmapItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);

  const toFetch = tickers.slice(0, MAX_TICKERS).filter(Boolean);

  useEffect(() => {
    if (warming) return;
    if (toFetch.length === 0) {
      setItems([]);
      return;
    }
    setLoading(true);
    setError(null);
    const q = toFetch.join(",");
    fetch(API_BASE ? `${API_BASE}/api/roadmaps?tickers=${encodeURIComponent(q)}` : `/api/roadmaps?tickers=${encodeURIComponent(q)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => setItems(data.roadmaps || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [toFetch.join(","), warming]);

  if (warming) {
    return (
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-8 text-center text-amber-200/90">
        <LayoutGrid className="h-10 w-10 mx-auto mb-2 opacity-50" />
        <p className="text-sm">Dashboard still warming — roadmaps load after the first compute finishes.</p>
      </div>
    );
  }

  if (toFetch.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-800/30 p-8 text-center text-slate-500">
        <LayoutGrid className="h-10 w-10 mx-auto mb-2 opacity-50" />
        <p>Add tickers to your watchlist to see roadmaps here.</p>
      </div>
    );
  }

  if (loading && items.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-800/30 p-8 text-center">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-emerald-500 border-t-transparent mx-auto mb-3" />
        <p className="text-slate-400">Loading roadmaps…</p>
      </div>
    );
  }

  if (error && items.length === 0) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-6 text-center text-red-200">
        <p className="text-sm">Failed to load roadmaps: {error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">
        One answer + buy/sell roadmap per ticker. Click a ticker to open full detail, or expand to see the full roadmap card.
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {items.map((item) => {
          const hasRoadmap = item.trade_roadmap != null;
          const isExpanded = expandedTicker === item.ticker;
          return (
            <div
              key={item.ticker}
              className={clsx(
                "rounded-xl border overflow-hidden",
                hasRoadmap ? "border-slate-700 bg-slate-800/50" : "border-slate-700/50 bg-slate-800/30"
              )}
            >
              {/* Compact card: ticker + one answer + Open / Expand */}
              <div className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => onTickerClick(item.ticker)}
                      className="font-mono font-semibold text-emerald-400 hover:text-emerald-300 text-lg"
                    >
                      {item.ticker}
                    </button>
                    {item.one_answer && (
                      <>
                        <p className="text-sm text-slate-200 mt-1 line-clamp-2">{item.one_answer.headline}</p>
                        {item.one_answer.subline && (
                          <p className="text-xs text-amber-200/90 mt-0.5">{item.one_answer.subline}</p>
                        )}
                        <span
                          className={clsx(
                            "inline-block mt-2 text-xs font-medium px-2 py-0.5 rounded",
                            (item.one_answer.verdict === "AVOID" || item.one_answer.verdict === "REDUCE") && "bg-red-500/20 text-red-300",
                            (item.one_answer.verdict === "BUY" || item.one_answer.verdict === "STRONG BUY") && "bg-emerald-500/20 text-emerald-300",
                            !["AVOID", "REDUCE", "BUY", "STRONG BUY"].includes(item.one_answer.verdict) && "bg-slate-600 text-slate-300"
                          )}
                        >
                          {item.one_answer.verdict}
                        </span>
                      </>
                    )}
                    {!item.one_answer && !item.trade_roadmap && (
                      <p className="text-xs text-slate-500 mt-1">Roadmap not available</p>
                    )}
                  </div>
                  <div className="flex flex-col gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => onTickerClick(item.ticker)}
                      className="text-xs font-medium text-emerald-400 hover:text-emerald-300 flex items-center gap-0.5"
                    >
                      Open <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                    {hasRoadmap && (
                      <button
                        type="button"
                        onClick={() => setExpandedTicker(isExpanded ? null : item.ticker)}
                        className="text-xs text-slate-400 hover:text-slate-300"
                      >
                        {isExpanded ? "Collapse" : "Expand roadmap"}
                      </button>
                    )}
                  </div>
                </div>
              </div>
              {/* Expanded: full Trade Roadmap card */}
              {isExpanded && item.trade_roadmap && (
                <div className="border-t border-slate-700 p-4 bg-slate-900/50">
                  <TradeRoadmapCard data={item.trade_roadmap} ticker={item.ticker} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
