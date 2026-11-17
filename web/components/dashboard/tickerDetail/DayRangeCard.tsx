"use client";

/** Today's likely close range + chance price trades at the entry band / stop. Display only. */
import React, { useEffect, useState } from "react";
import { CalendarRange } from "lucide-react";
import { apiUrl } from "@/lib/apiBase";
import { isUsEquityRth } from "@/lib/dashboardCache";

const LIVE_REFRESH_MS = 60_000;

/** During market hours, refetch just the day-range card every minute (1-min bars server-side). */
export function useLiveDayRange(ticker: string | undefined, initial?: DayRangePayload | null) {
  const [data, setData] = useState<DayRangePayload | null | undefined>(initial);
  useEffect(() => setData(initial), [initial]);
  useEffect(() => {
    if (!ticker) return;
    const ac = new AbortController();
    const tick = async () => {
      if (!isUsEquityRth() || document.visibilityState !== "visible") return;
      try {
        const res = await fetch(apiUrl(`/api/ticker/${encodeURIComponent(ticker)}/day-range`), { signal: ac.signal, cache: "no-store" });
        if (!res.ok) return;
        const j: { day_range?: DayRangePayload | null } = await res.json();
        if (j.day_range) setData(j.day_range);
      } catch {
        /* keep the last good card */
      }
    };
    const id = setInterval(tick, LIVE_REFRESH_MS);
    return () => {
      ac.abort();
      clearInterval(id);
    };
  }, [ticker]);
  return data;
}

export type DayRangeLevel = {
  label: string;
  price: number;
  side: "above" | "below";
  p_reach: number;
  /** Chance the close finishes beyond the level (below it for "below", above it for "above"). */
  p_close_beyond?: number;
  touched: boolean;
};
export type DayRangePayload = {
  phase: "intraday" | "next_session";
  ref_close: number;
  ref_date: string;
  session_date?: string | null;
  sigma_pct: number;
  last?: number;
  minutes_left?: number;
  close_low: number;
  close_mid: number;
  close_high: number;
  close_low50?: number;
  close_high50?: number;
  p_close_green: number | null;
  premarket?: number | null;
  day_open?: number | null;
  open_forecast?: { open_mid: number; open_low?: number; open_high?: number } | null;
  open_mid?: number;
  open_low?: number;
  open_high?: number;
  open_low50?: number;
  open_high50?: number;
  day_low?: number | null;
  day_high?: number | null;
  p_new_low?: number | null;
  p_new_high?: number | null;
  p_close_below_day?: number | null;
  p_close_above_day?: number | null;
  levels: DayRangeLevel[];
  ladder?: { p: number; dip: number; pop: number; close_below?: number; close_above?: number }[];
  scorecard?: { sessions: number; inside: number; coverage_pct: number } | null;
  reach_calibration?: { sessions: number; tickers: number; cases: number };
  bounce_zone?: {
    ref_close: number;
    drawdown_pct: number;
    ma50: number;
    low: number;
    mid: number;
    high: number;
    horizon_days: number;
    test: { from: string; coverage_pct: number; median_err_pct: number; limit_fill_pct: number; ret_limit_pct: number; ret_now_pct: number; ret_missed_pct: number };
  } | null;
  tracked?: {
    days: number;
    since: string | null;
    history?: { date: string; open_pred?: number | null; open?: number | null; low_pred?: number | null; low?: number | null; close_pred?: number | null; close?: number | null; in50?: boolean | null; in80?: boolean | null }[];
    slots: Record<string, { label: string; n: number; in80_pct: number | null; in50_pct: number | null; open_n?: number; open_in80_pct?: number | null; avg_abs_open_err_pct?: number; ladder: { p: number; hit_pct: number | null; n: number }[] }>;
  } | null;
};

/** 50% close band; older payloads lack it, so derive from the 80% band. */
export function band50(d: DayRangePayload): [number, number] {
  if (d.close_low50 != null && d.close_high50 != null) return [d.close_low50, d.close_high50];
  const f = (v: number) => d.close_mid * Math.exp(Math.log(v / d.close_mid) * (0.6745 / 1.2816));
  return [f(d.close_low), f(d.close_high)];
}

