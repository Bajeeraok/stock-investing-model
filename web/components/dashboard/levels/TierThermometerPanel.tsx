"use client";

import { useMemo, useState } from "react";
import { clsx } from "clsx";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { HorizonSignalPayload } from "../InvestorDecisionSummary";
// entryTiers is typed as the full NonNull of HorizonSignalPayload["entry_tiers"]
import { PriceThermometer, type ThermometerLevel } from "./PriceThermometer";
import { LongTermTierLadder } from "../retailActionUX";

function tierColor(id: string): string {
  if (id === "T1") return "amber";
  if (id === "T2") return "emerald";
  if (id === "T3") return "violet";
  return "slate";
}

export function TierThermometerPanel({
  entryTiers,
  currentPrice,
  structuralStop,
  ma200,
  defaultThermometerOpen = false,
  className,
}: {
  entryTiers: NonNullable<HorizonSignalPayload["entry_tiers"]>;
  currentPrice: number;
  structuralStop?: number | null;
  ma200?: number | null;
  /** Thermometer SVG is hidden by default — user can expand. Default false. */
  defaultThermometerOpen?: boolean;
  className?: string;
}) {
  const [thermOpen, setThermOpen] = useState(defaultThermometerOpen);
  const activeTierId = entryTiers.active_tier_id;
  const targetTierId = entryTiers.target_tier_id;

  const levels: ThermometerLevel[] = useMemo(() => {
    const out: ThermometerLevel[] = [];

    for (const tier of entryTiers.tiers ?? []) {
      const isActive = tier.id === activeTierId;
      const isTarget = tier.id === targetTierId && !isActive;
      const inside = currentPrice >= tier.low && currentPrice <= tier.high;
      out.push({
        id: tier.id,
        label: tier.id,
        value: (tier.low + tier.high) / 2,
        band: { low: tier.low, high: tier.high },
        color: tierColor(tier.id),
        role: "tier",
        description: tier.label,
        active: isActive || inside,
        target: isTarget,
        badge: isActive || inside ? "Active" : isTarget ? "Next" : undefined,
      });
    }

    if (ma200 && ma200 > 0) {
      out.push({
        id: "ma200",
        label: "MA200",
        value: ma200,
        color: "orange",
        role: "anchor",
      });
    }

    return out;
  }, [entryTiers, currentPrice, activeTierId, targetTierId, ma200]);

  const assessment = entryTiers.current_assessment;
  const mos = assessment?.margin_of_safety_pct;
  const minBuy = assessment?.min_price_to_buy;

  return (
    <div className={clsx("rounded-2xl border border-violet-500/20 bg-gradient-to-b from-violet-950/25 via-slate-950/60 to-slate-950/80 backdrop-blur-sm overflow-hidden", className)}>
      <div className="px-4 py-2.5 border-b border-violet-500/15 bg-violet-950/30 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-violet-200">
          Price thermometer · Long-term tiers
        </p>
        <div className="flex items-center gap-2">
          {mos != null && (
            <span className={clsx(
              "text-[10px] font-semibold px-2 py-0.5 rounded-full border",
              mos >= 25
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                : mos >= 15
                  ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                  : "border-red-500/30 bg-red-500/10 text-red-300",
            )}>
              {mos.toFixed(1)}% MOS
            </span>
          )}
          <span className="text-[10px] font-semibold text-amber-200/90 uppercase">
            {assessment?.label ?? "Watching"}
          </span>
        </div>
      </div>

      {/* Thermometer toggle */}
      <button
        type="button"
        onClick={() => setThermOpen(o => !o)}
        className="w-full flex items-center justify-between gap-2 px-4 py-2 text-left hover:bg-slate-800/30 transition-colors border-b border-violet-500/10"
      >
        <span className="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">
          Price thermometer
        </span>
        <span className="flex items-center gap-1 text-[9px] text-slate-500">
          {thermOpen ? (
            <><ChevronDown className="h-3 w-3" />Hide</>
          ) : (
            <><ChevronRight className="h-3 w-3" />Show</>
          )}
        </span>
      </button>

      {thermOpen && (
        <div className="p-4 space-y-4">
          {/* Thermometer + legend */}
          <div className="flex gap-4">
            <PriceThermometer
              levels={levels}
              currentPrice={currentPrice}
              structuralStop={structuralStop ?? undefined}
              className="flex-1 min-h-[300px]"
            />

            {/* Tier legend */}
            <div className="flex flex-col justify-center gap-2 text-right min-w-[80px]">
              {(entryTiers.tiers ?? []).map(tier => {
                const inside = currentPrice >= tier.low && currentPrice <= tier.high;
                const above = currentPrice > tier.high;
                return (
                  <div key={tier.id} className="flex flex-col gap-0.5">
                    <div className="flex items-center justify-end gap-1.5">
                      <span className="text-[9px] text-slate-500 uppercase">{tier.id}</span>
                      {inside && <span className="text-[8px] font-black text-emerald-300 bg-emerald-500/20 px-1 rounded">IN</span>}
                      {!inside && above && <span className="text-[8px] text-slate-600">↑</span>}
                    </div>
                    <span className={clsx(
                      "text-[10px] font-mono tabular-nums",
                      inside ? "text-emerald-300" : "text-slate-400",
                    )}>
                      ${tier.low.toFixed(0)}–${tier.high.toFixed(0)}
                    </span>
                  </div>
                );
              })}
              {minBuy != null && (
                <div className="flex flex-col gap-0.5 border-t border-slate-700/50 pt-2 mt-1">
                  <span className="text-[9px] text-cyan-400/70 uppercase">Full MOS</span>
                  <span className="text-[10px] font-mono text-cyan-300/80 tabular-nums">≤${minBuy.toFixed(0)}</span>
                </div>
              )}
            </div>
          </div>
          <p className="text-[9px] text-slate-600 text-center font-mono">
            Hover a zone to isolate · white line = current price
          </p>
        </div>
      )}

      {/* Tier ladder below */}
      <div className="border-t border-violet-500/15">
        <LongTermTierLadder
          entryTiers={entryTiers}
          currentPrice={currentPrice}
          modeLabel={assessment?.label}
        />
      </div>
    </div>
  );
}
