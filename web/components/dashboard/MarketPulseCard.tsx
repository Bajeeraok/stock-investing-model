"use client";

import React, { useEffect, useState } from "react";
import { clsx } from "clsx";
import { AlertTriangle } from "lucide-react";
import { apiUrl } from "@/lib/apiBase";

interface Levels {
  prev_close: number;
  expected_open?: number | null;
  open?: number | null;
  last?: number | null;
  close_low: number | null;
  close_mid?: number | null;
  close_high: number | null;
}
interface PreOpen {
  expected_gap_pct: number;
  lean: "BEARISH" | "BULLISH" | "MIXED";
  p_close_red: number;
  p_close_green: number;
  eod_range_pct: { q10: number; q50: number; q90: number };
  similar_days: number;
  high_risk: boolean;
  risk_reasons: string[];
  engine_bias?: string | null;
  note: string;
  preview?: boolean;
  as_of?: string;
  ref_close_date?: string;
  levels?: Levels | null;
}
interface Intraday {
  move_so_far_pct: number;
  minutes_since_open: number;
  range80_pct: [number, number];
  p_close_green: number;
  actual_gap_pct?: number;
  note: string;
  as_of?: string;
  ref_close_date?: string;
  levels?: Levels | null;
}
interface SlotSummary {
  days: number;
  direction_hit_pct: number | null;
  direction_calls: number;
  range_coverage_pct: number | null;
}
interface ScoredDay {
  date: string;
  actual_gap_pct?: number | null;
  actual_close_pct: number;
  pre_open?: { lean: string; hit: boolean | null; in_range: boolean | null; late?: boolean };
  "10:30"?: { call: string; hit: boolean; in_range: boolean };
  "12:30"?: { call: string; hit: boolean; in_range: boolean };
}
export interface MarketPulse {
  as_of: string;
  ref_close_date?: string;
  phase: "pre_open" | "intraday" | "closed";
  pre_open: PreOpen | null;
  intraday: Intraday | null;
  qqq?: { pre_open: PreOpen | null; intraday: Intraday | null } | null;
  vix?: { last: number | null; pct: number | null };
  scorecard?: {
    summary: Record<string, SlotSummary>;
    days: ScoredDay[];
    calibration?: {
      by_slot?: Record<string, { days: number; direction_hit_pct: number; range_coverage_pct: number }>;
      green_odds?: { range: [number, number]; n: number; avg_said_pct: number; closed_green_pct: number }[];
    };
  } | null;
  disclaimer: string;
}

