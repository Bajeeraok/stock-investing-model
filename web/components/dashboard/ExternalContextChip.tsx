"use client";

import { clsx } from "clsx";
import { Globe } from "lucide-react";

export type ExternalContextPayload = {
  rsi?: number | null;
  rsi_zone?: string | null;
  ma_alignment?: string | null;
  tags?: string[];
  screener_alignment?: string | null;
  summary_line?: string | null;
  source_note?: string | null;
};

const ALIGN_STYLE: Record<string, string> = {
  agree_trend: "border-emerald-500/30 bg-emerald-950/25 text-emerald-100",
  agree_dip: "border-emerald-500/30 bg-emerald-950/25 text-emerald-100",
  mixed: "border-amber-500/30 bg-amber-950/25 text-amber-100",
  caution: "border-red-500/25 bg-red-950/20 text-red-100",
};

export function ExternalContextChip({ context }: { context: ExternalContextPayload | null | undefined }) {
  if (!context?.summary_line) return null;
  const align = context.screener_alignment ?? "mixed";
  const tags = context.tags ?? [];

  return (
    <div
      className={clsx(
        "rounded-lg border px-3 py-2.5 space-y-1.5",
        ALIGN_STYLE[align] ?? ALIGN_STYLE.mixed,
      )}
      title={context.source_note ?? undefined}
    >
      <p className="text-[10px] uppercase tracking-wide font-semibold text-slate-400 flex items-center gap-1.5">
        <Globe className="h-3.5 w-3.5 shrink-0 opacity-80" />
        How popular screeners read this tape
      </p>
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tags.map((t) => (
            <span
              key={t}
              className="text-[10px] px-1.5 py-0.5 rounded border border-slate-600/80 bg-slate-900/50 text-slate-300 tabular-nums"
            >
              {t}
            </span>
          ))}
        </div>
      )}
      <p className="text-xs leading-snug">{context.summary_line}</p>
      {context.source_note && (
        <p className="text-[10px] text-slate-500 leading-snug">{context.source_note}</p>
      )}
    </div>
  );
}
