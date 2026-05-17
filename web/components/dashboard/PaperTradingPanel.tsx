"use client";

import { useState, useMemo } from "react";
import { clsx } from "clsx";
import type { DashboardData } from "@/app/page";

function fmtPct(p: number | null | undefined) {
  if (p == null) return "—";
  const sign = p >= 0 ? "+" : "";
  return `${sign}${p.toFixed(2)}%`;
}

/** CSV / JSON may use "" for missing numbers; Number("") is 0 — treat as absent for display. */
function hasNumericValue(v: unknown): boolean {
  if (v == null) return false;
  if (typeof v === "string" && v.trim() === "") return false;
  return !Number.isNaN(Number(v));
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

type DateRange = "1W" | "1M" | "3M" | "ALL";
const DATE_RANGES: { label: string; value: DateRange }[] = [
  { label: "1 W", value: "1W" },
  { label: "1 M", value: "1M" },
  { label: "3 M", value: "3M" },
  { label: "All", value: "ALL" },
];

function cutoffDate(range: DateRange): string | null {
  if (range === "ALL") return null;
  const d = new Date();
  if (range === "1W") d.setDate(d.getDate() - 7);
  else if (range === "1M") d.setMonth(d.getMonth() - 1);
  else if (range === "3M") d.setMonth(d.getMonth() - 3);
  return d.toISOString().slice(0, 10);
}

export function PaperTradingPanel({ data }: { data: DashboardData }) {
  const pt = data.paper_trading;
  if (!pt) return null;

  const summary = pt.summary ?? null;
  const allRecent = pt.recent ?? [];
  const [tickerFilter, setTickerFilter] = useState("");
  const [dateRange, setDateRange] = useState<DateRange>("ALL");

  const uniqueTickers = useMemo(
    () => Array.from(new Set(allRecent.map((r: any) => (r.ticker || "").toUpperCase()))).sort(),
    [allRecent],
  );

  const recent = useMemo(() => {
    const cutoff = cutoffDate(dateRange);
    const tf = tickerFilter.toUpperCase();
    return allRecent.filter((r: any) => {
      if (tf && (r.ticker || "").toUpperCase() !== tf) return false;
      if (cutoff && (r.date || "") < cutoff) return false;
      return true;
    });
  }, [allRecent, tickerFilter, dateRange]);

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-slate-300">Paper trading (signals → outcomes)</p>
          <p className="text-xs text-slate-500 mt-0.5">
            Entry = live quote when batch/Yahoo prices are available; otherwise last OHLCV bar (same as indicators).
            Outcomes use the first EOD snapshot on or after signal date + N <strong>business</strong> days.
            <strong> Return</strong> = vs signal entry; <strong>Last mark / daily Δ</strong> = change from <em>yesterday&apos;s</em> end-of-day mark to <em>today&apos;s</em> mark (shows &ldquo;—&rdquo; until two different EOD snapshots exist after you started logging).
            <strong> Bench %</strong> = same-window return for the benchmark (default SPY); <strong>Excess</strong> = your return minus bench (open uses MTM vs entry).
          </p>
        </div>
        {pt.log?.date && (
          <div className="text-xs text-slate-500">
            Logged {pt.log.appended}/{pt.log.seen} signals for {pt.log.date}
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={tickerFilter}
          onChange={(e) => setTickerFilter(e.target.value)}
          className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          <option value="">All tickers</option>
          {uniqueTickers.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <div className="flex rounded border border-slate-600 overflow-hidden">
          {DATE_RANGES.map((dr) => (
            <button
              key={dr.value}
              type="button"
              onClick={() => setDateRange(dr.value)}
              className={clsx(
                "px-2.5 py-1 text-xs font-medium transition-colors",
                dateRange === dr.value
                  ? "bg-emerald-600/70 text-white"
                  : "bg-slate-900 text-slate-400 hover:bg-slate-800",
              )}
            >
              {dr.label}
            </button>
          ))}
        </div>
        {(tickerFilter || dateRange !== "ALL") && (
          <span className="text-[10px] text-slate-500">
            Showing {recent.length} / {allRecent.length} trades
          </span>
        )}
      </div>

      {summary && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-300">
            <span className="text-slate-500">Status:</span>{" "}
            <span
              className={clsx(
                summary.status === "ok" ? "text-emerald-400" : summary.status === "preview" ? "text-sky-400" : "text-amber-300"
              )}
            >
              {summary.status}
            </span>
            {summary.completed != null && (
              <span title={summary.horizon_note ?? undefined}>
                <span className="text-slate-500">Completed:</span> {summary.completed}
                {summary.min_required != null ? ` / ${summary.min_required} for full` : ""}
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
            {summary.avg_excess_vs_spy_pct != null && (
              <span>
                <span className="text-slate-500">Avg excess vs {summary.benchmark_ticker ?? "SPY"}:</span>{" "}
                <span className={summary.avg_excess_vs_spy_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {fmtPct(summary.avg_excess_vs_spy_pct)}
                </span>
                {summary.n_benchmarked != null && (
                  <span className="text-slate-500"> ({summary.n_benchmarked} with bench)</span>
                )}
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
          {summary.buy_signals_summary && (
            <div className="rounded border border-slate-600/80 bg-slate-900/40 px-3 py-2 text-xs text-slate-400">
              <span className="font-medium text-slate-300">{summary.buy_signals_summary.label}</span>
              <span className="text-slate-500"> — n={summary.buy_signals_summary.completed_n}</span>
              {summary.buy_signals_summary.win_rate_pct != null && (
                <span className="ml-2">
                  Win {summary.buy_signals_summary.win_rate_pct.toFixed(1)}%
                </span>
              )}
              {summary.buy_signals_summary.avg_return_pct != null && (
                <span className="ml-2">Avg {fmtPct(summary.buy_signals_summary.avg_return_pct)}</span>
              )}
              {summary.buy_signals_summary.avg_excess_vs_spy_pct != null && (
                <span className="ml-2">
                  Excess vs {summary.benchmark_ticker ?? "SPY"} {fmtPct(summary.buy_signals_summary.avg_excess_vs_spy_pct)}
                </span>
              )}
            </div>
          )}
          {summary.horizon_note && (
            <p className="text-xs text-slate-600 leading-snug">{summary.horizon_note}</p>
          )}
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
          <table className="w-full text-sm text-left border-collapse min-w-[960px]">
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
                <th
                  className="py-1.5 pr-2 font-medium"
                  title="Benchmark total return over the same dates as this row (MTM window or completed horizon)"
                >
                  Bench %
                </th>
                <th className="py-1.5 pr-2 font-medium" title="Trade return minus benchmark (same window)">
                  Excess
                </th>
                <th className="py-1.5 pr-2 font-medium" title="Latest EOD close used as mark (stored in rolling_entry_price)">
                  Last mark
                </th>
                <th className="py-1.5 pr-2 font-medium" title="Day-over-day move of the mark: prior EOD close vs latest EOD close. Empty until a second trading day is captured.">
                  Daily Δ$
                </th>
                <th className="py-1.5 pr-2 font-medium" title="Day-over-day % move of the mark. Empty until a second trading day is captured.">
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
                      <span
                        className="text-slate-500 text-xs"
                        title={
                          r.effective_entry_source === "signal_entry_provisional"
                            ? "Provisional entry — marks use latest EOD; upgrades to next-session close when that snapshot exists. Final outcome after horizon (default 20 business days)."
                            : "Open — Return/Last mark from EOD; final HIT/MISS after horizon_trading_days (default 20 business days)."
                        }
                      >
                        {r.effective_entry_source === "signal_entry_provisional" ? "pending · prov." : "pending"}
                      </span>
                    )}
                  </td>
                  {(() => {
                    const isFinal = !!r.outcome && hasNumericValue(r.return_pct);
                    const val = isFinal ? Number(r.return_pct) : (hasNumericValue(r.mtm_return_pct) ? Number(r.mtm_return_pct) : null);
                    return (
                      <td className={clsx("py-1.5 pr-2", (val || 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {val != null ? fmtPct(val) : "—"}
                      </td>
                    );
                  })()}
                  <td className={clsx("py-1.5 pr-2", (Number(r.benchmark_return_pct) || 0) >= 0 ? "text-slate-400" : "text-slate-500")}>
                    {hasNumericValue(r.benchmark_return_pct) ? fmtPct(Number(r.benchmark_return_pct)) : "—"}
                  </td>
                  <td
                    className={clsx(
                      "py-1.5 pr-2",
                      r.excess_return_pct == null ? "text-slate-600" : Number(r.excess_return_pct) >= 0 ? "text-emerald-400" : "text-red-400"
                    )}
                  >
                    {r.excess_return_pct != null ? fmtPct(Number(r.excess_return_pct)) : "—"}
                  </td>
                  <td className="py-1.5 pr-2 text-slate-300" title={r.entry_price != null && r.rolling_entry_price != null ? `Signal entry $${Number(r.entry_price).toFixed(2)} → latest mark $${Number(r.rolling_entry_price).toFixed(2)} (total ${fmtPct(100 * (Number(r.rolling_entry_price) - r.entry_price) / r.entry_price)} vs entry)` : undefined}>
                    {r.rolling_entry_price != null ? `$${Number(r.rolling_entry_price).toFixed(2)}` : "—"}
                  </td>
                  <td className={clsx("py-1.5 pr-2", !hasNumericValue(r.rolling_pnl) ? "text-slate-500" : (Number(r.rolling_pnl) || 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                    {hasNumericValue(r.rolling_pnl) ? `$${Number(r.rolling_pnl).toFixed(2)}` : "—"}
                  </td>
                  <td className={clsx("py-1.5 pr-2", !hasNumericValue(r.rolling_return_pct) ? "text-slate-500" : (Number(r.rolling_return_pct) || 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                    {hasNumericValue(r.rolling_return_pct) ? fmtPct(Number(r.rolling_return_pct)) : "—"}
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

