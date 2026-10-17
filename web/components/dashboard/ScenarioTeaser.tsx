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
      className="w-full text-left rounded-xl border border-td-owner/30 bg-td-owner-weak/25 px-4 py-3 flex items-center gap-3 hover:bg-td-owner-weak/40 transition-colors group"
    >
      <Layers className="h-5 w-5 text-td-owner shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-td-text">
          {teaser.count} scenarios ·{" "}
          <span className="text-td-accent">{teaser.bullCount} bullish</span>
          <span className="text-td-muted"> / </span>
          <span className="text-td-crit">{teaser.bearCount} bearish</span>
        </p>
        {teaser.baseReturnPct != null && (
          <p className="text-xs text-td-muted mt-0.5">
            {teaser.baseName ?? "Base"}:{" "}
            <span className={teaser.baseReturnPct >= 0 ? "text-td-accent" : "text-td-warn"}>
              {teaser.baseReturnPct >= 0 ? "+" : ""}
              {teaser.baseReturnPct.toFixed(1)}%
            </span>
            {teaser.baseProbPct != null && (
              <span className="text-td-muted"> · {teaser.baseProbPct.toFixed(0)}% prob</span>
            )}
            <span className="text-td-owner/90 ml-1 group-hover:underline">→ Valuation &amp; scenarios</span>
          </p>
        )}
      </div>
      <ChevronRight className="h-5 w-5 text-td-owner/70 shrink-0" />
    </button>
  );
}
