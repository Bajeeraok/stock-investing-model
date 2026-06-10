"use client";

import { clsx } from "clsx";

interface LevelsSummaryProps {
  action?: string | null;
  nextLevel?: number | null;
  fairValue?: number | null;
  entryMode?: "hard_lock" | "starter_only" | "full_go" | null;
  unlockSequence?: string | null;
}

const MODE_STYLE: Record<string, { border: string; bg: string; badge: string; dot: string }> = {
  full_go:      { border: "border-emerald-500/40", bg: "bg-emerald-950/30",  badge: "border-emerald-500/50 bg-emerald-500/15 text-emerald-200",  dot: "bg-emerald-400" },
  starter_only: { border: "border-amber-500/40",   bg: "bg-amber-950/25",    badge: "border-amber-500/40 bg-amber-500/10 text-amber-200",         dot: "bg-amber-400"   },
  hard_lock:    { border: "border-red-500/35",      bg: "bg-red-950/25",      badge: "border-red-500/35 bg-red-500/10 text-red-200",               dot: "bg-red-400"     },
};

const MODE_LABEL: Record<string, string> = {
  full_go:      "FULL GO",
  starter_only: "STARTER ONLY",
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
  const style = MODE_STYLE[entryMode ?? ""] ?? MODE_STYLE.starter_only;

  return (
    <div className={clsx(
      "rounded-xl border backdrop-blur-sm p-3 flex flex-col gap-3",
      style.border,
      style.bg,
    )}>
      {/* At-a-glance row */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Action</span>
          <span className="text-xs font-bold text-slate-100 truncate">{action ?? "—"}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Next Level</span>
          <span className="text-xs font-mono font-bold text-amber-300 tabular-nums">{fmt(nextLevel)}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Fair Value</span>
          <span className="text-xs font-mono font-bold text-cyan-300 tabular-nums">{fmt(fairValue)}</span>
        </div>
      </div>

      {/* Entry mode badge */}
      {entryMode && (
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className={clsx("w-1.5 h-1.5 rounded-full", style.dot)} />
            <span className="text-[9px] text-slate-500 uppercase font-semibold">Entry mode</span>
          </div>
          <span className={clsx(
            "text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full border",
            style.badge,
          )}>
            {MODE_LABEL[entryMode] ?? entryMode}
          </span>
        </div>
      )}

      {/* Unlock sequence (compact) */}
      {unlockSequence && entryMode !== "full_go" && (
        <p className="text-[9px] text-slate-400 leading-snug border-t border-white/5 pt-2">
          {unlockSequence}
        </p>
      )}
    </div>
  );
}
