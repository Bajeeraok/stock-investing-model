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
  model_proven?: boolean;
  model_gain_pct: number | null;
  hist_prob?: number | null;
  hist_basis?: "similar" | "all" | null;
  chance?: number | null;
  odds_gap?: boolean;
  new?: boolean;
  edge_pct: number | null;
  target_first_pct?: number | null;
  stop_first_pct?: number | null;
  duration?: string | null;
  blockers: string[];
  gates_failing?: string[];
  live?: { qualified: boolean; price: number | null; reasons: string[] } | null;
}

interface ModelCheck {
  n: number;
  avg_predicted_pct: number;
  came_true_pct: number;
  buckets: { range: string; n: number; avg_predicted_pct: number; came_true_pct: number }[];
}

interface ModeTrack {
  picks: number;
  closed: number;
  target_first_pct: number | null;
  avg_return_pct: number | null;
  dip_watch?: {
    names: number;
    closed: number;
    avg_vs_spy_pts: number | null;
    beat_spy_pct: number | null;
    recent: { date: string; ticker: string; vs_spy_pts: number; sessions: number; status: string; became_pick: boolean }[];
  };
}

export interface BestSetupsResponse {
  available: boolean;
  model_check?: { horizons?: Partial<Record<"medium" | "long", ModelCheck | null>> } | null;
  report: { as_of: string; live_checked_at?: string | null; scanned: number; new_count?: number; model_proven?: Partial<Record<Mode, boolean>>; modes: Record<Mode, { picks: SetupRow[]; next_up: SetupRow[]; dip_watch?: SetupRow[] }> } | null;
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

function blockerLabel(r: SetupRow, b: string) {
  return b === "entry gates" && r.gates_total ? `entry gates ${r.gates_passed ?? 0}/${r.gates_total}` : b;
}

function NearMissLine({ r, onTickerClick }: { r: SetupRow; onTickerClick?: (t: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onTickerClick?.(r.ticker)}
      className="flex w-full flex-wrap items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-800/30 px-3 py-2 text-left hover:bg-slate-800/60"
    >
      <span className="font-mono font-semibold text-slate-100">{r.ticker}</span>
      {r.edge_pct != null && <Pill tone="blue">edge +{r.edge_pct.toFixed(1)}%</Pill>}
      {r.blockers[0] && <Pill tone="red">{blockerLabel(r, r.blockers[0])}</Pill>}
      {r.blockers[0] === "entry gates" && r.gates_failing?.length ? (
        <span className="text-[12px] text-slate-400">{r.gates_failing.join(", ")}</span>
      ) : null}
    </button>
  );
}

function Row({ r, onTickerClick, nextUp }: { r: SetupRow; onTickerClick?: (t: string) => void; nextUp?: boolean }) {
  return (
    <button
      type="button"
      onClick={() => onTickerClick?.(r.ticker)}
      className="w-full text-left rounded-xl border border-slate-700/60 bg-slate-800/40 hover:bg-slate-800/70 px-3 py-2.5 transition-colors"
    >
      <div className="flex flex-wrap items-center gap-2">
        {r.new && (
          <span className="relative flex h-2.5 w-2.5" aria-label="new today">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
          </span>
        )}
        <span className="font-mono font-semibold text-slate-100 text-[15px]">{r.ticker}</span>
        {r.new && <Pill tone="green">NEW</Pill>}
        <span className="font-mono text-slate-300 text-[14px] tabular-nums">{usd(r.price)}</span>
        {r.status && !(r.live && !r.live.qualified) && (
          <Pill tone={r.status === "Can add" ? "green" : "amber"}>{r.status}</Pill>
        )}
        {r.live && !r.live.qualified && <Pill tone="red">No longer qualifies</Pill>}
        {r.edge_pct != null && (
          <Pill tone={r.edge_pct > 0 ? "blue" : "slate"}>
            edge {r.edge_pct > 0 ? "+" : ""}
            {r.edge_pct.toFixed(1)}%
          </Pill>
        )}
        {nextUp &&
          r.blockers.map((b) => (
            <Pill key={b} tone="red">
              {blockerLabel(r, b)}
            </Pill>
          ))}
      </div>
      {!nextUp && r.live && !r.live.qualified && (
        <div className="mt-1 text-[13px] text-rose-200/90">
          Now{r.live.price != null ? ` ${usd(r.live.price)}` : ""}: {r.live.reasons.join(" · ") || "no longer passes"}
        </div>
      )}
      {nextUp && (
        <div className="mt-1 text-[13px] text-rose-200/90">
          {r.blockers[0] === "entry gates"
            ? `Blocked: ticker page says No new entries${r.gates_failing?.length ? ` · failing: ${r.gates_failing.join(", ")}` : ""}`
            : r.blockers[0] === "price above band"
              ? `Blocked: price is more than 3% above the entry band ($${r.band_low.toLocaleString()}–$${r.band_high.toLocaleString()})`
              : `Blocked: ${r.blockers[0]}`}
        </div>
      )}
      <div className="mt-1.5 grid grid-cols-2 sm:grid-cols-4 gap-x-3 gap-y-1 text-[13px] text-slate-300">
        <span className="col-span-2 sm:col-span-4">
          {r.model_gain_pct != null ? `+${r.model_gain_pct}% within ${r.duration ?? "horizon"}: ` : ""}
          Model <b className="text-slate-100">{r.model_prob ?? "–"}%</b>
          {!r.model_proven && r.model_prob != null && <span className="text-slate-500"> (unproven)</span>}
          <span className="text-slate-400"> · </span>
          History <b className="text-slate-100">{r.hist_prob ?? "–"}%</b>
          {r.hist_basis === "similar" && <span className="text-slate-400"> (similar setups)</span>}
          {r.odds_gap && (
            <span className="ml-1.5">
              <Pill tone="amber">model far above history</Pill>
            </span>
          )}
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
          Past first: <b className="text-emerald-300">target {r.target_first_pct != null ? `${r.target_first_pct}%` : "–"}</b>
          <span className="text-slate-400"> · stop {r.stop_first_pct != null ? `${r.stop_first_pct}%` : "–"}</span>
        </span>
      </div>
      <div className="mt-1 text-[12px] text-slate-400 font-mono tabular-nums">
        Band {usd(r.band_low)}–{usd(r.band_high)} · stop {usd(r.stop)} · target {usd(r.target)}
      </div>
    </button>
  );
}

export function useBestSetups() {
  const [data, setData] = useState<BestSetupsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
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
  return { data, err };
}

/** Best edge per ticker across Swing/Owner picks and next-up rows. */
export function bestSetupEdges(data: BestSetupsResponse | null): Record<string, number> {
  const out: Record<string, number> = {};
  const modes = data?.report?.modes;
  if (!modes) return out;
  for (const m of Object.values(modes)) {
    for (const r of [...(m?.picks || []), ...(m?.next_up || [])]) {
      if (r.edge_pct == null) continue;
      out[r.ticker] = Math.max(out[r.ticker] ?? -Infinity, r.edge_pct);
    }
  }
  return out;
}

export function BestSetupsPanel({
  onTickerClick,
  data,
  err,
}: {
  onTickerClick?: (t: string) => void;
  data: BestSetupsResponse | null;
  err: string | null;
}) {
  const [mode, setMode] = useState<Mode>("swing");

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
  const modelProven = !!data.report.model_proven?.[mode];

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
        <span className="text-[12px] text-slate-400">As of {data.report.as_of} close · {data.report.scanned} tickers
          {data.report.live_checked_at ? ` · picks rechecked ${data.report.live_checked_at.slice(11, 16)} ET` : ""}
        </span>
      </div>

      <p className="text-[13px] leading-relaxed rounded-md border-l-2 border-sky-400/60 bg-sky-500/5 px-3 py-2 text-slate-300">
        Ranked by <b className="text-sky-300">edge</b> = past target-first % × room to target − past stop-first % × room to stop, from the band middle.
        Listed only when entry is allowed, chance ≥ 40%, R:R ≥ {MIN_RR[mode]}, and price is in or within 3% of the band. Chance = this stock&apos;s past odds of the model&apos;s +N% move
        {modelProven ? ", capped by the model's %." : ". The model % is shown but not used until it proves itself (More → Model check)."}
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
        <details className="group rounded-xl border border-slate-700/60 bg-slate-800/20 px-3 py-2">
          <summary className="cursor-pointer list-none text-[13px] font-semibold text-amber-200">
            Near misses ({Math.min(m.next_up.length, 3)}) · blocked by one rule <span className="text-slate-400 group-open:hidden">› show</span>
          </summary>
          <p className="mt-1 mb-2 text-[12px] text-slate-400 leading-snug">
            These pass every rule except the red one. Tap for the ticker page.
          </p>
          <div className="space-y-1.5">
            {m.next_up.slice(0, 3).map((r) => <NearMissLine key={r.ticker} r={r} onTickerClick={onTickerClick} />)}
          </div>
        </details>
      )}

      {(m.dip_watch?.length ?? 0) > 0 && (
        <details className="group rounded-xl border border-slate-700/60 bg-slate-800/20 px-3 py-2">
          <summary className="cursor-pointer list-none text-[13px] font-semibold text-sky-200">
            Dip watch ({m.dip_watch!.length}) · watch only, not a buy <span className="text-slate-400 group-open:hidden">› show</span>
          </summary>
          <p className="mt-1 mb-2 text-[12px] text-slate-400 leading-snug">
            These pass every rule except Trend weather: the stock&apos;s own trend hasn&apos;t confirmed a recovery yet.
            In tracked history, stocks blocked only by weather lagged SPY until it cleared, so wait for the gate to turn green.
          </p>
          <div className="space-y-1.5">
            {m.dip_watch!.map((r) => <NearMissLine key={r.ticker} r={r} onTickerClick={onTickerClick} />)}
          </div>
        </details>
      )}

      {(tr?.dip_watch?.names ?? 0) > 0 && (
        <p className="text-[12px] text-slate-400 leading-snug">
          <span className="font-semibold text-sky-200">Dip watch track record</span> · {tr!.dip_watch!.names} names tracked
          {tr!.dip_watch!.closed > 0 ? (
            <>
              {" "}· after ~30 days: {tr!.dip_watch!.avg_vs_spy_pts! >= 0 ? "+" : ""}
              {tr!.dip_watch!.avg_vs_spy_pts!.toFixed(1)} pts vs SPY, beat SPY {tr!.dip_watch!.beat_spy_pct}% (n={tr!.dip_watch!.closed})
            </>
          ) : (
            <> · first 30-day results land ~30 days after a name is listed</>
          )}
          {tr!.dip_watch!.recent.length > 0 && (
            <span className="block text-slate-500">
              So far:{" "}
              {tr!.dip_watch!.recent.slice(0, 6).map((r) => `${r.ticker} ${r.vs_spy_pts >= 0 ? "+" : ""}${r.vs_spy_pts.toFixed(1)} (${r.sessions}d)`).join(" · ")}
            </span>
          )}
        </p>
      )}

      <p className="text-[12px] text-slate-500 leading-snug">
        Model chance and past odds are history-based estimates, not guarantees. Educational use only; not investment advice.
      </p>
    </div>
  );
}

