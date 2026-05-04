"use client";

import { Info } from "lucide-react";

export type DataFreshness = {
  as_of_utc: string;
  as_of_et?: string;
  prices?: string;
  fundamentals?: string;
  macro?: string;
  disclaimer?: string;
  /** Latest daily bar date across scanned tickers (YYYY-MM-DD) */
  price_last_bar_date?: string | null;
  /** Date string from most recent EOD snapshot row, if any */
  eod_snapshot_latest_date?: string | null;
  /** Short copy: targets/stops are ranges, not guaranteed prices */
  precision_note?: string | null;
};

/** As-of + data limitations — single trust strip for retail. */
export function DataFreshnessBar({ data }: { data: DataFreshness }) {
  return (
    <div
      className="rounded-lg border border-slate-600/80 bg-slate-800/40 px-3 py-2.5 text-xs text-slate-400 flex flex-wrap items-start gap-2"
      title={[data.prices, data.fundamentals, data.macro].filter(Boolean).join(" ")}
    >
      <Info className="h-4 w-4 text-slate-500 shrink-0 mt-0.5" aria-hidden />
      <div className="min-w-0 space-y-1">
        <p>
          <span className="text-slate-400 font-medium">As of:</span>{" "}
          <span className="font-mono text-slate-300">{data.as_of_et ?? data.as_of_utc}</span>
          <span className="text-slate-600"> (EST)</span>
        </p>
        {(data.price_last_bar_date || data.eod_snapshot_latest_date) && (
          <p className="text-slate-500 leading-snug">
            {data.price_last_bar_date && (
              <span>
                Last price bar: <span className="font-mono text-slate-400">{data.price_last_bar_date}</span>
              </span>
            )}
            {data.price_last_bar_date && data.eod_snapshot_latest_date && <span className="text-slate-600"> · </span>}
            {data.eod_snapshot_latest_date && (
              <span>
                EOD snapshot: <span className="font-mono text-slate-400">{data.eod_snapshot_latest_date}</span>
              </span>
            )}
          </p>
        )}
        <p className="text-slate-500 leading-snug">
          {data.fundamentals && <span>{data.fundamentals} </span>}
          {data.disclaimer && <span className="text-slate-600">— {data.disclaimer}</span>}
        </p>
        {data.precision_note && (
          <p className="text-slate-600 leading-snug">{data.precision_note}</p>
        )}
      </div>
    </div>
  );
}
