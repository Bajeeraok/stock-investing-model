"use client";

import { AlertTriangle } from "lucide-react";

export type PortfolioStressPayload = {
  base_value: number;
  scenarios: {
    name: string;
    shock_pct: number;
    portfolio_value_after: number;
    loss_dollars: number;
  }[];
  disclaimer?: string;
};

/** Illustrative parallel shocks to total portfolio (β≈1). */
export function PortfolioStressStrip({ stress }: { stress: PortfolioStressPayload }) {
  if (!stress.scenarios?.length) return null;
  return (
    <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-4 md:col-span-2 lg:col-span-4">
      <div className="flex items-center gap-2 text-amber-200/90 text-sm font-medium mb-2">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        Stress / max-pain (illustrative)
      </div>
      <p className="text-xs text-slate-500 mb-3">
        If the whole portfolio moved with a broad market shock (same direction, simplified — not individual betas).
        Base: ${stress.base_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {stress.scenarios.map((s) => (
          <div
            key={s.name}
            className="rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-2"
            title={stress.disclaimer}
          >
            <div className="text-slate-400 text-xs mb-0.5">{s.name}</div>
            <div className="text-lg font-semibold text-amber-400">
              ${s.portfolio_value_after.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
            <div className="text-xs text-slate-500">
              {s.shock_pct}% · P/L ${s.loss_dollars.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
          </div>
        ))}
      </div>
      {stress.disclaimer && (
        <p className="text-[10px] text-slate-600 mt-2 leading-snug">{stress.disclaimer}</p>
      )}
    </div>
  );
}