const pct = (n: number | null | undefined, d = 2) => (n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(d)}%`);
const tone = (lean?: string) =>
  lean === "BEARISH" ? "text-red-400" : lean === "BULLISH" ? "text-emerald-400" : "text-slate-300";
const mark = (v: boolean | null | undefined) =>
  v == null ? <span className="text-slate-600">—</span> : v ? <span className="text-emerald-400">✓</span> : <span className="text-red-400">✗</span>;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-11-05" → "Nov 5 close"; falls back to "yesterday" when the date is unknown. */
const closeLabel = (d?: string | null) => {
  const m = d && /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])} close` : "yesterday";
};
/** ISO timestamp → "Nov 6, 8:18 AM ET". */
const asOfEt = (iso?: string | null) => {
  if (!iso) return null;
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return null;
  return `${t.toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} ET`;
};
const usd = (n: number | null | undefined) =>
  n == null ? "—" : `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const withDate = (note: string, label: string) => note.replace(/vs yesterday/g, `vs ${label}`);

function PreOpenBlock({ sym, pre, refLabel, asOf }: { sym: string; pre: PreOpen; refLabel: string; asOf: string }) {
  const lv = pre.levels;
  return (
    <div className={clsx("rounded-lg border px-3 py-2", pre.high_risk ? "border-red-500/50 bg-red-500/10" : "border-slate-700 bg-slate-800/40")}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[13px] uppercase tracking-wide text-slate-400">{pre.preview ? `Next session preview (${sym})` : `Pre-open (${sym})`}</span>
        <span className={clsx("font-semibold", tone(pre.lean))}>{pre.lean}</span>
        <span className="text-slate-300 tabular-nums">Expected open {pct(pre.expected_gap_pct)}</span>
        <span className="text-slate-300 tabular-nums">Close red {Math.round(pre.p_close_red * 100)}%</span>
        {pre.high_risk && (
          <span className="inline-flex items-center gap-1 text-red-300 font-semibold">
            <AlertTriangle className="h-3.5 w-3.5" /> High-risk day
          </span>
        )}
      </div>
      {lv && (
        <p className="text-[13px] text-slate-200 mt-1 tabular-nums">
          {refLabel.replace(/ close$/, "")} close {usd(lv.prev_close)} → open ≈ {usd(lv.expected_open)} · likely close {usd(lv.close_low)}–{usd(lv.close_high)}
          {lv.close_mid != null && <span className="text-slate-400"> (median {usd(lv.close_mid)})</span>}
        </p>
      )}
      <p className="text-[13px] text-slate-500 mt-0.5">
        As of {asOfEt(pre.as_of ?? asOf) ?? "—"} · compared with {sym}&apos;s {refLabel}
      </p>
      <p className="text-[13px] text-slate-400 mt-1 tabular-nums">
        Likely close {pct(pre.eod_range_pct.q10)} to {pct(pre.eod_range_pct.q90)} vs {refLabel} (median {pct(pre.eod_range_pct.q50)}).
        {pre.risk_reasons.length > 0 && ` ${pre.risk_reasons.join(" · ")}.`}
        {pre.engine_bias && ` Engine: ${pre.engine_bias}.`}
      </p>
      <p className="text-[13px] text-slate-500 mt-0.5">{withDate(pre.note, refLabel)}</p>
    </div>
  );
}

function IntradayBlock({ sym, intra, phase, asOf }: { sym: string; intra: Intraday; phase: MarketPulse["phase"]; asOf: string }) {
  const refLabel = closeLabel(intra.ref_close_date);
  const lv = intra.levels;
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/40 px-3 py-2">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[13px] uppercase tracking-wide text-slate-400">{phase === "intraday" ? `Intraday (${sym})` : `Today's close (${sym})`}</span>
        <span className={clsx("font-semibold tabular-nums", intra.move_so_far_pct >= 0 ? "text-emerald-400" : "text-red-400")}>
          {pct(intra.move_so_far_pct)} so far
        </span>
        {phase === "intraday" && (
          <>
            <span className="text-slate-300 tabular-nums">
              Likely close {pct(intra.range80_pct[0])} to {pct(intra.range80_pct[1])}
            </span>
            <span className="text-slate-300 tabular-nums">Close green {Math.round(intra.p_close_green * 100)}%</span>
          </>
        )}
      </div>
      {lv && (
        <p className="text-[13px] text-slate-200 mt-1 tabular-nums">
          {refLabel.replace(/ close$/, "")} close {usd(lv.prev_close)}
          {lv.open != null && ` · open ${usd(lv.open)}`} · {phase === "intraday" ? "now" : "close"} {usd(lv.last)}
          {phase === "intraday" && ` · likely close ${usd(lv.close_low)}–${usd(lv.close_high)}`}
        </p>
      )}
      <p className="text-[13px] text-slate-500 mt-0.5">
        As of {asOfEt(intra.as_of ?? asOf) ?? "—"} · % vs {sym}&apos;s {refLabel}
      </p>
      {phase === "intraday" && <p className="text-[13px] text-slate-500 mt-0.5">{withDate(intra.note, refLabel)}</p>}
    </div>
  );
}

