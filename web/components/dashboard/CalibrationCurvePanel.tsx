"use client";

import React from "react";

export interface CalibrationBucket {
  label: string;
  predicted_avg: number;
  actual_win_rate: number;
  count: number;
  avg_return_pct: number;
}

export interface CalibrationData {
  buckets: CalibrationBucket[];
  total_observations: number;
  is_well_calibrated: boolean;
  calibration_error: number | null;
  monotonic: boolean;
  note: string;
}

function CalibrationChart({ buckets }: { buckets: CalibrationBucket[] }) {
  if (!buckets.length) return null;
  const maxRate = Math.max(...buckets.map((b) => Math.max(b.predicted_avg, b.actual_win_rate)), 100);

  return (
    <div className="mt-2">
      <div className="space-y-2">
        {buckets.map((b) => (
          <div key={b.label} className="flex items-center gap-2 text-sm">
            <span className="w-16 text-slate-400 text-right shrink-0 font-mono">{b.label}</span>
            <div className="flex-1 flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <div
                  className="h-3 rounded-sm bg-slate-600/80"
                  style={{ width: `${Math.max(4, (b.predicted_avg / maxRate) * 100)}%` }}
                  title={`Predicted: ${b.predicted_avg}%`}
                />
                <span className="text-slate-500 text-xs shrink-0">pred {b.predicted_avg}%</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className={`h-3 rounded-sm ${
                    b.actual_win_rate >= b.predicted_avg - 10 ? "bg-emerald-500/70" : "bg-red-500/70"
                  }`}
                  style={{ width: `${Math.max(4, (b.actual_win_rate / maxRate) * 100)}%` }}
                  title={`Actual: ${b.actual_win_rate}%`}
                />
                <span className="text-slate-400 text-xs shrink-0">actual {b.actual_win_rate}%</span>
              </div>
            </div>
            <span className="w-10 text-slate-500 text-right shrink-0 text-xs">n={b.count}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-4 mt-3 text-xs text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-4 h-2.5 rounded-sm bg-slate-600/80" /> Predicted confidence
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-4 h-2.5 rounded-sm bg-emerald-500/70" /> Actual win rate
        </span>
      </div>
      <p className="text-xs text-slate-500 mt-2 leading-snug">
        Points on the diagonal mean calibrated predictions. Above the line = model was conservative; below = overconfident.
      </p>
    </div>
  );
}

export function CalibrationCurvePanel({ calibration }: { calibration: CalibrationData | null | undefined }) {
  const has = calibration && calibration.buckets && calibration.buckets.length > 0;

  if (!has) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-4 text-center">
        <p className="text-sm text-slate-400">Calibration curve builds as paper trades and forward tracking accumulate.</p>
        <p className="text-xs text-slate-500 mt-1">Run the daily pipeline and log paper trades to populate buckets.</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-4">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <h3 className="text-sm font-semibold text-slate-200">Confidence calibration</h3>
        {calibration!.is_well_calibrated ? (
          <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/30">
            Well calibrated
          </span>
        ) : (
          <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 ring-1 ring-amber-500/30">
            Needs review
          </span>
        )}
      </div>
      {calibration!.note && <p className="text-xs text-slate-500 mb-2">{calibration!.note}</p>}
      {calibration!.calibration_error != null && (
        <p className="text-xs text-slate-400 mb-1">
          Mean calibration error: {calibration!.calibration_error}pp
          {calibration!.monotonic ? " · Monotonic ✓" : " · Non-monotonic ✗"}
          {` · ${calibration!.total_observations} observations`}
        </p>
      )}
      <CalibrationChart buckets={calibration!.buckets} />
    </div>
  );
}
