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
  /** Fused with One Answer — avoids reading breakout as "buy now". */
  action_today?: string | null;
  entry_stance?: string | null;
  stance_headline?: string | null;
  stance_note?: string | null;
  one_answer_verdict?: string | null;
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
  const headline =
    payload.stance_headline ??
    (watchOnly
      ? "Velocity watch (RVOL / BB)"
      : layout === "scout"
        ? "Scout — tactical breakout"
        : "Planner — quick in/out");
  const chaseAction =
    payload.action_today === "hold" ||
    payload.action_today === "wait_for_pullback" ||
    payload.action_today === "no_new_position";

  return (
    <div
      className={clsx(
        "border-b",
        watchOnly ? "border-td-owner/15 bg-td-owner-weak/15" : "border-td-owner/25 bg-td-owner-weak/30",
        compact ? "px-3 py-2 sm:px-5" : "px-4 py-3 sm:px-6",
      )}
    >
      <div className="flex items-start gap-2">
        <Zap className={clsx("h-4 w-4 mt-0.5 shrink-0", watchOnly ? "text-td-owner/70" : "text-td-owner")} />
        <div className="min-w-0 flex-1">
          <p
            className={clsx(
              "text-xs font-semibold uppercase tracking-wide",
              triggered && chaseAction ? "text-td-warn" : "text-td-owner",
            )}
          >
            {headline}
          </p>
          {payload.stance_note && (
            <p
              className={clsx(
                "text-[11px] mt-1 leading-snug",
                triggered && chaseAction ? "text-td-warn/90" : "text-td-muted",
              )}
            >
              {payload.stance_note}
            </p>
          )}
          {!compact && !payload.stance_note && (
            <p className="text-[11px] text-td-muted mt-1 leading-snug">
              Velocity flagged (RVOL / Bollinger). Separate from 4-gate GO — follow One Answer for sizing today.
              {payload.go_no_go === "go"
                ? " Full GO also clear."
                : payload.gates_passed != null
                  ? ` ${payload.gates_passed}/${payload.gates_total ?? 4} gates pass.`
                  : ""}
            </p>
          )}
          {triggered && chaseAction && payload.one_answer_verdict && (
            <p className="text-[10px] text-td-muted mt-1">
              Horizon read: {payload.one_answer_verdict} · Execution today: hold/watch (see bottom line)
            </p>
          )}
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-td-text tabular-nums">
            {payload.rvol != null && <span>RVOL {payload.rvol}×</span>}
            {payload.bb_pct_b != null && <span>BB %B {payload.bb_pct_b.toFixed(2)}</span>}
            {payload.velocity_score != null && <span>Score {Math.round(payload.velocity_score)}</span>}
            {payload.entry != null && <span>Entry ~${payload.entry.toFixed(2)}</span>}
            {payload.target_1 != null && <span>T1 ${payload.target_1.toFixed(2)}</span>}
            {payload.target_2 != null && <span>T2 ${payload.target_2.toFixed(2)}</span>}
            {payload.stop != null && <span>Stop ${payload.stop.toFixed(2)}</span>}
            {payload.rr_ratio != null && <span>R:R {payload.rr_ratio}×</span>}
            <span className="text-td-owner/90">T+{horizon}d</span>
          </div>
          {(payload.reasons?.length ?? 0) > 0 && !compact && (
            <p className="text-[11px] text-td-muted mt-1">{payload.reasons!.slice(0, 2).join(" · ")}</p>
          )}
          {payload.expiry_note && !compact && (
            <p className="text-[11px] text-td-warn/80 mt-1">{payload.expiry_note}</p>
          )}
        </div>
      </div>
    </div>
  );
}
