"use client";

import { type ReactNode, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { clsx } from "clsx";

export interface DataMetricCardProps {
  title: string;
  primary: ReactNode;
  /** Secondary line (delta, context, spark copy) */
  secondary?: ReactNode;
  icon?: ReactNode;
  className?: string;
  titleClassName?: string;
  primaryClassName?: string;
  /** Collapsible detail body — progressive disclosure */
  children?: ReactNode;
  defaultOpen?: boolean;
  /** Compact padding for hub strips */
  dense?: boolean;
}

export function DataMetricCard({
  title,
  primary,
  secondary,
  icon,
  className,
  titleClassName,
  primaryClassName,
  children,
  defaultOpen = false,
  dense,
}: DataMetricCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const expandable = Boolean(children);

  return (
    <div
      className={clsx(
        "rounded-xl border border-slate-700/90 bg-slate-900/50 text-left",
        dense ? "p-3 min-w-[7.5rem]" : "p-5 min-w-[180px]",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div
            className={clsx(
              "flex items-center gap-2 text-slate-400 mb-1",
              dense ? "text-[11px]" : "text-sm",
              titleClassName,
            )}
          >
            {icon ? <span className="shrink-0 text-slate-500 [&>svg]:h-4 [&>svg]:w-4">{icon}</span> : null}
            <span className="truncate">{title}</span>
          </div>
          <div className={clsx(dense ? "text-lg" : "text-2xl", "font-bold tabular-nums text-slate-100", primaryClassName)}>
            {primary}
          </div>
          {secondary != null && (
            <p className={clsx("text-slate-500 mt-0.5", dense ? "text-[10px] leading-snug" : "text-xs")}>{secondary}</p>
          )}
        </div>
        {expandable && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="shrink-0 p-1 rounded-md text-slate-500 hover:text-slate-300 hover:bg-slate-800/80 touch-manipulation"
            aria-expanded={open}
            aria-label={open ? "Hide details" : "Show details"}
          >
            {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        )}
      </div>
      {expandable && open && (
        <div className="mt-3 pt-3 border-t border-slate-700/70 text-sm text-slate-300 space-y-1.5">{children}</div>
      )}
    </div>
  );
}
