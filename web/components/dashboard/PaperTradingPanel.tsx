"use client";

import { clsx } from "clsx";
import type { DashboardData } from "@/app/page";

function fmtPct(p: number | null | undefined) {
  if (p == null) return "—";
  const sign = p >= 0 ? "+" : "";
  return `${sign}${p.toFixed(2)}%`;
}

export function PaperTradingPanel({ data }: { data: DashboardData }) {
  const pt = data.paper_trading;
  if (!pt) return null;

  const summary = pt.summary ?? null;
  const recent = pt.recent ?? [];

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-slate-300">Paper trading (signals → outcomes)</p>
          <p className="text-xs text-slate-500 mt-0.5">
            Logs signals daily; backfills outcomes using EOD snapshots (~20 trading days ≈ 30 calendar days).
          </p>
        </div>
        {pt.log?.date && (
          <div className="text-xs text-slate-500">
            Logged {pt.log.appended}/{pt.log.seen} signals for {pt.log.date}
          </div>
        )}
      </div>

      {summary && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-300">
          <span className="text-slate-500">Status:</span>{" "}
          <span className={clsx(summary.status === "ok" ? "text-emerald-400" : "text-amber-300")}>
            {summary.status}
          </span>
          {summary.completed != null && (
            <span>
              <span className="text-slate-500">Completed:</span> {summary.completed}
            </span>
          )}
          {summary.win_rate_pct != null && (
            <span>
              <span className="text-slate-500">Win rate:</span>{" "}
              <span className={summary.win_rate_pct >= 55 ? "text-emerald-400" : "text-amber-300"}>
                {summary.win_rate_pct.toFixed(1)}%
              </span>
            </span>
          )}
          {summary.avg_return_pct != null && (
            <span>
              <span className="text-slate-500">Avg:</span>{" "}
              <span className={summary.avg_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                {fmtPct(summary.avg_return_pct)}
              </span>
            </span>
          )}
          {summary.avg_win_pct != null && (
            <span>
              <span className="text-slate-500">Avg win:</span> {fmtPct(summary.avg_win_pct)}
            </span>
          )}
          {summary.avg_loss_pct != null && (
            <span>
              <span className="text-slate-500">Avg loss:</span> {fmtPct(summary.avg_loss_pct)}
            </span>
          )}
          {summary.message && <span className="text-slate-500">{summary.message}</span>}
        </div>
      )}

      {pt.fill?.message && <p className="text-xs text-slate-500">{pt.fill.message}</p>}

      {recent.length > 0 ? (
        <div className="overflow-x-auto [-webkit-overflow-scrolling:touch]">
          <table className="w-full text-sm text-left border-collapse min-w-[760px]">
            <thead>
              <tr className="text-slate-500 border-b border-slate-600">
                <th className="py-1.5 pr-2 font-medium">Date</th>
                <th className="py-1.5 pr-2 font-medium">Ticker</th>
                <th className="py-1.5 pr-2 font-medium">Signal</th>
                <th className="py-1.5 pr-2 font-medium">Entry</th>
                <th className="py-1.5 pr-2 font-medium">Target</th>
                <th className="py-1.5 pr-2 font-medium">Stop</th>
                <th className="py-1.5 pr-2 font-medium">Outcome</th>
                <th className="py-1.5 pr-2 font-medium">Return</th>
              </tr>
            </thead>
            <tbody>
              {recent.slice(0, 30).map((r, i) => (
                <tr key={`${r.date}-${r.ticker}-${r.signal}-${i}`} className="border-b border-slate-700/50 hover:bg-slate-800/30">
                  <td className="py-1.5 pr-2 text-slate-400">{r.date}</td>
                  <td className="py-1.5 pr-2 font-mono text-slate-200">{r.ticker}</td>
                  <td className="py-1.5 pr-2 text-slate-400">{r.signal}</td>
                  <td className="py-1.5 pr-2 text-slate-300">{r.entry_price != null ? `$${Number(r.entry_price).toFixed(2)}` : "—"}</td>
                  <td className="py-1.5 pr-2 text-slate-300">{r.target_1 != null ? `$${Number(r.target_1).toFixed(2)}` : "—"}</td>
                  <td className="py-1.5 pr-2 text-slate-300">{r.hard_stop != null ? `$${Number(r.hard_stop).toFixed(2)}` : "—"}</td>
                  <td className="py-1.5 pr-2">
                    {r.outcome ? (
                      <span className={clsx(
                        "px-2 py-0.5 rounded text-xs font-medium",
                        r.outcome === "HIT" && "bg-emerald-500/15 text-emerald-300",
                        r.outcome === "MISS" && "bg-red-500/15 text-red-300",
                      )}>
                        {r.outcome}
                      </span>
                    ) : (
                      <span className="text-slate-600">pending</span>
                    )}
                  </td>
                  <td className={clsx("py-1.5 pr-2", (Number(r.return_pct) || 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                    {r.return_pct != null ? fmtPct(Number(r.return_pct)) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-xs text-slate-500">No paper trades logged yet (load dashboard once per day to start logging).</p>
      )}
    </div>
  );
}

