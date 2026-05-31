"use client";

import { clsx } from "clsx";
import type { AnalystRatingDistribution } from "./valuationDeckTypes";

const SEGMENTS: { key: keyof AnalystRatingDistribution; label: string; color: string }[] = [
  { key: "strong_buy", label: "Strong buy", color: "bg-emerald-500" },
  { key: "buy", label: "Buy", color: "bg-emerald-400/80" },
  { key: "hold", label: "Hold", color: "bg-amber-500/90" },
  { key: "sell", label: "Sell", color: "bg-orange-500/80" },
  { key: "strong_sell", label: "Strong sell", color: "bg-red-500" },
];

export function AnalystRatingBar({
  ratings,
  compact = false,
}: {
  ratings: AnalystRatingDistribution;
  compact?: boolean;
}) {
  const total = ratings.total || 0;
  if (total <= 0) return null;

  const sourceLabel = ratings.source === "fmp" ? "FMP" : ratings.source === "yahoo" ? "Yahoo" : ratings.source;

  return (
    <div className={clsx("space-y-1.5", compact && "space-y-1")}>
      <div className="flex h-2.5 rounded-full overflow-hidden bg-slate-800/80 border border-slate-700/60">
        {SEGMENTS.map(({ key, color }) => {
          const n = Number(ratings[key]) || 0;
          if (n <= 0) return null;
          const pct = (n / total) * 100;
          return (
            <div
              key={key}
              className={clsx(color, "min-w-[2px]")}
              style={{ width: `${pct}%` }}
              title={`${key.replace("_", " ")}: ${n}`}
            />
          );
        })}
      </div>
      {!compact && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-slate-400">
          {SEGMENTS.map(({ key, label }) => {
            const n = Number(ratings[key]) || 0;
            if (n <= 0) return null;
            return (
              <span key={key}>
                {label} <span className="text-slate-300 font-medium tabular-nums">{n}</span>
              </span>
            );
          })}
        </div>
      )}
      <p className="text-[10px] text-slate-500">
        {total} analysts · {sourceLabel}
        {ratings.bullish_pct != null ? (
          <span className="text-slate-400"> · {ratings.bullish_pct}% bullish (buy+strong buy)</span>
        ) : null}
      </p>
    </div>
  );
}
