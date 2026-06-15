"use client";

import { clsx } from "clsx";
import type { HorizonSignalPayload } from "../InvestorDecisionSummary";
import { LongTermAccumulationScale } from "../retailActionUX";

/** Owner-mode hero: full-position MOS ceiling + tier bar (spot vs tiers vs max buy). */
export function MaxBuyPricePillow({
  horizon,
  entryTiers,
  currentPrice,
  stopLoss,
  target,
  className,
}: {
  horizon: Pick<HorizonSignalPayload, "entry_zone">;
  entryTiers: NonNullable<HorizonSignalPayload["entry_tiers"]>;
  currentPrice: number;
  stopLoss?: number | null;
  target?: number | null;
  className?: string;
}) {
  const tiers = entryTiers.tiers ?? [];
  if (!tiers.length || !(currentPrice > 0)) return null;

  const mos = entryTiers.current_assessment?.min_price_to_buy;
  const aboveMos =
    entryTiers.current_assessment?.above_full_mos_ceiling === true ||
    (mos != null && mos > 0 && currentPrice > mos);
  const activeTier = entryTiers.active_tier_id;
  const assessmentLabel = entryTiers.current_assessment?.label;

  return (
    <div
      className={clsx(
        "rounded-xl border border-cyan-500/35 bg-gradient-to-br from-cyan-950/35 via-slate-950/70 to-slate-950/90 overflow-hidden",
        className,
      )}
      aria-label="Max buy price and long-term accumulation tiers"
    >
      {mos != null && mos > 0 && (
        <div className="px-3.5 py-3 border-b border-cyan-500/20 bg-cyan-950/25 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-cyan-200/95">
              Max buy price · full position
            </p>
            <p className="text-xs text-slate-400 mt-1 leading-snug">
              Full allocation only at or below this level (25% MOS to model fair value).
              {activeTier ? (
                <span className="text-slate-500">
                  {" "}
                  Active tier {activeTier}
                  {assessmentLabel ? ` — ${assessmentLabel}` : ""}.
                </span>
              ) : null}
            </p>
          </div>
          <p className="text-2xl sm:text-3xl font-bold font-mono tabular-nums text-cyan-100 shrink-0">
            ≤ ${mos.toFixed(2)}
          </p>
        </div>
      )}

      {aboveMos && mos != null && (
        <p className="px-3.5 py-2 text-xs text-amber-200/95 border-b border-amber-500/20 bg-amber-950/20">
          Spot ${currentPrice.toFixed(2)} is above the full-position ceiling (${mos.toFixed(2)}) — use tier
          bands below for partial sizing only.
        </p>
      )}

      <div className="p-3.5">
        <LongTermAccumulationScale
          horizon={horizon}
          entryTiers={entryTiers}
          currentPrice={currentPrice}
          stopLoss={stopLoss}
          target={target}
          variant="deck"
          hideCatchLevels
          barClassName="h-10"
        />
      </div>
    </div>
  );
}
