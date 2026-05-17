"use client";

import { PieChart, Pie, Cell, Legend, ResponsiveContainer, Tooltip } from "recharts";
import type { PortfolioReport } from "@/app/page";

const COLORS = { UP: "#22c55e", NEUTRAL: "#64748b", DOWN: "#ef4444" };

export function RegimeChart({ report, embedded }: { report: PortfolioReport; embedded?: boolean }) {
  const data = [
    { name: "UP", value: report.regime_counts.UP, color: COLORS.UP },
    { name: "NEUTRAL", value: report.regime_counts.NEUTRAL, color: COLORS.NEUTRAL },
    { name: "DOWN", value: report.regime_counts.DOWN, color: COLORS.DOWN },
  ].filter((d) => d.value > 0);

  if (data.length === 0) return null;

  const inner = (
    <>
      {!embedded && (
        <h3
          className="text-sm font-medium text-slate-400 mb-4"
          title="Regime distribution of portfolio holdings (only tickers you own with regime data)"
        >
          Regime Distribution
        </h3>
      )}
      {embedded && (
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Regime mix</h4>
      )}
      <p className="text-xs text-slate-500 mb-3">
        UP = trend supports position; NEUTRAL = mixed; DOWN = consider trim or avoid new buys.
      </p>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={50}
              outerRadius={80}
              paddingAngle={2}
              dataKey="value"
              nameKey="name"
            >
              {data.map((entry, i) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: "8px" }}
              formatter={(value: number, name: string) => [value, `${name} holdings`]}
            />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </>
  );

  if (embedded) {
    return <div className="min-w-0">{inner}</div>;
  }

  return <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5">{inner}</div>;
}
