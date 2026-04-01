"use client";

import { clsx } from "clsx";
import type { DashboardData } from "@/app/page";

function fmtPct(p: number | null | undefined) {
  if (p == null) return "—";
  const sign = p >= 0 ? "+" : "";
  return `${sign}${p.toFixed(2)}%`;
}

type MtmPoint = { mtm_date: string; mtm_return_pct: number | null; mtm_price: number | null };

function formatPnlHistory(history: MtmPoint[] | undefined, maxPoints = 6): { short: string; tooltip: string } {
  if (!history?.length) return { short: "—", tooltip: "" };
  const lines = history.map((h) => `${h.mtm_date}: ${h.mtm_return_pct != null ? fmtPct(h.mtm_return_pct) : "—"}`);
  const short = history
    .slice(-maxPoints)
    .map((h) => (h.mtm_return_pct != null ? fmtPct(h.mtm_return_pct) : "—"))
    .join(" → ");
  return { short, tooltip: lines.join("\n") };
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
            Entry = live quote when batch/Yahoo prices are available; otherwise last OHLCV bar (same as indicators).
            Outcomes use the first EOD snapshot on or after signal date + N <strong>business</strong> days.
            <strong> Return</strong> = vs signal entry; <strong>Last mark / daily Δ</strong> = vs prior EOD mark once history exists.
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
      {pt.mtm?.as_of && (
        <p className="text-xs text-slate-500">
          Mark-to-market updated as of {pt.mtm.as_of} (open trades only).
        </p>
      )}
      {pt.persistence_note && (
        <p className="text-xs text-slate-500" title={pt.data_root ?? undefined}>
          {pt.persistence_note}
        </p>
      )}

      {recent.length > 0 ? (
        <div className="overflow-x-auto [-webkit-overflow-scrolling:touch]">
          <table className="w-full text-sm text-left border-collapse min-w-[760px]">
            <thead>
              <tr className="text-slate-500 border-b border-slate-600">
                <th className="py-1.5 pr-2 font-medium">Date</th>
                <th className="py-1.5 pr-2 font-medium">Ticker</th>
                <th className="py-1.5 pr-2 font-medium">Signal</th>
                <th
                  className="py-1.5 pr-2 font-medium"
                  title="Live batch/Yahoo when set by dashboard; else OHLCV last close"
                >
                  Entry
                </th>
                <th className="py-1.5 pr-2 font-medium">Target</th>
                <th className="py-1.5 pr-2 font-medium">Stop</th>
                <th className="py-1.5 pr-2 font-medium">Outcome</th>
                <th className="py-1.5 pr-2 font-medium">Return</th>
                <th className="py-1.5 pr-2 font-medium" title="Latest EOD close used as mark (stored in rolling_entry_price)">
                  Last mark
                </th>
                <th className="py-1.5 pr-2 font-medium" title="Dollar change vs previous mark only (empty on first MTM)">
                  Daily Δ$
                </th>
                <th className="py-1.5 pr-2 font-medium" title="Percent change vs previous mark only (empty on first MTM)">
                  Daily Δ%
                </th>
                <th className="py-1.5 pr-2 font-medium">P&L history</th>
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
                  {(() => {
                    const isFinal = !!r.outcome && r.return_pct != null;
                    const val = isFinal ? Number(r.return_pct) : (r.mtm_return_pct != null ? Number(r.mtm_return_pct) : null);
                    return (
                      <td className={clsx("py-1.5 pr-2", (val || 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {val != null ? fmtPct(val) : "—"}
                      </td>
                    );
                  })()}
                  <td className="py-1.5 pr-2 text-slate-300" title={r.entry_price != null && r.rolling_entry_price != null ? `Signal entry $${Number(r.entry_price).toFixed(2)} → latest mark $${Number(r.rolling_entry_price).toFixed(2)} (total ${fmtPct(100 * (Number(r.rolling_entry_price) - r.entry_price) / r.entry_price)} vs entry)` : undefined}>
                    {r.rolling_entry_price != null ? `$${Number(r.rolling_entry_price).toFixed(2)}` : "—"}
                  </td>
                  <td className={clsx("py-1.5 pr-2", (Number(r.rolling_pnl) || 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                    {r.rolling_pnl != null ? `$${Number(r.rolling_pnl).toFixed(2)}` : "—"}
                  </td>
                  <td className={clsx("py-1.5 pr-2", (Number(r.rolling_return_pct) || 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                    {r.rolling_return_pct != null ? fmtPct(Number(r.rolling_return_pct)) : "—"}
                  </td>
                  <td className="py-1.5 pr-2 text-slate-400 max-w-[200px]">
                    {(() => {
                      const tid = r.trade_id || "";
                      const history = tid ? pt.mtm_history?.[tid] : undefined;
                      const { short, tooltip } = formatPnlHistory(history);
                      if (!short || short === "—") return "—";
                      return (
                        <span
                          className="cursor-help border-b border-dotted border-slate-500"
                          title={tooltip || undefined}
                        >
                          {short}
                        </span>
                      );
                    })()}
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

