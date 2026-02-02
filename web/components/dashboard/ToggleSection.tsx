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
  children: React.ReactNode;
}

export function ToggleSection({
  id,
  title,
  icon,
  defaultOpen = true,
  badge,
  className,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={clsx("rounded-xl border border-slate-700 overflow-hidden", className)}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-2 px-4 py-3 bg-slate-800/50 hover:bg-slate-800/70 transition text-left"
      >
        <div className="flex items-center gap-2">
          {open ? (
            <ChevronDown className="h-5 w-5 text-slate-400 shrink-0" />
          ) : (
            <ChevronRight className="h-5 w-5 text-slate-400 shrink-0" />
          )}
          {icon}
          <h2 className="text-lg font-semibold text-slate-200">{title}</h2>
          {badge != null && badge !== "" && (
            <span className="px-2 py-0.5 rounded text-xs font-medium bg-slate-600 text-slate-300">
              {badge}
            </span>
          )}
        </div>
      </button>
      {open && <div className="p-4 pt-0">{children}</div>}
    </section>
  );
}
