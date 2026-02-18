"use client";

import { DollarSign, BarChart3, PieChart, AlertCircle } from "lucide-react";
import type { PortfolioReport } from "@/app/page";

export function PortfolioSummary({ report }: { report: PortfolioReport }) {
  return (
    <>
      <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5 min-w-[180px]">
        <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
          <DollarSign className="h-4 w-4 shrink-0" />
          <span className="whitespace-nowrap">Total Value</span>
        </div>
        <p className="text-2xl font-bold text-emerald-400">
          ${report.total_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
        </p>
      </div>
      <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5 min-w-[180px]" title="Simple stress: if portfolio drops 10%">
        <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span className="whitespace-nowrap">If −10%</span>
        </div>
        <p className="text-xl font-semibold text-amber-400">
          ${(report.total_value * 0.9).toLocaleString(undefined, { minimumFractionDigits: 2 })}
        </p>
      </div>
      <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5 min-w-[180px]">
        <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
          <BarChart3 className="h-4 w-4 shrink-0" />
          <span className="whitespace-nowrap">Avg Confidence</span>
        </div>
        <p className="text-2xl font-bold text-slate-100">{report.avg_score.toFixed(1)}</p>
      </div>
      <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5">
        <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
          <PieChart className="h-4 w-4" />
          Regime Mix
        </div>
        <div className="flex gap-3 mt-1">
          <span className="text-emerald-400">UP {report.regime_counts.UP}</span>
          <span className="text-slate-400">NEUTRAL {report.regime_counts.NEUTRAL}</span>
          <span className="text-red-400">DOWN {report.regime_counts.DOWN}</span>
        </div>
      </div>
      <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5 min-w-[180px]">
        <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span className="whitespace-nowrap">Largest</span>
        </div>
        {report.largest_position ? (
          <>
            <p className="text-lg font-semibold text-slate-200">
              {report.largest_position.ticker}{" "}
              <span className="text-slate-400 font-normal">({report.largest_position.pct.toFixed(1)}%)</span>
              {report.largest_position.score != null && (
                <span className="text-slate-500 font-normal ml-1">
                  score {report.largest_position.score.toFixed(0)}
                  {report.largest_position.regime && ` (${report.largest_position.regime})`}
                </span>
              )}
            </p>
            {report.top3_pct != null && report.top3_pct > 0 && (
              <p className="text-slate-500 text-sm mt-1">Top 3 = {report.top3_pct}% of portfolio</p>
            )}
          </>
        ) : (
          <p className="text-slate-400">-</p>
        )}
        {report.concentration_alert.length > 0 && (
          <p className="text-amber-400 text-xs mt-1">Concentration alert</p>
        )}
      </div>
      {report.mega_cap_pct != null && report.mega_cap_pct > 0 && (
        <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5 min-w-[180px]" title="Mega-cap (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA) combined %">
          <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">Mega-cap %</div>
          <p className="text-xl font-semibold text-slate-200">{report.mega_cap_pct}%</p>
        </div>
      )}
      {report.sector_allocation && report.sector_allocation.length > 0 && (
        <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5 md:col-span-2 lg:col-span-4">
          <div className="flex items-center gap-2 text-slate-400 text-sm mb-2">Sector allocation</div>
          <div className="flex flex-wrap gap-2">
            {report.sector_allocation.map((s) => (
              <span key={s.sector} className="px-2 py-1 rounded bg-slate-800 text-slate-300 text-base">
                {s.sector}: {s.pct}%
              </span>
            ))}
          </div>
        </div>
      )}
      {report.correlation_alerts && report.correlation_alerts.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-5 md:col-span-2 lg:col-span-4">
          <div className="text-amber-400 text-base mb-1">High correlation (&gt;0.8)</div>
          <p className="text-slate-400 text-sm">{report.correlation_alerts.join(" · ")}</p>
        </div>
      )}
    </>
  );
}