const usd = (n: number) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
/** Levels under this chance are grouped into one "out of reach" line. */
export const REACH_MIN = 0.05;
export const splitLevels = (d: DayRangePayload) => ({
  near: d.levels.filter((l) => l.p_reach >= REACH_MIN),
  far: d.levels.filter((l) => l.p_reach < REACH_MIN),
});

/** Highest-probability lows (75% and 50% chance) and where they sit vs the entry bands.
 *  Intraday, a dip above the low already printed today is not a new low, so skip to deeper rungs. */
/** Ladder for today's full low/high. Intraday, a level the session already traded is 100% reached,
 * so the low at any chance is never above the low so far (and the high never below the high so far). */
export function dayLadder(d: DayRangePayload) {
  const live = d.phase === "intraday";
  const lo = live ? d.day_low ?? null : null;
  const hi = live ? d.day_high ?? null : null;
  return (d.ladder ?? []).map((r) => {
    const dipReached = lo != null && r.dip >= lo;
    const popReached = hi != null && r.pop <= hi;
    return {
      ...r,
      dip: dipReached ? (lo as number) : r.dip,
      pop: popReached ? (hi as number) : r.pop,
      dipReached,
      popReached,
      close_below: dipReached ? d.p_close_below_day ?? r.close_below : r.close_below,
      close_above: popReached ? d.p_close_above_day ?? r.close_above : r.close_above,
    };
  });
}

export function likelyLow(d: DayRangePayload) {
  const soFar = d.phase === "intraday" && d.day_low != null ? d.day_low : null;
  const lad = (d.ladder ?? []).filter((x) => soFar == null || x.dip < soFar);
  const hi = soFar == null ? lad.find((x) => x.p === 0.75) : lad[0];
  const mid = soFar == null ? lad.find((x) => x.p === 0.5) : lad[1];
  if (!hi) return soFar != null ? { hi: null, mid: null, where: "", soFar } : null;
  const lv = (label: string) => d.levels.find((l) => l.label === label)?.price;
  const sLo = lv("Swing band low");
  const sHi = lv("Swing band top");
  const oHi = lv("Owner band top");
  const where = (v: number) =>
    oHi != null && v <= oHi
      ? "inside the Owner band"
      : sLo != null && sHi != null && v >= sLo && v <= sHi
        ? "inside the Swing band"
        : sHi != null && v > sHi
          ? "above the Swing band"
          : "outside the entry bands";
  return { hi, mid, where: where(hi.dip), soFar };
}

export const pct = (p: number) => (p < 0.01 ? "<1%" : p > 0.99 ? ">99%" : `${Math.round(p * 100)}%`);

function oddsTone(p: number) {
  if (p >= 0.5) return "text-td-accent";
  if (p >= 0.2) return "text-td-warn";
  return "text-td-muted";
}

