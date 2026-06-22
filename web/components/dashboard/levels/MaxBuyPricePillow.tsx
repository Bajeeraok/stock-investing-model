"use client";

import { clsx } from "clsx";
import type { HorizonSignalPayload } from "../InvestorDecisionSummary";
import { LongTermAccumulationScale } from "../retailActionUX";

/** Owner-mode hero: full-size MOS ceiling + tier bar (spot vs structural tiers). */
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

  const assessment = entryTiers.current_assessment;
  const mos = assessment?.min_price_to_buy;
  const withinMos =
    assessment?.within_full_mos_ceiling === true ||
    (mos != null && mos > 0 && currentPrice <= mos);
  const aboveMos =
    assessment?.above_full_mos_ceiling === true ||
    (mos != null && mos > 0 && currentPrice > mos);
  const fullSizeOk = assessment?.full_size_eligible_at_spot === true;
  const belowAllWithinMos = entryTiers.spot_position?.below_all_within_mos === true;
  const activeTier = entryTiers.active_tier_id;
  const assessmentLabel = assessment?.label;

  return (
    <div
      className={clsx(
        "rounded-xl border border-cyan-500/35 bg-gradient-to-br from-cyan-950/35 via-slate-950/70 to-slate-950/90 overflow-hidden",
        className,
      )}
      aria-label="Full-size ceiling and long-term accumulation tiers"
    >
      {mos != null && mos > 0 && (
        <div className="px-3.5 py-3 border-b border-cyan-500/20 bg-cyan-950/25 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-cyan-200/95">
              Full-size ceiling · 25% MOS
            </p>
            <p className="text-xs text-slate-400 mt-1 leading-snug">
              Upper bound for a full allocation vs model fair value — not a target entry price. Tier bands
              (MA200 / FV MOS / 52w stress) are separate scale-in guides.
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

      {withinMos && fullSizeOk && mos != null && (
        <p className="px-3.5 py-2 text-xs text-emerald-200/95 border-b border-emerald-500/25 bg-emerald-950/25 leading-snug">
          Spot ${currentPrice.toFixed(2)} is at/below the full-size ceiling (${mos.toFixed(2)}) — valuation
          supports full allocation.
          {belowAllWithinMos
            ? " Tier bands sit above spot (MA200/FV anchors); they do not block buying at this price."
            : " Scale per the tier ladder when timing and regime confirm."}
        </p>
      )}

      {aboveMos && mos != null && (
        <p className="px-3.5 py-2 text-xs text-amber-200/95 border-b border-amber-500/20 bg-amber-950/20">
          Spot ${currentPrice.toFixed(2)} is above the full-size ceiling (${mos.toFixed(2)}) — use tier bands
          below for partial sizing only.
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
