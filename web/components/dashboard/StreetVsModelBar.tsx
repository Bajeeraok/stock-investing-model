"use client";

import type { FairValueVsExternal } from "./InvestorDecisionSummary";

function fmt(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export function StreetVsModelBar({
  modelFairValue,
  currentPrice,
  external,
}: {
  modelFairValue: number;
  currentPrice: number;
  external?: FairValueVsExternal | null;
}) {
  if (!external) return null;

  const street =
    external.fmp_consensus_median_usd ??
    external.yahoo_12m_mean_usd ??
    (external.fmp_consensus_low_usd != null && external.fmp_consensus_high_usd != null
      ? (external.fmp_consensus_low_usd + external.fmp_consensus_high_usd) / 2
      : null);

  if (street == null || !Number.isFinite(street) || modelFairValue <= 0) return null;

  const low = Math.min(currentPrice, modelFairValue, street) * 0.97;
  const high = Math.max(currentPrice, modelFairValue, street) * 1.03;
  const span = high - low || 1;
  const pct = (v: number) => `${Math.max(0, Math.min(100, ((v - low) / span) * 100)).toFixed(1)}%`;

  const streetLabel = external.fmp_consensus_median_usd
    ? external.fmp_median_is_range_midpoint
      ? "Street (FMP midpoint)"
      : "Street (FMP median)"
    : external.yahoo_12m_mean_usd
      ? "Street (Yahoo 12m)"
      : "Street consensus";

  const gapModelVsStreet = ((modelFairValue - street) / street) * 100;

  return (
    <div className="rounded-xl border border-sky-500/25 bg-sky-950/20 px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-sky-300/90">Model vs street</h4>
        <span className="text-[11px] text-slate-400">
          Model FV {gapModelVsStreet >= 0 ? "+" : ""}
          {gapModelVsStreet.toFixed(1)}% vs {streetLabel.toLowerCase()}
        </span>
      </div>
      <div className="relative h-8 rounded-lg bg-slate-900/80 border border-slate-700/60 overflow-hidden">
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-slate-100 z-20"
          style={{ left: pct(currentPrice) }}
          title={`Now ${fmt(currentPrice)}`}
        />
        <div
          className="absolute top-1 bottom-1 w-1 rounded-full bg-emerald-400 z-20"
          style={{ left: pct(modelFairValue) }}
          title={`Model FV ${fmt(modelFairValue)}`}
        />
        <div
          className="absolute top-1 bottom-1 w-1 rounded-full bg-violet-400 z-20"
          style={{ left: pct(street) }}
          title={`${streetLabel} ${fmt(street)}`}
        />
        <div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-slate-700/20 via-emerald-500/10 to-violet-500/15"
          style={{ width: "100%" }}
        />
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 text-[10px]">
        <div>
          <p className="text-slate-500">Now</p>
          <p className="text-slate-200 font-medium">{fmt(currentPrice)}</p>
        </div>
        <div>
          <p className="text-emerald-400/80">Model FV</p>
          <p className="text-emerald-200 font-medium">{fmt(modelFairValue)}</p>
        </div>
        <div>
          <p className="text-violet-400/80">{streetLabel}</p>
          <p className="text-violet-200 font-medium">{fmt(street)}</p>
        </div>
      </div>
      {external.note && (
        <p className="text-[10px] text-slate-500 mt-2 leading-snug">{external.note}</p>
      )}
    </div>
  );
}
