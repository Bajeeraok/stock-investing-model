"use client";

import { useState } from "react";
import { clsx } from "clsx";
import { Activity, ChevronDown, ChevronUp, Target } from "lucide-react";

export type EventRiskRow = {
  ticker: string;
  event_score?: number | null;
  event_tags?: string[];
  close?: number | null;
  atr_pct?: number | null;
  velocity_score?: number | null;
  velocity_triggered?: boolean;
  rvol?: number | null;
  earnings_days_until?: number | null;
  expected_move_pct?: number | null;
  pre_earnings_bias?: string | null;
  bias_prob_pct?: number | null;
  post_earnings_upside?: number | null;
  post_earnings_downside?: number | null;
  post_earnings_directional?: number | null;
  calibration_hit_rate?: number | null;
  calibration_mae_pct?: number | null;
  calibration_confidence_pct?: number | null;
  calibration_events?: number | null;
  calibration_note?: string | null;
  historical_avg_abs_move_pct?: number | null;
  recent_earnings_moves?: Array<{ date?: string; move_pct?: number | null }>;
};

export type EventRiskStripPayload = {
  rows?: EventRiskRow[];
  rank_note?: string | null;
  message?: string | null;
};

function fmt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `$${n.toFixed(2)}`;
}

function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

function biasTone(bias: string | null | undefined): string {
  const b = String(bias || "").toLowerCase();
  if (b.includes("bull")) return "text-emerald-300 bg-emerald-500/15 border-emerald-500/30";
  if (b.includes("bear")) return "text-red-300 bg-red-500/15 border-red-500/30";
  return "text-amber-300 bg-amber-500/10 border-amber-500/25";
}

function tagLabel(tag: string): string {
  if (tag === "earnings") return "ER";
  if (tag === "velocity") return "VEL";
  if (tag === "high_atr") return "ATR";
  return tag.slice(0, 3).toUpperCase();
}

function EventRiskCard({
  row,
  onTickerClick,
}: {
  row: EventRiskRow;
  onTickerClick?: (ticker: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const hitPct =
    row.calibration_hit_rate != null ? Math.round(row.calibration_hit_rate * 100) : null;
  const hasCalibration = hitPct != null && (row.calibration_events ?? 0) > 0;
  const erSoon =
    row.earnings_days_until != null &&
    row.earnings_days_until >= 0 &&
    row.earnings_days_until <= 14;

  return (
    <div className="rounded-lg border border-amber-500/25 bg-slate-900/70 overflow-hidden">
      <button
        type="button"
        onClick={() => onTickerClick?.(row.ticker)}
        className="w-full px-3 py-2.5 text-left touch-manipulation hover:bg-slate-800/40"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-sm font-semibold text-amber-100">{row.ticker}</span>
              {(row.event_tags ?? []).slice(0, 3).map((t) => (
                <span
                  key={t}
                  className="text-[9px] font-bold uppercase px-1 py-0.5 rounded border border-slate-600 text-slate-400"
                >
                  {tagLabel(t)}
                </span>
              ))}
            </div>
            <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-slate-400 tabular-nums">
              {row.expected_move_pct != null && (
                <span>±{row.expected_move_pct.toFixed(1)}% 1d</span>
              )}
              {row.atr_pct != null && <span>ATR {row.atr_pct.toFixed(1)}%</span>}
              {row.velocity_score != null && row.velocity_score > 0 && (
                <span>vel {Math.round(row.velocity_score)}</span>
              )}
              {erSoon && <span className="text-amber-300/90">ER in {row.earnings_days_until}d</span>}
            </div>
          </div>
          <div className="text-right shrink-0">
            <span className="text-sm font-mono text-slate-200">{fmt(row.close)}</span>
            {row.event_score != null && (
              <p className="text-[10px] text-slate-500">score {row.event_score.toFixed(0)}</p>
            )}
          </div>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span
            className={clsx(
              "text-[10px] font-semibold uppercase px-2 py-0.5 rounded border",
              biasTone(row.pre_earnings_bias),
            )}
          >
            Pre-ER {row.pre_earnings_bias ?? "Neutral"}
            {row.bias_prob_pct != null ? ` ${Math.round(row.bias_prob_pct)}%` : ""}
          </span>
          {row.post_earnings_directional != null && (
            <span className="text-[10px] text-slate-400">
              Post-ER target{" "}
              <span className="font-mono text-slate-200">{fmt(row.post_earnings_directional)}</span>
            </span>
          )}
        </div>
      </button>

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-center gap-1 py-1 text-[10px] text-slate-500 border-t border-slate-700/50 hover:bg-slate-800/30 touch-manipulation"
      >
        {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        {open ? "Hide calibration" : "Calibration & targets"}
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 space-y-2 border-t border-slate-700/40 bg-slate-950/40">
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <div>
              <p className="text-slate-500">Upside (post-ER)</p>
              <p className="font-mono text-emerald-300">{fmt(row.post_earnings_upside)}</p>
            </div>
            <div>
              <p className="text-slate-500">Downside (post-ER)</p>
              <p className="font-mono text-red-300">{fmt(row.post_earnings_downside)}</p>
            </div>
            <div>
              <p className="text-slate-500">Hist avg |move|</p>
              <p className="font-mono text-slate-300">
                {row.historical_avg_abs_move_pct != null
                  ? `${row.historical_avg_abs_move_pct.toFixed(1)}%`
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-slate-500">Model hit rate</p>
              <p className="font-mono text-slate-300">
                {hasCalibration ? `${hitPct}% (${row.calibration_events} evts)` : "—"}
              </p>
            </div>
          </div>

          {!!row.recent_earnings_moves?.length && (
            <div>
              <p className="text-[10px] text-slate-500 mb-1">Recent earnings reactions</p>
              <div className="flex flex-wrap gap-2">
                {row.recent_earnings_moves.map((ev) => (
                  <span
                    key={ev.date}
                    className={clsx(
                      "text-[10px] font-mono px-1.5 py-0.5 rounded",
                      (ev.move_pct ?? 0) >= 0 ? "text-emerald-300 bg-emerald-500/10" : "text-red-300 bg-red-500/10",
                    )}
                  >
                    {ev.date?.slice(5)} {fmtPct(ev.move_pct ?? undefined, 1)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {row.calibration_note && (
            <p className="text-[10px] text-slate-500 leading-snug">{row.calibration_note}</p>
          )}
        </div>
      )}
    </div>
  );
}

export function EventRiskStrip({
  payload,
  onTickerClick,
}: {
  payload: EventRiskStripPayload | null | undefined;
  onTickerClick?: (ticker: string) => void;
}) {
  const rows = payload?.rows ?? [];
  if (!rows.length) return null;

  return (
    <div className="rounded-xl border border-amber-500/30 bg-gradient-to-r from-amber-950/30 to-slate-900/40 p-4 space-y-3">
      <div className="flex items-start gap-2">
        <Activity className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-amber-100">High 1-day event risk</p>
            <span className="text-[10px] text-slate-500">Scout · ER + ATR + velocity</span>
          </div>
          {payload?.rank_note && (
            <p className="text-[10px] text-slate-500 mt-1 leading-snug line-clamp-3">{payload.rank_note}</p>
          )}
        </div>
        <Target className="h-4 w-4 text-slate-600 shrink-0" aria-hidden />
      </div>

      <div className="space-y-2">
        {rows.map((row) => (
          <EventRiskCard key={row.ticker} row={row} onTickerClick={onTickerClick} />
        ))}
      </div>
    </div>
  );
}
