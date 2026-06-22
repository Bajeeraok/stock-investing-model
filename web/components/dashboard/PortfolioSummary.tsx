"use client";

import { DollarSign, BarChart3, PieChart, AlertCircle, Gauge } from "lucide-react";
import type { PortfolioReport } from "@/app/page";
import { DataMetricCard } from "./DataMetricCard";

export function PortfolioSummary({ report }: { report: PortfolioReport }) {
  const mismatch = report.score_confidence_mismatch_count ?? 0;

  return (
    <>
      <DataMetricCard
        title="Total value"
        icon={<DollarSign />}
        primary={`$${report.total_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
        primaryClassName="text-emerald-400"
      />
      <DataMetricCard
        title="If −10%"
        icon={<AlertCircle />}
        primary={`$${(report.total_value * 0.9).toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
        primaryClassName="text-amber-400 text-xl"
        secondary="Simple stress: portfolio drops 10%"
      />
      <DataMetricCard
        title="Avg composite score"
        icon={<BarChart3 />}
        primary={report.avg_score.toFixed(1)}
        secondary="Chart rules (MA / RSI / MACD) — tile fill color"
      />
      <DataMetricCard
        title="Avg model confidence"
        icon={<Gauge />}
        primary={
          report.avg_confidence != null ? (
            <span className="text-xl font-semibold text-slate-100">{report.avg_confidence.toFixed(1)}%</span>
          ) : (
            "—"
          )
        }
        secondary="7-layer fused model — tile ring; — if not computed for holdings"
      />
      {mismatch > 0 && (
        <DataMetricCard
          title="Score ≠ confidence"
          icon={<AlertCircle />}
          primary={<span className="text-xl font-semibold text-amber-300">{mismatch}</span>}
          secondary="Holdings where chart score and model confidence disagree"
          primaryClassName="text-amber-300"
        />
      )}
      <DataMetricCard
        title="Regime mix"
        icon={<PieChart />}
        primary={
          <span className="text-xl font-semibold flex flex-wrap gap-x-3 gap-y-1">
            <span className="text-emerald-400">UP {report.regime_counts.UP}</span>
            <span className="text-slate-400">NEUTRAL {report.regime_counts.NEUTRAL}</span>
            <span className="text-red-400">DOWN {report.regime_counts.DOWN}</span>
          </span>
        }
      />
      <DataMetricCard
        title="Largest"
        icon={<AlertCircle />}
        primary={
          report.largest_position ? (
            <span className="text-lg font-semibold text-slate-200">
              {report.largest_position.ticker}{" "}
              <span className="text-slate-400 font-normal">({report.largest_position.pct.toFixed(1)}%)</span>
            </span>
          ) : (
            "—"
          )
        }
        secondary={
          <>
            {report.largest_position?.score != null && (
              <span>
                Score {report.largest_position.score.toFixed(0)}
                {report.largest_position.confidence != null &&
                  ` · Conf ${Math.round(report.largest_position.confidence)}%`}
                {report.largest_position.regime && ` (${report.largest_position.regime})`}
              </span>
            )}
            {report.top3_pct != null && report.top3_pct > 0 && (
              <span className="block text-slate-500 mt-0.5">Top 3 = {report.top3_pct}% of portfolio</span>
            )}
            {report.concentration_alert.length > 0 && (
              <span className="block text-amber-400 text-xs mt-1">{report.concentration_alert.join(" · ")}</span>
            )}
          </>
        }
      />
      {report.mega_cap_pct != null && report.mega_cap_pct > 0 && (
        <DataMetricCard
          title="Mega-cap %"
          primary={<span className="text-xl font-semibold text-slate-200">{report.mega_cap_pct}%</span>}
          secondary="AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA combined"
        />
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
          <div className="text-amber-400 text-base mb-1">High correlation ({">"}0.8)</div>
          <p className="text-slate-400 text-sm">{report.correlation_alerts.join(" · ")}</p>
        </div>
      )}
    </>
  );
}
