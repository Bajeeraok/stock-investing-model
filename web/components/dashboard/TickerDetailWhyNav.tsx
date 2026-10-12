"use client";

import { clsx } from "clsx";
import { BarChart3, Shield } from "lucide-react";

/** Context used to be a third option here — it's now its own top-level ticker-detail tab
 * (see TickerDetailModal's modalTab), so this nav only ever switches between these two. */
export type WhySubTab = "valuation" | "proof";

const TABS: { id: WhySubTab; label: string; icon: typeof BarChart3 }[] = [
  { id: "valuation", label: "Valuation & scenarios", icon: BarChart3 },
  { id: "proof", label: "Model proof", icon: Shield },
];

export function TickerDetailWhyNav({
  active,
  onChange,
}: {
  active: WhySubTab;
  onChange: (tab: WhySubTab) => void;
}) {
  return (
    <div className="sticky top-[52px] z-[14] -mx-4 sm:-mx-6 px-4 sm:px-6 py-2 bg-td-surface/95 border-b border-td-line backdrop-blur-sm">
      <div className="flex gap-1 rounded-lg bg-td-surface2/60 p-1 border border-td-line">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            className={clsx(
              "flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-md text-xs font-medium transition-colors min-w-0",
              active === id
                ? "bg-td-accent text-slate-950 shadow-sm"
                : "text-td-muted hover:text-td-text hover:bg-td-surface2",
            )}
          >
            <Icon className="h-3.5 w-3.5 shrink-0 hidden sm:block" />
            <span className="truncate">{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
