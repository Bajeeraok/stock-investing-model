"use client";

/**
 * Why tab header — "Why the verdict is X": one card per primary gate, blocking first.
 * Same gate rows the Verdict tab's "Unlocks when" list uses (one record, two views).
 */

import { clsx } from "clsx";
import type { TradingGateRow } from "../retailActionUX";

export function WhyGateCards({
  verdictWord,
  gates,
  gatesPassed,
  gatesTotal,
  currentPrice,
  fairValue,
}: {
  verdictWord: string;
  gates: TradingGateRow[];
  gatesPassed: number;
  gatesTotal: number;
  currentPrice: number | null | undefined;
  fairValue?: number | null;
}) {
  if (!gates.length) return null;
  const sorted = [...gates].sort((a, b) => Number(a.pass) - Number(b.pass) || (b.blockerWeight ?? 0) - (a.blockerWeight ?? 0));

  const nowNeeds = (g: TradingGateRow): Array<[string, string]> => {
    if (g.id === "valuation" && currentPrice != null && currentPrice > 0) {
      const out: Array<[string, string]> = [["Now", `$${currentPrice.toFixed(2)}`]];
      if (fairValue != null && fairValue > 0) out.push(["Fair value", `$${fairValue.toFixed(2)}`]);
      return out;
    }
    if (g.id === "regime" && g.regimeWeatherStatus) return [["Now", g.regimeWeatherStatus]];
    if (g.id === "momentum" && g.rsiStatus) return [["RSI", g.rsiStatus]];
    return [];
  };

  return (
    <section className="space-y-2.5" aria-label="Gate checks">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-[15px] font-semibold text-td-text">Why the verdict is {verdictWord}</h3>
        <span className="text-[11.5px] text-td-muted tabular-nums">
          {gatesPassed} of {gatesTotal} gates pass
        </span>
      </div>
      <div className="grid gap-2.5 sm:grid-cols-2">
        {sorted.map((g) => (
          <div
            key={g.id}
            className={clsx(
              "rounded-xl border px-3.5 py-3",
              g.pass ? "bg-td-accent-weak/60 border-td-accent/25" : "bg-td-crit-weak/60 border-td-crit/25",
            )}
          >
            <div className={clsx("flex items-center justify-between gap-2 text-[13px] font-bold", g.pass ? "text-td-accent" : "text-td-crit")}>
              <span>
                {g.pass ? "✓" : "✕"} {g.label}
              </span>
              <span className="font-mono text-[10px] font-semibold opacity-80">{g.pass ? "PASSING" : "BLOCKING"}</span>
            </div>
            {g.detail && <p className="mt-1.5 text-[12px] text-td-text/85 leading-snug">{g.detail}</p>}
            {nowNeeds(g).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10.5px] text-td-muted">
                {nowNeeds(g).map(([k, v]) => (
                  <span key={k}>
                    {k} <b className="text-td-text font-semibold">{v}</b>
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
