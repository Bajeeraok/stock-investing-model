"use client";

/**
 * Smart DCA — dedicated SPY/QQQ index-timing section.
 *
 * Same total dollars, better entry points: the panel reads the model's own
 * gate/zone state on the index rows and turns it into a tranche decision —
 * ACCELERATE (pull next tranche forward into the dip), ON SCHEDULE (deploy the
 * calendar tranche only), or HOLD (park the tranche in cash until the band).
 *
 * Framing: DCA is the default; this only reschedules tranches, never skips
 * them outright — validated against the measured cohort edges (30–50 dip
 * bucket +2.6%/21d excess vs SPY; full_go +3.6%).
 */
import React from "react";
import { TrendingUp, TrendingDown, Pause, CalendarClock } from "lucide-react";
import { clsx } from "clsx";
import type { Signal } from "@/app/page";

type DcaAction = "accelerate" | "on_schedule" | "hold";

const ACTION_META: Record<DcaAction, { label: string; chip: string; icon: React.ReactNode; hint: string }> = {
  accelerate: {
    label: "ACCELERATE",
    chip: "border-td-accent/50 bg-td-accent/15 text-td-accent",
    icon: <TrendingUp className="h-3.5 w-3.5" aria-hidden />,
    hint: "Index in an actionable dip zone — pull the next tranche forward.",
  },
  on_schedule: {
    label: "ON SCHEDULE",
    chip: "border-td-warn/45 bg-td-warn/10 text-td-warn",
    icon: <CalendarClock className="h-3.5 w-3.5" aria-hidden />,
    hint: "Deploy this period's tranche normally — no edge either way.",
  },
  hold: {
    label: "HOLD TRANCHE",
    chip: "border-td-crit/45 bg-td-crit/10 text-td-crit",
    icon: <Pause className="h-3.5 w-3.5" aria-hidden />,
    hint: "Optional: park this tranche until price is back in the band. Waiting has been roughly break-even historically.",
  },
};

function dcaActionFor(r: Signal): { action: DcaAction; reason: string } {
  const score = r.composite_buy;
  const em = (r.entry_mode || "").toLowerCase();
  const dipZone =
    score != null && 30 <= score && score < 50 && (em === "starter_only" || em === "full_go");

  const band = r.st_band;
  const cp = r.close;
  let bandNote = "";
  if (cp != null && band?.low != null && band?.high != null) {
    if (cp < band.low) {
      bandNote = ` · ${(((band.low - cp) / cp) * 100).toFixed(1)}% below band $${band.low.toFixed(0)}–$${band.high.toFixed(0)}`;
    } else if (cp > band.high) {
      bandNote = ` · ${(((cp - band.high) / band.high) * 100).toFixed(1)}% above band`;
    } else {
      bandNote = " · inside entry band";
    }
  }

  if (dipZone || em === "full_go") {
    return {
      action: "accelerate",
      reason: dipZone ? "Dip-zone cohort — the measured edge" : "Gates clear — actionable entry",
    };
  }
  if (em === "starter_only") {
    return { action: "on_schedule", reason: "Partial setup — scheduled tranche only, keep powder dry" };
  }
  if (em === "hard_lock" && cp != null && band?.high != null && cp > band.high * 1.08) {
    return { action: "hold", reason: `Chasing — spot ${(((cp - band.high) / band.high) * 100).toFixed(0)}% above band` };
  }
  return {
    action: em === "hard_lock" ? "hold" : "on_schedule",
    reason: em === "hard_lock" ? "No margin of safety at spot — optional pause" : "No edge — keep the schedule",
  };
}

export function SmartDcaPanel({ signals }: { signals: Signal[] }) {
  const idx = signals.filter((s) => s.ticker === "SPY" || s.ticker === "QQQ");
  if (idx.length === 0) return null;

  return (
    <section className="rounded-xl border border-td-line bg-td-surface/60 overflow-hidden mb-3">
      <div className="px-4 py-2.5 border-b border-td-line/70 flex items-center justify-between gap-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-td-muted">
          Smart DCA — index tranche timing
        </p>
        <p className="text-[10px] text-td-muted normal-case">
          Same dollars, better entries — timing the schedule, not stock-picking
        </p>
      </div>
      <div className="grid sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-td-line/60">
        {idx.map((r) => {
          const { action, reason } = dcaActionFor(r);
          const meta = ACTION_META[action];
          const unlock = r.retail_status?.unlock_summary ?? r.retail_status?.unlock_sequence ?? null;
          return (
            <div key={r.ticker} className="px-4 py-3 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className="font-mono text-sm font-bold text-td-text">{r.ticker}</span>
                  {r.close != null && (
                    <span className="font-mono text-xs text-td-muted tabular-nums">${r.close.toFixed(2)}</span>
                  )}
                  {r.composite_buy != null && (
                    <span className="text-[10px] text-td-muted tabular-nums">score {Math.round(r.composite_buy)}</span>
                  )}
                </div>
                <span className={clsx("inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded border shrink-0", meta.chip)}>
                  {meta.icon}
                  {meta.label}
                </span>
              </div>
              <p className="text-xs text-td-text leading-snug">
                {reason}
                <span className="text-td-muted">{ACTION_META[action].hint ? "" : ""}</span>
              </p>
              <p className="text-[11px] text-td-muted leading-snug">{meta.hint}</p>
              {unlock && <p className="text-[11px] text-td-info/90 leading-snug">{unlock}</p>}
            </div>
          );
        })}
      </div>
    </section>
  );
}
