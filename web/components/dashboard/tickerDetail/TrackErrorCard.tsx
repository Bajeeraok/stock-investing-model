"use client";

import type { Calibration, TrackRecordResponse } from "@/lib/useTickerTrackRecord";
import { fmtPct } from "./ReferenceDetailGrid";

function pp(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)} pts`;
}

function CalTable({ cal, actualLabel }: { cal: Calibration; actualLabel: string }) {
  return (
    <table className="mt-1 w-full text-[11px]">
      <thead className="text-slate-500">
        <tr className="text-left">
          <th className="pr-2 font-normal">We said</th>
          <th className="pr-2 font-normal">Avg said</th>
          <th className="pr-2 font-normal">{actualLabel}</th>
          <th className="pr-2 font-normal">Gap</th>
          <th className="font-normal">Calls</th>
        </tr>
      </thead>
      <tbody className="font-mono text-slate-300">
        {cal.buckets.map((b) => {
          const act = b.actual_up_pct ?? b.actual_hit_pct ?? 0;
          const gap = act - b.avg_predicted_pct;
          return (
            <tr key={b.range}>
              <td className="pr-2">{b.range}</td>
              <td className="pr-2">{b.avg_predicted_pct.toFixed(0)}%</td>
              <td className="pr-2">{act.toFixed(0)}%</td>
              <td className={Math.abs(gap) <= 10 ? "pr-2 text-emerald-400" : "pr-2 text-amber-400"}>{pp(gap)}</td>
              <td className={b.n < 30 ? "text-slate-500" : ""}>{b.n}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function pickCal(own?: Record<string, Calibration | null> | null, pooled?: Record<string, Calibration | null> | null, h = "20") {
  const mine = own?.[h];
  if (mine && mine.n >= 30) return { cal: mine, scope: "this stock" };
  const all = pooled?.[h];
  if (all) return { cal: all, scope: "all tracked stocks" };
  return mine ? { cal: mine, scope: "this stock" } : null;
}

export default function TrackErrorCard({ data }: { data: TrackRecordResponse }) {
  const es = data.error_summary;
  const err = es?.current ?? es?.all ?? null;
  const errScope = es?.current ? "current model" : "all versions";
  const prob = pickCal(data.prob_calibration, data.prob_calibration_pooled, "20") ??
    pickCal(data.prob_calibration, data.prob_calibration_pooled, "5");
  const lvl = data.level_odds_check;
  const lvlPick = pickCal(lvl?.ticker, lvl?.pooled, "20") ?? pickCal(lvl?.ticker, lvl?.pooled, "63");
  if (!err && !prob && !lvlPick && !lvl?.pending) return null;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-300">
      <div className="mb-2 text-sm font-semibold text-slate-200">How far off were we?</div>

      <div className="mb-3">
        <div className="font-medium text-slate-200">
          Target vs 20-day result <span className="font-normal text-slate-500">({errScope})</span>
        </div>
        {err ? (
          <>
            <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
              <div title="Average size of the miss, ignoring direction">
                <div className="text-slate-500">Avg miss</div>
                <div className="font-mono">{err.mae_pp.toFixed(1)} pts</div>
              </div>
              <div title="Average of (actual − target). Negative = targets were too optimistic">
                <div className="text-slate-500">Bias</div>
                <div className={err.bias_pp < 0 ? "font-mono text-amber-400" : "font-mono text-emerald-400"}>
                  {pp(err.bias_pp)} {err.bias_pp < 0 ? "(too optimistic)" : "(too cautious)"}
                </div>
              </div>
              <div title="Close after 20 days landed between the frozen stop and target">
                <div className="text-slate-500">Inside stop–target</div>
                <div className="font-mono">{err.within_range_pct == null ? "—" : `${err.within_range_pct.toFixed(0)}%`}</div>
              </div>
              <div>
                <div className="text-slate-500">Target / stop touched</div>
                <div className="font-mono">
                  {err.target_hit_pct.toFixed(0)}% / {err.stop_hit_pct.toFixed(0)}%
                </div>
              </div>
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              Avg target {fmtPct(err.avg_expected_pct)} vs avg actual {fmtPct(err.avg_actual_pct)} over {err.n} calls
              {err.n < 30 ? " — too few to judge yet" : ""}.
            </div>
          </>
        ) : (
          <div className="mt-1 text-[11px] text-slate-500">Fills in once calls with a target reach 20 days.</div>
        )}
      </div>

      <div className="mb-3">
        <div className="font-medium text-slate-200">
          Up-probability check{" "}
          {prob && <span className="font-normal text-slate-500">({prob.scope}, {prob.cal.n} calls)</span>}
        </div>
        {prob ? (
          <CalTable cal={prob.cal} actualLabel="Actually rose" />
        ) : (
          <div className="mt-1 text-[11px] text-slate-500">No resolved calls with an ML probability yet.</div>
        )}
      </div>

      <div>
        <div className="font-medium text-slate-200">
          Entry-level hit odds check{" "}
          {lvlPick && <span className="font-normal text-slate-500">({lvlPick.scope}, {lvlPick.cal.n} levels)</span>}
        </div>
        {lvlPick ? (
          <CalTable cal={lvlPick.cal} actualLabel="Actually hit" />
        ) : (
          <div className="mt-1 text-[11px] text-slate-500">
            Logging daily odds for levels 2%, 5% and 10% below the close
            {lvl?.pending ? ` (${lvl.pending} waiting for their window)` : ""}. Results appear after 20 trading days.
          </div>
        )}
      </div>

      <div className="mt-2 text-[11px] text-slate-600">
        Gap within ±10 pts is green. Under 30 calls is grey: too few to trust. Education only, not advice.
      </div>
    </div>
  );
}
