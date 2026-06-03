"use client";

import React, { useEffect, useMemo, useState } from "react";
import { ChevronRight, LayoutGrid } from "lucide-react";
import { clsx } from "clsx";
import type { TradeRoadmapData } from "./TradeRoadmapCard";
import { TradeRoadmapCard } from "./TradeRoadmapCard";
import { TickerFilterBar } from "./TickerFilterBar";
import {
  filterTickersBySource,
  loadTickerSourceFilter,
  saveTickerSourceFilter,
  toTickerSet,
  type TickerSourceFilter,
} from "@/lib/tickerSourceFilter";
import {
  filterTickersByPreset,
  loadSignalsPreset,
  saveSignalsPreset,
  type SignalPresetRow,
  type SignalsPresetId,
} from "@/lib/signalPresets";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
const MAX_TICKERS = 24;

export interface RoadmapItem {
  ticker: string;
  one_answer: { headline: string; subline?: string | null; verdict: string; action_today: string } | null;
  trade_roadmap: TradeRoadmapData | null;
}

interface Props {
  /** Tickers to load (e.g. watchlist or signals). */
  tickers: string[];
  onTickerClick: (ticker: string, tab?: "today" | "levels" | "why") => void;
  /** Skip fetch while dashboard background compute is running. */
  warming?: boolean;
  portfolioTickers?: string[];
  watchlistTickers?: string[];
  /** Signal rows keyed by ticker — used for View presets. */
  signalsByTicker?: Map<string, SignalPresetRow>;
}

export function RoadmapsPanel({
  tickers,
  onTickerClick,
  warming = false,
  portfolioTickers,
  watchlistTickers,
  signalsByTicker,
}: Props) {
  const [items, setItems] = useState<RoadmapItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState(false);
  const [preset, setPreset] = useState<SignalsPresetId>("all");
  const [sourceFilter, setSourceFilter] = useState<TickerSourceFilter>("all");

  useEffect(() => {
    setPreset(loadSignalsPreset());
    setSourceFilter(loadTickerSourceFilter());
  }, []);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const sync = () => setIsMobile(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  const applyPreset = (id: SignalsPresetId) => {
    setPreset(id);
    saveSignalsPreset(id);
  };

  const applySourceFilter = (id: TickerSourceFilter) => {
    setSourceFilter(id);
    saveTickerSourceFilter(id);
  };

  const filteredTickers = useMemo(() => {
    const portfolioSet = toTickerSet(portfolioTickers);
    const watchlistSet = toTickerSet(watchlistTickers);
    const bySource = filterTickersBySource(tickers, sourceFilter, portfolioSet, watchlistSet);
    const map = signalsByTicker ?? new Map<string, SignalPresetRow>();
    return filterTickersByPreset(bySource, preset, map);
  }, [tickers, sourceFilter, preset, portfolioTickers, watchlistTickers, signalsByTicker]);

  const toFetch = filteredTickers.slice(0, MAX_TICKERS).filter(Boolean);
  const fetchKey = toFetch.join(",");

  useEffect(() => {
    if (warming) return;
    if (toFetch.length === 0) {
      setItems([]);
      return;
    }
    setLoading(true);
    setError(null);
    fetch(
      API_BASE
        ? `${API_BASE}/api/roadmaps?tickers=${encodeURIComponent(fetchKey)}`
        : `/api/roadmaps?tickers=${encodeURIComponent(fetchKey)}`,
    )
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => setItems(data.roadmaps || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [fetchKey, warming, toFetch.length]);

  if (warming) {
    return (
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-8 text-center text-amber-200/90">
        <LayoutGrid className="h-10 w-10 mx-auto mb-2 opacity-50" />
        <p className="text-sm">Dashboard still warming — roadmaps load after the first compute finishes.</p>
      </div>
    );
  }

  if (tickers.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-800/30 p-8 text-center text-slate-500">
        <LayoutGrid className="h-10 w-10 mx-auto mb-2 opacity-50" />
        <p>Add holdings to your portfolio or tickers to your watchlist to see roadmaps here.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-700 bg-slate-800/40 px-3 sm:px-4 py-2">
        <TickerFilterBar
          source={sourceFilter}
          onSourceChange={applySourceFilter}
          preset={preset}
          onPresetChange={applyPreset}
          tickers={tickers}
          portfolioTickers={portfolioTickers}
          watchlistTickers={watchlistTickers}
          shownCount={filteredTickers.length}
          totalCount={tickers.length}
        />
      </div>

      {filteredTickers.length === 0 ? (
        <div className="rounded-xl border border-slate-700 bg-slate-800/30 p-8 text-center text-slate-500">
          <LayoutGrid className="h-10 w-10 mx-auto mb-2 opacity-50" />
          <p>No tickers match the current filters. Try a broader source or view.</p>
        </div>
      ) : loading && items.length === 0 ? (
        <div className="rounded-xl border border-slate-700 bg-slate-800/30 p-8 text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-emerald-500 border-t-transparent mx-auto mb-3" />
          <p className="text-slate-400">Loading roadmaps…</p>
        </div>
      ) : error && items.length === 0 ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-6 text-center text-red-200">
          <p className="text-sm">Failed to load roadmaps: {error}</p>
        </div>
      ) : (
        <>
          <p className="text-sm text-slate-400">
            One answer + buy/sell roadmap per ticker (portfolio holdings first, then watchlist). Tap a ticker for
            full detail; on phone, roadmap opens full-screen on the Levels tab.
            {filteredTickers.length > MAX_TICKERS && (
              <span className="text-slate-500">
                {" "}
                Showing first {MAX_TICKERS} of {filteredTickers.length} matching tickers.
              </span>
            )}
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
                    hasRoadmap ? "border-slate-700 bg-slate-800/50" : "border-slate-700/50 bg-slate-800/30",
                  )}
                >
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
                                (item.one_answer.verdict === "AVOID" || item.one_answer.verdict === "REDUCE") &&
                                  "bg-red-500/20 text-red-300",
                                (item.one_answer.verdict === "BUY" || item.one_answer.verdict === "STRONG BUY") &&
                                  "bg-emerald-500/20 text-emerald-300",
                                !["AVOID", "REDUCE", "BUY", "STRONG BUY"].includes(item.one_answer.verdict) &&
                                  "bg-slate-600 text-slate-300",
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
                            onClick={() => {
                              if (isMobile) {
                                onTickerClick(item.ticker, "levels");
                                return;
                              }
                              setExpandedTicker(isExpanded ? null : item.ticker);
                            }}
                            className="text-xs text-slate-400 hover:text-slate-300"
                          >
                            {isMobile ? "Roadmap" : isExpanded ? "Collapse" : "Expand roadmap"}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                  {isExpanded && !isMobile && item.trade_roadmap && (
                    <div className="border-t border-slate-700 p-4 bg-slate-900/50">
                      <TradeRoadmapCard data={item.trade_roadmap} ticker={item.ticker} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
