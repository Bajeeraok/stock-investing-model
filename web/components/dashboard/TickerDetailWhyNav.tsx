"use client";

import { clsx } from "clsx";
import { BarChart3, FileText, Shield } from "lucide-react";

export type WhySubTab = "valuation" | "proof" | "context";

const TABS: { id: WhySubTab; label: string; icon: typeof BarChart3 }[] = [
  { id: "valuation", label: "Valuation & scenarios", icon: BarChart3 },
  { id: "proof", label: "Model proof", icon: Shield },
  { id: "context", label: "Context", icon: FileText },
];

export function TickerDetailWhyNav({
  active,
  onChange,
}: {
  active: WhySubTab;
  onChange: (tab: WhySubTab) => void;
}) {
  return (
    <div className="sticky top-[52px] z-[14] -mx-4 sm:-mx-6 px-4 sm:px-6 py-2 bg-slate-900/95 border-b border-slate-700/80 backdrop-blur-sm">
      <div className="flex gap-1 rounded-lg bg-slate-800/60 p-1 border border-slate-700/60">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            className={clsx(
              "flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-md text-xs font-medium transition-colors min-w-0",
              active === id
                ? "bg-emerald-600/90 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-700/50",
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
