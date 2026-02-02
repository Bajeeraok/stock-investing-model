"use client";

import { Info, Check, XCircle } from "lucide-react";
import type { FMPPlanStatus } from "@/app/page";

export function FMPPlanStatus({ status }: { status: FMPPlanStatus | null | undefined }) {
  if (!status) return null;

  const { has_key, available, unavailable } = status;

  if (!has_key) {
    return (
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
        <h3 className="text-sm font-semibold text-amber-400 flex items-center gap-2 mb-2">
          <Info className="h-4 w-4" />
          FMP data source
        </h3>
        <p className="text-sm text-slate-300 mb-2">Add fmp_api_key to config for: economic calendar, treasury, price targets, insider stats.</p>
        <p className="text-xs text-slate-500">
          <span className="font-medium text-amber-400">Upgrade path:</span> Starter $22/mo – calendar, analysts, insider. Ultimate $149/mo – 13F, transcripts, ETF holdings.
        </p>
      </div>
    );
  }

  if (unavailable.length === 0) {
    return (
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
        <h3 className="text-sm font-semibold text-emerald-400 flex items-center gap-2 mb-2">
          <Check className="h-4 w-4" />
          FMP features available
        </h3>
        <p className="text-xs text-slate-400">All probed features working.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
      <h3 className="text-sm font-semibold text-amber-400 flex items-center gap-2 mb-2">
        <XCircle className="h-4 w-4" />
        FMP plan limits
      </h3>
      <p className="text-xs text-slate-400 mb-2">Current plan doesn&apos;t support these – upgrade to unlock:</p>
      <ul className="space-y-1 text-xs">
        {unavailable.map((u, i) => (
          <li key={i} className="text-slate-300">
            <span className="text-amber-400">{u.feature}:</span> upgrade to <span className="font-medium">{u.suggested_plan}</span>
            {u.error && <span className="text-slate-500 ml-1">({u.error.slice(0, 40)})</span>}
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-500 mt-2">
        Ultimate $149/mo unlocks: 13F institutional, earnings transcripts, ETF holdings.
      </p>
    </div>
  );
}
