"use client";

import { useEffect, useState } from "react";
import { Building2, TrendingDown, TrendingUp, AlertCircle } from "lucide-react";
import { clsx } from "clsx";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

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
  institutional_trend?: {
    trend?: string;
    pct_institutions_increasing?: number;
    total_institutions?: number;
    error?: string | null;
  };
}

interface Props {
  ticker: string;
}

function trendColor(trend: string | undefined): string {
  if (trend === "ACCUMULATING") return "text-emerald-400";
  if (trend === "DISTRIBUTING") return "text-red-400";
  return "text-slate-400";
}

export function InstitutionalInsightsPanel({ ticker, silentOnError = true }: Props & { silentOnError?: boolean }) {
  const [data, setData] = useState<InstitutionalBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const sym = ticker.toUpperCase();
    const url = API_BASE ? `${API_BASE}/api/insights/${sym}` : `/api/insights/${sym}`;
    fetch(url)
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
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (loading) {
    if (silentOnError) return null;
    return (
      <div className="rounded-lg border border-slate-600/80 bg-slate-800/30 px-3 py-2 text-xs text-slate-500">
        Loading holder & positioning proxies…
      </div>
    );
  }

  if (error) {
    if (silentOnError) return null;
    return (
      <div className="rounded-lg border border-slate-600/80 bg-slate-800/30 px-3 py-2 text-xs text-slate-500 flex items-center gap-2">
        <AlertCircle className="h-3.5 w-3.5 shrink-0" />
        Positioning data unavailable — insider/13F feeds need FMP Starter+ (holders need Ultimate tier).
      </div>
    );
  }

  if (!data) return null;

  const iw = data.insider_weighted;
  const si = data.short_interest;
  const it = data.institutional_trend;

  return (
    <div className="rounded-lg border border-slate-600/80 bg-slate-800/30 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Building2 className="h-4 w-4 text-slate-400 shrink-0" />
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Positioning proxies
        </p>
        <span className="text-[10px] text-slate-600">FMP + FINRA/Yahoo · not live flow</span>
      </div>

      <div className="grid gap-2 sm:grid-cols-3 text-xs">
        <div className="rounded-md border border-slate-700/60 bg-slate-900/40 px-2.5 py-2">
          <p className="text-[10px] uppercase text-slate-500 mb-0.5">Insider (FMP list)</p>
          {iw?.error ? (
            <p className="text-slate-500">{iw.error}</p>
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
          <p className="text-[10px] uppercase text-slate-500 mb-0.5">Institutional holders</p>
          {it?.trend && it.trend !== "UNKNOWN" ? (
            <>
              <p className={clsx("font-medium", trendColor(it.trend))}>{it.trend}</p>
              {it.pct_institutions_increasing != null && (
                <p className="text-slate-500 text-[10px]">
                  {(it.pct_institutions_increasing * 100).toFixed(0)}% increasing · n={it.total_institutions}
                </p>
              )}
            </>
          ) : (
            <p className="text-slate-500 text-[10px] leading-snug">
              {it?.error || "Needs FMP holder feed (may require higher tier). Form 4 insider still in confidence layer."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
