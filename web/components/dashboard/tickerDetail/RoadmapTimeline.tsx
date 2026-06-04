"use client";

import { clsx } from "clsx";
import type { BuyStagePreview } from "../executionPlanModel";
import {
  catchLevelsFingerprint,
  periodCatchLevelTone,
  resolveSharedBridgeZone,
  resolveSharedCatchLevels,
  stageActChipClass,
} from "../executionPlanModel";

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
  periodLabel,
  periodKey,
}: {
  levels?: BuyStagePreview["catch_levels"];
  bridgeLow?: number;
  bridgeHigh?: number;
  periodLabel?: string;
  periodKey?: string;
}) {
  if (!levels?.length && bridgeLow == null) return null;
  const periodTone = periodKey ? periodCatchLevelTone(periodKey) : "";

  return (
    <div
      className={clsx(
        "mt-2 space-y-1.5",
        periodKey && periodLabel && "rounded-md border px-2 py-1.5",
        periodTone,
      )}
    >
      {periodLabel && (
        <p className="text-[10px] uppercase tracking-wider text-slate-500">{periodLabel}</p>
      )}
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

function SharedCatchLevelsBanner({
  levels,
  bridgeLow,
  bridgeHigh,
}: {
  levels: NonNullable<BuyStagePreview["catch_levels"]>;
  bridgeLow?: number | null;
  bridgeHigh?: number | null;
}) {
  return (
    <div className="mb-3 pb-3 border-b border-slate-700/60">
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">
        Catch levels valid across all watch periods
      </p>
      {bridgeLow != null && bridgeHigh != null && (
        <p className="text-[10px] text-cyan-300/90 font-mono mb-1.5">
          Bridge ${bridgeLow.toFixed(2)}–${bridgeHigh.toFixed(2)}
        </p>
      )}
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
      <p className="text-[10px] text-slate-600 mt-1.5 leading-snug">
        Same ladder for every row below — each period differs by <span className="text-slate-500">when to act</span>, not by price steps.
      </p>
    </div>
  );
}

export function RoadmapTimeline({ stages, title }: { stages: BuyStagePreview[]; title?: string }) {
  if (stages.length === 0) return null;

  const { shared: sharedCatch, uniform: uniformCatch } = resolveSharedCatchLevels(stages);
  const { uniform: uniformBridge, low: sharedBridgeLow, high: sharedBridgeHigh } =
    resolveSharedBridgeZone(stages);
  const showSharedCatch = uniformCatch && sharedCatch != null && sharedCatch.length > 0;
  const sharedCatchFp = catchLevelsFingerprint(sharedCatch);

  return (
    <div className="rounded-2xl border border-slate-700/50 bg-slate-900/60 p-4">
      {title && (
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-3">{title}</p>
      )}

      {showSharedCatch && (
        <SharedCatchLevelsBanner
          levels={sharedCatch}
          bridgeLow={uniformBridge ? sharedBridgeLow : null}
          bridgeHigh={uniformBridge ? sharedBridgeHigh : null}
        />
      )}

      <div>
        {stages.map((stage, i) => {
          const isLast = i === stages.length - 1;
          const isGap = Boolean(stage.is_gap_row);
          const rowCatchFp = catchLevelsFingerprint(stage.catch_levels);
          const showRowCatch =
            !showSharedCatch &&
            stage.catch_levels != null &&
            stage.catch_levels.length > 0;
          const showRowBridge =
            !showSharedCatch &&
            !uniformBridge &&
            stage.bridge_zone_low != null &&
            stage.bridge_zone_high != null;

          return (
            <div
              key={stage.timeline_key}
              className={clsx(
                "flex gap-3",
                isGap && "rounded-lg border border-amber-500/25 bg-amber-950/20 px-2 py-2 -mx-2 mb-1",
              )}
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
                <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
                  <span className="text-xs font-medium text-slate-300 shrink-0 min-w-[5.5rem]">
                    {stage.label}
                  </span>
                  <span
                    className={clsx(
                      "text-xs font-medium px-1.5 py-0.5 rounded shrink-0",
                      stageActChipClass(stage.when_to_act),
                    )}
                  >
                    {stage.when_to_act}
                  </span>
                  <span className="text-[11px] font-mono text-slate-400 sm:ml-auto tabular-nums">
                    {isGap ? "Gap span " : ""}${stage.price_zone_low.toFixed(2)}–${stage.price_zone_high.toFixed(2)}
                    {stage.position_pct > 0 ? (
                      <span className="text-slate-600 ml-1.5">· {stage.position_pct}%</span>
                    ) : null}
                  </span>
                </div>
                {stage.condition && (
                  <p className="text-[11px] text-slate-400 mt-1 leading-snug">{stage.condition}</p>
                )}
                {stage.sync_note && (
                  <p className="text-[10px] text-sky-300/80 mt-1 leading-snug">{stage.sync_note}</p>
                )}
                {showRowCatch && (
                  <CatchLevelChips
                    levels={stage.catch_levels}
                    bridgeLow={showRowBridge ? stage.bridge_zone_low : undefined}
                    bridgeHigh={showRowBridge ? stage.bridge_zone_high : undefined}
                    periodLabel={`Catch levels · ${stage.label}`}
                    periodKey={stage.timeline_key}
                  />
                )}
                {showSharedCatch &&
                  rowCatchFp &&
                  rowCatchFp !== sharedCatchFp &&
                  stage.catch_levels &&
                  stage.catch_levels.length > 0 && (
                    <CatchLevelChips
                      levels={stage.catch_levels}
                      periodLabel={`Catch levels differ · ${stage.label}`}
                      periodKey={stage.timeline_key}
                    />
                  )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
