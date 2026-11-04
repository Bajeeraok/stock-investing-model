"use client";

import React, { useEffect, useState } from "react";
import { clsx } from "clsx";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

type Mode = "swing" | "owner";

interface SetupRow {
  ticker: string;
  price: number;
  status: string | null;
  gates_passed?: number | null;
  gates_total?: number | null;
  band_low: number;
  band_high: number;
  band_gap_pct: number | null;
  target: number;
  stop: number;
  target_pct: number;
  stop_pct: number;
  rr: number | null;
  model_prob: number | null;
  model_gain_pct: number | null;
  edge_pct: number | null;
  target_first_pct?: number | null;
  stop_first_pct?: number | null;
  duration?: string | null;
  blockers: string[];
}

interface ModeTrack {
  picks: number;
  closed: number;
  target_first_pct: number | null;
  avg_return_pct: number | null;
}

interface BestSetupsResponse {
  available: boolean;
  report: { as_of: string; scanned: number; modes: Record<Mode, { picks: SetupRow[]; next_up: SetupRow[] }> } | null;
  track: Record<Mode, ModeTrack> | null;
}

const MODE_LABEL: Record<Mode, string> = { swing: "Swing · ~3 months", owner: "Owner · ~12 months" };
const MIN_RR: Record<Mode, string> = { swing: "2:1", owner: "1.5:1" };

