"use client";

import { Activity } from "lucide-react";
import type { MarketReversalOverlay } from "@/app/page";

export function MarketReversalBanner({ overlay }: { overlay: MarketReversalOverlay | null | undefined }) {
  if (!overlay || overlay.enabled === false) return null;
  if (overlay.error && !overlay.headline) return null;

  const label = overlay.label ?? "normal";
  const border =
    label === "stressed"
      ? "border-red-500/35 bg-red-950/25"
      : label === "bounce_risk"
        ? "border-sky-500/35 bg-sky-950/20"
        : label === "cautious"
          ? "border-amber-500/30 bg-amber-950/15"
          : "border-slate-600 bg-slate-800/40";

  return (
    <div className={`rounded-lg border px-4 py-3 space-y-2 ${border}`}>
      <div className="flex items-start gap-2">
        <Activity className="h-4 w-4 text-sky-400 shrink-0 mt-0.5" aria-hidden />
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Market tape overlay</p>
          <p className="text-sm text-slate-200 leading-snug">{overlay.headline ?? "Market backdrop"}</p>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs font-mono text-slate-400">
            {overlay.stress_score != null && <span>Stress {overlay.stress_score.toFixed(0)}/100</span>}
            {overlay.bounce_setup_score != null && <span>Bounce-setup {overlay.bounce_setup_score.toFixed(0)}/100</span>}
            {overlay.composite_buy_delta != null && overlay.composite_buy_delta !== 0 && (
              <span className="text-amber-200/90">Composite Δ {overlay.composite_buy_delta > 0 ? "+" : ""}{overlay.composite_buy_delta.toFixed(1)}</span>
            )}
            {overlay.ml_bounce_prob != null && (
              <span title="Trained on historical stress days; not a guarantee of direction">
                ML P(bounce) {(overlay.ml_bounce_prob * 100).toFixed(0)}%
              </span>
            )}
          </div>
        </div>
      </div>
      {overlay.bullets && overlay.bullets.length > 0 && (
        <ul className="text-xs text-slate-500 list-disc list-inside space-y-0.5 pl-1">
          {overlay.bullets.slice(0, 4).map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>
      )}
      <p className="text-[10px] text-slate-600 leading-snug">
        Illustrative index-level risk context + optional ML on SPY/VIX features. Does not predict a specific next-day close.
      </p>
    </div>
  );
}
