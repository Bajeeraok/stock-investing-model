"use client";

import { clsx } from "clsx";
import { Target } from "lucide-react";
import type { RetailMarketDecisions } from "./RetailMarketDecisionsPanel";

type LevelChip = {
  label: string;
  price: number;
  distance_pct?: number | null;
  type?: string;
};

function chipTone(dist: number | null | undefined): string {
  if (dist == null) return "border-slate-600 text-slate-300 bg-slate-800/50";
  if (dist <= 0.5) return "border-amber-500/40 text-amber-200 bg-amber-500/10";
  if (dist <= 2) return "border-orange-500/30 text-orange-200 bg-orange-500/10";
  return "border-slate-600 text-slate-300 bg-slate-800/50";
}

function formatDist(dist: number | null | undefined): string {
  if (dist == null || Number.isNaN(dist)) return "—";
  if (dist <= 0) return "at/below";
  return `${dist.toFixed(1)}% above`;
}

/**
 * Phase C2 — SPY/QQQ distance-to-level chips (%), not prose only.
 */
export function TriggerLevelChips({
  triggerLevels,
}: {
  triggerLevels?: RetailMarketDecisions["trigger_levels"] | null;
}) {
  const levels = triggerLevels?.levels;
  if (!levels || (!levels.SPY && !levels.QQQ)) return null;

  const rows: { ticker: string; last: number; chips: LevelChip[] }[] = [];
  for (const sym of ["SPY", "QQQ"] as const) {
    const lv = levels[sym];
    if (!lv) continue;
    const chips: LevelChip[] =
      (lv.chip_levels as LevelChip[] | undefined) ??
      (lv.supports as LevelChip[] | undefined)?.map((s) => ({
        label: s.label,
        price: s.price,
        distance_pct:
          lv.last_close && s.price
            ? Math.round((100 * (lv.last_close - s.price)) / lv.last_close * 100) / 100
            : null,
        type: s.type,
      })) ??
      [];
    if (chips.length === 0 && lv.primary_trigger && lv.last_close) {
      chips.push({
        label: "Primary",
        price: lv.primary_trigger,
        distance_pct: Math.round((100 * (lv.last_close - lv.primary_trigger)) / lv.last_close * 100) / 100,
      });
    }
    rows.push({ ticker: sym, last: lv.last_close, chips: chips.slice(0, 3) });
  }

  if (rows.length === 0) return null;

  return (
    <div className="rounded-lg border border-sky-500/25 bg-sky-950/15 px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-2">
        <Target className="h-3.5 w-3.5 text-sky-400" />
        <span className="text-xs font-semibold text-sky-200">Trigger levels</span>
        <span className="text-[10px] text-slate-500">distance to support</span>
      </div>
      {rows.map((row) => (
        <div key={row.ticker}>
          <p className="text-[10px] text-slate-500 mb-1">
            {row.ticker}{" "}
            <span className="font-mono text-slate-300">${row.last.toFixed(2)}</span>
          </p>
          <div className="flex flex-wrap gap-1.5">
            {row.chips.map((c) => (
              <span
                key={`${row.ticker}-${c.label}`}
                title={`${c.label} $${c.price.toFixed(2)} · ${formatDist(c.distance_pct)}`}
                className={clsx(
                  "text-[10px] font-mono px-2 py-0.5 rounded border",
                  chipTone(c.distance_pct),
                )}
              >
                {c.label.replace(/ support.*/i, "")} {formatDist(c.distance_pct)}
              </span>
            ))}
          </div>
        </div>
      ))}
      {triggerLevels?.headline && (
        <p className="text-[10px] text-slate-500 leading-snug">{triggerLevels.headline}</p>
      )}
    </div>
  );
}
