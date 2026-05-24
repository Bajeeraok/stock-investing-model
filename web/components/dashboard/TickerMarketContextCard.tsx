"use client";

import { clsx } from "clsx";
import { GitBranch, Layers, Target, Thermometer } from "lucide-react";

export interface TickerMarketContext {
  headline?: string;
  market_temperature_label?: string;
  horizon_overlay?: {
    short?: { action?: string; note?: string };
    medium?: { action?: string; note?: string };
    long?: { action?: string; note?: string };
  };
  earnings_rule?: { days_until?: number; rule?: string; urgency?: string } | null;
  trigger_watch?: { benchmark?: string; trigger_price?: number; rule?: string } | null;
  macro_watch?: { condition: string; impact?: string; action?: string }[];
  sector_rotation_note?: string | null;
  crowd_note?: string | null;
  personal_question?: { question: string; answer: string } | null;
  disclaimer?: string;
}

const ACTION_STYLE: Record<string, string> = {
  BUY: "text-emerald-300",
  HOLD: "text-slate-300",
  REDUCE: "text-amber-300",
};

export function TickerMarketContextCard({ data }: { data: TickerMarketContext | null | undefined }) {
  if (!data?.headline) return null;

  const horizon = data.horizon_overlay;

  return (
    <section className="rounded-xl border border-violet-500/25 bg-violet-950/10 p-4 space-y-3">
      <div className="flex items-start gap-2">
        <Layers className="h-4 w-4 text-violet-400 shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-violet-300/90">Market context for this name</p>
          <p className="text-sm text-slate-200 mt-1 leading-snug">{data.headline}</p>
          {data.market_temperature_label && (
            <p className="text-[11px] text-slate-500 mt-1 flex items-center gap-1">
              <Thermometer className="h-3 w-3" /> Tape: {data.market_temperature_label}
            </p>
          )}
        </div>
      </div>

      {horizon && (
        <div className="grid grid-cols-3 gap-2 text-center">
          {(["short", "medium", "long"] as const).map((k) => {
            const row = horizon[k];
            const label = k === "short" ? "ST" : k === "medium" ? "MT" : "LT";
            return (
              <div key={k} className="rounded-lg border border-slate-700/50 bg-slate-800/30 px-2 py-1.5">
                <p className="text-[10px] text-slate-500 uppercase">{label}</p>
                <p className={clsx("text-xs font-bold", ACTION_STYLE[row?.action ?? "HOLD"] ?? ACTION_STYLE.HOLD)}>
                  {row?.action ?? "—"}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {data.personal_question && (
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-950/15 px-3 py-2">
          <p className="text-xs text-slate-400">{data.personal_question.question}</p>
          <p className="text-sm text-emerald-200/90 mt-0.5">{data.personal_question.answer}</p>
        </div>
      )}

      {data.earnings_rule?.rule && (
        <p className="text-xs text-amber-200/90 border-l-2 border-amber-500/50 pl-2">{data.earnings_rule.rule}</p>
      )}

      {data.trigger_watch?.rule && (
        <p className="text-xs text-slate-400 flex items-start gap-1.5">
          <Target className="h-3.5 w-3.5 shrink-0 mt-0.5 text-sky-400" />
          {data.trigger_watch.rule}
        </p>
      )}

      {(data.macro_watch ?? []).length > 0 && (
        <ul className="space-y-1">
          {data.macro_watch!.slice(0, 2).map((s, i) => (
            <li key={i} className="text-[11px] text-slate-500 flex items-start gap-1">
              <GitBranch className="h-3 w-3 shrink-0 mt-0.5 text-violet-400/70" />
              <span>
                <span className="text-violet-200/80">IF {s.condition}</span>
                {s.action ? ` → ${s.action}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}

      {data.sector_rotation_note && <p className="text-xs text-slate-400">{data.sector_rotation_note}</p>}
      {data.crowd_note && <p className="text-xs text-slate-500 italic">{data.crowd_note}</p>}
      {data.disclaimer && <p className="text-[10px] text-slate-600">{data.disclaimer}</p>}
    </section>
  );
}
