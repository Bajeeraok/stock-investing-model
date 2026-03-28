"use client";

import type { PortfolioHolding } from "@/app/page";
import { clsx } from "clsx";

export function PortfolioHoldings({
  holdings,
  onTickerClick,
  hideAccountColumn,
  addMinConfidence = 70,
  trimMaxConfidence = 30,
}: {
  holdings: PortfolioHolding[];
  onTickerClick?: (ticker: string) => void;
  hideAccountColumn?: boolean;
  /** From config model_rules.add_min_confidence — confidence column coloring */
  addMinConfidence?: number;
  trimMaxConfidence?: number;
}) {
  const sorted = [...holdings].sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  const hasAccounts = !hideAccountColumn && holdings.some((h) => h.account);
  const hasGainLoss = holdings.some((h) => h.gain_loss != null);
  const hasActionToday = holdings.some((h) => h.action_today);
  return (
    <div className="rounded-xl border border-slate-700 overflow-hidden">
      <div className="overflow-x-auto [-webkit-overflow-scrolling:touch]">
        <table className={clsx("w-full border-collapse text-sm", hasActionToday ? "min-w-[880px]" : "min-w-[640px]")}>
          <thead>
            <tr className="text-left text-slate-400">
              {hasAccounts && (
                <th className="sticky top-0 left-0 z-[30] min-w-[5rem] w-28 px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]">
                  Account
                </th>
              )}
              <th
                className={clsx(
                  "sticky top-0 z-[20] min-w-[4.5rem] w-24 px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700",
                  hasAccounts && "left-28 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)] border-r border-slate-700"
                )}
              >
                Ticker
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">Value</th>
              {hasGainLoss && <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">Gain/Loss</th>}
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">%</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700" title="0-100 calibrated confidence (7-layer engine). Falls back to composite score when confidence is unavailable.">Confidence</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">Regime</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">Suggestion</th>
              {hasActionToday && (
                <th
                  className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700 max-w-[14rem]"
                  title="Single-line cue: confidence/score, regime, suggestion, earnings if soon"
                >
                  Today
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {sorted.map((h, i) => (
              <tr key={h.account ? `${h.account}-${h.ticker}-${i}` : h.ticker} className="group border-t border-slate-700/50 hover:bg-slate-800/30">
                {hasAccounts && (
                  <td className="sticky left-0 z-[10] min-w-[5rem] w-28 px-3 py-2.5 text-slate-400 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30">
                    {h.account ?? "-"}
                  </td>
                )}
                <td
                  className={clsx(
                    "sticky z-[10] min-w-[4.5rem] w-24 px-3 py-2.5 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30",
                    hasAccounts ? "left-28" : "left-0"
                  )}
                >
                  {onTickerClick ? (
                    <button type="button" onClick={() => onTickerClick(h.ticker)} className="font-mono font-medium text-emerald-400 hover:underline cursor-pointer">
                      {h.ticker}
                    </button>
                  ) : (
                    <span className="font-mono font-medium">{h.ticker}</span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  {h.value != null ? `$${h.value.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "-"}
                </td>
                {hasGainLoss && (
                  <td className="px-3 py-2.5">
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
                <td className="px-3 py-2.5 text-slate-400">
                  {h.pct != null ? `${h.pct.toFixed(1)}%` : "-"}
                </td>
                <td className="px-3 py-2.5">
                  {(() => {
                    const val = (h.confidence ?? h.score);
                    return (
                  <span
                    className={clsx(
                      (val ?? 0) >= addMinConfidence && "text-emerald-400",
                      (val ?? 0) < addMinConfidence && (val ?? 0) > trimMaxConfidence && "text-slate-300",
                      (val ?? 0) <= trimMaxConfidence && "text-red-400"
                    )}
                  >
                    {val != null ? val.toFixed(1) : "-"}
                  </span>
                    );
                  })()}
                </td>
                <td className="px-3 py-2.5">
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
                <td className="px-3 py-2.5 text-slate-300">
                  {h.suggestion}
                  {h.action && (
                    <span
                      className={clsx(
                        "ml-2 inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium",
                        (h.action === "STRONG BUY" || h.action === "BUY") && "bg-emerald-500/15 text-emerald-300",
                        (h.action === "HOLD / WATCH") && "bg-slate-500/20 text-slate-300",
                        (h.action === "REDUCE") && "bg-amber-500/15 text-amber-300",
                        (h.action === "AVOID") && "bg-red-500/15 text-red-300"
                      )}
                      title="7-layer engine action"
                    >
                      {h.action}
                    </span>
                  )}
                  {h.gain_loss_pct != null && h.gain_loss_pct >= 20 && (
                    <span className="block text-xs text-amber-400/90 mt-0.5" title="Consider holding 12+ months for long-term capital gains treatment (taxable accounts).">LTCG note                    </span>
                  )}
                </td>
                {hasActionToday && (
                  <td className="px-3 py-2.5 text-xs text-slate-400 max-w-[14rem] align-top">
                    {h.action_today ? <span className="text-slate-300 leading-snug">{h.action_today}</span> : "—"}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
