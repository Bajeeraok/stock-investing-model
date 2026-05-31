"use client";

import { clsx } from "clsx";
import { Users } from "lucide-react";
import type { ValuationDeckPayload } from "./valuationDeckTypes";

function fmtUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

export function StreetSentimentChip({
  deck,
  executionLabel,
}: {
  deck: ValuationDeckPayload;
  executionLabel?: string | null;
}) {
  if (!deck.scout_street_alert && !deck.street?.ratings) return null;

  const street = deck.street;
  const ratings = street?.ratings;
  const buyCount = ratings ? (ratings.strong_buy || 0) + (ratings.buy || 0) : null;
  const pt = street?.primary_usd;

  if (!deck.scout_street_alert) return null;

  return (
    <div
      className={clsx(
        "rounded-lg border px-3 py-2 text-xs leading-snug",
        "border-amber-500/35 bg-amber-950/30 text-amber-100/95",
      )}
    >
      <p className="text-[10px] uppercase tracking-wide font-semibold text-amber-300/80 flex items-center gap-1.5 mb-1">
        <Users className="h-3.5 w-3.5" />
        Street vs execution
      </p>
      <p>
        {buyCount != null && ratings
          ? `Analysts lean bullish (${buyCount}/${ratings.total} buy-side). `
          : pt != null
            ? `Street PT ~${fmtUsd(pt)}. `
            : ""}
        {executionLabel
          ? `Our execution today: ${executionLabel} — don’t chase consensus at this price.`
          : "Horizon may look constructive; execution says wait — don’t chase crowd price."}
      </p>
    </div>
  );
}
