"use client";

import { useEffect, useState } from "react";
import { clsx } from "clsx";
import {
  getPositionIntent,
  setPositionIntent,
  intentGateHint,
  intentLabel,
  type PositionIntent,
} from "@/lib/positionIntent";

export function PositionIntentChip({
  ticker,
  compact,
  onChange,
}: {
  ticker: string;
  compact?: boolean;
  onChange?: (intent: PositionIntent | null) => void;
}) {
  const [intent, setIntent] = useState<PositionIntent | null>(null);

  useEffect(() => {
    setIntent(getPositionIntent(ticker));
  }, [ticker]);

  const cycle = () => {
    const next: PositionIntent | null =
      intent === null ? "trade" : intent === "trade" ? "invest" : null;
    setPositionIntent(ticker, next);
    setIntent(next);
    onChange?.(next);
  };

  if (compact) {
    return (
      <button
        type="button"
        onClick={cycle}
        className={clsx(
          "text-[10px] px-2 py-0.5 rounded-full border transition-colors",
          intent === "trade" && "border-cyan-500/40 bg-cyan-500/10 text-cyan-200",
          intent === "invest" && "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
          !intent && "border-slate-600 text-slate-500 hover:text-slate-300"
        )}
        title={intentGateHint(intent)}
      >
        {intent ? intentLabel(intent) : "Intent?"}
      </button>
    );
  }

  return (
    <div className="rounded-lg border border-slate-700/70 bg-slate-900/50 px-3 py-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-[11px] text-slate-400">Position intent</p>
        <div className="flex gap-1">
          {(["trade", "invest"] as const).map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => {
                const next = intent === id ? null : id;
                setPositionIntent(ticker, next);
                setIntent(next);
                onChange?.(next);
              }}
              className={clsx(
                "text-[10px] px-2.5 py-1 rounded-full border font-medium",
                intent === id
                  ? id === "trade"
                    ? "border-cyan-500/50 bg-cyan-500/15 text-cyan-200"
                    : "border-emerald-500/50 bg-emerald-500/15 text-emerald-200"
                  : "border-slate-600 text-slate-500 hover:text-slate-300"
              )}
            >
              {id === "trade" ? "Trade (weeks)" : "Invest (years)"}
            </button>
          ))}
        </div>
      </div>
      <p className="text-[10px] text-slate-500 mt-1.5 leading-snug">{intentGateHint(intent)}</p>
    </div>
  );
}
