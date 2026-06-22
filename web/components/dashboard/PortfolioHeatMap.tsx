"use client";

import type { PortfolioHolding } from "@/app/page";
import { clsx } from "clsx";
import {
  confidenceRingClass,
  confidenceTextClass,
  fmtConfidence,
  fmtScore,
  isScoreConfidenceMismatch,
  mismatchHint,
  scoreTileClass,
} from "@/lib/scoreConfidenceDisplay";

function regimeDot(regime: string | null | undefined): string {
  if (regime === "UP") return "bg-emerald-400";
  if (regime === "DOWN") return "bg-red-400";
  return "bg-slate-400";
}

function tileTooltip(h: PortfolioHolding, pct: number): string {
  const parts = [
    h.ticker,
    `${pct.toFixed(1)}%`,
    `score ${fmtScore(h.score)}`,
    h.confidence != null ? `conf ${fmtScore(h.confidence)}%` : "conf —",
    h.regime ?? "—",
  ];
  const hint = mismatchHint(h.score, h.confidence);
  if (hint) parts.push(hint);
  return parts.join(" · ");
}

function MismatchBadge() {
  return (
    <span
      className="absolute top-1 left-1 z-10 text-[8px] font-black uppercase px-1 py-0.5 rounded bg-amber-500/90 text-amber-950 leading-none"
      title="Chart score and model confidence disagree"
    >
      ⚠
    </span>
  );
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
  const mismatchCount = items.filter((h) => isScoreConfidenceMismatch(h.score, h.confidence)).length;

  return (
    <div className="rounded-xl border border-slate-700/90 bg-slate-900/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-700/80 bg-slate-900/60 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">Portfolio heat map</h3>
          <p className="text-[11px] text-slate-400 mt-1 md:hidden">Sorted by weight · tap a row for detail</p>
          <p className="text-[11px] text-slate-400 mt-1 hidden md:block">
            Size = weight · fill = composite score · ring = model confidence · dot = regime
          </p>
          {mismatchCount > 0 && (
            <p className="text-[10px] text-amber-300/90 mt-1">
              {mismatchCount} holding{mismatchCount === 1 ? "" : "s"}: score vs confidence disagree (⚠)
            </p>
          )}
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
        {/* Mobile: scannable list */}
        <div className="md:hidden divide-y divide-slate-700/60 rounded-lg border border-slate-700/50 overflow-hidden">
          {sorted.map((h) => {
            const pct = h.pct ?? 0;
            const mismatch = isScoreConfidenceMismatch(h.score, h.confidence);
            const rowClass = clsx(
              "w-full flex items-center gap-2 px-3 py-2.5 text-left touch-manipulation min-h-[44px]",
              scoreTileClass(h.score),
              confidenceRingClass(h.confidence),
              onTickerClick && "hover:opacity-95 active:opacity-90",
            );
            const inner = (
              <>
                {mismatch && <MismatchBadge />}
                <span className="font-mono text-sm font-semibold w-12 shrink-0 truncate">{h.ticker}</span>
                <span className="text-xs tabular-nums w-10 shrink-0 opacity-80">{pct.toFixed(1)}%</span>
                <span className="text-xs font-medium tabular-nums w-7 shrink-0">{fmtScore(h.score)}</span>
                <span className={clsx("text-[10px] tabular-nums w-10 shrink-0", confidenceTextClass(h.confidence))}>
                  {fmtConfidence(h.confidence)}
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
                className={clsx(rowClass, "relative")}
                title={tileTooltip(h, pct)}
              >
                {inner}
              </button>
            ) : (
              <div key={h.ticker} className={clsx(rowClass, "relative")}>
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
              const mismatch = isScoreConfidenceMismatch(h.score, h.confidence);
              const inner = (
                <>
                  {mismatch && <MismatchBadge />}
                  <span className="font-mono text-xs sm:text-sm font-semibold truncate">{h.ticker}</span>
                  <span className="text-[10px] opacity-80">{pct.toFixed(1)}%</span>
                  <div className="flex items-baseline gap-1.5 flex-wrap">
                    {h.score != null && (
                      <span className="text-[10px] font-semibold opacity-95">{fmtScore(h.score)}</span>
                    )}
                    <span className={clsx("text-[9px] font-mono tabular-nums", confidenceTextClass(h.confidence))}>
                      {fmtConfidence(h.confidence)}
                    </span>
                  </div>
                  <span
                    className={clsx("absolute top-1.5 right-1.5 h-2 w-2 rounded-full", regimeDot(h.regime))}
                    title={h.regime ?? "Regime"}
                  />
                </>
              );
              const className = clsx(
                "relative rounded-lg border px-2 py-2 min-w-[4.75rem] min-h-[3.5rem] flex flex-col justify-center gap-0.5 transition-opacity hover:opacity-95",
                scoreTileClass(h.score),
                confidenceRingClass(h.confidence),
                onTickerClick && "cursor-pointer hover:ring-1 hover:ring-emerald-500/40",
              );
              return onTickerClick ? (
                <button
                  key={h.ticker}
                  type="button"
                  onClick={() => onTickerClick(h.ticker)}
                  className={className}
                  style={{ flex: `${flexGrow} 1 5rem` }}
                  title={tileTooltip(h, pct)}
                >
                  {inner}
                </button>
              ) : (
                <div key={h.ticker} className={className} style={{ flex: `${flexGrow} 1 5rem` }}>
                  {inner}
                </div>
              );
            })}
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-[10px] text-slate-500">
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-4 rounded bg-emerald-600/40 border border-emerald-500/40" /> Score ≥65
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-4 rounded bg-slate-600/40 border border-slate-500/40" /> Mixed score
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-4 rounded bg-red-600/30 border border-red-500/40" /> Score ≤35
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-4 rounded border-2 border-emerald-400/70 bg-slate-800/80" /> Conf ≥70%
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-4 rounded border-2 border-dashed border-slate-500/60 bg-slate-800/80" /> Conf &lt;40%
          </span>
        </div>
      </div>
    </div>
  );
}
