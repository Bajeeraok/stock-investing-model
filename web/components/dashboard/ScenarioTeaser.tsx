"use client";

import { ChevronRight, Layers } from "lucide-react";
import type { PriceTargetsData, Scenario } from "./PriceTargetsPanel";

export function buildScenarioTeaser(data: PriceTargetsData | null | undefined): {
  count: number;
  bullCount: number;
  bearCount: number;
  baseName: string | null;
  baseReturnPct: number | null;
  baseProbPct: number | null;
} | null {
  if (!data?.scenarios?.length) return null;
  const scenarios = data.scenarios;
  const base = scenarios.find((s) => s.is_base) ?? scenarios.find((s) => s.scenario_type === "base");
  return {
    count: scenarios.length,
    bullCount: scenarios.filter((s) => s.return_pct >= 0).length,
    bearCount: scenarios.filter((s) => s.return_pct < 0).length,
    baseName: base?.name ?? null,
    baseReturnPct: base?.return_pct ?? null,
    // API stores probability as 0–1; PriceTargetsPanel multiplies by 100 for display.
    baseProbPct: base?.probability != null ? base.probability * 100 : null,
  };
}

export function ScenarioTeaser({
  data,
  onOpenValuation,
}: {
  data: PriceTargetsData | null | undefined;
  onOpenValuation: () => void;
}) {
  const teaser = buildScenarioTeaser(data);
  if (!teaser) return null;

  return (
    <button
      type="button"
      onClick={onOpenValuation}
      className="w-full text-left rounded-xl border border-violet-500/30 bg-violet-950/25 px-4 py-3 flex items-center gap-3 hover:bg-violet-950/40 transition-colors group"
    >
      <Layers className="h-5 w-5 text-violet-400 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-slate-200">
          {teaser.count} scenarios ·{" "}
          <span className="text-emerald-400">{teaser.bullCount} bullish</span>
          <span className="text-slate-500"> / </span>
          <span className="text-red-400">{teaser.bearCount} bearish</span>
        </p>
        {teaser.baseReturnPct != null && (
          <p className="text-xs text-slate-400 mt-0.5">
            {teaser.baseName ?? "Base"}:{" "}
            <span className={teaser.baseReturnPct >= 0 ? "text-emerald-400" : "text-amber-300"}>
              {teaser.baseReturnPct >= 0 ? "+" : ""}
              {teaser.baseReturnPct.toFixed(1)}%
            </span>
            {teaser.baseProbPct != null && (
              <span className="text-slate-500"> · {teaser.baseProbPct.toFixed(0)}% prob</span>
            )}
            <span className="text-violet-400/90 ml-1 group-hover:underline">→ Valuation &amp; scenarios</span>
          </p>
        )}
      </div>
      <ChevronRight className="h-5 w-5 text-violet-400/70 shrink-0" />
    </button>
  );
}
