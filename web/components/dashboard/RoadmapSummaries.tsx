"use client";

import { useState } from "react";
import { Calendar, ChevronDown, ChevronRight, TrendingUp } from "lucide-react";
import { clsx } from "clsx";
import type { InvestorDecisionSummary } from "./InvestorDecisionSummary";

type TraderRoadmap = NonNullable<InvestorDecisionSummary["trader_roadmap"]>;
type InvestorRoadmap = NonNullable<InvestorDecisionSummary["investor_roadmap"]>;

const ACTION_BADGE: Record<string, string> = {
  hold:         "border-slate-600 bg-slate-800 text-slate-300",
  accumulate:   "border-emerald-500/50 bg-emerald-500/15 text-emerald-200",
  add:          "border-emerald-500/50 bg-emerald-500/15 text-emerald-200",
  buy:          "border-emerald-500/60 bg-emerald-500/20 text-emerald-100",
  trim:         "border-amber-500/50 bg-amber-500/15 text-amber-200",
  sell:         "border-red-500/45 bg-red-500/15 text-red-200",
  wait:         "border-slate-600 bg-slate-800 text-slate-400",
  watch:        "border-cyan-500/40 bg-cyan-500/10 text-cyan-300",
  patience:     "border-amber-500/30 bg-amber-500/10 text-amber-300",
};

function ActionBadge({ text }: { text: string }) {
  const key = text.toLowerCase().split(/[\s_]/)[0];
  const cls = ACTION_BADGE[key] ?? "border-slate-600 bg-slate-800 text-slate-300";
  return (
    <span className={clsx(
      "inline-flex items-center px-2 py-0.5 rounded-full border text-[9px] font-black uppercase tracking-widest",
      cls,
    )}>
      {text.replace(/_/g, " ")}
    </span>
  );
}

function MonoPrice({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-slate-500">—</span>;
  return <span className="font-mono tabular-nums text-slate-200">${v.toFixed(2)}</span>;
}

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
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/50 backdrop-blur-sm overflow-hidden divide-y divide-slate-700/50">
      {/* ── Trader roadmap ─────────────────────────────── */}
      {traderRoadmap && (
        <div>
          <button
            type="button"
            onClick={() => setTraderOpen((o) => !o)}
            className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-800/40 transition-colors"
          >
            <span className="flex items-center gap-2 text-xs font-semibold text-slate-200 uppercase tracking-wider">
              <TrendingUp className="h-3.5 w-3.5 text-amber-400" />
              Trader roadmap
              <ActionBadge text={traderRoadmap.action_today} />
            </span>
            {traderOpen ? (
              <ChevronDown className="h-4 w-4 text-slate-500" />
            ) : (
              <ChevronRight className="h-4 w-4 text-slate-500" />
            )}
          </button>
          {traderOpen && (
            <div className="px-4 pb-4 pt-1 space-y-3 border-t border-slate-700/40">
              {traderRoadmap.short.entry_zone && (
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 px-3 py-2.5 grid grid-cols-3 gap-2">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-[9px] uppercase text-slate-500 font-semibold">Short entry</span>
                    <span className="text-xs font-mono text-slate-200 tabular-nums">
                      ${traderRoadmap.short.entry_zone.low?.toFixed(2)}–${traderRoadmap.short.entry_zone.high?.toFixed(2)}
                    </span>
                  </div>
                  {traderRoadmap.short.target != null && (
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[9px] uppercase text-slate-500 font-semibold">Target</span>
                      <MonoPrice v={traderRoadmap.short.target} />
                    </div>
                  )}
                  {traderRoadmap.short.stop != null && (
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[9px] uppercase text-slate-500 font-semibold">Stop</span>
                      <span className="font-mono tabular-nums text-red-300 text-xs">
                        ${traderRoadmap.short.stop.toFixed(2)}
                      </span>
                    </div>
                  )}
                  {traderRoadmap.short.trigger && (
                    <p className="col-span-3 text-[10px] text-slate-400 leading-snug">{traderRoadmap.short.trigger}</p>
                  )}
                </div>
              )}
              {traderRoadmap.medium.entry_zone && (
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 px-3 py-2.5 grid grid-cols-3 gap-2">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-[9px] uppercase text-slate-500 font-semibold">Med entry</span>
                    <span className="text-xs font-mono text-slate-200 tabular-nums">
                      ${traderRoadmap.medium.entry_zone.low?.toFixed(2)}–${traderRoadmap.medium.entry_zone.high?.toFixed(2)}
                    </span>
                  </div>
                  {traderRoadmap.medium.target != null && (
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[9px] uppercase text-slate-500 font-semibold">Target</span>
                      <MonoPrice v={traderRoadmap.medium.target} />
                    </div>
                  )}
                  {traderRoadmap.medium.stop != null && (
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[9px] uppercase text-slate-500 font-semibold">Stop</span>
                      <span className="font-mono tabular-nums text-red-300 text-xs">
                        ${traderRoadmap.medium.stop.toFixed(2)}
                      </span>
                    </div>
                  )}
                  {traderRoadmap.medium.trigger && (
                    <p className="col-span-3 text-[10px] text-slate-400 leading-snug">{traderRoadmap.medium.trigger}</p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Investor roadmap ─────────────────────────────── */}
      {investorRoadmap && (
        <div>
          <button
            type="button"
            onClick={() => setInvestorOpen((o) => !o)}
            className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-800/40 transition-colors"
          >
            <span className="flex items-center gap-2 text-xs font-semibold text-slate-200 uppercase tracking-wider">
              <Calendar className="h-3.5 w-3.5 text-emerald-400" />
              Investor roadmap
              <ActionBadge text={investorRoadmap.action_today} />
            </span>
            {investorOpen ? (
              <ChevronDown className="h-4 w-4 text-slate-500" />
            ) : (
              <ChevronRight className="h-4 w-4 text-slate-500" />
            )}
          </button>
          {investorOpen && (
            <div className="px-4 pb-4 pt-1 space-y-3 border-t border-slate-700/40">
              {investorRoadmap.add_tiers.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-[9px] uppercase font-semibold text-slate-500 tracking-wider">Add tiers</p>
                  <div className="grid grid-cols-1 gap-1.5">
                    {investorRoadmap.add_tiers
                      .filter(t => t.low != null && t.high != null)
                      .map(t => (
                        <div key={t.id} className="flex items-center justify-between gap-2 rounded-lg border border-slate-700/40 bg-slate-800/25 px-3 py-2">
                          <span className="text-[10px] text-slate-400">{t.label ?? t.id}</span>
                          <span className="text-xs font-mono font-semibold text-emerald-300 tabular-nums">
                            ${(t.low as number).toFixed(2)}–${(t.high as number).toFixed(2)}
                          </span>
                          {(t.allocation_pct ?? 0) > 0 && (
                            <span className="text-[9px] text-slate-500 font-mono">{t.allocation_pct}%</span>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              )}
              <div className="flex items-center gap-2">
                <span className="text-[9px] uppercase text-slate-500 font-semibold shrink-0">Trim near</span>
                <span className="text-xs font-mono font-semibold text-amber-300 tabular-nums">
                  ${investorRoadmap.trim_near.toFixed(2)}
                </span>
              </div>
              {investorRoadmap.hold_thesis && (
                <p className="text-[10px] text-slate-400 leading-snug">{investorRoadmap.hold_thesis}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
