"use client";

import { clsx } from "clsx";
import type { EvidenceStatus } from "../executionPlanModel";

const VERDICT_CLASS: Record<EvidenceStatus, string> = {
  Constructive: "bg-teal-500/15 text-teal-300 border-teal-500/40",
  Neutral: "bg-slate-700/80 text-slate-300 border-slate-600",
  Cautionary: "bg-amber-500/15 text-amber-300 border-amber-500/40",
};

export function SignalBreakdownGrid({
  rows,
  bottomLine,
}: {
  rows: { label: string; status: EvidenceStatus; summary: string }[];
  bottomLine?: string | null;
}) {
  if (rows.length === 0) return null;

  return (
    <div className="rounded-2xl border border-slate-700/50 bg-slate-900/60 p-4">
      <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">Signal breakdown</p>
      <div className="divide-y divide-slate-800/60">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
            <div className="min-w-0 flex-1">
              <p className="text-xs text-slate-300">{row.label}</p>
              <p className="text-[10px] text-slate-600 truncate">{row.summary}</p>
            </div>
            <span
              className={clsx(
                "text-[10px] font-mono px-2 py-0.5 rounded-full border shrink-0",
                VERDICT_CLASS[row.status],
              )}
            >
              {row.status}
            </span>
          </div>
        ))}
      </div>
      {bottomLine && (
        <p className="mt-3 pt-2 border-t border-slate-800 text-xs text-slate-400 leading-snug">
          <span className="text-slate-200 font-medium">Bottom line: </span>
          {bottomLine}
        </p>
      )}
    </div>
  );
}
