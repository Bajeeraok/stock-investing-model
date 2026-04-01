"use client";

import { BookOpen } from "lucide-react";

/** Methodology & data limits for retail trust (survivorship, PIT, data sources). */
export function KnownLimitsPanel({ items }: { items: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="rounded-lg border border-slate-600/80 bg-slate-900/40 px-3 py-2.5">
      <div className="flex items-center gap-2 text-slate-400 text-xs font-medium mb-2">
        <BookOpen className="h-4 w-4 shrink-0" aria-hidden />
        Known limits (methodology)
      </div>
      <ul className="list-disc list-inside text-xs text-slate-500 space-y-1 leading-snug">
        {items.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
    </div>
  );
}
