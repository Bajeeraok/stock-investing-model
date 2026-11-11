"use client";

/** Today's likely close range + chance price trades at the entry band / stop. Display only. */
import React from "react";
import { CalendarRange } from "lucide-react";

export type DayRangeLevel = { label: string; price: number; side: "above" | "below"; p_reach: number; touched: boolean };
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
  scorecard?: { sessions: number; inside: number; coverage_pct: number } | null;
};

/** 50% close band; older payloads lack it, so derive from the 80% band. */
export function band50(d: DayRangePayload): [number, number] {
  if (d.close_low50 != null && d.close_high50 != null) return [d.close_low50, d.close_high50];
  const f = (v: number) => d.close_mid * Math.exp(Math.log(v / d.close_mid) * (0.6745 / 1.2816));
  return [f(d.close_low), f(d.close_high)];
}

const usd = (n: number) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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

      {data.levels.length > 0 && (
        <ul className="space-y-1.5">
          {data.levels.map((l) => (
            <li key={`${l.label}-${l.price}`} className="flex items-center justify-between gap-2 text-[13px]">
              <span className="text-td-muted">
                {l.label} <span className="font-mono text-td-text">{usd(l.price)}</span>
              </span>
              <span className={`font-semibold ${oddsTone(l.p_reach)}`}>
                {l.touched ? `Traded there earlier · ${pct(l.p_reach)} chance again` : `${pct(l.p_reach)} chance ${live ? "before close" : "next session"}`}
              </span>
            </li>
          ))}
        </ul>
      )}

      <p className="text-[12px] text-td-muted leading-relaxed">
        {data.scorecard && (
          <>
            Last {data.scorecard.sessions} sessions: {data.scorecard.inside} closes inside the band ({data.scorecard.coverage_pct}%, target 80%).{" "}
          </>
        )}
        Odds, not predictions. Wider around earnings. Doesn't change the signal.
      </p>
    </section>
  );
}
