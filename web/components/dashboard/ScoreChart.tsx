"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { Signal } from "@/app/page";

export function ScoreChart({
  signals,
  onTickerClick,
  embedded,
}: {
  signals: Signal[];
  onTickerClick?: (ticker: string) => void;
  /** When true, omit outer card chrome (for {@link import("./AnchorChartPanel").AnchorChartPanel}) */
  embedded?: boolean;
}) {
  const data = signals
    .filter((s) => s.composite_buy != null && !s.error)
    .sort((a, b) => (b.composite_buy ?? 0) - (a.composite_buy ?? 0))
    .map((s) => ({
      ticker: s.ticker,
      score: s.composite_buy ?? 0,
      fill: (s.composite_buy ?? 0) >= 70 ? "#22c55e" : (s.composite_buy ?? 0) <= 30 ? "#ef4444" : "#64748b",
    }));

  if (data.length === 0) return null;

  const inner = (
    <>
      {!embedded && <h3 className="text-sm font-medium text-slate-400 mb-4">Confidence by Ticker</h3>}
      {embedded && (
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">Confidence by ticker</h4>
      )}
      <div className={embedded ? "h-[min(28rem,70vh)]" : "h-64"}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            layout="vertical"
            data={data}
            margin={{ top: 4, right: 12, left: 4, bottom: 4 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
            <XAxis type="number" domain={[0, 100]} tick={{ fill: "#94a3b8", fontSize: 11 }} />
            <YAxis
              type="category"
              dataKey="ticker"
              width={embedded ? 48 : 56}
              tick={{ fill: "#cbd5e1", fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: "8px" }}
              labelStyle={{ color: "#f8fafc" }}
              formatter={(value: number) => [value.toFixed(1), "Confidence"]}
              labelFormatter={(label) => `Ticker: ${label}`}
            />
            <Bar
              dataKey="score"
              radius={[0, 4, 4, 0]}
              barSize={embedded ? 14 : 18}
              onClick={(e: { payload?: { ticker?: string } }) => e?.payload?.ticker && onTickerClick?.(e.payload.ticker)}
              cursor={onTickerClick ? "pointer" : undefined}
            >
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  );

  if (embedded) {
    return <div className="min-w-0">{inner}</div>;
  }

  return <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5">{inner}</div>;
}