export function BestSetupsTodayCard({
  data,
  onOpen,
  onTickerClick,
}: {
  data: BestSetupsResponse | null;
  onOpen: () => void;
  onTickerClick?: (t: string) => void;
}) {
  const modes = data?.report?.modes;
  if (!modes) return null;
  const picks = (["swing", "owner"] as Mode[]).flatMap((m) => (modes[m]?.picks || []).map((r) => ({ m, r })));
  const next = (["swing", "owner"] as Mode[]).flatMap((m) => (modes[m]?.next_up || []).slice(0, 1).map((r) => ({ m, r })));
  const nNew = data?.report?.new_count ?? 0;
  const label = (m: Mode) => (m === "swing" ? "Swing" : "Owner");
  return (
    <div className={clsx("rounded-2xl border p-4", nNew > 0 ? "border-emerald-500/50 bg-emerald-500/5" : "border-slate-700/60 bg-slate-800/30")}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {nNew > 0 && (
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
            </span>
          )}
          <h3 className="text-[15px] font-semibold text-slate-100">Best setups</h3>
          <Pill tone={picks.length ? "green" : "slate"}>
            {(modes.swing?.picks || []).length} Swing · {(modes.owner?.picks || []).length} Owner
          </Pill>
          {nNew > 0 && <Pill tone="green">{nNew} NEW</Pill>}
        </div>
        <button type="button" onClick={onOpen} className="text-[13px] font-medium text-violet-300 hover:underline">
          Open ›
        </button>
      </div>
      <div className="mt-2 space-y-1.5 text-[13px] text-slate-300">
        {picks.length ? (
          picks.slice(0, 3).map(({ m, r }) => (
            <button key={m + r.ticker} type="button" onClick={() => onTickerClick?.(r.ticker)} className="flex w-full flex-wrap items-center gap-2 text-left">
              <span className="font-mono font-semibold text-slate-100">{r.ticker}</span>
              <span className="text-slate-400">{label(m)}</span>
              {r.new && <Pill tone="green">NEW</Pill>}
              <Pill tone="blue">edge +{(r.edge_pct ?? 0).toFixed(1)}%</Pill>
              <span>chance {r.chance ?? "–"}%</span>
            </button>
          ))
        ) : (
          <p className="text-slate-400">
            None clear every check today{next.length ? " · next up " : "."}
            {next.map(({ m, r }, i) => (
              <span key={m + r.ticker}>
                {i > 0 ? ", " : ""}
                <button type="button" onClick={() => onTickerClick?.(r.ticker)} className="font-mono font-semibold text-slate-200 hover:underline">
                  {r.ticker}
                </button>{" "}
                ({label(m)})
              </span>
            ))}
          </p>
        )}
      </div>
    </div>
  );
}
