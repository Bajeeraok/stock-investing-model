"use client";

import { useEffect, useMemo, useState } from "react";
import { clsx } from "clsx";
import { LineChart, Crosshair, LayoutGrid, Grid3x3 } from "lucide-react";
import type { Signal } from "@/app/page";
import { SignalsTable } from "./SignalsTable";
import { SmartDcaPanel } from "./SmartDcaPanel";
import { HunterPanel, type HunterPanelPayload } from "./HunterPanel";
import { RoadmapsPanel } from "./RoadmapsPanel";
import { SignalsHeatmap } from "./SignalsHeatmap";
import { TickerFilterBar } from "./TickerFilterBar";
import type { SignalListContext } from "./retailActionUX";
import {
  filterTickersBySource,
  loadTickerSourceFilter,
  saveTickerSourceFilter,
  toTickerSet,
  type TickerSourceFilter,
} from "@/lib/tickerSourceFilter";
import {
  loadSignalsPreset,
  matchesSignalPreset,
  saveSignalsPreset,
  type SignalPresetRow,
  type SignalsPresetId,
} from "@/lib/signalPresets";
import { defaultPresetForLens, type TradingLens } from "@/lib/tradingLens";

type SignalsSubTab = "scanner" | "hunter" | "roadmaps" | "heatmap";

const SUB_TABS: { id: SignalsSubTab; label: string; icon: typeof LineChart }[] = [
  { id: "hunter", label: "Hunter", icon: Crosshair },
  { id: "scanner", label: "Scanner", icon: LineChart },
  { id: "heatmap", label: "Heatmap", icon: Grid3x3 },
  { id: "roadmaps", label: "Roadmaps", icon: LayoutGrid },
];

const SUB_TAB_STORAGE_KEY = "thrive-signals-subtab";

function loadSubTab(): SignalsSubTab {
  try {
    const raw = typeof window !== "undefined" ? localStorage.getItem(SUB_TAB_STORAGE_KEY) : null;
    if (raw === "scanner" || raw === "hunter" || raw === "roadmaps" || raw === "heatmap") return raw;
  } catch {
    /* ignore */
  }
  return "hunter";
}

