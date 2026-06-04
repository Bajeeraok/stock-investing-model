"use client";

import { clsx } from "clsx";
import type { BuyStagePreview } from "../executionPlanModel";
import { stageActChipClass } from "../executionPlanModel";

function statusDot(whenToAct: string): string {
  const lower = whenToAct.toLowerCase();
  if (lower.includes("add") || lower.includes("start") || lower.includes("core")) return "bg-teal-400";
  if (lower.includes("watch")) return "bg-slate-500";
  if (lower.includes("patience") || lower.includes("pause") || lower.includes("no")) return "bg-amber-400";
  return "bg-slate-500";
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
          return (
            <div key={stage.timeline_key} className="flex gap-3">
              <div className="flex flex-col items-center w-4 shrink-0 pt-2">
                <div
                  className={clsx(
                    "w-2 h-2 rounded-full ring-2 ring-offset-1 ring-offset-slate-950 shrink-0",
                    statusDot(stage.when_to_act),
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
                  ${stage.price_zone_low.toFixed(2)}–${stage.price_zone_high.toFixed(2)}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
