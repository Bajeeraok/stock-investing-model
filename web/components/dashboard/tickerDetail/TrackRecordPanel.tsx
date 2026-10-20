"use client";

import { useState } from "react";
import { History } from "lucide-react";
import { earliestAvailableHorizon, useTickerTrackRecord } from "@/lib/useTickerTrackRecord";
import { fmtPct } from "./ReferenceDetailGrid";

function fmtPrice(n: number | null | undefined): string {
  return n == null || !Number.isFinite(n) ? "—" : `$${n.toFixed(2)}`;
}

/**
 * Standalone "Track" tab — "has our own model been right on THIS ticker?" Reads a cheap,
 * already-cached watchlist-wide forward-tracking slice filtered server-side to one ticker
 * (see signals/forward_tracking_metrics.py::build_ticker_track_record). Own fetch-on-mount.
 * Previously the 8th of 10 cards buried in the Today tab's reference grid, squeezed into a
 * 1/3-width cell; promoted to its own full-width tab since the per-trade win/loss-vs-outcome
 * display bug here was confirmed live and fixed this session.
 */
export default function TrackRecordPanel({ ticker }: { ticker: string }) {
  const { data, loading } = useTickerTrackRecord(ticker);
  const [showLegacyRows, setShowLegacyRows] = useState(false);

  const current = data?.current;
  const legacy = data?.legacy;
  const version = data?.current_model_version;
  const earlyRead = !current || (current.n_observations ?? 0) === 0 ? earliestAvailableHorizon(data?.by_horizon) : null;

  if (loading && !data) {
    return <p className="text-sm text-slate-500">Loading signal track record…</p>;
  }
  if ((data && !data.available) || (!loading && !current && !legacy && !earlyRead)) {
    return <p className="text-sm text-slate-500">No forward-tracking history available for {ticker} yet.</p>;
  }

  const dailyCalls = data?.daily_calls ?? [];
  const scored = dailyCalls.filter((c) => c.right != null);
  const rightN = scored.filter((c) => c.right).length;
  const allTrades = data?.daily_trades ?? [];
  const currentTrades = version ? allTrades.filter((t) => t.model_version === version) : allTrades;
  const legacyTrades = version ? allTrades.filter((t) => t.model_version !== version) : [];
  const shownTrades = showLegacyRows ? allTrades : currentTrades;

  return (
    <section className="max-w-3xl space-y-3">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-slate-100">
        <History className="h-4 w-4 text-emerald-400 shrink-0" aria-hidden />
        Signal track record
      </h3>
      <p className="text-xs text-slate-500 leading-relaxed">
        What we said vs. what happened, for this ticker specifically — from the same
        forward-tracking data behind the Analysis tab.
      </p>

      {current && (current.n_observations ?? 0) > 0 ? (
        <p className="text-sm text-slate-300 leading-relaxed">
          Since <span className="font-mono text-slate-200">{version}</span>: right{" "}
          <span className={(current.win_rate_pct ?? 0) >= 50 ? "text-emerald-400" : "text-amber-300"}>
            {current.win_rate_pct != null ? `${current.win_rate_pct.toFixed(0)}%` : "—"}
          </span>{" "}
          of the time <span className="text-slate-600">(n={current.n_observations})</span>
          {current.avg_return_pct != null && (
            <>
              {" · avg return "}
              <span className={current.avg_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                {fmtPct(current.avg_return_pct)}
              </span>
            </>
          )}
          .
        </p>
      ) : earlyRead ? (
        <p className="text-sm text-slate-400 leading-relaxed">
          Too early for a 20d read on {ticker} under <span className="font-mono text-slate-300">{version}</span> —
          early {earlyRead.horizon}d look: right{" "}
          <span className={(earlyRead.stats.win_rate_pct ?? 0) >= 50 ? "text-emerald-400" : "text-amber-300"}>
            {earlyRead.stats.win_rate_pct != null ? `${earlyRead.stats.win_rate_pct.toFixed(0)}%` : "—"}
          </span>{" "}
          <span className="text-slate-600">(n={earlyRead.stats.n_observations}, small sample — noisy)</span>.
        </p>
      ) : (
        <p className="text-sm text-slate-500 leading-relaxed">
          Not enough resolved signals on {ticker} yet under {version || "the current model"} —
          this fills in as new EOD snapshots accumulate.
        </p>
      )}

      {dailyCalls.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-xs font-semibold text-slate-300">
              Daily calls — scored every session
              {scored.length > 0 && (
                <span className="ml-2 font-normal text-slate-500">
                  {rightN}/{scored.length} right on ADD/TRIM calls
                </span>
              )}
            </p>
            {data?.eod_date_last && (
              <span className="text-[11px] text-slate-600">through {data.eod_date_last}</span>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[520px]">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-700">
                  <th className="py-1 pr-2 font-medium">Date</th>
                  <th className="py-1 pr-2 font-medium">Call</th>
                  <th className="py-1 pr-2 font-medium">Gates</th>
                  <th className="py-1 pr-2 font-medium">Close</th>
                  <th className="py-1 pr-2 font-medium">Next close</th>
                  <th className="py-1 pr-2 font-medium">Next day</th>
                  <th className="py-1 font-medium">Right?</th>
                </tr>
              </thead>
              <tbody>
                {dailyCalls.slice(0, 15).map((c) => (
                  <tr key={`${c.date}-${c.next_date}`} className="border-b border-slate-800 text-slate-300">
                    <td className="py-1 pr-2 font-mono">{c.date}</td>
                    <td className="py-1 pr-2">{c.signal ?? "—"}</td>
                    <td className="py-1 pr-2 font-mono text-slate-500">
                      {c.gates_passed != null ? `${c.gates_passed}/${c.gates_total ?? 4}` : "—"}
                    </td>
                    <td className="py-1 pr-2 font-mono">{fmtPrice(c.close)}</td>
                    <td className="py-1 pr-2 font-mono">{c.status === "pending" ? "pending" : fmtPrice(c.next_close)}</td>
                    <td
                      className={
                        c.return_pct == null
                          ? "py-1 pr-2 font-mono text-slate-500"
                          : c.return_pct >= 0
                            ? "py-1 pr-2 font-mono text-emerald-400"
                            : "py-1 pr-2 font-mono text-red-400"
                      }
                    >
                      {c.return_pct == null ? "—" : fmtPct(c.return_pct)}
                    </td>
                    <td className="py-1">
                      {c.right == null ? (
                        <span className="text-slate-600" title="HOLD calls aren't scored for direction">—</span>
                      ) : c.right ? (
                        <span className="text-emerald-400">✓</span>
                      ) : (
                        <span className="text-red-400">✗</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-slate-600 leading-snug">
            Every EOD snapshot, the model&apos;s call vs the next session&apos;s close — no waiting for a 5d/20d
            window. ADD counts as right if the next close is higher, TRIM if lower; HOLD isn&apos;t scored.
          </p>
        </div>
      )}

      {legacy && (legacy.n_observations ?? 0) > 0 && (
        <p className="text-xs text-slate-600 leading-relaxed">
          Pre-{version || "current"} history: {legacy.win_rate_pct != null ? `${legacy.win_rate_pct.toFixed(0)}%` : "—"}{" "}
          (n={legacy.n_observations}) — kept separate, not blended into the number above.
        </p>
      )}

      {allTrades.length > 0 && (
        <div>
          <div className="flex items-baseline justify-between gap-2 mb-1">
            <p className="text-xs text-slate-500">
              Per-trade detail (most recent first){version && !showLegacyRows ? ` — ${version} only` : ""}
            </p>
            {legacyTrades.length > 0 && (
              <button
                type="button"
                onClick={() => setShowLegacyRows((s) => !s)}
                className="text-xs text-slate-500 hover:text-slate-300 shrink-0"
              >
                {showLegacyRows ? "Hide" : `Show ${legacyTrades.length} legacy`} ›
              </button>
            )}
          </div>
          {shownTrades.length === 0 ? (
            <p className="text-xs text-slate-600">No trades logged under {version} for this ticker yet.</p>
          ) : (
            <>
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-700/70">
                    <th className="pr-3 py-1.5 font-medium">Date</th>
                    <th className="pr-3 py-1.5 font-medium">Signal</th>
                    <th className="pr-3 py-1.5 font-medium">Model px</th>
                    <th className="pr-3 py-1.5 font-medium">Fill px</th>
                    <th className="pr-3 py-1.5 font-medium">Target / Stop</th>
                    <th className="pr-3 py-1.5 font-medium">Outcome px</th>
                    <th className="pr-3 py-1.5 font-medium">P&amp;L</th>
                    <th className="py-1.5 font-medium">Result</th>
                    <th className="pl-3 py-1.5 font-medium">Ver.</th>
                  </tr>
                </thead>
                <tbody>
                  {shownTrades.map((t, i) => (
                    <tr key={`${t.date}-${i}`} className="border-t border-slate-800/70 text-slate-300">
                      <td className="pr-3 py-1.5 text-slate-400 whitespace-nowrap">{t.date ?? "—"}</td>
                      <td className="pr-3 py-1.5 whitespace-nowrap">{t.signal ?? "—"}</td>
                      <td className="pr-3 py-1.5 font-mono tabular-nums">{fmtPrice(t.model_price)}</td>
                      <td className="pr-3 py-1.5 font-mono tabular-nums">{fmtPrice(t.fill_price)}</td>
                      <td className="pr-3 py-1.5 font-mono tabular-nums text-slate-500 whitespace-nowrap">
                        {fmtPrice(t.target)} / {fmtPrice(t.stop)}
                      </td>
                      <td className="pr-3 py-1.5 font-mono tabular-nums">
                        {t.status === "resolved" ? (
                          fmtPrice(t.outcome_price)
                        ) : t.outcome_price != null ? (
                          <span title={t.mark_date ? `Latest marked close (${t.mark_date}) — final outcome prints at the horizon` : "Latest marked close — final outcome prints at the horizon"}>
                            {fmtPrice(t.outcome_price)} <span className="text-slate-600">(mark)</span>
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="pr-3 py-1.5 font-mono tabular-nums">
                        {t.status === "resolved" ? (
                          <span className={(t.return_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}>
                            {fmtPct(t.return_pct)}
                          </span>
                        ) : t.unrealized_return_pct != null ? (
                          <span className={t.unrealized_return_pct >= 0 ? "text-emerald-400/70" : "text-amber-300/70"}>
                            {fmtPct(t.unrealized_return_pct)} <span className="text-slate-600">(open)</span>
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-1.5 whitespace-nowrap" title={t.volatile_note ?? undefined}>
                        {t.status === "pending" ? (
                          <span className="text-slate-500">pending</span>
                        ) : t.win ? (
                          <span className="text-emerald-400">
                            WIN{t.volatile_note && <span className="text-amber-400/80"> *</span>}
                          </span>
                        ) : (
                          <span className="text-red-400">{t.outcome === "STOP_HIT" ? "STOP" : "LOSS"}</span>
                        )}
                      </td>
                      <td className="pl-3 py-1.5 text-slate-600 whitespace-nowrap">
                        {t.track === "velocity" ? (
                          <span className="text-amber-400/80" title="Velocity track — tactical T+N rules, not the accumulate win criterion">vel</span>
                        ) : (
                          t.model_version ?? "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-[11px] text-slate-600 mt-1.5">
                * stop also touched intraday that day, but the close still cleared target — counted as a win, same rule the headline win rate uses.
                {allTrades.some((t) => t.track === "velocity") && " \"vel\" = velocity track (T+N rules), kept separate from accumulate's win criterion."}
              </p>
            </>
          )}
        </div>
      )}
    </section>
  );
}
