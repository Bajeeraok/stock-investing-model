"use client";

import { clsx } from "clsx";
import { Zap } from "lucide-react";

export type TacticalEntryPayload = {
  active?: boolean;
  /** True when RVOL/BB rules fired (same as paper-trading tactical track). */
  velocity_triggered?: boolean;
  /** Backend hint: show velocity strip even when not fully triggered (watch band). */
  show_panel?: boolean;
  track?: string;
  velocity_score?: number | null;
  rvol?: number | null;
  bb_pct_b?: number | null;
  reasons?: string[];
  entry?: number | null;
  target_1?: number | null;
  target_2?: number | null;
  stop?: number | null;
  rr_ratio?: number | null;
  horizon_trading_days?: number;
  expiry_note?: string | null;
  gates_passed?: number | null;
  gates_total?: number | null;
  go_no_go?: string | null;
};

export function TacticalEntryPanel({
  payload,
  layout = "planner",
}: {
  payload: TacticalEntryPayload | null | undefined;
  layout?: "scout" | "planner";
}) {
  if (!payload) return null;
  const triggered = Boolean(payload.active || payload.velocity_triggered);
  const show =
    payload.show_panel ??
    (triggered ||
      (payload.velocity_score != null && payload.velocity_score >= 40) ||
      payload.track === "velocity");
  if (!show) return null;

  const horizon = payload.horizon_trading_days ?? 5;
  const compact = layout === "scout";
  const watchOnly = !triggered;

  return (
    <div
      className={clsx(
        "border-b",
        watchOnly ? "border-violet-500/15 bg-violet-950/15" : "border-violet-500/25 bg-violet-950/30",
        compact ? "px-3 py-2 sm:px-5" : "px-4 py-3 sm:px-6",
      )}
    >
      <div className="flex items-start gap-2">
        <Zap className={clsx("h-4 w-4 mt-0.5 shrink-0", watchOnly ? "text-violet-400/70" : "text-violet-400")} />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-200">
            {watchOnly
              ? "Velocity watch (RVOL / BB)"
              : layout === "scout"
                ? "Scout — tactical breakout"
                : "Planner — quick in/out"}
          </p>
          {!compact && (
            <p className="text-[11px] text-slate-400 mt-1 leading-snug">
              Velocity flagged (RVOL / Bollinger). Gates logged for context — not required for this track.
              {payload.go_no_go === "go"
                ? " Full GO also clear."
                : payload.gates_passed != null
                  ? ` ${payload.gates_passed}/${payload.gates_total ?? 4} gates pass.`
                  : ""}
            </p>
          )}
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-slate-300 tabular-nums">
            {payload.rvol != null && <span>RVOL {payload.rvol}×</span>}
            {payload.bb_pct_b != null && <span>BB %B {payload.bb_pct_b.toFixed(2)}</span>}
            {payload.velocity_score != null && <span>Score {Math.round(payload.velocity_score)}</span>}
            {payload.entry != null && <span>Entry ~${payload.entry.toFixed(2)}</span>}
            {payload.target_1 != null && <span>T1 ${payload.target_1.toFixed(2)}</span>}
            {payload.target_2 != null && <span>T2 ${payload.target_2.toFixed(2)}</span>}
            {payload.stop != null && <span>Stop ${payload.stop.toFixed(2)}</span>}
            {payload.rr_ratio != null && <span>R:R {payload.rr_ratio}×</span>}
            <span className="text-violet-300/90">T+{horizon}d</span>
          </div>
          {(payload.reasons?.length ?? 0) > 0 && !compact && (
            <p className="text-[11px] text-slate-500 mt-1">{payload.reasons!.slice(0, 2).join(" · ")}</p>
          )}
          {payload.expiry_note && !compact && (
            <p className="text-[11px] text-amber-300/80 mt-1">{payload.expiry_note}</p>
          )}
        </div>
      </div>
    </div>
  );
}
