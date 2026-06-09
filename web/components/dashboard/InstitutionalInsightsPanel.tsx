"use client";

import { useEffect, useState } from "react";
import { Building2, TrendingDown, TrendingUp, AlertCircle } from "lucide-react";
import { clsx } from "clsx";
import { apiUrl } from "@/lib/apiBase";

export interface InstitutionalOwnership {
  institutional_pct?: number | null;
  institutional_pct_label?: string | null;
  source?: string;
  source_note?: string;
  as_of?: string | null;
  major_holders?: {
    insiders_pct?: number | null;
    institutions_pct?: number | null;
    institutions_float_pct?: number | null;
    institutions_count?: number | null;
  };
  top_holders?: Array<{
    holder?: string;
    shares?: number;
    pct_held?: number;
    pct_change_qoq?: number;
    value_usd?: number;
  }>;
  error?: string | null;
}

export interface Edgar13fSnapshot {
  trend?: string;
  period_ending?: string | null;
  prior_period_ending?: string | null;
  pct_filings_increasing?: number | null;
  filers_sampled?: number;
  filers_comparable?: number;
  filings_analyzed?: number;
  cusip?: string | null;
  source_note?: string;
  timed_out?: boolean;
  top_holder_changes?: Array<{
    filer?: string;
    shares?: number;
    prior_shares?: number | null;
    change_pct?: number | null;
    period_ending?: string;
  }>;
  error?: string | null;
}

export interface InstitutionalBundle {
  ticker?: string;
  insider_weighted?: {
    signal?: number;
    buy_score?: number;
    sell_score?: number;
    n?: number;
    error?: string | null;
  };
  short_interest?: {
    short_float_pct?: number | null;
    signal?: string;
    source?: string;
    days_to_cover?: number | null;
    trend?: string;
    error?: string | null;
  };
  institutional_ownership?: InstitutionalOwnership;
  institutional_trend?: {
    trend?: string;
    pct_institutions_increasing?: number;
    total_institutions?: number;
    source?: string | null;
    as_of?: string | null;
    period_ending?: string | null;
    error?: string | null;
  };
  edgar_13f?: Edgar13fSnapshot;
}

interface Props {
  ticker: string;
  /** Only fetch when tab is visible — avoids blocking ticker modal on open. */
  enabled?: boolean;
}

function trendColor(trend: string | undefined): string {
  if (trend === "ACCUMULATING") return "text-emerald-400";
  if (trend === "DISTRIBUTING") return "text-red-400";
  return "text-slate-400";
}

function sourceLabel(source: string | undefined): string {
  if (source === "yfinance_delayed") return "Yahoo · delayed";
  if (source === "sec_edgar_13f") return "SEC 13F · quarterly";
  if (source === "fmp") return "FMP";
  return source ?? "—";
}

const INSIGHTS_TIMEOUT_MS = 90000;

