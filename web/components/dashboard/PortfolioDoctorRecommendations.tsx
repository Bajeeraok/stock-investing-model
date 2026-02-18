"use client";

import type { PortfolioDoctorRecommendation } from "@/app/page";
import { clsx } from "clsx";

export function PortfolioDoctorRecommendations({
  recommendation,
  selectedPortfolio,
  onTickerClick,
}: {
  recommendation: PortfolioDoctorRecommendation | null | undefined;
  selectedPortfolio: string;
  onTickerClick?: (ticker: string) => void;
}) {
  if (!recommendation) {
    return (
      <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-6 text-center">
        <p className="text-slate-400 text-sm">No allocation recommendations for {selectedPortfolio}.</p>
        <p className="text-slate-500 text-xs mt-1">Set portfolio_doctor in config (risk_appetite, goal, target_portfolio_value, time_period_years).</p>
      </div>
    );
  }

  const { inputs, implied_cagr_pct, profile, trim, add } = recommendation;

  return (
    <div className="space-y-6">
      <p className="text-slate-500 text-sm">When you have multiple accounts (e.g. IRA + Taxable), prefer trimming in IRA first to avoid taxable gains; trim in Taxable when you want to realize losses or rebalance.</p>
      {/* Inputs summary + audit */}
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4">
        <h4 className="text-sm font-medium text-slate-400 mb-2">Settings &amp; assumptions (from config)</h4>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-300">
          <span><strong className="text-slate-400">Risk:</strong> {inputs.risk_appetite}</span>
          <span><strong className="text-slate-400">Goal:</strong> {inputs.goal}</span>
          {inputs.target_portfolio_value != null && inputs.target_portfolio_value > 0 && (
            <>
              <span><strong className="text-slate-400">Target $:</strong> ${inputs.target_portfolio_value.toLocaleString()}</span>
              <span><strong className="text-slate-400">Years:</strong> {inputs.time_period_years}</span>
              {implied_cagr_pct != null && (
                <span><strong className="text-emerald-400">Implied CAGR:</strong> {implied_cagr_pct}%</span>
              )}
            </>
          )}
          <span><strong className="text-slate-400">Profile:</strong> {profile}</span>
        </div>
      </div>

      {/* Trim */}
      <div>
        <h4 className="text-sm font-medium text-amber-400 mb-2">Suggested trims</h4>
        {trim.length === 0 ? (
          <p className="text-slate-500 text-sm">No trim suggestions for this profile.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-700">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-800/80 text-left text-slate-400">
                  <th className="px-4 py-3 font-medium">Ticker</th>
                  <th className="px-4 py-3 font-medium">Current %</th>
                  <th className="px-4 py-3 font-medium">Current $</th>
                  <th className="px-4 py-3 font-medium">Trim %</th>
                  <th className="px-4 py-3 font-medium">Trim $</th>
                  <th className="px-4 py-3 font-medium">Sell at</th>
                  <th className="px-4 py-3 font-medium">Reason</th>
                </tr>
              </thead>
              <tbody>
                {trim.map((r) => (
                  <tr key={r.ticker} className="border-t border-slate-700/50 hover:bg-slate-800/30">
                    <td className="px-4 py-3">
                      {onTickerClick ? (
                        <button type="button" onClick={() => onTickerClick(r.ticker)} className="font-mono font-medium text-amber-400 hover:underline">
                          {r.ticker}
                        </button>
                      ) : (
                        <span className="font-mono font-medium">{r.ticker}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-300">{r.current_pct}%</td>
                    <td className="px-4 py-3 text-slate-300">${r.current_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                    <td className="px-4 py-3 text-amber-400">{r.suggest_trim_pct}%</td>
                    <td className="px-4 py-3 text-amber-400">${r.suggest_trim_dollars.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                    <td className="px-4 py-3 text-slate-300">{r.sell_price != null ? `$${r.sell_price.toFixed(2)}` : "—"}</td>
                    <td className="px-4 py-3 text-slate-500 max-w-[200px] truncate" title={r.reason}>{r.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add */}
      <div>
        <h4 className="text-sm font-medium text-emerald-400 mb-2">Suggested adds (from Opportunities & Best 2026)</h4>
        {add.length === 0 ? (
          <p className="text-slate-500 text-sm">No add suggestions; consider rebalancing or adding cash.</p>
        ) : (
          <>
          <p className="text-slate-500 text-xs mb-2">Consider limit orders for illiquid names; avoid market orders in size.</p>
          <div className="overflow-x-auto rounded-xl border border-slate-700">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-800/80 text-left text-slate-400">
                  <th className="px-4 py-3 font-medium">Ticker</th>
                  <th className="px-4 py-3 font-medium">Confidence</th>
                  <th className="px-4 py-3 font-medium">Regime</th>
                  <th className="px-4 py-3 font-medium">Add %</th>
                  <th className="px-4 py-3 font-medium">Add $</th>
                  <th className="px-4 py-3 font-medium">Buy below</th>
                  <th className="px-4 py-3 font-medium">Source</th>
                </tr>
              </thead>
              <tbody>
                {add.map((a) => (
                  <tr key={a.ticker} className="border-t border-slate-700/50 hover:bg-slate-800/30">
                    <td className="px-4 py-3">
                      {onTickerClick ? (
                        <button type="button" onClick={() => onTickerClick(a.ticker)} className="font-mono font-medium text-emerald-400 hover:underline">
                          {a.ticker}
                        </button>
                      ) : (
                        <span className="font-mono font-medium">{a.ticker}</span>
                      )}
                    </td>
                    <td className={clsx("px-4 py-3", a.score >= 70 ? "text-emerald-400" : "text-slate-300")}>{a.score}</td>
                    <td className="px-4 py-3">
                      <span className={clsx("px-2 py-0.5 rounded text-xs", a.regime === "UP" && "bg-emerald-500/20 text-emerald-400", a.regime === "NEUTRAL" && "bg-slate-500/20 text-slate-400", a.regime === "DOWN" && "bg-red-500/20 text-red-400")}>
                        {a.regime || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-emerald-400">{a.suggest_add_pct}%</td>
                    <td className="px-4 py-3 text-emerald-400">${a.suggest_add_dollars.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                    <td className="px-4 py-3 text-slate-300">{a.buy_price != null ? `$${a.buy_price.toFixed(2)}` : "—"}</td>
                    <td className="px-4 py-3 text-slate-500">{a.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
          </>
        )}
      </div>
    </div>
  );
}
