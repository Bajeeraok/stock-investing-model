"use client";

import { clsx } from "clsx";
import {
  TICKER_SOURCE_FILTERS,
  type TickerSourceFilter,
  countBySource,
  toTickerSet,
} from "@/lib/tickerSourceFilter";
import {
  SIGNAL_PRESETS,
  presetsForLens,
  type SignalsPresetId,
} from "@/lib/signalPresets";
import type { TradingLens } from "@/lib/tradingLens";

interface TickerFilterBarProps {
  source: TickerSourceFilter;
  onSourceChange: (id: TickerSourceFilter) => void;
  preset: SignalsPresetId;
  onPresetChange: (id: SignalsPresetId) => void;
  tickers: string[];
  portfolioTickers?: string[];
  watchlistTickers?: string[];
  /** Shown as filtered/total after both filters applied */
  shownCount: number;
  totalCount: number;
  showPresets?: boolean;
  tradingLens?: TradingLens;
}

export function TickerFilterBar({
  source,
  onSourceChange,
  preset,
  onPresetChange,
  tickers,
  portfolioTickers,
  watchlistTickers,
  shownCount,
  totalCount,
  showPresets = true,
  tradingLens,
}: TickerFilterBarProps) {
  const presetList = tradingLens ? presetsForLens(tradingLens) : SIGNAL_PRESETS;
  const portfolioSet = toTickerSet(portfolioTickers);
  const watchlistSet = toTickerSet(watchlistTickers);
  const counts = countBySource(tickers, portfolioSet, watchlistSet);

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-center gap-1.5 min-w-0">
        <span className="text-[10px] text-slate-500 uppercase tracking-wide shrink-0">Source</span>
        {TICKER_SOURCE_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            title={f.hint}
            onClick={() => onSourceChange(f.id)}
            className={clsx(
              "text-[11px] px-2 py-1 rounded-full border shrink-0",
              source === f.id
                ? "border-sky-500/45 bg-sky-500/15 text-sky-200"
                : "border-slate-600 text-slate-400 hover:text-slate-200",
            )}
          >
            {f.label}
            {counts[f.id] > 0 && counts[f.id] !== counts.all && (
              <span className="text-slate-500 ml-1">({counts[f.id]})</span>
            )}
          </button>
        ))}
      </div>
      {showPresets && (
        <div className="flex flex-wrap items-center gap-1.5 min-w-0">
          <span className="text-[10px] text-slate-500 uppercase tracking-wide shrink-0">View</span>
          {presetList.map((p) => (
            <button
              key={p.id}
              type="button"
              title={p.hint}
              onClick={() => onPresetChange(p.id)}
              className={clsx(
                "text-[11px] px-2 py-1 rounded-full border shrink-0",
                preset === p.id
                  ? "border-emerald-500/45 bg-emerald-500/15 text-emerald-200"
                  : "border-slate-600 text-slate-400 hover:text-slate-200",
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
      <span className="text-[10px] text-slate-600 shrink-0">
        {shownCount}/{totalCount} shown
      </span>
    </div>
  );
}