/** SPY + QQQ pre-open odds + intraday likely-close range + how past SPY calls held up. */
export function MarketPulseCard() {
  const [data, setData] = useState<MarketPulse | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      fetch(apiUrl("/api/market-pulse"), { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((j) => alive && (setData(j), setErr(false)))
        .catch(() => alive && setErr(true));
    load();
    const id = window.setInterval(load, 5 * 60 * 1000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  if (err && !data) return <p className="text-[13px] text-slate-500">Market pulse unavailable right now.</p>;
  if (!data) return <p className="text-[13px] text-slate-500">Loading market pulse…</p>;
  const pre = data.pre_open;
  const intra = data.intraday;
  const qPre = data.qqq?.pre_open ?? null;
  const qIntra = data.qqq?.intraday ?? null;
  const sum = data.scorecard?.summary;
  const days = data.scorecard?.days ?? [];
  const preRef = closeLabel(pre?.ref_close_date ?? data.ref_close_date);
  const hasLate = days.some((d) => d.pre_open?.late);

  return (
    <div className="space-y-3 text-sm">
      {pre && <PreOpenBlock sym="SPY" pre={pre} refLabel={preRef} asOf={data.as_of} />}
      {qPre && <PreOpenBlock sym="QQQ" pre={qPre} refLabel={closeLabel(qPre.ref_close_date ?? data.ref_close_date)} asOf={data.as_of} />}
      {intra && <IntradayBlock sym="SPY" intra={intra} phase={data.phase} asOf={data.as_of} />}
      {qIntra && <IntradayBlock sym="QQQ" intra={qIntra} phase={data.phase} asOf={data.as_of} />}
      {!pre && !intra && <p className="text-[13px] text-slate-500">No pulse yet — pre-open read starts ~4 AM ET on trading days.</p>}

      <div>
        <p className="text-[13px] text-slate-400 mb-1">How these calls held up</p>
        {sum && Object.values(sum).some((s) => s.days > 0) ? (
          <>
            <div className="grid grid-cols-3 gap-2 text-[13px] tabular-nums">
              {(["pre_open", "10:30", "12:30"] as const).map((k) => (
                <div key={k} className="rounded border border-slate-700 px-2 py-1">
                  <p className="text-slate-500">{k === "pre_open" ? "Pre-open" : k}</p>
                  <p className="text-slate-200">
                    Direction {sum[k]?.direction_hit_pct != null ? `${sum[k].direction_hit_pct}%` : "—"}
                    <span className="text-slate-500"> (n={sum[k]?.direction_calls ?? 0})</span>
                  </p>
                  <p className="text-slate-400">In range {sum[k]?.range_coverage_pct != null ? `${sum[k].range_coverage_pct}%` : "—"}</p>
                </div>
              ))}
            </div>
            <div className="overflow-x-auto mt-2">
              <table className="w-full text-[13px] min-w-[420px] tabular-nums">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-700">
                    <th className="py-1 pr-2 font-medium">Date</th>
                    <th className="py-1 pr-2 font-medium">Pre-open call</th>
                    <th className="py-1 pr-2 font-medium">Open</th>
                    <th className="py-1 pr-2 font-medium">Close</th>
                    <th className="py-1 pr-2 font-medium">Pre</th>
                    <th className="py-1 pr-2 font-medium">10:30</th>
                    <th className="py-1 font-medium">12:30</th>
                  </tr>
                </thead>
                <tbody>
                  {days.slice(0, 10).map((d) => (
                    <tr key={d.date} className="border-b border-slate-800 text-slate-300">
                      <td className="py-1 pr-2 font-mono">{d.date}</td>
                      <td className={clsx("py-1 pr-2", d.pre_open?.late ? "text-slate-500" : tone(d.pre_open?.lean))}>
                        {d.pre_open?.lean ?? "—"}
                        {d.pre_open?.late && "*"}
                      </td>
                      <td className="py-1 pr-2">{pct(d.actual_gap_pct)}</td>
                      <td className={clsx("py-1 pr-2", d.actual_close_pct >= 0 ? "text-emerald-400" : "text-red-400")}>{pct(d.actual_close_pct)}</td>
                      <td className="py-1 pr-2">{mark(d.pre_open?.hit)}</td>
                      <td className="py-1 pr-2">{mark(d["10:30"]?.hit)}</td>
                      <td className="py-1">{mark(d["12:30"]?.hit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {(data.scorecard?.calibration?.green_odds?.length ?? 0) > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-[13px] text-slate-400">
                  Calibration check · hourly snapshots 10:30–3:30 (not in the scores above)
                </summary>
                <p className="text-[12px] text-slate-500 mt-1">
                  When the card said X% green, how often SPY actually closed green. Later hours are easier, so they are kept out of the headline scores.
                </p>
                <table className="w-full text-[13px] tabular-nums mt-1">
                  <thead>
                    <tr className="text-left text-slate-500 border-b border-slate-700">
                      <th className="py-1 pr-2 font-medium">Said green</th>
                      <th className="py-1 pr-2 font-medium">Avg said</th>
                      <th className="py-1 pr-2 font-medium">Closed green</th>
                      <th className="py-1 font-medium">n</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.scorecard!.calibration!.green_odds!.map((b) => (
                      <tr key={b.range[0]} className="border-b border-slate-800 text-slate-300">
                        <td className="py-1 pr-2">{Math.round(b.range[0] * 100)}–{Math.round(b.range[1] * 100)}%</td>
                        <td className="py-1 pr-2">{b.avg_said_pct}%</td>
                        <td className="py-1 pr-2">{b.closed_green_pct}%</td>
                        <td className="py-1">{b.n}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-[12px] text-slate-500 mt-1">
                  In range by hour:{" "}
                  {Object.entries(data.scorecard!.calibration!.by_slot ?? {})
                    .map(([k, v]) => `${k} ${v.range_coverage_pct}% (n=${v.days})`)
                    .join(" · ")}
                </p>
              </details>
            )}
          </>
        ) : (
          <p className="text-[13px] text-slate-500">Scoring starts after the first logged trading day (calls saved at 9:20, 10:31 and 12:31 ET).</p>
        )}
      </div>
      {hasLate && (
        <p className="text-[13px] text-slate-500">
          * Saved after the open by an earlier version (it already saw the first hour), so not scored. Pre-open calls are now saved at 9:20 ET.
        </p>
      )}
      <p className="text-[13px] text-slate-500">{data.disclaimer} MIXED pre-open calls aren&apos;t scored for direction.</p>
    </div>
  );
}
