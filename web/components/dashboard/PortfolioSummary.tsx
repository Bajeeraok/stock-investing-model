"use client";

import { DollarSign, BarChart3, PieChart, AlertCircle } from "lucide-react";
import type { PortfolioReport } from "@/app/page";

export function PortfolioSummary({ report }: { report: PortfolioReport }) {
  return (
    <>
      <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5">
        <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
          <DollarSign className="h-4 w-4" />
          Total Value
        </div>
        <p className="text-2xl font-bold text-emerald-400">
          ${report.total_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
        </p>
      </div>
      <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5">
        <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
          <BarChart3 className="h-4 w-4" />
          Avg Score
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
      <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5">
        <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
          <AlertCircle className="h-4 w-4" />
          Largest
        </div>
        {report.largest_position ? (
          <p className="text-lg font-semibold text-slate-200">
            {report.largest_position.ticker}{" "}
            <span className="text-slate-400 font-normal">({report.largest_position.pct.toFixed(1)}%)</span>
          </p>
        ) : (
          <p className="text-slate-400">-</p>
        )}
        {report.concentration_alert.length > 0 && (
          <p className="text-amber-400 text-xs mt-1">Concentration alert</p>
        )}
      </div>
    </>
  );
}
