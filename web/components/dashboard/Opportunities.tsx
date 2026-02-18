"use client";

import type { Opportunity } from "@/app/page";
import { Sparkles } from "lucide-react";
import { clsx } from "clsx";

export function Opportunities({ items, onTickerClick }: { items: Opportunity[]; onTickerClick?: (ticker: string) => void }) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900/30 p-6 text-center text-slate-400">
        No tickers passed criteria today. Try relaxing min_score or max_rsi in config.
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-slate-700 overflow-hidden">
      {/* Mobile: card list */}
      <div className="md:hidden divide-y divide-slate-700/50">
        {items.map((o) => (
          <button
            key={o.ticker}
            type="button"
            onClick={() => onTickerClick?.(o.ticker)}
            className="w-full text-left px-4 py-3 active:bg-slate-800/50 transition-colors"
          >
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="font-mono font-semibold text-emerald-400 text-base">{o.ticker}</span>
              <span className="text-slate-300 text-sm">${o.close.toFixed(2)}</span>
            </div>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className={clsx(
                "font-medium text-sm",
                o.composite_buy >= 80 && "text-emerald-400",
                o.composite_buy >= 70 && o.composite_buy < 80 && "text-emerald-300",
                o.composite_buy < 70 && "text-slate-300"
              )}>
                {o.composite_buy.toFixed(0)} conf
              </span>
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/20 text-emerald-400">
                {o.regime}
              </span>
              <span className="text-slate-500 text-sm">RSI {o.rsi.toFixed(0)}</span>
            </div>
            <p className="text-slate-400 text-sm mt-1 line-clamp-2">{o.reason}</p>
          </button>
        ))}
      </div>

      {/* Desktop: table with sticky header + sticky Ticker & Close */}
      <div className="hidden md:block overflow-x-auto [-webkit-overflow-scrolling:touch]">
        <table className="w-full min-w-[640px] text-sm border-collapse">
          <thead>
            <tr className="text-left text-slate-400">
              <th className="sticky top-0 left-0 z-[30] min-w-[4.5rem] w-24 px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]">Ticker</th>
              <th className="sticky top-0 left-24 z-[25] min-w-[5rem] w-20 px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)]">Close</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">Confidence</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">RSI</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">Regime</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">Reason</th>
            </tr>
          </thead>
          <tbody>
            {items.map((o) => (
              <tr key={o.ticker} className="group border-t border-slate-700/50 hover:bg-slate-800/30">
                <td className="sticky left-0 z-[10] min-w-[4.5rem] w-24 px-3 py-2.5 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30">
                  {onTickerClick ? (
                    <button type="button" onClick={() => onTickerClick(o.ticker)} className="font-mono font-medium text-emerald-400 hover:underline cursor-pointer">
                      {o.ticker}
                    </button>
                  ) : (
                    <span className="font-mono font-medium">{o.ticker}</span>
                  )}
                </td>
                <td className="sticky left-24 z-[10] min-w-[5rem] w-20 px-3 py-2.5 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30">${o.close.toFixed(2)}</td>
                <td className="px-3 py-2.5">
                  <span className={clsx(
                    "font-medium",
                    o.composite_buy >= 80 && "text-emerald-400",
                    o.composite_buy >= 70 && o.composite_buy < 80 && "text-emerald-300",
                    o.composite_buy < 70 && "text-slate-300"
                  )}>
                    {o.composite_buy.toFixed(1)}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-slate-400">{o.rsi.toFixed(1)}</td>
                <td className="px-3 py-2.5">
                  <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/20 text-emerald-400">
                    {o.regime}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-sm text-slate-400">{o.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-3 sm:px-4 py-2 text-xs text-slate-500 border-t border-slate-700">
        Candidates to research - not buy recommendations. Use your judgment.
      </p>
    </div>
  );
}
