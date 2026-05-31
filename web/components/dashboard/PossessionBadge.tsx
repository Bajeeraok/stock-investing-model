"use client";

import { clsx } from "clsx";

export type PositionStatus = "owned" | "watching" | "universe";

const STYLES: Record<PositionStatus, { label: string; className: string }> = {
  owned: { label: "Owning", className: "border-emerald-500/40 bg-emerald-500/15 text-emerald-200" },
  watching: { label: "Watching", className: "border-sky-500/40 bg-sky-500/15 text-sky-200" },
  universe: { label: "Scan", className: "border-slate-600 bg-slate-800/80 text-slate-400" },
};

export function PossessionBadge({ status }: { status: PositionStatus | string | null | undefined }) {
  const key = (status === "owned" || status === "watching" || status === "universe"
    ? status
    : "universe") as PositionStatus;
  const s = STYLES[key];
  return (
    <span
      className={clsx(
        "inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide border",
        s.className,
      )}
    >
      {s.label}
    </span>
  );
}
