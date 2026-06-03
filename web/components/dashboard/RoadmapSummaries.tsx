"use client";

import { useState } from "react";
import { Calendar, ChevronDown, ChevronRight, TrendingUp } from "lucide-react";
import type { InvestorDecisionSummary } from "./InvestorDecisionSummary";

type TraderRoadmap = NonNullable<InvestorDecisionSummary["trader_roadmap"]>;
type InvestorRoadmap = NonNullable<InvestorDecisionSummary["investor_roadmap"]>;

/** Trader + investor roadmap blocks (Levels tab). */
export function RoadmapSummaries({
  traderRoadmap,
  investorRoadmap,
  defaultOpen = true,
}: {
  traderRoadmap?: TraderRoadmap | null;
  investorRoadmap?: InvestorRoadmap | null;
  defaultOpen?: boolean;
}) {
  const [traderOpen, setTraderOpen] = useState(defaultOpen);
  const [investorOpen, setInvestorOpen] = useState(defaultOpen);

  if (!traderRoadmap && !investorRoadmap) return null;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800/40 overflow-hidden divide-y divide-slate-700/80">
      {traderRoadmap && (
        <div>
          <button
            type="button"
            onClick={() => setTraderOpen((o) => !o)}
            className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-700/30 transition-colors"
          >
            <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <TrendingUp className="h-4 w-4 text-amber-500" />
              Trader roadmap (short / medium)
            </span>
            {traderOpen ? (
              <ChevronDown className="h-4 w-4 text-slate-400" />
            ) : (
              <ChevronRight className="h-4 w-4 text-slate-400" />
            )}
          </button>
          {traderOpen && (
            <div className="px-4 pb-4 pt-0 space-y-2 text-sm border-t border-slate-700/50">
              <p className="text-slate-300">
                Today:{" "}
                <span className="font-medium text-slate-200">
                  {traderRoadmap.action_today.replace(/_/g, " ")}
                </span>
                .
              </p>
              {traderRoadmap.short.entry_zone && (
                <p className="text-slate-400">
                  Short (~1 mo): Entry $
                  {traderRoadmap.short.entry_zone.low?.toFixed(2)}–$
                  {traderRoadmap.short.entry_zone.high?.toFixed(2)}
                  {traderRoadmap.short.target != null
                    ? ` → target $${traderRoadmap.short.target.toFixed(2)}`
                    : ""}
                  {traderRoadmap.short.stop != null
                    ? ` · stop $${traderRoadmap.short.stop.toFixed(2)}`
                    : ""}
                  . {traderRoadmap.short.trigger}
                </p>
              )}
              {traderRoadmap.medium.entry_zone && (
                <p className="text-slate-400">
                  Medium (3–6 mo): Entry $
                  {traderRoadmap.medium.entry_zone.low?.toFixed(2)}–$
                  {traderRoadmap.medium.entry_zone.high?.toFixed(2)}
                  {traderRoadmap.medium.target != null
                    ? ` → target $${traderRoadmap.medium.target.toFixed(2)}`
                    : ""}
                  {traderRoadmap.medium.stop != null
                    ? ` · stop $${traderRoadmap.medium.stop.toFixed(2)}`
                    : ""}
                  . {traderRoadmap.medium.trigger}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {investorRoadmap && (
        <div>
          <button
            type="button"
            onClick={() => setInvestorOpen((o) => !o)}
            className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-700/30 transition-colors"
          >
            <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <Calendar className="h-4 w-4 text-emerald-500" />
              Investor roadmap (medium / long)
            </span>
            {investorOpen ? (
              <ChevronDown className="h-4 w-4 text-slate-400" />
            ) : (
              <ChevronRight className="h-4 w-4 text-slate-400" />
            )}
          </button>
          {investorOpen && (
            <div className="px-4 pb-4 pt-0 space-y-2 text-sm border-t border-slate-700/50">
              <p className="text-slate-300">
                Today:{" "}
                <span className="font-medium text-slate-200">{investorRoadmap.action_today}</span>.
              </p>
              {investorRoadmap.add_tiers.length > 0 && (
                <p className="text-slate-400">
                  Add:{" "}
                  {investorRoadmap.add_tiers
                    .filter((t) => t.low != null && t.high != null)
                    .map(
                      (t) =>
                        `${t.label ?? t.id}: $${(t.low as number).toFixed(2)}–$${(t.high as number).toFixed(2)} (${t.allocation_pct ?? 0}%)`,
                    )
                    .join(" · ")}
                </p>
              )}
              <p className="text-slate-400">
                Trim near ${investorRoadmap.trim_near.toFixed(2)}. {investorRoadmap.hold_thesis}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
