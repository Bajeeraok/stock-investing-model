"use client";

import { LayoutDashboard, LineChart, Wallet, Sparkles, TrendingUp, BarChart3, LayoutGrid } from "lucide-react";
import { clsx } from "clsx";

const TABS = [
  { id: "overview",    label: "Overview",    compactLabel: "Main",    shortcut: "1", icon: LayoutDashboard },
  { id: "signals",     label: "Signals",     compactLabel: "Signals", shortcut: "2", icon: LineChart       },
  { id: "roadmaps",    label: "Roadmaps",    compactLabel: "Roads",   shortcut: "7", icon: LayoutGrid      },
  { id: "portfolio",   label: "Portfolio",   compactLabel: "Port",    shortcut: "3", icon: Wallet          },
  { id: "opportunities", label: "Opportunities", compactLabel: "Opps", shortcut: "4", icon: Sparkles    },
  { id: "markets",     label: "Markets",     compactLabel: "Mkt",     shortcut: "5", icon: TrendingUp      },
  { id: "analysis",    label: "Analysis",    compactLabel: "Data",    shortcut: "6", icon: BarChart3       },
] as const;

export type TabId = (typeof TABS)[number]["id"];

const ADVANCED_TAB_IDS = new Set<TabId>(["analysis"]);

interface Props {
  active: TabId;
  onChange: (id: TabId) => void;
  badges?: Partial<Record<TabId, number>>;
  /** Hide Analysis unless power-user mode */
  advancedMode?: boolean;
  /** Compact bottom bar (mobile) — icon-first, thumb-friendly */
  variant?: "default" | "bottom";
}

export function DashboardTabs({ active, onChange, badges, advancedMode = false, variant = "default" }: Props) {
  const visibleTabs = TABS.filter((t) => advancedMode || !ADVANCED_TAB_IDS.has(t.id));
  if (variant === "bottom") {
    return (
      <nav
        role="tablist"
        aria-label="Dashboard sections"
        className="flex gap-0.5 px-1 pt-1 pb-[max(0.5rem,env(safe-area-inset-bottom))] overflow-x-auto [-webkit-overflow-scrolling:touch] touch-manipulation bg-slate-950/95 border-t border-slate-800/90 backdrop-blur-md supports-[backdrop-filter]:bg-slate-950/80"
      >
        {visibleTabs.map(({ id, label, compactLabel, icon: Icon }) => {
          const isActive = active === id;
          const badge = badges?.[id];
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-label={label}
              onClick={() => onChange(id)}
              className={clsx(
                "flex flex-col items-center justify-center gap-0.5 flex-1 min-w-[3.25rem] max-w-[5.5rem] py-2 rounded-lg text-[10px] font-medium transition-colors",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40",
                isActive ? "text-emerald-300 bg-emerald-500/15" : "text-slate-500 hover:text-slate-200 hover:bg-slate-800/50",
              )}
            >
              <span className="relative inline-flex">
                <Icon className={clsx("h-5 w-5", isActive ? "text-emerald-400" : "text-slate-500")} strokeWidth={2} />
                {badge != null && badge > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[0.95rem] h-3.5 px-0.5 rounded bg-emerald-600 text-[9px] font-bold text-white flex items-center justify-center leading-none">
                    {badge > 99 ? "99+" : badge}
                  </span>
                )}
              </span>
              <span className="truncate w-full text-center leading-tight px-0.5">{compactLabel}</span>
            </button>
          );
        })}
      </nav>
    );
  }

  return (
    <div
      role="tablist"
      aria-label="Dashboard sections (1-7 to switch)"
      className="flex gap-0.5 p-1 rounded-xl bg-slate-900/80 border border-slate-700/60 backdrop-blur-sm shadow-inner overflow-x-auto [-webkit-overflow-scrolling:touch] min-h-[44px] touch-manipulation"
    >
      {visibleTabs.map(({ id, label, shortcut, icon: Icon }) => {
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
