"use client";

/** Today's likely close range + chance price trades at the entry band / stop. Display only. */
import React from "react";
import { CalendarRange } from "lucide-react";

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
  sigma_pct: number;
  last?: number;
  minutes_left?: number;
  close_low: number;
  close_mid: number;
  close_high: number;
  close_low50?: number;
  close_high50?: number;
  p_close_green: number | null;
  day_low?: number | null;
  day_high?: number | null;
  levels: DayRangeLevel[];
  ladder?: { p: number; dip: number; pop: number }[];
  scorecard?: { sessions: number; inside: number; coverage_pct: number } | null;
  tracked?: {
    days: number;
    since: string | null;
    slots: Record<string, { label: string; n: number; in80_pct: number | null; in50_pct: number | null; ladder: { p: number; hit_pct: number | null; n: number }[] }>;
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

/** Highest-probability lows (75% and 50% chance) and where they sit vs the entry bands. */
export function likelyLow(d: DayRangePayload) {
  const lad = d.ladder ?? [];
  const hi = lad.find((x) => x.p === 0.75);
  const mid = lad.find((x) => x.p === 0.5);
  if (!hi) return null;
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
  return { hi, mid, where: where(hi.dip) };
}

export const pct = (p: number) => (p < 0.01 ? "<1%" : p > 0.99 ? ">99%" : `${Math.round(p * 100)}%`);

function oddsTone(p: number) {
  if (p >= 0.5) return "text-td-accent";
  if (p >= 0.2) return "text-td-warn";
  return "text-td-muted";
}

export function DayRangeCard({ data, price }: { data?: DayRangePayload | null; price?: number | null }) {
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
          <h3 className="text-sm font-semibold text-td-text">{live ? "Today's likely close" : "Next session range"}</h3>
        </div>
        <span className="text-[12px] text-td-muted">{live ? hrs : `vs ${data.ref_date} close ${usd(data.ref_close)}`}</span>
      </div>

      {ll && (
        <div className="rounded-lg border border-td-accent/40 bg-td-accent/10 px-3 py-2 text-[13px]">
          <div className="flex justify-between gap-2">
            <span className="font-semibold text-td-text">Likely low {live ? "today" : "next session"}</span>
            <span className="font-mono font-semibold text-td-accent">{usd(ll.hi.dip)}</span>
          </div>
          <p className="text-[12px] text-td-muted mt-0.5">
            {pct(ll.hi.p)} chance it trades there {when} ({ll.where})
            {ll.mid && <> · deeper {usd(ll.mid.dip)} at {pct(ll.mid.p)}</>}
          </p>
        </div>
      )}

      <ul className="space-y-1 text-[13px]">
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
            <span>Chance {when}</span>
            <span className="text-right">Low reaches</span>
            <span className="text-right">High reaches</span>
          </div>
          {data.ladder.map((r) => (
            <div key={r.p} className="grid grid-cols-3 gap-2 font-mono">
              <span className={`font-semibold ${oddsTone(r.p)}`}>{pct(r.p)}</span>
              <span className="text-right text-td-text">{usd(r.dip)}</span>
              <span className="text-right text-td-text">{usd(r.pop)}</span>
            </div>
          ))}
          <p className="text-[12px] text-td-muted mt-1">
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
        Odds, not predictions. Wider around earnings. Doesn't change the signal.
      </p>
    </section>
  );
}

/** Live record: snapshots saved at 9:20/10:30/12:30/3:30 ET and scored after each close. */
function trackedLine(d: DayRangePayload): string {
  const slots = d.tracked?.slots;
  const s = slots && (slots["0920"] ?? Object.values(slots)[0]);
  if (!s || !s.n) return "Live tracking: snapshots saved at 9:20, 10:30, 12:30 and 3:30, scored after each close. ";
  const low75 = s.ladder.find((x) => x.p === 0.75);
  return `Live record (${s.label}, ${s.n} day${s.n === 1 ? "" : "s"}): close inside 80% range ${s.in80_pct}%, 50% range ${s.in50_pct}%${
    low75?.hit_pct != null ? `, 75% levels reached ${low75.hit_pct}%` : ""
  }. `;
}
