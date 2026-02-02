"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { Signal } from "@/app/page";

export function ScoreChart({ signals, onTickerClick }: { signals: Signal[]; onTickerClick?: (ticker: string) => void }) {
  const data = signals
    .filter((s) => s.composite_buy != null && !s.error)
    .sort((a, b) => (b.composite_buy ?? 0) - (a.composite_buy ?? 0))
    .map((s) => ({
      ticker: s.ticker,
      score: s.composite_buy ?? 0,
      fill: (s.composite_buy ?? 0) >= 70 ? "#22c55e" : (s.composite_buy ?? 0) <= 30 ? "#ef4444" : "#64748b",
    }));

  if (data.length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5">
      <h3 className="text-sm font-medium text-slate-400 mb-4">Score by Ticker</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="ticker" tick={{ fill: "#94a3b8", fontSize: 12 }} />
            <YAxis domain={[0, 100]} tick={{ fill: "#94a3b8", fontSize: 12 }} />
            <Tooltip
              contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: "8px" }}
              labelStyle={{ color: "#f8fafc" }}
              formatter={(value: number) => [value.toFixed(1), "Score"]}
              labelFormatter={(label) => `Ticker: ${label}`}
            />
            <Bar
              dataKey="score"
              radius={[4, 4, 0, 0]}
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
    </div>
  );
}
