"use client";

import { Info } from "lucide-react";

export type DataFreshness = {
  as_of_utc: string;
  prices?: string;
  fundamentals?: string;
  macro?: string;
  disclaimer?: string;
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
          <span className="font-mono text-slate-300">{data.as_of_utc}</span>
          <span className="text-slate-600"> (UTC)</span>
        </p>
        <p className="text-slate-500 leading-snug">
          {data.fundamentals && <span>{data.fundamentals} </span>}
          {data.disclaimer && <span className="text-slate-600">— {data.disclaimer}</span>}
        </p>
      </div>
    </div>
  );
}
