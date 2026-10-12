"use client";

import { Fragment } from "react";
import { clsx } from "clsx";
import type { Signal } from "@/app/page";
import { scoreTileClass, SCORE_BULL, SCORE_BEAR, fmtScore } from "@/lib/scoreConfidenceDisplay";

type Regime = "UP" | "NEUTRAL" | "DOWN";
const REGIME_COLS: Regime[] = ["UP", "NEUTRAL", "DOWN"];

type ScoreTier = "bull" | "neutral" | "bear";
const SCORE_ROWS: { tier: ScoreTier; label: string; midpoint: number }[] = [
  { tier: "bull", label: `Bull · ≥${SCORE_BULL}`, midpoint: 80 },
  { tier: "neutral", label: "Neutral", midpoint: 50 },
  { tier: "bear", label: `Bear · ≤${SCORE_BEAR}`, midpoint: 20 },
];

function canonicalScore(s: Signal): number | null {
  // Same preference order as buyReadinessSortValue (lib/signalsTableAudit.ts) — composite_buy
  // is the actual 0-100 score a row's own action text is generated from.
  return s.composite_buy ?? s.confluence_score ?? null;
}

function scoreTier(score: number | null): ScoreTier {
  if (score == null) return "neutral";
  if (score >= SCORE_BULL) return "bull";
  if (score <= SCORE_BEAR) return "bear";
  return "neutral";
}

function regimeOf(s: Signal): Regime {
  return s.regime === "UP" || s.regime === "DOWN" ? s.regime : "NEUTRAL";
}

export function SignalsHeatmap({
  signals,
  onTickerClick,
}: {
  /** Already filtered by the shared Book/Preset bar — this component just buckets and colors. */
  signals: Signal[];
  onTickerClick?: (ticker: string) => void;
}) {
  const cells = new Map<string, Signal[]>();
  for (const s of signals) {
    if (!s.ticker) continue;
    const key = `${scoreTier(canonicalScore(s))}|${regimeOf(s)}`;
    const list = cells.get(key) ?? [];
    list.push(s);
    cells.set(key, list);
  }

  if (signals.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-800/30 p-8 text-center text-slate-500">
        <p>No tickers match the current filters. Try a broader source or view.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-700 overflow-hidden">
      <div className="px-3 sm:px-4 py-2 bg-slate-800 border-b border-slate-700">
        <p className="text-[11px] text-slate-500">
          Score tier × market regime — {signals.length} tickers. Tap a ticker to open it.
        </p>
      </div>
      <div className="p-3 sm:p-4 overflow-x-auto">
        <div className="grid grid-cols-[6.5rem_repeat(3,minmax(10rem,1fr))] gap-2 min-w-[640px]">
          <div />
          {REGIME_COLS.map((r) => (
            <div
              key={r}
              className={clsx(
                "text-center text-[11px] font-semibold uppercase tracking-wide py-1.5 rounded-lg",
                r === "UP" && "text-emerald-300 bg-emerald-500/10",
                r === "DOWN" && "text-red-300 bg-red-500/10",
                r === "NEUTRAL" && "text-slate-300 bg-slate-700/40",
              )}
            >
              {r}
            </div>
          ))}
          {SCORE_ROWS.map((row) => (
            <Fragment key={row.tier}>
              <div className="flex items-center text-[11px] text-slate-400 font-medium px-1">
                {row.label}
              </div>
              {REGIME_COLS.map((col) => {
                const key = `${row.tier}|${col}`;
                const items = cells.get(key) ?? [];
                return (
                  <div
                    key={key}
                    className={clsx(
                      "rounded-lg border p-2 min-h-[4.5rem] flex flex-wrap content-start gap-1",
                      scoreTileClass(row.midpoint),
                    )}
                  >
                    {items.length === 0 ? (
                      <span className="text-[10px] opacity-50 italic">—</span>
                    ) : (
                      items
                        .sort((a, b) => (canonicalScore(b) ?? 0) - (canonicalScore(a) ?? 0))
                        .map((s) => (
                          <button
                            key={s.ticker}
                            type="button"
                            title={`${s.ticker} · score ${fmtScore(canonicalScore(s))}`}
                            onClick={() => onTickerClick?.(s.ticker!)}
                            className="text-[10.5px] font-mono font-semibold px-1.5 py-0.5 rounded bg-black/20 hover:bg-black/35 transition-colors"
                          >
                            {s.ticker}
                          </button>
                        ))
                    )}
                  </div>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
