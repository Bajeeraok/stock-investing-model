"use client";

import { clsx } from "clsx";

export interface Best2026Pick {
  ticker: string;
  score: number | null;
  regime: string | null;
  confidence: number;
  reason: string;
  close?: number | null;
}

export function Best2026Section({
  items,
  onTickerClick,
}: {
  items: Best2026Pick[];
  onTickerClick?: (ticker: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5">
      <h3 className="text-sm font-semibold text-slate-400 mb-2 flex items-center gap-2">
        <span className="text-emerald-400">2026 best tickers</span>
        (confidence-based; absorbs daily stats)
      </h3>
      <p className="text-xs text-slate-500 mb-3">
        Ranked by LT score + regime + confidence. Excludes earnings within 2 weeks. Refresh daily to update.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-400 border-b border-slate-700">
              <th className="py-2 font-medium">Ticker</th>
              <th className="py-2 font-medium">Score</th>
              <th className="py-2 font-medium">Regime</th>
              <th className="py-2 font-medium">Confidence</th>
              <th className="py-2 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.ticker} className="border-b border-slate-700/50 hover:bg-slate-800/30">
                <td className="py-2">
                  {onTickerClick ? (
                    <button
                      type="button"
                      onClick={() => onTickerClick(p.ticker)}
                      className="font-mono font-medium text-emerald-400 hover:underline cursor-pointer"
                    >
                      {p.ticker}
                    </button>
                  ) : (
                    <span className="font-mono font-medium">{p.ticker}</span>
                  )}
                </td>
                <td className="py-2 text-slate-300">{p.score != null ? p.score.toFixed(1) : "-"}</td>
                <td className="py-2">
                  <span
                    className={clsx(
                      "px-2 py-0.5 rounded text-xs",
                      p.regime === "UP" && "bg-emerald-500/20 text-emerald-400",
                      p.regime === "NEUTRAL" && "bg-slate-500/20 text-slate-400",
                      p.regime === "DOWN" && "bg-red-500/20 text-red-400"
                    )}
                  >
                    {p.regime ?? "-"}
                  </span>
                </td>
                <td className="py-2">
                  <span className={p.confidence >= 70 ? "text-emerald-400" : "text-slate-300"}>
                    {p.confidence}%
                  </span>
                </td>
                <td className="py-2 text-slate-400 text-xs">{p.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
