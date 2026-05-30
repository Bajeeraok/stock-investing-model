"use client";

import { clsx } from "clsx";
import { Crosshair, TrendingUp, Landmark } from "lucide-react";
import {
  type TradingLens,
  tradingLensHint,
  tradingLensLabel,
} from "@/lib/tradingLens";

const LENSES: { id: TradingLens; icon: typeof Crosshair }[] = [
  { id: "scout", icon: Crosshair },
  { id: "swing", icon: TrendingUp },
  { id: "owner", icon: Landmark },
];

export function TradingLensSelector({
  lens,
  onChange,
  compact = false,
  className,
}: {
  lens: TradingLens;
  onChange: (lens: TradingLens) => void;
  compact?: boolean;
  className?: string;
}) {
  return (
    <div
      className={clsx(compact ? "flex items-center gap-1.5" : "space-y-1.5", className)}
      role="group"
      aria-label="Trading lens"
      title={tradingLensHint(lens)}
    >
      {!compact && (
        <p className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold px-0.5">
          Trading as
        </p>
      )}
      <div
        className={clsx(
          "flex gap-0.5 rounded-lg border border-slate-600/80 bg-slate-950/60 p-0.5",
          compact && "p-0.5"
        )}
      >
        {LENSES.map(({ id, icon: Icon }) => {
          const active = lens === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onChange(id)}
              title={tradingLensHint(id)}
              className={clsx(
                "flex items-center gap-1 rounded-md px-2 py-1.5 text-center transition-colors touch-manipulation",
                compact ? "py-1 px-1.5" : "flex-col py-2 px-2 min-w-[4.5rem]",
                active
                  ? id === "scout"
                    ? "bg-cyan-500/20 border border-cyan-500/45 text-cyan-100"
                    : id === "swing"
                      ? "bg-violet-500/20 border border-violet-500/45 text-violet-100"
                      : "bg-emerald-500/20 border border-emerald-500/45 text-emerald-100"
                  : "border border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              )}
            >
              <Icon className={clsx("shrink-0", compact ? "h-3.5 w-3.5" : "h-4 w-4")} aria-hidden />
              <span className={clsx("font-semibold leading-tight", compact ? "text-[10px]" : "text-xs")}>
                {tradingLensLabel(id)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
