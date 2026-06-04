"use client";

import { useMemo, useState } from "react";
import { clsx } from "clsx";
import type { BuyStagePreview } from "../executionPlanModel";
import {
  catchLevelsFingerprint,
  resolveSharedBridgeZone,
  resolveSharedCatchLevels,
  stageActChipClass,
} from "../executionPlanModel";
import { CatchLevelsRow } from "../zoneContextUX";

const NEAR_TERM_KEYS = ["today", "days_1_10", "week_2_4"];
const BRIDGE_RATIONALE =
  "Bridge zone — partial starter if regime improves; not full position sizing.";

function statusDot(whenToAct: string, isGap?: boolean): string {
  const lower = whenToAct.toLowerCase();
  if (isGap && lower.includes("partial")) return "bg-cyan-400";
  if (isGap && lower.includes("hold")) return "bg-amber-400";
  if (lower.includes("add") || lower.includes("start") || lower.includes("core")) return "bg-teal-400";
  if (lower.includes("watch")) return "bg-slate-500";
  if (lower.includes("patience") || lower.includes("pause") || lower.includes("no")) return "bg-amber-400";
  return "bg-slate-500";
}

function isWatchingAction(whenToAct: string): boolean {
  const l = whenToAct.toLowerCase();
  return (
    l.includes("watch") ||
    l.includes("patience") ||
    l.includes("hold at") ||
    l.includes("hold size")
  );
}

function shouldCollapseWatchPhase(stages: BuyStagePreview[]): boolean {
  const rows = stages.filter((s) => NEAR_TERM_KEYS.includes(s.timeline_key) && !s.is_gap_row);
  if (rows.length < 2) return false;
  if (!rows.every((r) => isWatchingAction(r.when_to_act || ""))) return false;
  const zones = rows.map((r) => `${r.price_zone_low}-${r.price_zone_high}`);
  return new Set(zones).size === 1;
}

function TimelineRow({
  stage,
  isLast,
  currentPrice,
  showSharedCatch,
  sharedCatchFp,
  uniformBridge,
  showRowCatch,
  showRowBridge,
}: {
  stage: BuyStagePreview;
  isLast: boolean;
  currentPrice?: number | null;
  showSharedCatch: boolean;
  sharedCatchFp: string;
  uniformBridge: boolean;
  showRowCatch: boolean;
  showRowBridge: boolean;
}) {
  const isGap = Boolean(stage.is_gap_row);
  const rowCatchFp = catchLevelsFingerprint(stage.catch_levels);
  const gapLabel = stage.label === "Watch Zone" || isGap ? stage.label : stage.label;

  return (
    <div
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
          <span className="text-xs font-medium text-slate-300 shrink-0 min-w-[5.5rem]">{gapLabel}</span>
          <span
            className={clsx(
              "text-xs font-medium px-1.5 py-0.5 rounded shrink-0",
              stageActChipClass(stage.when_to_act),
            )}
          >
            {stage.when_to_act}
          </span>
          <span className="text-[11px] font-mono text-slate-400 sm:ml-auto tabular-nums">
            {isGap && !stage.label?.includes("Watch") ? "Gap span " : ""}$
            {stage.price_zone_low.toFixed(2)}–${stage.price_zone_high.toFixed(2)}
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
        {isGap && stage.bridge_zone_low != null && stage.bridge_zone_high != null && showSharedCatch && (
          <p className="text-[10px] text-slate-400 mt-1 leading-snug">{BRIDGE_RATIONALE}</p>
        )}
        {showRowCatch && (
          <CatchLevelsRow
            levels={stage.catch_levels}
            currentPrice={currentPrice}
            bridgeLow={showRowBridge ? stage.bridge_zone_low : undefined}
            bridgeHigh={showRowBridge ? stage.bridge_zone_high : undefined}
            bridgeRationale={showRowBridge ? BRIDGE_RATIONALE : undefined}
            sharedLabel={`Catch levels · ${stage.label}`}
            periodKey={stage.timeline_key}
          />
        )}
        {showSharedCatch &&
          rowCatchFp &&
          rowCatchFp !== sharedCatchFp &&
          stage.catch_levels &&
          stage.catch_levels.length > 0 && (
            <CatchLevelsRow
              levels={stage.catch_levels}
              currentPrice={currentPrice}
              sharedLabel={`Catch levels differ · ${stage.label}`}
              periodKey={stage.timeline_key}
            />
          )}
      </div>
    </div>
  );
}

