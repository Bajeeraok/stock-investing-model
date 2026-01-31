"use client";

import type { Opportunity } from "@/app/page";
import { Sparkles } from "lucide-react";
import { clsx } from "clsx";

export function Opportunities({ items }: { items: Opportunity[] }) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900/30 p-6 text-center text-slate-400">
        No tickers passed criteria today. Try relaxing min_score or max_rsi in config.
      </div>
    );
  }
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
              <th className="px-4 py-3 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody>
            {items.map((o) => (
              <tr key={o.ticker} className="border-t border-slate-700/50 hover:bg-slate-800/30">
                <td className="px-4 py-3 font-mono font-medium">{o.ticker}</td>
                <td className="px-4 py-3">${o.close.toFixed(2)}</td>
                <td className="px-4 py-3">
                  <span className={clsx(
                    "font-medium",
                    o.composite_buy >= 80 && "text-emerald-400",
                    o.composite_buy >= 70 && o.composite_buy < 80 && "text-emerald-300",
                    o.composite_buy < 70 && "text-slate-300"
                  )}>
                    {o.composite_buy.toFixed(1)}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-400">{o.rsi.toFixed(1)}</td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/20 text-emerald-400">
                    {o.regime}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-slate-400">{o.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-4 py-2 text-xs text-slate-500 border-t border-slate-700">
        Candidates to research - not buy recommendations. Use your judgment.
      </p>
    </div>
  );
}
