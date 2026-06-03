"use client";

import type { PortfolioHolding } from "@/app/page";
import { clsx } from "clsx";

function scoreColor(score: number | null | undefined): string {
  if (score == null) return "bg-slate-700/80 border-slate-600 text-slate-300";
  if (score >= 65) return "bg-emerald-600/35 border-emerald-500/45 text-emerald-100";
  if (score <= 35) return "bg-red-600/30 border-red-500/40 text-red-100";
  return "bg-slate-600/40 border-slate-500/40 text-slate-200";
}

function regimeDot(regime: string | null | undefined): string {
  if (regime === "UP") return "bg-emerald-400";
  if (regime === "DOWN") return "bg-red-400";
  return "bg-slate-400";
}

export function PortfolioHeatMap({
  holdings,
  onTickerClick,
  regimeCounts,
}: {
  holdings: PortfolioHolding[];
  onTickerClick?: (ticker: string) => void;
  regimeCounts?: { UP?: number; NEUTRAL?: number; DOWN?: number };
}) {
  const items = holdings.filter((h) => h.ticker && (h.pct ?? 0) > 0);
  if (items.length === 0) return null;

  const sorted = [...items].sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0));

  return (
    <div className="rounded-xl border border-slate-700/90 bg-slate-900/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-700/80 bg-slate-900/60 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">Portfolio heat map</h3>
          <p className="text-[11px] text-slate-400 mt-1 md:hidden">Sorted by weight · tap a row for detail</p>
          <p className="text-[11px] text-slate-400 mt-1 hidden md:block">
            Tile size = weight · color = score · dot = regime (green up, red down)
          </p>
        </div>
        {regimeCounts && (
          <div className="flex flex-wrap gap-1.5 text-[10px] font-medium">
            <span className="px-2 py-0.5 rounded border border-emerald-500/35 bg-emerald-950/30 text-emerald-200">
              UP {regimeCounts.UP ?? 0}
            </span>
            <span className="px-2 py-0.5 rounded border border-slate-500/40 bg-slate-800/50 text-slate-300">
              NEUTRAL {regimeCounts.NEUTRAL ?? 0}
            </span>
            <span className="px-2 py-0.5 rounded border border-red-500/35 bg-red-950/25 text-red-200">
              DOWN {regimeCounts.DOWN ?? 0}
            </span>
          </div>
        )}
      </div>
      <div className="p-3 sm:p-4">
        {/* Mobile: scannable list (heat map tiles don't scale to many holdings) */}
        <div className="md:hidden divide-y divide-slate-700/60 rounded-lg border border-slate-700/50 overflow-hidden">
          {sorted.map((h) => {
            const pct = h.pct ?? 0;
            const rowClass = clsx(
              "w-full flex items-center gap-3 px-3 py-2.5 text-left touch-manipulation min-h-[44px]",
              scoreColor(h.score),
              onTickerClick && "hover:opacity-95 active:opacity-90",
            );
            const inner = (
              <>
                <span className="font-mono text-sm font-semibold w-14 shrink-0 truncate">{h.ticker}</span>
                <span className="text-xs tabular-nums w-10 shrink-0 opacity-80">{pct.toFixed(1)}%</span>
                <span className="text-xs font-medium tabular-nums w-8 shrink-0">
                  {h.score != null ? Math.round(h.score) : "—"}
                </span>
                <span
                  className={clsx("ml-auto h-2.5 w-2.5 rounded-full shrink-0", regimeDot(h.regime))}
                  title={h.regime ?? "Regime"}
                />
              </>
            );
            return onTickerClick ? (
              <button
                key={h.ticker}
                type="button"
                onClick={() => onTickerClick(h.ticker)}
                className={rowClass}
                title={`${h.ticker} · ${pct.toFixed(1)}% · score ${h.score ?? "—"} · ${h.regime ?? "—"}`}
              >
                {inner}
              </button>
            ) : (
              <div key={h.ticker} className={rowClass}>
                {inner}
              </div>
            );
          })}
        </div>

        {/* Desktop: tile heat map */}
        <div className="hidden md:block">
        <div className="flex flex-wrap gap-1.5 min-h-[5rem]">
          {sorted.map((h) => {
            const pct = Math.max(h.pct ?? 1, 1);
            const flexGrow = Math.round(pct * 10);
            const inner = (
              <>
                <span className="font-mono text-xs sm:text-sm font-semibold truncate">{h.ticker}</span>
                <span className="text-[10px] opacity-80">{pct.toFixed(1)}%</span>
                {h.score != null && (
                  <span className="text-[10px] font-medium opacity-90">{Math.round(h.score)}</span>
                )}
                <span
                  className={clsx("absolute top-1.5 right-1.5 h-2 w-2 rounded-full", regimeDot(h.regime))}
                  title={h.regime ?? "Regime"}
                />
              </>
            );
            const className = clsx(
              "relative rounded-lg border px-2 py-2 min-w-[4.5rem] min-h-[3.25rem] flex flex-col justify-center gap-0.5 transition-opacity hover:opacity-95",
              scoreColor(h.score),
              onTickerClick && "cursor-pointer hover:ring-1 hover:ring-emerald-500/40"
            );
            return onTickerClick ? (
              <button
                key={h.ticker}
                type="button"
                onClick={() => onTickerClick(h.ticker)}
                className={className}
                style={{ flex: `${flexGrow} 1 5rem` }}
                title={`${h.ticker} · ${pct.toFixed(1)}% · score ${h.score ?? "—"} · ${h.regime ?? "—"}`}
              >
                {inner}
              </button>
            ) : (
              <div
                key={h.ticker}
                className={className}
                style={{ flex: `${flexGrow} 1 5rem` }}
              >
                {inner}
              </div>
            );
          })}
        </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-3 text-[10px] text-slate-500">
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-4 rounded bg-emerald-600/40 border border-emerald-500/40" /> Score ≥65
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-4 rounded bg-slate-600/40 border border-slate-500/40" /> Mixed
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-4 rounded bg-red-600/30 border border-red-500/40" /> Score ≤35
          </span>
        </div>
      </div>
    </div>
  );
}
