"use client";

import { AlertTriangle } from "lucide-react";
import { clsx } from "clsx";

export type DegradedSource = {
  source: string;
  status: "ok" | "degraded" | "unavailable" | string;
  message: string;
};

interface Props {
  degradedMode?: boolean;
  sources?: DegradedSource[] | null;
  compact?: boolean;
}

/** Phase D5 — show when vendors partially fail. */
export function DegradedDataBanner({ degradedMode, sources, compact }: Props) {
  const problems = (sources || []).filter((s) => s.status !== "ok");
  if (!degradedMode && problems.length === 0) return null;

  const summary = problems.length
    ? problems.map((p) => `${p.source}: ${p.message}`).join(" · ")
    : "Some data sources may be limited — signals use fallbacks where wired.";

  return (
    <div
      className={clsx(
        "rounded-lg border px-3 py-2 flex items-start gap-2",
        compact ? "text-xs" : "text-sm",
        "border-amber-500/30 bg-amber-950/20 text-amber-100/90",
      )}
      role="status"
    >
      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
      <div className="min-w-0">
        <p className="font-medium text-amber-200/95">Degraded data mode</p>
        <p className="text-amber-100/80 leading-snug mt-0.5">{summary}</p>
      </div>
    </div>
  );
}