const usd = (v: number) => `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function Pill({ children, tone }: { children: React.ReactNode; tone: "green" | "amber" | "red" | "blue" | "slate" }) {
  const cls = {
    green: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
    amber: "bg-amber-500/10 text-amber-200 border-amber-500/30",
    red: "bg-rose-500/10 text-rose-300 border-rose-500/30",
    blue: "bg-sky-500/10 text-sky-300 border-sky-500/30",
    slate: "bg-slate-700/40 text-slate-300 border-slate-600/50",
  }[tone];
  return <span className={clsx("inline-flex items-center rounded-full border px-2 py-0.5 text-[12px] font-medium tabular-nums", cls)}>{children}</span>;
}

function Row({ r, onTickerClick, nextUp }: { r: SetupRow; onTickerClick?: (t: string) => void; nextUp?: boolean }) {
  return (
    <button
      type="button"
      onClick={() => onTickerClick?.(r.ticker)}
      className="w-full text-left rounded-xl border border-slate-700/60 bg-slate-800/40 hover:bg-slate-800/70 px-3 py-2.5 transition-colors"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono font-semibold text-slate-100 text-[15px]">{r.ticker}</span>
        <span className="font-mono text-slate-300 text-[14px] tabular-nums">{usd(r.price)}</span>
        {r.status && <Pill tone={r.status === "Can add" ? "green" : "amber"}>{r.status}</Pill>}
        {r.edge_pct != null && (
          <Pill tone={r.edge_pct > 0 ? "blue" : "slate"}>
            edge {r.edge_pct > 0 ? "+" : ""}
            {r.edge_pct.toFixed(1)}%
          </Pill>
        )}
        {nextUp && r.blockers.map((b) => <Pill key={b} tone="red">{b}</Pill>)}
      </div>
      <div className="mt-1.5 grid grid-cols-2 sm:grid-cols-4 gap-x-3 gap-y-1 text-[13px] text-slate-300">
        <span>
          Model <b className="text-slate-100">{r.model_prob ?? "–"}%</b>
          {r.model_gain_pct != null && <span className="text-slate-400"> of +{r.model_gain_pct}%</span>}
        </span>
        <span>
          Target <b className="text-emerald-300">+{r.target_pct.toFixed(1)}%</b>
          <span className="text-slate-400"> · stop −{r.stop_pct.toFixed(1)}%</span>
        </span>
        <span>
          R:R <b className="text-slate-100">{r.rr != null ? r.rr.toFixed(1) : "–"}</b>
          <span className="text-slate-400">
            {" "}
            · {r.band_gap_pct ? `${r.band_gap_pct.toFixed(1)}% above band` : "in band"}
          </span>
        </span>
        <span>
          Past target first <b className="text-slate-100">{r.target_first_pct != null ? `${r.target_first_pct}%` : "–"}</b>
        </span>
      </div>
      <div className="mt-1 text-[12px] text-slate-400 font-mono tabular-nums">
        Band {usd(r.band_low)}–{usd(r.band_high)} · stop {usd(r.stop)} · target {usd(r.target)}
      </div>
    </button>
  );
}

export function BestSetupsPanel({ onTickerClick }: { onTickerClick?: (t: string) => void }) {
  const [data, setData] = useState<BestSetupsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("swing");

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/api/best-setups`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => alive && setData(j))
      .catch((e) => alive && setErr(String(e?.message || e)));
    return () => {
      alive = false;
    };
  }, []);

  if (err) return <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-amber-200 text-sm">Best setups unavailable: {err}</div>;
  if (!data) return <div className="rounded-lg border border-slate-700 bg-slate-900/40 px-4 py-3 text-slate-400 text-sm">Loading best setups…</div>;
  if (!data.available || !data.report)
    return (
      <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-6 text-center text-slate-400 text-sm">
        Best setups are built after the nightly 8 PM ET refresh.
      </div>
    );

  const m = data.report.modes[mode] || { picks: [], next_up: [] };
  const tr = data.track?.[mode];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {(["swing", "owner"] as Mode[]).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setMode(k)}
            className={clsx(
              "rounded-full px-3 py-1 text-[13px] font-medium border",
              mode === k ? "bg-violet-500/20 text-violet-200 border-violet-400/50" : "bg-slate-800/40 text-slate-300 border-slate-700",
            )}
          >
            {MODE_LABEL[k]}
          </button>
        ))}
        <span className="text-[12px] text-slate-400">As of {data.report.as_of} close · {data.report.scanned} tickers</span>
      </div>

      <p className="text-[13px] leading-relaxed rounded-md border-l-2 border-sky-400/60 bg-sky-500/5 px-3 py-2 text-slate-300">
        Ranked by <b className="text-sky-300">edge</b> = model chance × room to target − the rest × room to stop, from the band middle.
        Listed only when entry is allowed, R:R ≥ {MIN_RR[mode]}, and price is in or within 3% of the band.
      </p>

      <div className="rounded-md border border-slate-700/60 bg-slate-800/30 px-3 py-2 text-[13px] text-slate-300 flex flex-wrap gap-x-4 gap-y-1">
        <span className="font-semibold text-slate-200">List track record</span>
        {tr && tr.picks > 0 ? (
          <>
            <span>{tr.picks} picks</span>
            <span>{tr.closed} closed</span>
            <span>
              Target first <b className="text-slate-100">{tr.target_first_pct != null ? `${tr.target_first_pct}%` : "–"}</b>
            </span>
            <span>
              Avg result{" "}
              <b className={clsx((tr.avg_return_pct ?? 0) >= 0 ? "text-emerald-300" : "text-rose-300")}>
                {tr.avg_return_pct != null ? `${tr.avg_return_pct > 0 ? "+" : ""}${tr.avg_return_pct.toFixed(1)}%` : "–"}
              </b>
            </span>
          </>
        ) : (
          <span className="text-slate-400">Starts with tonight&apos;s picks; results appear as they play out.</span>
        )}
      </div>

      {m.picks.length ? (
        <div className="space-y-2">
          {m.picks.map((r) => <Row key={r.ticker} r={r} onTickerClick={onTickerClick} />)}
        </div>
      ) : (
        <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-4 text-slate-400 text-sm">
          No ticker clears every check today. That&apos;s a valid answer: no setup is better than a forced one.
        </div>
      )}

      {m.next_up.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-[13px] font-semibold text-amber-200">Next up · one check away</h4>
          {m.next_up.map((r) => <Row key={r.ticker} r={r} onTickerClick={onTickerClick} nextUp />)}
        </div>
      )}

      <p className="text-[12px] text-slate-500 leading-snug">
        Model chance and past odds are history-based estimates, not guarantees. Educational use only; not investment advice.
      </p>
    </div>
  );
}
