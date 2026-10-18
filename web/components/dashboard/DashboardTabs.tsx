"use client";

import { Home, Activity, Target, BarChart3, MoreHorizontal } from "lucide-react";
import { clsx } from "clsx";

/**
 * Five-tab IA from the Thrive Alpha redesign (8 → 5):
 *   Today (was Main) · Signals (+ Roadmaps sub-tab) · Plan (Opportunities + Income)
 *   · Portfolio (+ risk, tax-exit, journal) · More (Markets + Admin, was Mkt + Data).
 * Alerts moved to the header bell; it is a destination, not a tab.
 */
const TABS = [
  { id: "today", label: "Today", shortcut: "1", icon: Home },
  { id: "signals", label: "Signals", shortcut: "2", icon: Activity },
  { id: "plan", label: "Plan", shortcut: "3", icon: Target },
  { id: "portfolio", label: "Portfolio", shortcut: "4", icon: BarChart3 },
  { id: "more", label: "More", shortcut: "5", icon: MoreHorizontal },
] as const;

export type TabId = (typeof TABS)[number]["id"];

export const TAB_IDS: TabId[] = TABS.map((t) => t.id);

/** Old 7-tab ids (localStorage "thrive-tab", ?tab= links) → new tab + sub-view. */
export function migrateLegacyTab(raw: string | null | undefined): { tab: TabId; sub?: string } | null {
  if (!raw) return null;
  if ((TAB_IDS as string[]).includes(raw)) return { tab: raw as TabId };
  switch (raw) {
    case "overview":
      return { tab: "today" };
    case "opportunities":
      return { tab: "plan", sub: "opportunities" };
    case "income":
      return { tab: "plan", sub: "income" };
    case "markets":
      return { tab: "more", sub: "markets" };
    case "analysis":
    case "testsuite":
      return { tab: "more", sub: "admin" };
    default:
      return null;
  }
}

interface Props {
  active: TabId;
  onChange: (id: TabId) => void;
  badges?: Partial<Record<TabId, number>>;
  /** rail = desktop persistent left column · bottom = mobile thumb bar */
  variant?: "rail" | "bottom";
}

export function DashboardTabs({ active, onChange, badges, variant = "rail" }: Props) {
  if (variant === "bottom") {
    return (
      <nav
        role="tablist"
        aria-label="Dashboard sections"
        className="flex px-1 pt-1.5 pb-[max(0.5rem,env(safe-area-inset-bottom))] touch-manipulation bg-td-surface/95 border-t border-td-line backdrop-blur-md"
      >
        {TABS.map(({ id, label, icon: Icon }) => {
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
                "flex flex-1 flex-col items-center justify-center gap-0.5 py-1.5 rounded-lg text-[10.5px] font-medium transition-colors",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40",
                isActive ? "text-td-accent" : "text-td-muted hover:text-td-text",
              )}
            >
              <span className="relative inline-flex">
                <Icon className="h-5 w-5" strokeWidth={2} />
                {badge != null && badge > 0 && (
                  <span className="absolute -top-1 -right-2 min-w-[0.95rem] h-3.5 px-0.5 rounded bg-td-surface2 text-[9px] font-bold text-td-text flex items-center justify-center leading-none">
                    {badge > 99 ? "99+" : badge}
                  </span>
                )}
              </span>
              <span>{label}</span>
            </button>
          );
        })}
      </nav>
    );
  }

  return (
    <nav role="tablist" aria-label="Dashboard sections (1-5 to switch)" aria-orientation="vertical" className="flex flex-col gap-1">
      {TABS.map(({ id, label, shortcut, icon: Icon }) => {
        const isActive = active === id;
        const badge = badges?.[id];
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={isActive}
            title={`${label} (${shortcut})`}
            onClick={() => onChange(id)}
            className={clsx(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-semibold transition-colors border",
              "focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50",
              isActive
                ? "bg-td-accent-weak/60 border-td-accent/30 text-td-text"
                : "border-transparent text-td-muted hover:text-td-text hover:bg-td-surface2/60",
            )}
          >
            <Icon className={clsx("h-[18px] w-[18px] shrink-0", isActive && "text-td-accent")} strokeWidth={2} />
            <span className="flex-1 text-left">{label}</span>
            {badge != null && badge > 0 && (
              <span className="min-w-[1.4rem] h-5 px-1.5 rounded-md text-[11px] font-semibold flex items-center justify-center bg-td-surface2 text-td-muted">
                {badge > 99 ? "99+" : badge}
              </span>
            )}
            <span className="hidden xl:inline text-[10.5px] text-td-muted/70 font-mono" aria-hidden>
              {shortcut}
            </span>
          </button>
        );
      })}
    </nav>
  );
}

/** Segmented sub-view switch used inside Plan (Income sleeve / Opportunities) and More (Markets / Admin). */
export function SubViewSwitch<T extends string>({
  value,
  options,
  onChange,
  className,
}: {
  value: T;
  options: { id: T; label: string; badge?: number }[];
  onChange: (id: T) => void;
  className?: string;
}) {
  return (
    <div className={clsx("flex gap-1 rounded-xl bg-td-surface2/80 border border-td-line p-1 max-w-md", className)} role="tablist">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          role="tab"
          aria-selected={value === o.id}
          onClick={() => onChange(o.id)}
          className={clsx(
            "flex-1 rounded-lg px-3 py-1.5 text-[13px] font-semibold transition-colors",
            value === o.id ? "bg-td-surface text-td-text shadow-sm border border-td-line" : "text-td-muted hover:text-td-text border border-transparent",
          )}
        >
          {o.label}
          {o.badge != null && o.badge > 0 && <span className="ml-1.5 text-[11px] text-td-muted">{o.badge}</span>}
        </button>
      ))}
    </div>
  );
}