export function InstitutionalInsightsPanel({
  ticker,
  enabled = true,
  silentOnError = true,
}: Props & { silentOnError?: boolean }) {
  const [data, setData] = useState<InstitutionalBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !ticker) {
      return;
    }
    let cancelled = false;
    const ac = new AbortController();
    const timer = window.setTimeout(() => ac.abort(), INSIGHTS_TIMEOUT_MS);

    setLoading(true);
    setError(null);
    setData(null);

    const sym = ticker.toUpperCase();
    fetch(apiUrl(`/api/insights/${sym}`), { signal: ac.signal, cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => {
        if (cancelled) return;
        if (j?.disabled) {
          setError(j.message || "Insights disabled");
          setData(null);
          return;
        }
        setData((j?.institutional as InstitutionalBundle) || null);
      })
      .catch((e) => {
        if (cancelled || (e instanceof DOMException && e.name === "AbortError")) {
          if (!cancelled) setError("Institutional data timed out — Yahoo % may still load on retry.");
          return;
        }
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      })
      .finally(() => {
        window.clearTimeout(timer);
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      ac.abort();
      window.clearTimeout(timer);
    };
  }, [ticker, enabled]);

  if (!enabled) return null;

  if (loading) {
    if (silentOnError) return null;
    return (
      <div className="rounded-lg border border-slate-600/80 bg-slate-800/30 px-3 py-2 text-xs text-slate-500">
        Loading institutional ownership & positioning… (first load may take up to 60s)
      </div>
    );
  }

  if (error) {
    if (silentOnError) return null;
    return (
      <div className="rounded-lg border border-slate-600/80 bg-slate-800/30 px-3 py-2 text-xs text-slate-500 flex items-center gap-2">
        <AlertCircle className="h-3.5 w-3.5 shrink-0" />
        Positioning data unavailable — {error}
      </div>
    );
  }

  if (!data) return null;

  const iw = data.insider_weighted;
  const si = data.short_interest;
  const io = data.institutional_ownership;
  const it = data.institutional_trend;
  const e13 = data.edgar_13f;
  const instPct = io?.institutional_pct;

  return (
    <div className="rounded-lg border border-slate-600/80 bg-slate-800/30 p-3 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <Building2 className="h-4 w-4 text-slate-400 shrink-0" />
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Institutional positioning
        </p>
        <span className="text-[10px] text-slate-600">Yahoo 13F-derived + SEC EDGAR · not live flow</span>
      </div>

      <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 px-3 py-2.5">
        <p className="text-[10px] uppercase text-slate-500 mb-0.5">Institutional % (Yahoo, delayed)</p>
        {instPct != null ? (
          <>
            <p className="text-lg font-semibold text-emerald-300 font-mono">{instPct.toFixed(1)}%</p>
            <p className="text-[10px] text-slate-500 leading-snug mt-0.5">
              {io?.source_note ?? "Aggregated from quarterly 13F filings via Yahoo Finance"}
              {io?.as_of ? ` · as of ${io.as_of}` : ""}
              {io?.major_holders?.institutions_count != null
                ? ` · ${Math.round(io.major_holders.institutions_count).toLocaleString()} institutions`
                : ""}
            </p>
          </>
        ) : (
          <p className="text-slate-500 text-xs">{io?.error || "Institutional % unavailable"}</p>
        )}
      </div>

      <div className="grid gap-2 sm:grid-cols-3 text-xs">
        <div className="rounded-md border border-slate-700/60 bg-slate-900/40 px-2.5 py-2">
          <p className="text-[10px] uppercase text-slate-500 mb-0.5">Insider (FMP list)</p>
          {iw?.error ? (
            <p className="text-slate-500 text-[10px] leading-snug">No FMP list — Form 4 insider still in confidence layer.</p>
          ) : (
            <p className="text-slate-200 flex items-center gap-1">
              {(iw?.signal ?? 0) >= 0 ? (
                <TrendingUp className="h-3 w-3 text-emerald-400" />
              ) : (
                <TrendingDown className="h-3 w-3 text-red-400" />
              )}
              Net {iw?.signal != null ? `${iw.signal > 0 ? "+" : ""}${iw.signal}` : "—"}
              {iw?.n ? ` · ${iw.n} tx` : ""}
            </p>
          )}
        </div>

        <div className="rounded-md border border-slate-700/60 bg-slate-900/40 px-2.5 py-2">
          <p className="text-[10px] uppercase text-slate-500 mb-0.5">Short interest</p>
          {si?.short_float_pct != null ? (
            <>
              <p className="text-slate-200 font-mono">{si.short_float_pct.toFixed(1)}% float</p>
              <p className="text-slate-500 text-[10px] leading-snug">{si.signal}</p>
              {si.days_to_cover != null && (
                <p className="text-slate-600 text-[10px]">DTC {si.days_to_cover.toFixed(1)}d · {si.source}</p>
              )}
            </>
          ) : (
            <p className="text-slate-500">{si?.error || "No data"}</p>
          )}
        </div>

        <div className="rounded-md border border-slate-700/60 bg-slate-900/40 px-2.5 py-2">
          <p className="text-[10px] uppercase text-slate-500 mb-0.5">Holder trend</p>
          {it?.trend && it.trend !== "UNKNOWN" ? (
            <>
              <p className={clsx("font-medium", trendColor(it.trend))}>{it.trend}</p>
              {it.pct_institutions_increasing != null && (
                <p className="text-slate-500 text-[10px]">
                  {(it.pct_institutions_increasing * 100).toFixed(0)}% increasing · n={it.total_institutions}
                  {" · "}
                  {sourceLabel(it.source ?? undefined)}
                </p>
              )}
            </>
          ) : (
            <p className="text-slate-500 text-[10px] leading-snug">
              {it?.error || "Trend unavailable — check top holders below."}
            </p>
          )}
        </div>
      </div>

      {(io?.top_holders?.length ?? 0) > 0 && (
        <div className="rounded-md border border-slate-700/60 bg-slate-900/40 px-2.5 py-2">
          <p className="text-[10px] uppercase text-slate-500 mb-1.5">Top institutional holders (Yahoo)</p>
          <ul className="space-y-1">
            {io!.top_holders!.slice(0, 5).map((h, i) => (
              <li key={`${h.holder}-${i}`} className="flex items-center justify-between gap-2 text-[11px]">
                <span className="text-slate-300 truncate">{h.holder}</span>
                <span className="text-slate-500 shrink-0 font-mono">
                  {h.pct_held != null ? `${h.pct_held.toFixed(1)}%` : "—"}
                  {h.pct_change_qoq != null && (
                    <span className={clsx("ml-1", h.pct_change_qoq >= 0 ? "text-emerald-400" : "text-red-400")}>
                      ({h.pct_change_qoq >= 0 ? "+" : ""}
                      {h.pct_change_qoq.toFixed(1)}% q/q)
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {e13 && !e13.error && (e13.top_holder_changes?.length ?? 0) > 0 && (
        <div className="rounded-md border border-slate-700/60 bg-slate-900/40 px-2.5 py-2">
          <p className="text-[10px] uppercase text-slate-500 mb-0.5">SEC 13F holder changes (sample)</p>
          <p className="text-[10px] text-slate-600 mb-1.5">
            {e13.source_note}
            {e13.period_ending ? ` · Q ending ${e13.period_ending}` : ""}
            {e13.filings_analyzed ? ` · ${e13.filings_analyzed} filings parsed` : ""}
          </p>
          <ul className="space-y-1">
            {e13.top_holder_changes!.slice(0, 4).map((r, i) => (
              <li key={`${r.filer}-${i}`} className="flex justify-between gap-2 text-[11px]">
                <span className="text-slate-400 truncate">{r.filer}</span>
                <span
                  className={clsx(
                    "font-mono shrink-0",
                    (r.change_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400",
                  )}
                >
                  {r.change_pct != null ? `${r.change_pct >= 0 ? "+" : ""}${r.change_pct.toFixed(1)}%` : "—"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {e13?.timed_out && (
        <p className="text-[10px] text-amber-400/90">
          SEC 13F sample timed out — institutional % and Yahoo holder trend above are still valid.
        </p>
      )}
    </div>
  );
}
