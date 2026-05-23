"use client";

import { Calendar, AlertTriangle, Zap, Target, Clock } from "lucide-react";
import { clsx } from "clsx";

export interface MarketCatalystScenario {
  avg_return_pct?: number;
  avg_same_day_pct?: number;
  std_pct?: number;
  pct_positive?: number;
  pct_gap_fade?: number;
  n_events?: number;
  rationale?: string;
  gap_fade?: { pct_gap_fade?: number; n_events?: number; rationale?: string };
}

export interface MarketCatalystRelease {
  time_et?: string;
  status?: "pending" | "released";
  minutes_until?: number | null;
  minutes_since?: number | null;
}

export interface MarketCatalystScheduled {
  date: string;
  time_et?: string | null;
  name: string;
  event_type: string;
  impact: string;
  scenario?: MarketCatalystScenario | null;
  release?: MarketCatalystRelease | null;
  gap_fade_line?: string | null;
}

export interface MarketCatalystTension {
  level: "High" | "Medium" | "Low";
  code: string;
  message: string;
}

export interface MarketCatalystFlip {
  event_type: string;
  title: string;
  bullets: string[];
  scenario?: MarketCatalystScenario | null;
}

export interface MarketCatalystIntraday {
  spy_last?: number;
  spy_open?: number;
  since_open_pct?: number;
  as_of_et?: string;
  since_release?: {
    event_type?: string;
    name?: string;
    pct_since_release?: number;
    release_time_et?: string;
  } | null;
}

export interface MarketCatalystBoard {
  as_of_date?: string;
  as_of_et?: string;
  summary_line?: string;
  scheduled_today?: MarketCatalystScheduled[];
  live_tape?: { name: string; raw_value: string; direction: string; score: number; category?: string }[];
  tensions?: MarketCatalystTension[];
  flip_narratives?: MarketCatalystFlip[];
  intraday?: MarketCatalystIntraday | null;
  polling?: {
    premarket_poll_ms?: number;
    intraday_poll_ms?: number;
    is_premarket_et?: boolean;
    is_rth_et?: boolean;
  };
  premarket_vs_close?: { pct_contradict?: number; n_days?: number; rationale?: string } | null;
  digest_line?: string | null;
  disclaimer?: string;
  premarket_bias?: string;
  spy_regime?: string | null;
  macro_regime?: string | null;
}

function levelClass(level: string) {
  if (level === "High") return "text-amber-300 border-amber-500/30 bg-amber-500/10";
  if (level === "Medium") return "text-slate-300 border-slate-600 bg-slate-800/40";
  return "text-slate-400 border-slate-700 bg-slate-800/30";
}

function ReleaseBadge({ release }: { release?: MarketCatalystRelease | null }) {
  if (!release?.status) return null;
  const pending = release.status === "pending";
  return (
    <span
      className={clsx(
        "text-[10px] font-medium px-1.5 py-0.5 rounded border uppercase tracking-wide",
        pending ? "border-amber-500/40 text-amber-300 bg-amber-500/10" : "border-emerald-500/30 text-emerald-300 bg-emerald-500/10",
      )}
    >
      {pending ? `pending · ${release.minutes_until ?? "?"}m` : "released"}
    </span>
  );
}

