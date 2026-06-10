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
  full_go:      "border-emerald-500/50 bg-emerald-500/15 text-emerald-200",
  starter_only: "border-amber-500/40  bg-amber-500/10  text-amber-200",
  hard_lock:    "border-red-500/35    bg-red-500/10    text-red-300",
};
const MODE_DOT: Record<string, string> = {
  full_go:      "bg-emerald-400",
  starter_only: "bg-amber-400",
  hard_lock:    "bg-red-400",
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
            <span className={clsx("w-1 h-1 rounded-full", MODE_DOT[mode] ?? "bg-slate-400")} />
            {MODE_LABEL[mode] ?? mode}
          </span>
        )}

        {/* Action */}
        {action && (
          <span className="text-[10px] font-semibold text-slate-200 truncate max-w-[140px]">
            {action}
          </span>
        )}

        <span className="text-slate-700 text-[10px] select-none">·</span>

        {/* Next Level */}
        {nextLevel != null && (
          <span className="text-[10px] text-slate-400">
            Next <span className="font-mono font-semibold text-amber-300 tabular-nums">{fmt(nextLevel)}</span>
          </span>
        )}

        <span className="text-slate-700 text-[10px] select-none">·</span>

        {/* Fair Value */}
        {fairValue != null && (
          <span className="text-[10px] text-slate-400">
            FV <span className="font-mono font-semibold text-cyan-300 tabular-nums">{fmt(fairValue)}</span>
          </span>
        )}
      </div>

      {/* Unlock hint — single truncated line */}
      {unlockSequence && entryMode !== "full_go" && (
        <p className="text-[9px] text-slate-500 leading-snug truncate" title={unlockSequence}>
          {unlockSequence}
        </p>
      )}
    </div>
  );
}
