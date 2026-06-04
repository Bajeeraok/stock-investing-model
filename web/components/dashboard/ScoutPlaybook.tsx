"use client";

import { BookOpen } from "lucide-react";
import { ToggleSection } from "./ToggleSection";

/**
 * Phase C3 — Scout open rules from morning checklist (collapsed by default).
 */
export function ScoutPlaybook({
  checklist,
}: {
  checklist?: { time: string; task: string }[] | null;
}) {
  if (!checklist?.length) return null;

  return (
    <ToggleSection
      id="scout-playbook"
      title="Scout open playbook"
      icon={<BookOpen className="h-4 w-4" />}
      defaultOpen={false}
    >
      <ul className="space-y-2">
        {checklist.map((c, i) => (
          <li
            key={`${c.time}-${i}`}
            className="text-sm flex gap-3 rounded-lg border border-slate-600/60 bg-slate-800/40 px-3 py-2"
          >
            <span className="text-violet-300 shrink-0 text-xs font-mono font-semibold min-w-[6.5rem]">
              {c.time}
            </span>
            <span className="text-slate-100 leading-snug">{c.task}</span>
          </li>
        ))}
      </ul>
      <p className="text-[10px] text-slate-500 mt-2">
        Scout mode — quick in/out rules before sizing tactical or earnings plays.
      </p>
    </ToggleSection>
  );
}