export function SignalsHub({
  signals,
  horizons,
  onTickerClick,
  riskSizing,
  cotByTicker,
  tickerActions,
  listContext,
  portfolioTickers,
  watchlistTickers,
  tradingLens,
  hunterPanel,
  roadmapTickers,
  roadmapsWarming,
  signalsByTicker,
  splitPane = false,
  activeTicker = null,
}: {
  signals: Signal[];
  horizons?: { short_term: string; medium_term: string; long_term: string } | null;
  onTickerClick?: (ticker: string, tab?: "verdict" | "levels" | "why" | "context" | "track") => void;
  riskSizing?: { risk_pct: number; stop_pct: number };
  cotByTicker?: Record<string, string>;
  tickerActions?: Record<string, { action: string; one_liner: string }>;
  listContext?: SignalListContext;
  portfolioTickers?: string[];
  watchlistTickers?: string[];
  tradingLens?: TradingLens;
  hunterPanel?: HunterPanelPayload | null;
  roadmapTickers: string[];
  roadmapsWarming?: boolean;
  signalsByTicker?: Map<string, SignalPresetRow>;
  /** Desktop list + detail split view is active (see Dashboard / useTickerDetailLayout). */
  splitPane?: boolean;
  activeTicker?: string | null;
}) {
  const [subTab, setSubTab] = useState<SignalsSubTab>("hunter");
  const [source, setSource] = useState<TickerSourceFilter>("all");
  const [preset, setPreset] = useState<SignalsPresetId>("all");

  useEffect(() => {
    setSubTab(loadSubTab());
    setSource(loadTickerSourceFilter());
  }, []);

  // Lens-aware default preset — both on first load and live, if the user switches
  // Scout/Swing/Owner lens elsewhere while this tab is already open (same behavior
  // SignalsTable used to own itself before this filter bar was lifted up).
  useEffect(() => {
    if (tradingLens) {
      setPreset(defaultPresetForLens(tradingLens));
    } else {
      setPreset(loadSignalsPreset());
    }
  }, [tradingLens]);

  const handleSubTabChange = (id: SignalsSubTab) => {
    setSubTab(id);
    try {
      localStorage.setItem(SUB_TAB_STORAGE_KEY, id);
    } catch {
      /* ignore */
    }
  };

  const handleSourceChange = (id: TickerSourceFilter) => {
    setSource(id);
    saveTickerSourceFilter(id);
  };

  const handlePresetChange = (id: SignalsPresetId) => {
    setPreset(id);
    saveSignalsPreset(id);
  };

  const tickerList = useMemo(() => signals.map((s) => s.ticker).filter(Boolean) as string[], [signals]);

  // Scanner/Roadmaps filter themselves internally from the same source/preset — Heatmap has no
  // internal filtering logic of its own, so it needs the already-filtered row set handed to it.
  const heatmapSignals = useMemo(() => {
    const portfolioSet = toTickerSet(portfolioTickers);
    const watchlistSet = toTickerSet(watchlistTickers);
    const bySource = new Set(
      filterTickersBySource(tickerList, source, portfolioSet, watchlistSet).map((t) => t.toUpperCase()),
    );
    return signals.filter(
      (s) => s.ticker && bySource.has(s.ticker.toUpperCase()) && matchesSignalPreset(s, preset),
    );
  }, [signals, tickerList, source, preset, portfolioTickers, watchlistTickers]);

  return (
    <div className="space-y-3">
      <div
        role="tablist"
        aria-label="Signals sections"
        className="flex flex-wrap gap-1.5 p-1.5 rounded-xl bg-slate-900/80 border border-slate-700/60"
      >
        {SUB_TABS.map(({ id, label, icon: Icon }) => {
          const isActive = subTab === id;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => handleSubTabChange(id)}
              className={clsx(
                "flex items-center justify-center gap-1.5 px-3 py-3 sm:py-2 rounded-lg text-sm font-medium transition-colors",
                "basis-[calc(50%-0.1875rem)] sm:basis-auto sm:flex-initial min-h-[44px] sm:min-h-0 touch-manipulation",
                isActive
                  ? "bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/30"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60",
              )}
            >
              <Icon className={clsx("h-4 w-4 shrink-0", isActive ? "text-emerald-400" : "text-slate-500")} />
              {label}
            </button>
          );
        })}
      </div>

      {/* Dedicated SPY/QQQ smart-DCA section — index tranche timing from the
          same gate/zone state the table rows carry. */}
      <SmartDcaPanel signals={signals} />

      {subTab !== "hunter" && (
        <div className="rounded-xl border border-slate-700 bg-slate-800/40 px-3 sm:px-4 py-2">
          <TickerFilterBar
            source={source}
            onSourceChange={handleSourceChange}
            preset={preset}
            onPresetChange={handlePresetChange}
            tickers={subTab === "roadmaps" ? roadmapTickers : tickerList}
            portfolioTickers={portfolioTickers}
            watchlistTickers={watchlistTickers}
            shownCount={
              subTab === "heatmap"
                ? heatmapSignals.length
                : subTab === "roadmaps"
                  ? roadmapTickers.length
                  : tickerList.length
            }
            totalCount={subTab === "roadmaps" ? roadmapTickers.length : tickerList.length}
            tradingLens={tradingLens}
          />
        </div>
      )}

      {subTab === "scanner" && (
        <SignalsTable
          signals={signals}
          horizons={horizons}
          onTickerClick={onTickerClick}
          riskSizing={riskSizing}
          cotByTicker={cotByTicker}
          tickerActions={tickerActions}
          listContext={listContext}
          portfolioTickers={portfolioTickers}
          watchlistTickers={watchlistTickers}
          source={source}
          preset={preset}
          splitPane={splitPane}
          activeTicker={activeTicker}
        />
      )}

      {subTab === "hunter" && (
        <HunterPanel
          panel={hunterPanel}
          portfolioTickers={portfolioTickers}
          watchlistTickers={watchlistTickers}
          onTickerClick={onTickerClick}
          source={source}
          onSourceChange={handleSourceChange}
        />
      )}

      {subTab === "roadmaps" && (
        <RoadmapsPanel
          warming={roadmapsWarming}
          tickers={roadmapTickers}
          onTickerClick={onTickerClick ?? (() => {})}
          portfolioTickers={portfolioTickers}
          watchlistTickers={watchlistTickers}
          signalsByTicker={signalsByTicker}
          source={source}
          preset={preset}
        />
      )}

      {subTab === "heatmap" && <SignalsHeatmap signals={heatmapSignals} onTickerClick={onTickerClick} />}
    </div>
  );
}
