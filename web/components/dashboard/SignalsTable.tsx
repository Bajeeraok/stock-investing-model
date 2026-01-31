"use client";

import type { Signal } from "@/app/page";
import { clsx } from "clsx";

export function SignalsTable({ signals }: { signals: Signal[] }) {
  return (
    <div className="rounded-xl border border-slate-700 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-slate-800/80 text-left text-sm text-slate-400">
              <th className="px-4 py-3 font-medium">Ticker</th>
              <th className="px-4 py-3 font-medium">Close</th>
              <th className="px-4 py-3 font-medium">Score</th>
              <th className="px-4 py-3 font-medium">RSI</th>
              <th className="px-4 py-3 font-medium">Regime</th>
              <th className="px-4 py-3 font-medium">Signal</th>
              <th className="px-4 py-3 font-medium">Short / Medium / Long</th>
              <th className="px-4 py-3 font-medium">Notes</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((r) => (
              <tr
                key={r.ticker}
                className={clsx(
                  "border-t border-slate-700/50 hover:bg-slate-800/30",
                  r.story_change && "bg-amber-500/5"
                )}
              >
                <td className="px-4 py-3 font-mono font-medium">{r.ticker}</td>
                <td className="px-4 py-3">
                  {r.close != null ? `$${r.close.toFixed(2)}` : "-"}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      "font-medium",
                      (r.composite_buy ?? 0) >= 70 && "text-emerald-400",
                      (r.composite_buy ?? 0) < 70 && (r.composite_buy ?? 0) > 30 && "text-slate-300",
                      (r.composite_buy ?? 0) <= 30 && "text-red-400"
                    )}
                  >
                    {r.composite_buy != null ? r.composite_buy.toFixed(1) : "-"}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-300">{r.rsi != null ? r.rsi.toFixed(1) : "-"}</td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      "px-2 py-0.5 rounded text-xs font-medium",
                      r.regime === "UP" && "bg-emerald-500/20 text-emerald-400",
                      r.regime === "NEUTRAL" && "bg-slate-500/20 text-slate-400",
                      r.regime === "DOWN" && "bg-red-500/20 text-red-400"
                    )}
                  >
                    {r.regime ?? "-"}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      "font-medium",
                      r.signal === "BUY" && "text-emerald-400",
                      r.signal === "HOLD" && "text-slate-400",
                      r.signal === "SELL" && "text-red-400"
                    )}
                  >
                    {r.signal ?? "-"}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-slate-400">
                  {[r.short_suggestion, r.medium_suggestion, r.long_suggestion]
                    .filter(Boolean)
                    .join(" / ") || "-"}
                </td>
                <td className="px-4 py-3 text-sm">
                  {r.earnings_note && (
                    <span className="text-amber-400">{r.earnings_note}</span>
                  )}
                  {r.story_change && (
                    <span className="text-amber-400 ml-1">• {r.story_change}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
