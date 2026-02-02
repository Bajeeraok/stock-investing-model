"use client";

import { clsx } from "clsx";

export interface CryptoSignal {
  ticker: string;
  close: number | null;
  composite_buy: number | null;
  regime: string | null;
  signal: string | null;
  rsi: number | null;
  error?: string;
}

export function CryptoSection({ items }: { items: CryptoSignal[] }) {
  const display = items.filter((c) => !c.error && c.close != null);
  if (display.length === 0) return null;
  const label = (t: string) => (t === "BTC-USD" ? "BTC" : t === "ETH-USD" ? "ETH" : t);
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5">
      <h3 className="text-sm font-semibold text-slate-400 mb-3 flex items-center gap-2">
        <span className="text-amber-400">Crypto</span> (BTC, ETH)
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {display.map((c) => (
          <div
            key={c.ticker}
            className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700/50"
          >
            <div>
              <span className="font-mono font-medium text-slate-200">{label(c.ticker)}</span>
              <p className="text-lg font-bold text-emerald-400 mt-1">
                {c.close != null ? `$${c.close.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "-"}
              </p>
            </div>
            <div className="text-right">
              <span
                className={clsx(
                  "px-2 py-0.5 rounded text-xs font-medium",
                  c.regime === "UP" && "bg-emerald-500/20 text-emerald-400",
                  c.regime === "NEUTRAL" && "bg-slate-500/20 text-slate-400",
                  c.regime === "DOWN" && "bg-red-500/20 text-red-400"
                )}
              >
                {c.regime ?? "-"}
              </span>
              <p className="text-sm text-slate-400 mt-1">
                Score {c.composite_buy?.toFixed(0) ?? "-"} · RSI {c.rsi?.toFixed(0) ?? "-"}
              </p>
              <p
                className={clsx(
                  "text-sm font-medium mt-0.5",
                  c.signal === "BUY" && "text-emerald-400",
                  c.signal === "HOLD" && "text-slate-400",
                  c.signal === "SELL" && "text-red-400"
                )}
              >
                {c.signal ?? "-"}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
