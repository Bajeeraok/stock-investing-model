"use client";

import { BarChart3 } from "lucide-react";
import type { TradingLens } from "@/lib/tradingLens";
import { tradingLensLabel } from "@/lib/tradingLens";
import { lensForwardLine, type SummaryByLens } from "@/lib/forwardTrackingLens";

interface Props {
  activeLens: TradingLens;
  summaryByLens?: SummaryByLens | null;
  loading?: boolean;
}

/** Phase D2 — forward hit rate line for active trading lens. */
export function LensTrackRecordStrip({ activeLens, summaryByLens, loading }: Props) {
  const line = lensForwardLine(activeLens, summaryByLens);
  const scout = lensForwardLine("scout", summaryByLens);
  const swing = lensForwardLine("swing", summaryByLens);
  const owner = lensForwardLine("owner", summaryByLens);

  if (loading) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 px-3 py-2 text-xs text-slate-500">
        Loading track record…
      </div>
    );
  }

  if (!line && !scout && !swing && !owner) return null;

  return (
    <div
      className="rounded-lg border border-slate-600 bg-slate-800/30 px-3 py-2 flex flex-wrap items-center gap-x-4 gap-y-1"
      title="Forward returns from EOD snapshot pairs — not paper trades"
    >
      <BarChart3 className="h-4 w-4 text-violet-400 shrink-0" />
      <span className="text-xs text-slate-400 font-medium">
        Track record · {tradingLensLabel(activeLens)}
      </span>
      {line && <span className="text-xs text-slate-200">{line}</span>}
      {(scout || swing || owner) && (
        <span className="text-[10px] text-slate-600 hidden lg:inline">
          Scout: {scout || "—"} · Swing: {swing || "—"} · Owner: {owner || "—"}
        </span>
      )}
    </div>
  );
}
