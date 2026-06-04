"use client";

import { clsx } from "clsx";
import { Activity, Clock } from "lucide-react";
import { PremarketMoverStrip } from "./PremarketMoverStrip";
import type { PreMarketData } from "./PreMarketPanel";
import type { MarketCatalystIntraday } from "./MarketCatalystBoard";

interface SimplePreMarket {
  es_pct?: number | null;
  nq_pct?: number | null;
  tech_avg_pct?: number | null;
  message?: string | null;
}

/**
 * Phase C1 — session strip: pre-market tape + RTH since-open on one surface.
 */
export function SessionStrip({
  full,
  simple,
  intraday,
  isRth,
  isPremarket,
  onTickerClick,
}: {
  full?: PreMarketData | null;
  simple?: SimplePreMarket | null;
  intraday?: MarketCatalystIntraday | null;
  isRth?: boolean;
  isPremarket?: boolean;
  onTickerClick?: (ticker: string) => void;
}) {
  const phase = isRth ? "RTH" : isPremarket ? "Pre-market" : "Session";
  const hasIntraday = intraday && intraday.since_open_pct != null;
  const hasPremarket = Boolean(full || simple);

  if (!hasPremarket && !hasIntraday) return null;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500 px-0.5">
        <Clock className="h-3 w-3" />
        <span>Session tape</span>
        <span
          className={clsx(
            "px-1.5 py-0.5 rounded border font-semibold normal-case",
            isRth && "border-emerald-500/35 text-emerald-300 bg-emerald-500/10",
            isPremarket && !isRth && "border-violet-500/35 text-violet-300 bg-violet-500/10",
            !isRth && !isPremarket && "border-slate-600 text-slate-400",
          )}
        >
          {phase}
        </span>
      </div>

      {hasIntraday && (
        <div className="rounded-lg border border-emerald-500/25 bg-emerald-950/15 px-3 py-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <span className="text-slate-400 flex items-center gap-1">
            <Activity className="h-3 w-3" /> SPY since open
          </span>
          <span
            className={clsx(
              "font-mono font-semibold",
              (intraday!.since_open_pct ?? 0) >= 0 ? "text-emerald-300" : "text-red-300",
            )}
          >
            {(intraday!.since_open_pct ?? 0) >= 0 ? "+" : ""}
            {intraday!.since_open_pct}%
          </span>
          {intraday!.since_release && (
            <span className="text-slate-500">
              Since {intraday!.since_release.name ?? intraday!.since_release.event_type}:{" "}
              <span className="font-mono text-slate-300">
                {(intraday!.since_release.pct_since_release ?? 0) >= 0 ? "+" : ""}
                {intraday!.since_release.pct_since_release}%
              </span>
            </span>
          )}
        </div>
      )}

      {hasPremarket && (
        <PremarketMoverStrip full={full} simple={simple} onTickerClick={onTickerClick} />
      )}
    </div>
  );
}