export function MarketCatalystBoardPanel({
  board,
  compact = false,
}: {
  board: MarketCatalystBoard | null | undefined;
  compact?: boolean;
}) {
  if (!board) return null;

  const scheduled = board.scheduled_today ?? [];
  const live = board.live_tape ?? [];
  const tensions = board.tensions ?? [];
  const flips = compact ? [] : board.flip_narratives ?? [];

  return (
    <div className={clsx("rounded-lg border border-violet-500/25 bg-violet-950/20 p-4 space-y-4", compact && "p-3 space-y-3")}>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-violet-300 flex items-center gap-1.5">
          <Target className="h-3.5 w-3.5" />
          Today&apos;s catalyst board
        </p>
        {board.summary_line && <p className="text-sm text-slate-300 mt-1">{board.summary_line}</p>}
        {(board.spy_regime || board.macro_regime) && (
          <p className="text-xs text-slate-500 mt-1">
            {board.spy_regime && <>SPY regime: {board.spy_regime}</>}
            {board.spy_regime && board.macro_regime && " · "}
            {board.macro_regime && <>Macro: {board.macro_regime}</>}
          </p>
        )}
        {board.premarket_vs_close?.pct_contradict != null && (
          <p className="text-xs text-slate-500 mt-1">
            Pre-market vs close: contradicted {board.premarket_vs_close.pct_contradict}% of days (n=
            {board.premarket_vs_close.n_days})
          </p>
        )}
      </div>

      {scheduled.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1">
            <Calendar className="h-3 w-3" /> Scheduled (today)
          </p>
          <ul className="space-y-2">
            {scheduled.map((ev) => (
              <li key={`${ev.date}-${ev.name}`} className="rounded border border-slate-700/60 bg-slate-900/40 px-3 py-2">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                  {(ev.time_et || ev.release?.time_et) && (
                    <span className="font-mono text-violet-300 flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {ev.time_et || ev.release?.time_et} ET
                    </span>
                  )}
                  <ReleaseBadge release={ev.release} />
                  <span className="text-slate-200">{ev.name}</span>
                  <span className="text-xs text-slate-500">{ev.event_type}</span>
                  <span className="text-xs text-amber-400/90">{ev.impact}</span>
                </div>
                {ev.gap_fade_line && (
                  <p className="text-xs text-violet-300/90 mt-1 font-medium">{ev.gap_fade_line}</p>
                )}
                {ev.scenario && !ev.gap_fade_line && ev.scenario.pct_gap_fade != null && (
                  <p className="text-xs text-violet-300/90 mt-1">
                    Gap faded {ev.scenario.pct_gap_fade}% on past {ev.event_type} days (n={ev.scenario.n_events})
                  </p>
                )}
                {ev.scenario && (
                  <p className="text-xs text-slate-500 mt-1">
                    Hist. SPY next-day: avg {ev.scenario.avg_return_pct != null && ev.scenario.avg_return_pct >= 0 ? "+" : ""}
                    {ev.scenario.avg_return_pct}%
                    {ev.scenario.avg_same_day_pct != null && (
                      <> · same-day {ev.scenario.avg_same_day_pct >= 0 ? "+" : ""}{ev.scenario.avg_same_day_pct}%</>
                    )}
                    {" · "}
                    {ev.scenario.pct_positive}% positive (n={ev.scenario.n_events})
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {live.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1">
            <Zap className="h-3 w-3" /> Live tape (moving now)
          </p>
          <div className="flex flex-wrap gap-2">
            {live.map((d) => (
              <span
                key={d.name}
                className={clsx(
                  "text-xs px-2 py-1 rounded border font-mono",
                  d.direction === "Bullish" && "border-emerald-500/30 text-emerald-400 bg-emerald-500/5",
                  d.direction === "Bearish" && "border-red-500/30 text-red-400 bg-red-500/5",
                  d.direction === "Neutral" && "border-slate-600 text-slate-400",
                )}
              >
                {d.name.split("(")[0].trim()}: {d.raw_value}
              </span>
            ))}
          </div>
        </div>
      )}

      {tensions.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" /> Tension / flip setup
          </p>
          <ul className="space-y-1.5">
            {tensions.map((t) => (
              <li key={t.code} className={clsx("text-xs px-2.5 py-1.5 rounded border", levelClass(t.level))}>
                <span className="font-medium">{t.level}:</span> {t.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {flips.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">What could flip direction?</p>
          {flips.map((f) => (
            <div key={f.event_type} className="mb-2 last:mb-0">
              <p className="text-xs font-medium text-slate-400 mb-1">{f.title}</p>
              <ul className="list-disc list-inside text-xs text-slate-500 space-y-0.5">
                {f.bullets.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {board.disclaimer && <p className="text-[10px] text-slate-600 leading-snug">{board.disclaimer}</p>}
    </div>
  );
}
