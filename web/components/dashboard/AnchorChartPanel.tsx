"use client";

import type { ReactNode } from "react";

/**
 * Single chrome for “tape” charts — reuse across Overview / Portfolio so charts feel like one product surface.
 */
export function AnchorChartPanel({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-700/90 bg-slate-900/40 overflow-hidden">
      <div className="px-4 py-3 sm:px-5 border-b border-slate-700/80 bg-slate-900/60">
        <h3 className="text-sm font-semibold text-slate-200 tracking-tight">{title}</h3>
        {hint ? <p className="text-[11px] text-slate-500 mt-1 leading-snug">{hint}</p> : null}
      </div>
      <div className="p-4 sm:p-5 grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6">{children}</div>
    </div>
  );
}
