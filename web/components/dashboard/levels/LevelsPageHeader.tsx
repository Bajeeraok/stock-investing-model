"use client";

import { clsx } from "clsx";

interface LevelsSummaryProps {
  action?: string | null;
  nextLevel?: number | null;
  fairValue?: number | null;
  entryMode?: "hard_lock" | "starter_only" | "full_go" | null;
  unlockSequence?: string | null;
}

const MODE_BADGE: Record<string, string> = {
  full_go:      "border-td-accent/50 bg-td-accent/15 text-td-accent-ink",
  starter_only: "border-td-warn/40  bg-td-warn/10  text-td-warn",
  hard_lock:    "border-td-crit/35    bg-td-crit/10    text-td-crit",
};
const MODE_DOT: Record<string, string> = {
  full_go:      "bg-td-accent",
  starter_only: "bg-td-warn",
  hard_lock:    "bg-td-crit",
};
const MODE_LABEL: Record<string, string> = {
  full_go:      "FULL GO",
  starter_only: "STARTER",
  hard_lock:    "HARD LOCK",
};

function fmt(v: number | null | undefined): string {
  if (!v) return "—";
  return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function LevelsPageHeader({
  action,
  nextLevel,
  fairValue,
  entryMode,
  unlockSequence,
}: LevelsSummaryProps) {
  const mode = entryMode ?? "";

  return (
    <div className="space-y-1">
      {/* Single compact row */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Entry mode pill */}
        {entryMode && (
          <span className={clsx(
            "inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded-full border",
            MODE_BADGE[mode] ?? MODE_BADGE.starter_only,
          )}>
            <span className={clsx("w-1 h-1 rounded-full", MODE_DOT[mode] ?? "bg-td-line")} />
            {MODE_LABEL[mode] ?? mode}
          </span>
        )}

        {/* Action */}
        {action && (
          <span className="text-[10px] font-semibold text-td-text truncate max-w-[140px]">
            {action}
          </span>
        )}

        <span className="text-td-muted text-[10px] select-none">·</span>

        {/* Next Level */}
        {nextLevel != null && (
          <span className="text-[10px] text-td-muted">
            Next <span className="font-mono font-semibold text-td-warn tabular-nums">{fmt(nextLevel)}</span>
          </span>
        )}

        <span className="text-td-muted text-[10px] select-none">·</span>

        {/* Fair Value */}
        {fairValue != null && (
          <span className="text-[10px] text-td-muted">
            FV <span className="font-mono font-semibold text-td-info tabular-nums">{fmt(fairValue)}</span>
          </span>
        )}
      </div>

      {/* Unlock hint — single truncated line */}
      {unlockSequence && entryMode !== "full_go" && (
        <p className="text-[9px] text-td-muted leading-snug truncate" title={unlockSequence}>
          {unlockSequence}
        </p>
      )}
    </div>
  );
}
