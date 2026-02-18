"use client";

import { clsx } from "clsx";

export interface CrossAssetItem {
  ticker: string;
  label?: string;
  close?: number;
  pct_change: number | null;
  error?: string;
}

export function CrossAssetSection({ items }: { items: CrossAssetItem[] }) {
  if (!items?.length) return null;
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5 min-w-0">
      <h3 className="text-sm font-semibold text-slate-400 mb-3 flex items-center gap-2">
        <span className="text-amber-400">Cross-asset</span> (DXY, Gold, Oil, VIX) – daily % change
      </h3>
      <div className="flex flex-wrap gap-4">
        {items.map((c) => {
          const hasValue = !c.error && c.pct_change != null;
          return (
            <div
              key={c.ticker}
              className="flex items-center gap-3 px-4 py-2 rounded-lg bg-slate-800/50 border border-slate-700/50"
              title={
                c.label === "VIX" && c.close != null
                  ? `VIX ${c.close.toFixed(1)} – ${c.close >= 20 ? "Elevated (caution)" : "Normal"}`
                  : c.error
                    ? c.error
                    : undefined
              }
            >
              <span className="font-medium text-slate-300">{c.label ?? c.ticker}</span>
              {c.label === "VIX" && c.close != null && (
                <span className="text-slate-500 text-xs">({c.close.toFixed(1)})</span>
              )}
              <span
                className={clsx(
                  "font-bold",
                  hasValue
                    ? c.label === "VIX"
                      ? "text-amber-400"
                      : (c.pct_change ?? 0) >= 0
                        ? "text-emerald-400"
                        : "text-red-400"
                    : "text-slate-500"
                )}
              >
                {hasValue
                  ? `${(c.pct_change ?? 0) >= 0 ? "+" : ""}${c.pct_change?.toFixed(2)}%`
                  : c.close != null && c.label === "10Y Treasury"
                    ? `${c.close.toFixed(2)}%`
                    : "—"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