export function DayRangeCard({ data: initial, price, ticker }: { data?: DayRangePayload | null; price?: number | null; ticker?: string }) {
  const data = useLiveDayRange(ticker, initial);
  if (!data) return null;
  const live = data.phase === "intraday";
  const spot = price ?? data.last ?? data.ref_close;
  const lo = Math.min(data.close_low, data.day_low ?? data.close_low, spot);
  const hi = Math.max(data.close_high, data.day_high ?? data.close_high, spot);
  const pos = (v: number) => `${Math.max(0, Math.min(100, ((v - lo) / (hi - lo || 1)) * 100))}%`;
  const [lo50, hi50] = band50(data);
  const { near, far } = splitLevels(data);
  const when = live ? "before close" : "next session";
  const ll = likelyLow(data);
  const hrs = data.minutes_left != null ? `${Math.floor(data.minutes_left / 60)}h ${data.minutes_left % 60}m left` : "";

  return (
    <section className="rounded-xl border border-td-line bg-td-surface/60 p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <CalendarRange className="h-4 w-4 text-td-accent" aria-hidden />
          <h3 className="text-sm font-semibold text-td-text">{live ? "Today's likely close" : `Next session range${data.session_date ? ` · ${sessionDay(data.session_date)}` : ""}`}</h3>
        </div>
        <span className="text-[12px] text-td-muted">
          {live ? hrs : data.premarket != null ? `from pre-market ${usd(data.premarket)} · ${data.ref_date} close ${usd(data.ref_close)}` : `vs ${data.ref_date} close ${usd(data.ref_close)}`}
        </span>
      </div>

      {ll && (
        <div className="rounded-lg border border-td-accent/40 bg-td-accent/10 px-3 py-2 text-[13px]">
          <div className="flex justify-between gap-2">
            <span className="font-semibold text-td-text">
              {ll.soFar != null ? (ll.hi ? `Low so far ${usd(ll.soFar)} · next low` : "Today's low so far") : `Likely low ${live ? "today" : "next session"}`}
            </span>
            <span className="font-mono font-semibold text-td-accent">{usd(ll.hi ? ll.hi.dip : (ll.soFar as number))}</span>
          </div>
          <p className="text-[12px] text-td-muted mt-0.5">
            {ll.hi ? (
              <>
                {pct(ll.hi.p)} chance it trades there {when} ({ll.where})
                {ll.mid && <> · deeper {usd(ll.mid.dip)} at {pct(ll.mid.p)}</>}
              </>
            ) : (
              <>
                Already traded there.
                {data.p_new_low != null && <> {pct(data.p_new_low)} chance of a new low below it {when}</>}
                {data.p_close_below_day != null && <> · {pct(data.p_close_below_day)} it closes below it</>}.
              </>
            )}
          </p>
        </div>
      )}

      <ul className="space-y-1 text-[13px]">
        {!live && data.open_mid != null && (
          <li className="flex justify-between gap-2">
            <span className="text-td-muted">Predicted open</span>
            <span className="font-mono text-td-text">
              <span className="font-semibold">{usd(data.open_mid)}</span>
              {data.open_low != null && data.open_high != null && <span className="text-td-muted"> · 80% {usd(data.open_low)}–{usd(data.open_high)}</span>}
            </span>
          </li>
        )}
        {live && data.day_open != null && (
          <li className="flex justify-between gap-2">
            <span className="text-td-muted">Open</span>
            <span className="font-mono text-td-text">
              <span className="font-semibold">{usd(data.day_open)}</span>
              {data.open_forecast?.open_mid != null && (
                <span className="text-td-muted">
                  {" "}· predicted {usd(data.open_forecast.open_mid)} ({missPct(data.day_open, data.open_forecast.open_mid)})
                </span>
              )}
            </span>
          </li>
        )}
        <li className="flex justify-between gap-2">
          <span className="text-td-muted">Most likely close</span>
          <span className="font-mono font-semibold text-td-text">{usd(data.close_mid)}</span>
        </li>
        <li className="flex justify-between gap-2">
          <span className="text-td-muted">50% chance it closes in</span>
          <span className="font-mono text-td-text">{usd(lo50)}–{usd(hi50)}</span>
        </li>
        <li className="flex justify-between gap-2">
          <span className="text-td-muted">80% chance it closes in</span>
          <span className="font-mono text-td-text">{usd(data.close_low)}–{usd(data.close_high)}</span>
        </li>
      </ul>

      <div>
        <div className="relative h-2 mt-1.5 rounded-full bg-td-bg">
          <div
            className="absolute h-2 rounded-full bg-td-accent/30"
            style={{ left: pos(data.close_low), width: `calc(${pos(data.close_high)} - ${pos(data.close_low)})` }}
          />
          <div
            className="absolute h-2 rounded-full bg-td-accent/60"
            style={{ left: pos(lo50), width: `calc(${pos(hi50)} - ${pos(lo50)})` }}
          />
          <div className="absolute -top-1 h-4 w-0.5 bg-td-text" style={{ left: pos(spot) }} title={`Now ${usd(spot)}`} />
        </div>
        <p className="text-[12.5px] text-td-muted mt-1.5">
          {live && data.p_close_green != null ? (
            <>
              Green close odds <span className="font-semibold text-td-text">{pct(data.p_close_green)}</span>
              {data.day_low != null && data.day_high != null && <> · day so far {usd(data.day_low)}–{usd(data.day_high)}</>}
            </>
          ) : (
            <>Sized by this stock's typical daily move (±{data.sigma_pct.toFixed(1)}%). Before the open, up or down is close to a coin flip.</>
          )}
        </p>
      </div>

      {data.ladder && data.ladder.length > 0 && (
        <div className="text-[13px]">
          <div className="grid grid-cols-3 gap-2 text-[12px] text-td-muted">
            <span>Chance {live ? "for today's low / high" : when}</span>
            <span className="text-right">Low reaches</span>
            <span className="text-right">High reaches</span>
          </div>
          {dayLadder(data).map((r) => (
            <div key={r.p} className="grid grid-cols-3 gap-2 font-mono">
              <span className={`font-semibold ${oddsTone(r.p)}`}>{pct(r.p)}</span>
              <span className={`text-right ${r.dipReached ? "text-td-muted" : "text-td-text"}`}>
                {usd(r.dip)}
                {r.dipReached ? (
                  <span className="block text-[11px] text-td-muted">already reached</span>
                ) : (
                  r.close_below != null && <span className="block text-[11px] text-td-muted">closes below {pct(r.close_below)}</span>
                )}
              </span>
              <span className={`text-right ${r.popReached ? "text-td-muted" : "text-td-text"}`}>
                {usd(r.pop)}
                {r.popReached ? (
                  <span className="block text-[11px] text-td-muted">already reached</span>
                ) : (
                  r.close_above != null && <span className="block text-[11px] text-td-muted">closes above {pct(r.close_above)}</span>
                )}
              </span>
            </div>
          ))}
          <p className="text-[12px] text-td-muted mt-1">
            {live && data.day_low != null && data.day_high != null && (
              <>Today so far {usd(data.day_low)}–{usd(data.day_high)}; the day&apos;s low can only go lower from here, so it is at or below the low so far at every chance. </>
            )}
            Chance price trades there at any moment, not where it closes. A brief touch is about twice as likely as closing beyond
            the same level. Lower lows and higher highs are possible, just less likely.
          </p>
        </div>
      )}

      {near.length > 0 && (
        <ul className="space-y-1.5">
          {near.map((l) => (
            <li key={`${l.label}-${l.price}`} className="flex items-center justify-between gap-2 text-[13px]">
              <span className="text-td-muted">
                {l.label} <span className="font-mono text-td-text">{usd(l.price)}</span>
              </span>
              <span className="text-right">
                <span className={`block font-semibold ${oddsTone(l.p_reach)}`}>
                  {l.touched ? `Traded there earlier · ${pct(l.p_reach)} chance it trades there again` : `${pct(l.p_reach)} chance it trades there ${when}`}
                </span>
                {l.p_close_beyond != null && (
                  <span className="block text-[12px] text-td-muted">
                    {pct(l.p_close_beyond)} chance it closes {l.side === "below" ? "below" : "above"}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {far.length > 0 && (
        <p className="text-[12.5px] text-td-muted">
          Out of reach {live ? "today" : "next session"} (&lt;5%):{" "}
          {far.map((l) => `${l.label.toLowerCase()} ${usd(l.price)}`).join(" · ")}
        </p>
      )}

      <p className="text-[12px] text-td-muted leading-relaxed">
        {data.scorecard && (
          <>
            Last {data.scorecard.sessions} sessions: {data.scorecard.inside} closes inside the band ({data.scorecard.coverage_pct}%, target 80%).{" "}
          </>
        )}
        {trackedLine(data)}
        {data.reach_calibration && (
          <>
            Trade-there odds checked against {data.reach_calibration.cases.toLocaleString()} past cases ({data.reach_calibration.tickers} stocks, {data.reach_calibration.sessions} sessions).{" "}
          </>
        )}
        Odds, not predictions. Wider around earnings. Doesn't change the signal.
      </p>

      {data.bounce_zone && <BounceZone z={data.bounce_zone} />}

      {data.tracked?.history && data.tracked.history.length > 0 && (
        <div className="text-[12px]">
          <p className="text-td-muted mb-1">9:20 forecast vs actual (predicted → actual)</p>
          <div className="grid grid-cols-[3.5rem_1fr_1fr_1fr] gap-x-2 text-td-muted">
            <span>Day</span>
            <span className="text-right">Open</span>
            <span className="text-right">Low (75%)</span>
            <span className="text-right">Close</span>
          </div>
          {data.tracked.history.map((h) => (
            <div key={h.date} className="grid grid-cols-[3.5rem_1fr_1fr_1fr] gap-x-2 font-mono">
              <span className="text-td-muted">{h.date.slice(5)}</span>
              <span className="text-right text-td-text">{pair(h.open_pred, h.open)}</span>
              <span className="text-right text-td-text">{pair(h.low_pred, h.low)}</span>
              <span className={`text-right ${h.in80 === false ? "text-td-warn" : "text-td-text"}`}>
                {pair(h.close_pred, h.close)}
                {h.in50 ? " ●" : h.in80 ? " ○" : h.in80 === false ? " ×" : ""}
              </span>
            </div>
          ))}
          <p className="text-td-muted mt-1">● inside the 50% close range · ○ inside 80% · × outside</p>
        </div>
      )}
    </section>
  );
}

const short = (n: number | null | undefined) => (n == null ? "—" : n.toFixed(2));
const pair = (p: number | null | undefined, a: number | null | undefined) => `${short(p)} → ${short(a)}`;
function missPct(actual: number, pred: number): string {
  const m = (actual / pred - 1) * 100;
  return `${m >= 0 ? "+" : ""}${m.toFixed(2)}%`;
}

/** Live record: snapshots saved at 9:20/10:30/12:30/3:30 ET and scored after each close. */
function trackedLine(d: DayRangePayload): string {
  const slots = d.tracked?.slots;
  const s = slots && (slots["0920"] ?? Object.values(slots)[0]);
  if (!s || !s.n) return "Live tracking: snapshots saved at 9:20, 10:30, 12:30 and 3:30, scored after each close. ";
  const low75 = s.ladder.find((x) => x.p === 0.75);
  const open = s.open_n ? `, open inside 80% range ${s.open_in80_pct}% (avg miss ${s.avg_abs_open_err_pct}%)` : "";
  return `Live record (${s.label}, ${s.n} day${s.n === 1 ? "" : "s"}): close inside 80% range ${s.in80_pct}%, 50% range ${s.in50_pct}%${
    low75?.hit_pct != null ? `, 75% levels reached ${low75.hit_pct}%` : ""
  }${open}. `;
}

export function sessionDay(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function BounceZone({ z }: { z: NonNullable<DayRangePayload["bounce_zone"]> }) {
  const t = z.test;
  return (
    <div className="rounded-lg border border-td-line p-3 text-[12.5px] space-y-1">
      <p className="text-td-text font-semibold">Bounce zone · next ~{z.horizon_days} sessions · not a reason to wait</p>
      <p className="text-td-muted">
        {Math.abs(z.drawdown_pct).toFixed(0)}% off its 1-year high and below the 50-day ({usd(z.ma50)}). From the {usd(z.ref_close)} close, the
        low usually lands near <span className="font-mono text-td-text">{usd(z.mid)}</span>, 80% zone{" "}
        <span className="font-mono text-td-text">{usd(z.low)}–{usd(z.high)}</span>.
      </p>
      <p className="text-td-muted">
        Tested {t.from}–now: the zone caught the low {t.coverage_pct}% of the time, typical miss {t.median_err_pct}%. Waiting for {usd(z.mid)} filled{" "}
        {t.limit_fill_pct}% and made +{t.ret_limit_pct}% at 60 days vs +{t.ret_now_pct}% buying now; the ones that never dipped made +{t.ret_missed_pct}%.
        Stage entries with a stop instead.
      </p>
    </div>
  );
}
