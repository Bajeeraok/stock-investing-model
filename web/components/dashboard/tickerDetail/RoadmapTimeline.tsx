"use client";

import { clsx } from "clsx";
import type { BuyStagePreview } from "../executionPlanModel";
import { stageActChipClass } from "../executionPlanModel";

function statusDot(whenToAct: string, isGap?: boolean): string {
  const lower = whenToAct.toLowerCase();
  if (isGap && lower.includes("partial")) return "bg-cyan-400";
  if (isGap && lower.includes("hold")) return "bg-amber-400";
  if (lower.includes("add") || lower.includes("start") || lower.includes("core")) return "bg-teal-400";
  if (lower.includes("watch")) return "bg-slate-500";
  if (lower.includes("patience") || lower.includes("pause") || lower.includes("no")) return "bg-amber-400";
  return "bg-slate-500";
}

function CatchLevelChips({
  levels,
  bridgeLow,
  bridgeHigh,
}: {
  levels?: BuyStagePreview["catch_levels"];
  bridgeLow?: number;
  bridgeHigh?: number;
}) {
  if (!levels?.length && bridgeLow == null) return null;
  return (
    <div className="mt-2 space-y-1.5">
      {bridgeLow != null && bridgeHigh != null && (
        <p className="text-[10px] text-cyan-300/90 font-mono">
          Bridge ${bridgeLow.toFixed(2)}–${bridgeHigh.toFixed(2)}
        </p>
      )}
      {levels && levels.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {levels.map((lv) => (
            <span
              key={lv.id}
              className={clsx(
                "text-[10px] font-mono tabular-nums px-1.5 py-0.5 rounded border",
                lv.role === "anchor"
                  ? "border-cyan-500/35 text-cyan-200/90 bg-cyan-950/30"
                  : "border-emerald-500/30 text-emerald-200/90 bg-emerald-950/25",
              )}
              title={lv.label}
            >
              ${lv.price.toFixed(2)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function RoadmapTimeline({ stages, title }: { stages: BuyStagePreview[]; title?: string }) {
  if (stages.length === 0) return null;

  return (
    <div className="rounded-2xl border border-slate-700/50 bg-slate-900/60 p-4">
      {title && (
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-3">{title}</p>
      )}
      <div>
        {stages.map((stage, i) => {
          const isLast = i === stages.length - 1;
          const isGap = Boolean(stage.is_gap_row);
          return (
            <div
              key={stage.timeline_key}
              className={clsx("flex gap-3", isGap && "rounded-lg border border-amber-500/25 bg-amber-950/20 px-2 py-2 -mx-2 mb-1")}
            >
              <div className="flex flex-col items-center w-4 shrink-0 pt-2">
                <div
                  className={clsx(
                    "w-2 h-2 rounded-full ring-2 ring-offset-1 ring-offset-slate-950 shrink-0",
                    statusDot(stage.when_to_act, isGap),
                  )}
                />
                {!isLast && <div className="w-px flex-1 mt-1 min-h-3 bg-slate-700/50" />}
              </div>
              <div className={clsx("flex-1 min-w-0", isLast ? "pb-0" : "pb-3")}>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                    {stage.label}
                  </span>
                  {stage.position_pct > 0 && (
                    <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded-full bg-teal-500/15 text-teal-300 border border-teal-500/25">
                      {stage.position_pct}%
                    </span>
                  )}
                </div>
                <span
                  className={clsx(
                    "inline-block mt-1 text-xs font-medium px-1.5 py-0.5 rounded",
                    stageActChipClass(stage.when_to_act),
                  )}
                >
                  {stage.when_to_act}
                </span>
                <p className="text-[10px] font-mono text-slate-500 mt-1">
                  {isGap ? "Gap span " : ""}${stage.price_zone_low.toFixed(2)}–${stage.price_zone_high.toFixed(2)}
                </p>
                {stage.condition && (
                  <p className="text-[11px] text-slate-400 mt-1 leading-snug">{stage.condition}</p>
                )}
                {stage.sync_note && (
                  <p className="text-[10px] text-sky-300/80 mt-1 leading-snug">{stage.sync_note}</p>
                )}
                <CatchLevelChips
                  levels={stage.catch_levels}
                  bridgeLow={stage.bridge_zone_low}
                  bridgeHigh={stage.bridge_zone_high}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
