"use client";

import { useEffect, useState } from "react";
import { History } from "lucide-react";
import { apiUrl } from "@/lib/apiBase";
import { fmtPct } from "./ReferenceDetailGrid";

const TRACK_RECORD_TIMEOUT_MS = 15000;

interface TrackRecordHorizonStats {
  n_observations?: number;
  win_rate_pct?: number;
  avg_return_pct?: number;
}

interface TrackRecordResponse {
  available: boolean;
  ticker?: string;
  current_model_version?: string | null;
  current?: TrackRecordHorizonStats | null;
  legacy?: TrackRecordHorizonStats | null;
  by_horizon?: Record<string, { current?: TrackRecordHorizonStats | null; legacy?: TrackRecordHorizonStats | null }> | null;
  daily_trades?: DailyTradeRow[] | null;
}

interface DailyTradeRow {
  date: string | null;
  signal: string | null;
  model_price: number | null;
  fill_price: number | null;
  target: number | null;
  stop: number | null;
  outcome_price: number | null;
  outcome: string | null;
  win: boolean | null;
  status: "resolved" | "pending";
  return_pct: number | null;
  unrealized_return_pct: number | null;
  model_version?: string | null;
  volatile_note?: string | null;
  track?: string | null;
}

function fmtPrice(n: number | null | undefined): string {
  return n == null || !Number.isFinite(n) ? "—" : `$${n.toFixed(2)}`;
}

/** Shortest horizon with at least one resolved "current"-version observation — lets a
 * just-launched model_version show an early (noisier) read instead of only "not enough
 * data yet" for the weeks it takes a 20d pair to resolve. */
function earliestAvailableHorizon(
  byHorizon: TrackRecordResponse["by_horizon"],
): { horizon: number; stats: TrackRecordHorizonStats } | null {
  if (!byHorizon) return null;
  const horizons = Object.keys(byHorizon).map(Number).filter((h) => !Number.isNaN(h)).sort((a, b) => a - b);
  for (const h of horizons) {
    const stats = byHorizon[String(h)]?.current;
    if (stats && (stats.n_observations ?? 0) > 0) {
      return { horizon: h, stats };
    }
  }
  return null;
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
  const [data, setData] = useState<TrackRecordResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [showLegacyRows, setShowLegacyRows] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    setData(null);
    setLoading(true);
    const ac = new AbortController();
    const timer = window.setTimeout(() => ac.abort(), TRACK_RECORD_TIMEOUT_MS);
    fetch(apiUrl(`/api/ticker/${ticker}/track-record`), { signal: ac.signal, cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (j) setData(j as TrackRecordResponse);
      })
      .catch(() => {
        /* quietly stay empty */
      })
      .finally(() => {
        window.clearTimeout(timer);
        setLoading(false);
      });
    return () => {
      ac.abort();
      window.clearTimeout(timer);
    };
  }, [ticker]);

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
                        {t.status === "resolved" ? fmtPrice(t.outcome_price) : "—"}
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
