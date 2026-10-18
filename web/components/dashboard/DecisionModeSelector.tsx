"use client";

import { clsx } from "clsx";
import { Crosshair, TrendingUp, Landmark } from "lucide-react";
import {
  type DecisionMode,
  decisionModeHint,
  decisionModeLabel,
} from "@/lib/decisionMode";

const MODES: { id: DecisionMode; icon: typeof Crosshair }[] = [
  { id: "scout", icon: Crosshair },
  { id: "swing", icon: TrendingUp },
  { id: "owner", icon: Landmark },
];

export function DecisionModeSelector({
  mode,
  onChange,
  className,
  variant = "default",
}: {
  mode: DecisionMode;
  onChange: (mode: DecisionMode) => void;
  className?: string;
  /** "segmented" — one-row Scout / Swing / Owner switch (redesign header pattern), hint as tooltip only. */
  variant?: "default" | "segmented";
}) {
  if (variant === "segmented") {
    return (
      <div
        className={clsx("flex gap-1 rounded-xl bg-td-surface2/80 border border-td-line p-1", className)}
        role="group"
        aria-label="Decision mode"
      >
        {MODES.map(({ id }) => {
          const active = mode === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onChange(id)}
              title={decisionModeHint(id)}
              aria-pressed={active}
              className={clsx(
                "flex-1 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold transition-colors touch-manipulation",
                active ? "bg-td-owner text-white shadow-sm" : "text-td-muted hover:text-td-text",
              )}
            >
              {decisionModeLabel(id)}
            </button>
          );
        })}
      </div>
    );
  }
  return (
    <div className={clsx("space-y-1.5", className)} role="group" aria-label="Decision mode">
      <p className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold px-0.5">
        I am deciding as a…
      </p>
      <div className="grid grid-cols-3 gap-1.5 rounded-xl border border-slate-600/80 bg-slate-950/60 p-1">
        {MODES.map(({ id, icon: Icon }) => {
          const active = mode === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onChange(id)}
              title={decisionModeHint(id)}
              className={clsx(
                "flex flex-col items-center gap-1 rounded-lg px-2 py-2.5 text-center transition-colors touch-manipulation",
                active
                  ? id === "scout"
                    ? "bg-cyan-500/20 border border-cyan-500/45 text-cyan-100"
                    : id === "swing"
                      ? "bg-violet-500/20 border border-violet-500/45 text-violet-100"
                      : "bg-emerald-500/20 border border-emerald-500/45 text-emerald-100"
                  : "border border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              <span className="text-xs font-semibold leading-tight">{decisionModeLabel(id)}</span>
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-slate-500 leading-snug px-0.5">{decisionModeHint(mode)}</p>
    </div>
  );
}
