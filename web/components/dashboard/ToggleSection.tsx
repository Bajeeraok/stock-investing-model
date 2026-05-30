"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { clsx } from "clsx";

interface Props {
  id: string;
  title: string;
  icon: React.ReactNode;
  defaultOpen?: boolean;
  badge?: string | number | null;
  className?: string;
  /** Keep children mounted when collapsed (avoids refetch flicker for AlertsPanel). */
  keepMounted?: boolean;
  children: React.ReactNode;
}

export function ToggleSection({
  id,
  title,
  icon,
  defaultOpen = true,
  badge,
  className,
  keepMounted = false,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={clsx("rounded-xl border border-slate-700 overflow-hidden", className)}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-2 sm:gap-3 px-3 sm:px-5 py-3.5 sm:py-4 bg-slate-800 hover:bg-slate-700/80 transition text-left group min-h-[48px] touch-manipulation"
      >
        <div className="flex items-center gap-3">
          <span
            className={clsx(
              "flex items-center justify-center w-8 h-8 rounded-lg transition",
              open ? "bg-slate-700/80 text-emerald-400" : "bg-slate-700/50 text-slate-400 group-hover:text-slate-300"
            )}
          >
            {open ? (
              <ChevronDown className="h-5 w-5 shrink-0" aria-hidden />
            ) : (
              <ChevronRight className="h-5 w-5 shrink-0" aria-hidden />
            )}
          </span>
          <span className="[&>svg]:h-6 [&>svg]:w-6 [&>svg]:shrink-0 text-slate-400 group-hover:text-slate-300">
            {icon}
          </span>
          <h2 className="text-base sm:text-xl font-semibold text-slate-100 leading-snug">{title}</h2>
          {badge != null && badge !== "" && (
            <span className="px-2.5 py-1 rounded-md text-sm font-medium bg-slate-600 text-slate-200">
              {badge}
            </span>
          )}
        </div>
      </button>
      {(open || keepMounted) && (
        <div className={clsx("p-3 sm:p-5 pt-0", !open && keepMounted && "hidden")}>{children}</div>
      )}
    </section>
  );
}