export function RoadmapTimeline({
  stages,
  title,
  currentPrice,
}: {
  stages: BuyStagePreview[];
  title?: string;
  currentPrice?: number | null;
}) {
  const [timelineExpanded, setTimelineExpanded] = useState(false);

  const collapseWatch = useMemo(() => shouldCollapseWatchPhase(stages), [stages]);

  const displayStages = useMemo(() => {
    if (!collapseWatch || timelineExpanded) return stages;
    const hidden = new Set(["days_1_10", "week_2_4"]);
    const today = stages.find((s) => s.timeline_key === "today");
    const filtered = stages.filter((s) => !hidden.has(s.timeline_key));
    if (!today) return filtered;
    const collapsedToday: BuyStagePreview = {
      ...today,
      label: "Current phase",
      when_to_act: today.when_to_act || "Watching",
      condition:
        "Today through week 2–4 share the same watch band — expand for day-by-day breakdown.",
    };
    return filtered.map((s) => (s.timeline_key === "today" ? collapsedToday : s));
  }, [stages, collapseWatch, timelineExpanded]);

  if (stages.length === 0) return null;

  const { shared: sharedCatch, uniform: uniformCatch } = resolveSharedCatchLevels(stages);
  const { uniform: uniformBridge, low: sharedBridgeLow, high: sharedBridgeHigh } =
    resolveSharedBridgeZone(stages);
  const showSharedCatch = uniformCatch && sharedCatch != null && sharedCatch.length > 0;
  const sharedCatchFp = catchLevelsFingerprint(sharedCatch);

  return (
    <div className="rounded-2xl border border-slate-700/50 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        {title ? (
          <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500">{title}</p>
        ) : (
          <span />
        )}
        {collapseWatch && (
          <button
            type="button"
            onClick={() => setTimelineExpanded((v) => !v)}
            className="text-[10px] text-cyan-400/90 hover:text-cyan-300"
          >
            {timelineExpanded ? "Collapse periods" : "Expand Today · Days 1–10 · Week 2–4"}
          </button>
        )}
      </div>

      {showSharedCatch && (
        <div className="mb-3 pb-3 border-b border-slate-700/60 space-y-2">
          <CatchLevelsRow
            levels={sharedCatch}
            currentPrice={currentPrice}
            bridgeLow={uniformBridge ? sharedBridgeLow : undefined}
            bridgeHigh={uniformBridge ? sharedBridgeHigh : undefined}
            bridgeRationale={uniformBridge ? BRIDGE_RATIONALE : undefined}
            sharedLabel="Catch levels valid across all watch periods"
          />
          <p className="text-[10px] text-slate-600 leading-snug">
            Rows below differ by <span className="text-slate-500">when to act</span>, not price steps.
          </p>
        </div>
      )}

      <div>
        {displayStages.map((stage, i) => {
          const isLast = i === displayStages.length - 1;
          const showRowCatch =
            !showSharedCatch && stage.catch_levels != null && stage.catch_levels.length > 0;
          const showRowBridge =
            !showSharedCatch &&
            !uniformBridge &&
            stage.bridge_zone_low != null &&
            stage.bridge_zone_high != null;

          return (
            <TimelineRow
              key={`${stage.timeline_key}-${stage.label}`}
              stage={stage}
              isLast={isLast}
              currentPrice={currentPrice}
              showSharedCatch={showSharedCatch}
              sharedCatchFp={sharedCatchFp}
              uniformBridge={uniformBridge}
              showRowCatch={showRowCatch}
              showRowBridge={showRowBridge}
            />
          );
        })}
      </div>
    </div>
  );
}
