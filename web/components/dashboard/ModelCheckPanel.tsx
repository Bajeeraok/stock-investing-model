"use client";

import { useEffect, useState } from "react";
import { clsx } from "clsx";
import type { Calibration } from "@/lib/useTickerTrackRecord";
import { CalTable } from "./tickerDetail/TrackErrorCard";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface TargetSummary {
  n: number;
  avg_expected_pct: number;
  avg_actual_pct: number;
  within_range_pct: number | null;
  target_hit_pct: number;
  stop_hit_pct: number;
}

interface ModelCheckResponse {
  short: { odds: Calibration | null; odds_current?: Calibration | null; target: TargetSummary | null; current_model_version?: string } | null;
  medium: Calibration | null;
  long: Calibration | null;
  eod_date_last?: string | null;
}

const VERDICT: Record<string, { label: string; tone: string; means: string }> = {
  proven: {
    label: "Proven",
    tone: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
    means: "Its % beats guessing the average and roughly matches what happened. It can help rank picks.",
  },
  miscalibrated: {
    label: "Edge, % off",
    tone: "bg-amber-500/10 text-amber-200 border-amber-500/30",
    means: "Higher % calls did better, but the numbers themselves are off. Use it to compare, not as a real chance.",
  },
  no_edge: {
    label: "No edge",
    tone: "bg-rose-500/10 text-rose-300 border-rose-500/30",
    means: "Not better than guessing the average for every stock. Don't use this % to pick stocks.",
  },
  unproven: {
    label: "Unproven",
    tone: "bg-slate-700/40 text-slate-300 border-slate-600/50",
    means: "Too few finished calls (needs 200) to judge. Treat the % as untested.",
  },
};

function pct(v: number | null | undefined, sign = false) {
  if (v == null || !Number.isFinite(v)) return "–";
  return `${sign && v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function HorizonCard({ title, question, cal, pending }: { title: string; question: string; cal: Calibration | null | undefined; pending: string }) {
  const v = VERDICT[cal?.verdict ?? "unproven"];
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-3 text-[13px] text-slate-300">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-[14px] font-semibold text-slate-100">{title}</h4>
        <span className={clsx("rounded-full border px-2 py-0.5 text-[12px] font-medium", v.tone)}>{v.label}</span>
      </div>
      <div className="mt-0.5 text-slate-400">{question}</div>
      {cal ? (
        <>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
            <span>{cal.n} calls</span>
            <span>
              said avg <b className="text-slate-100">{cal.avg_predicted_pct.toFixed(0)}%</b>
            </span>
            <span>
              came true <b className="text-slate-100">{(cal.came_true_pct ?? cal.actual_hit_pct ?? 0).toFixed(0)}%</b>
            </span>
            {cal.skill_pct != null && (
              <span title="Brier score vs always guessing the overall came-true rate. Above 0 = better than guessing.">
                skill vs guessing <b className={cal.skill_pct > 0 ? "text-emerald-300" : "text-rose-300"}>{pct(cal.skill_pct, true)}</b>
              </span>
            )}
          </div>
          <CalTable cal={cal} actualLabel="Came true" />
          {cal.rose_pct != null && (
            <div className="mt-1 text-slate-500">For reference: {cal.rose_pct.toFixed(0)}% ended higher at all (any gain, not the model&apos;s question).</div>
          )}
        </>
      ) : (
        <div className="mt-2 text-slate-500">{pending}</div>
      )}
      <div className="mt-2 rounded-md border-l-2 border-sky-400/60 bg-sky-500/5 px-2 py-1 text-slate-300">{v.means}</div>
    </div>
  );
}

export function ModelCheckPanel() {
  const [data, setData] = useState<ModelCheckResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/api/model-check`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => alive && setData(j))
      .catch((e) => alive && setErr(String(e?.message || e)));
    return () => {
      alive = false;
    };
  }, []);
  if (err) return <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">Model check unavailable: {err}</div>;
  if (!data) return <div className="rounded-lg border border-slate-700 bg-slate-900/40 px-4 py-3 text-sm text-slate-400">Loading model check…</div>;
  const s = data.short;
  const gains = s?.odds?.gain_pcts?.length ? s.odds.gain_pcts.map((g) => `+${g}%`).join(" / ") : "+N%";
  const t = s?.target;
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-[15px] font-semibold text-slate-100">Model check · all tracked stocks</h3>
        <p className="mt-0.5 text-[13px] text-slate-400">
          Does the model&apos;s % come true? Each horizon is checked against its own question: did the close N trading days later
          reach the stock&apos;s +X% threshold?{data.eod_date_last ? ` Data through ${data.eod_date_last}.` : ""}
        </p>
      </div>
      <HorizonCard
        title="1 month"
        question={`${gains} within 20 trading days (threshold depends on the stock)`}
        cal={s?.odds}
        pending="No finished 1-month calls yet."
      />
      <HorizonCard
        title="3 months · used by Swing"
        question="Stock's +N% within 60 trading days"
        cal={data.medium}
        pending="Saving daily 3-month odds since Nov 4. First results after 60 trading days."
      />
      <HorizonCard
        title="6 months · used by Owner"
        question="Stock's +N% within 120 trading days"
        cal={data.long}
        pending="Saving daily 6-month odds since Nov 4. First results after 120 trading days."
      />
      {t && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-3 text-[13px] text-slate-300">
          <h4 className="text-[14px] font-semibold text-slate-100">Short-term target vs 20-day path</h4>
          <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
            <span>Avg target <b className="text-slate-100">{pct(t.avg_expected_pct, true)}</b></span>
            <span>Avg 20-day result <b className="text-slate-100">{pct(t.avg_actual_pct, true)}</b></span>
            <span>Target touched <b className="text-emerald-300">{t.target_hit_pct.toFixed(0)}%</b></span>
            <span>Stop touched <b className="text-rose-300">{t.stop_hit_pct.toFixed(0)}%</b></span>
          </div>
          <div className="mt-1 text-slate-500">
            {t.n} calls. Swing and Owner targets are checked on their own 3- and 12-month horizons in Plan → Best setups track record.
          </div>
        </div>
      )}
      <p className="text-[12px] text-slate-500">Past results, not guarantees. Educational use only; not investment advice.</p>
    </div>
  );
}
