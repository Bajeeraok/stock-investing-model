"use client";

import { LayoutDashboard, LineChart, Wallet, Sparkles, TrendingUp, BarChart3 } from "lucide-react";
import { clsx } from "clsx";

const TABS = [
  { id: "overview", label: "Overview", shortcut: "1", icon: LayoutDashboard },
  { id: "signals", label: "Signals", shortcut: "2", icon: LineChart },
  { id: "portfolio", label: "Portfolio", shortcut: "3", icon: Wallet },
  { id: "opportunities", label: "Opportunities", shortcut: "4", icon: Sparkles },
  { id: "markets", label: "Markets", shortcut: "5", icon: TrendingUp },
  { id: "analysis", label: "Analysis", shortcut: "6", icon: BarChart3 },
] as const;

export type TabId = (typeof TABS)[number]["id"];

interface Props {
  active: TabId;
  onChange: (id: TabId) => void;
  badges?: Partial<Record<TabId, number>>;
}

export function DashboardTabs({ active, onChange, badges }: Props) {
  return (
    <div
      role="tablist"
      aria-label="Dashboard sections (1-6 to switch)"
      className="flex gap-0.5 p-1 rounded-xl bg-slate-900/80 border border-slate-700/60 backdrop-blur-sm shadow-inner overflow-x-auto [-webkit-overflow-scrolling:touch] min-h-[44px] touch-manipulation"
    >
      {TABS.map(({ id, label, shortcut, icon: Icon }) => {
        const isActive = active === id;
        const badge = badges?.[id];
        return (
          <button
            key={id}
            role="tab"
            aria-selected={isActive}
            aria-label={`${label}${badge != null ? `, ${badge} items` : ""} (${shortcut})`}
            title={`${label} (${shortcut})`}
            onClick={() => onChange(id)}
            className={`
              relative flex items-center gap-2 px-3 sm:px-4 py-2.5 rounded-lg text-base font-medium transition-all duration-200 shrink-0
              focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950
              ${isActive
                ? "text-emerald-100 bg-gradient-to-b from-emerald-500/20 to-emerald-600/10 text-shadow-sm shadow-emerald-500/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              }
            `}
          >
            {isActive && (
              <span
                className="absolute inset-0 rounded-lg bg-emerald-500/10 ring-1 ring-emerald-500/30 -z-10"
                aria-hidden
              />
            )}
            <Icon className={`h-4 w-4 shrink-0 ${isActive ? "text-emerald-400" : "text-slate-500"}`} strokeWidth={2} />
            <span>{label}</span>
            {badge != null && badge > 0 && (
              <span
                className={clsx(
                  "min-w-[1.25rem] h-5 px-1.5 rounded-md text-xs font-semibold flex items-center justify-center",
                  isActive ? "bg-emerald-500/30 text-emerald-200" : "bg-slate-700 text-slate-300"
                )}
              >
                {badge > 99 ? "99+" : badge}
              </span>
            )}
            <span className="hidden lg:inline text-slate-500 text-xs ml-0.5" aria-hidden>({shortcut})</span>
          </button>
        );
      })}
    </div>
  );
}
