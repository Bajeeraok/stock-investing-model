"use client";

import type { PortfolioHolding } from "@/app/page";
import { clsx } from "clsx";

export function PortfolioHoldings({ holdings, onTickerClick }: { holdings: PortfolioHolding[]; onTickerClick?: (ticker: string) => void }) {
  const sorted = [...holdings].sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  const hasAccounts = holdings.some((h) => h.account);
  const hasGainLoss = holdings.some((h) => h.gain_loss != null);
  return (
    <div className="rounded-xl border border-slate-700 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-slate-800/80 text-left text-sm text-slate-400">
              {hasAccounts && <th className="px-4 py-3 font-medium">Account</th>}
              <th className="px-4 py-3 font-medium">Ticker</th>
              <th className="px-4 py-3 font-medium">Value</th>
              {hasGainLoss && <th className="px-4 py-3 font-medium">Gain/Loss</th>}
              <th className="px-4 py-3 font-medium">%</th>
              <th className="px-4 py-3 font-medium">Score</th>
              <th className="px-4 py-3 font-medium">Regime</th>
              <th className="px-4 py-3 font-medium">Suggestion</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((h, i) => (
              <tr key={h.account ? `${h.account}-${h.ticker}-${i}` : h.ticker} className="border-t border-slate-700/50 hover:bg-slate-800/30">
                {hasAccounts && <td className="px-4 py-3 text-slate-400">{h.account ?? "-"}</td>}
                <td className="px-4 py-3">
                  {onTickerClick ? (
                    <button type="button" onClick={() => onTickerClick(h.ticker)} className="font-mono font-medium text-emerald-400 hover:underline cursor-pointer">
                      {h.ticker}
                    </button>
                  ) : (
                    <span className="font-mono font-medium">{h.ticker}</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {h.value != null ? `$${h.value.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "-"}
                </td>
                {hasGainLoss && (
                  <td className="px-4 py-3">
                    {h.gain_loss != null ? (
                      <span className={h.gain_loss >= 0 ? "text-emerald-400" : "text-red-400"}>
                        {h.gain_loss >= 0 ? "+" : ""}${h.gain_loss.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        {h.gain_loss_pct != null ? ` (${h.gain_loss_pct >= 0 ? "+" : ""}${h.gain_loss_pct}%)` : ""}
                      </span>
                    ) : (
                      "-"
                    )}
                  </td>
                )}
                <td className="px-4 py-3 text-slate-400">
                  {h.pct != null ? `${h.pct.toFixed(1)}%` : "-"}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      (h.score ?? 0) >= 65 && "text-emerald-400",
                      (h.score ?? 0) < 65 && (h.score ?? 0) > 35 && "text-slate-300",
                      (h.score ?? 0) <= 35 && "text-red-400"
                    )}
                  >
                    {h.score != null ? h.score.toFixed(1) : "-"}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      "px-2 py-0.5 rounded text-xs font-medium",
                      h.regime === "UP" && "bg-emerald-500/20 text-emerald-400",
                      h.regime === "NEUTRAL" && "bg-slate-500/20 text-slate-400",
                      h.regime === "DOWN" && "bg-red-500/20 text-red-400"
                    )}
                  >
                    {h.regime ?? "-"}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-300">{h.suggestion}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
