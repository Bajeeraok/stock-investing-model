"use client";

import { clsx } from "clsx";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";

export type SignalReasonFactor = {
  id?: string;
  label: string;
  category?: string;
  stance?: "helps" | "hurts" | "neutral";
  weight_pct?: number;
  score_pct?: number | null;
  summary?: string;
};

export type SignalReasonPayload = {
  headline?: string;
  wait_plain?: string | null;
  factors?: SignalReasonFactor[];
  supporting?: string[];
  blocking?: string[];
  top_driver?: string | null;
  top_blocker?: string | null;
};

const STANCE_ICON = {
  helps: TrendingUp,
  hurts: TrendingDown,
  neutral: Minus,
} as const;

const STANCE_CLASS = {
  helps: "text-emerald-400 border-emerald-500/35 bg-emerald-500/10",
  hurts: "text-amber-300 border-amber-500/35 bg-amber-500/10",
  neutral: "text-slate-400 border-slate-600/50 bg-slate-800/40",
} as const;

export function SignalReasonCard({
  reason,
  compact = false,
  className,
}: {
  reason: SignalReasonPayload | null | undefined;
  compact?: boolean;
  className?: string;
}) {
  if (!reason?.headline && !(reason?.factors?.length)) return null;

  return (
    <div
      className={clsx(
        "rounded-xl border border-slate-700/60 bg-slate-900/50 overflow-hidden",
        className,
      )}
    >
      <div className="px-4 py-3 border-b border-slate-800/80">
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-1">
          Why this signal
        </p>
        {reason.headline && (
          <p className="text-sm text-slate-100 leading-snug font-medium">{reason.headline}</p>
        )}
      </div>

      {reason.wait_plain && (
        <div className="mx-4 mt-3 rounded-lg border border-amber-500/30 bg-amber-950/25 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wider text-amber-300/90 font-semibold mb-0.5">
            If you&apos;re waiting — roughly when
          </p>
          <p className="text-xs text-amber-100/90 leading-relaxed">{reason.wait_plain}</p>
        </div>
      )}

      {(reason.factors?.length ?? 0) > 0 && (
        <div className={clsx("px-4 py-3 space-y-2", compact && "py-2 space-y-1.5")}>
          <p className="text-[10px] uppercase tracking-wider text-slate-500">What drove it</p>
          {reason.factors!.slice(0, compact ? 4 : 6).map((f) => {
            const stance = f.stance ?? "neutral";
            const Icon = STANCE_ICON[stance];
            return (
              <div key={`${f.id ?? f.label}`} className="flex gap-2.5 items-start">
                <span
                  className={clsx(
                    "mt-0.5 shrink-0 inline-flex h-6 w-6 items-center justify-center rounded-md border",
                    STANCE_CLASS[stance],
                  )}
                >
                  <Icon className="h-3.5 w-3.5" aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <span className="text-xs font-semibold text-slate-200">{f.label}</span>
                    {f.weight_pct != null && (
                      <span className="text-[10px] tabular-nums text-slate-500">
                        {f.weight_pct.toFixed(0)}% weight
                      </span>
                    )}
                  </div>
                  {f.summary && (
                    <p className={clsx("text-slate-400 leading-snug mt-0.5", compact ? "text-[10px]" : "text-xs")}>
                      {f.summary}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
