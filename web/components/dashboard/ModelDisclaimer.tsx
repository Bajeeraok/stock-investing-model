"use client";

import { ShieldAlert } from "lucide-react";

/** Single reusable legal/model disclaimer — keep copy short; link to known limits for detail. */
export function ModelDisclaimer({ className }: { className?: string }) {
  return (
    <p
      className={className ?? "text-[10px] text-slate-600 leading-snug flex items-start gap-1.5"}
      role="note"
    >
      <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-slate-600 mt-0.5" aria-hidden />
      <span>
        Educational model output only — not investment advice, not a fiduciary recommendation, and not a
        promise of results. Past performance does not guarantee future returns.
      </span>
    </p>
  );
}
