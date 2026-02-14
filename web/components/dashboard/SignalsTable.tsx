"use client";

import { useState, useMemo } from "react";
import type { Signal } from "@/app/page";
import { clsx } from "clsx";

const DEFAULT_HORIZONS = {
  short_term: "~1 mo",
  medium_term: "~3–6 mo",
  long_term: "1–2 yr",
};

const POSITIONING_TOOLTIPS: Record<string, string> = {
  long: "Crowded long (CFTC): specs very long, reversal risk.",
  short: "Crowded short (CFTC): specs very short, reversal risk.",
};

export function SignalsTable({
  signals,
  horizons,
  onTickerClick,
  riskSizing,
  cotByTicker,
}: {
  signals: Signal[];
  horizons?: { short_term: string; medium_term: string; long_term: string } | null;
  onTickerClick?: (ticker: string) => void;
  riskSizing?: { risk_pct: number; stop_pct: number };
  cotByTicker?: Record<string, string>;
}) {
  const h = horizons || DEFAULT_HORIZONS;
  const [sortBy, setSortBy] = useState<"ticker" | "score" | "regime" | "rsi">("score");
  const sorted = useMemo(() => {
    const arr = [...signals];
    arr.sort((a, b) => {
      if (sortBy === "ticker") return (a.ticker ?? "").localeCompare(b.ticker ?? "");
      if (sortBy === "score") return (b.composite_buy ?? 0) - (a.composite_buy ?? 0);
      if (sortBy === "regime") {
        const ord = { UP: 0, NEUTRAL: 1, DOWN: 2 };
        return (ord[a.regime as keyof typeof ord] ?? 1) - (ord[b.regime as keyof typeof ord] ?? 1);
      }
      if (sortBy === "rsi") return (b.rsi ?? 0) - (a.rsi ?? 0);
      return 0;
    });
    return arr;
  }, [signals, sortBy]);

  return (
    <div className="rounded-xl border border-slate-700 overflow-hidden">
      <div className="flex items-center justify-end gap-2 px-4 py-2 bg-slate-800/50 border-b border-slate-700">
        <span className="text-xs text-slate-400">Sort by:</span>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
          className="text-xs bg-slate-800 border border-slate-600 rounded px-2 py-1 text-slate-300"
        >
          <option value="score">Score</option>
          <option value="ticker">Ticker</option>
          <option value="regime">Regime</option>
          <option value="rsi">RSI</option>
        </select>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-slate-800/80 text-left text-base text-slate-400">
              <th className="px-4 py-3 font-medium">Ticker</th>
              <th className="px-4 py-3 font-medium">Close</th>
              <th className="px-4 py-3 font-medium">Score</th>
              <th className="px-4 py-3 font-medium" title="Liquidity score – placeholder for future; grey-out low-LIS tickers">LIS</th>
              <th className="px-4 py-3 font-medium">RSI</th>
              <th className="px-4 py-3 font-medium">Regime</th>
              <th className="px-4 py-3 font-medium">Signal</th>
              <th className="px-4 py-3 font-medium" title="CFTC Commitment of Traders: speculative positioning in the related commodity (GLD=Gold, SLV=Silver, USO=Oil). Crowded Long/Short = reversal risk.">
                Positioning
              </th>
              <th className="px-4 py-3 font-medium" title="Buy: add on pullback. Sell: trim when overbought/weak. Support: break below = caution">
                Buy / Sell / Support
              </th>
              <th className="px-4 py-3 font-medium" title={`Short ${h.short_term} / Medium ${h.medium_term} / Long ${h.long_term}`}>
                Short / Medium / Long
              </th>
              <th className="px-4 py-3 font-medium" title="Vol: today vs 20d avg. DD: % below 52w high">
                Vol / DD
              </th>
              <th className="px-4 py-3 font-medium">Notes</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr
                key={r.ticker}
                className={clsx(
                  "border-t border-slate-700/50 hover:bg-slate-800/30",
                  r.story_change && "bg-amber-500/5"
                )}
              >
                <td className="px-4 py-3">
                  <button
                    type="button"
                    onClick={() => onTickerClick?.(r.ticker)}
                    className={clsx(
                      "font-mono font-medium hover:underline cursor-pointer",
                      onTickerClick && "text-emerald-400 hover:text-emerald-300"
                    )}
                  >
                    {r.ticker}
                  </button>
                </td>
                <td
                  className="px-4 py-3"
                  title={r.risk_sizing ? `At ${riskSizing?.risk_pct ?? 1}% risk and ${r.risk_sizing.stop_pct}% stop: $${r.risk_sizing.size_dollars.toLocaleString()} (~${r.risk_sizing.shares} shares)` : undefined}
                >
                  {r.close != null ? `$${r.close.toFixed(2)}` : "-"}
                  {r.risk_sizing && (
                    <span className="block text-xs text-slate-500 mt-0.5">
                      ~{r.risk_sizing.shares} sh
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      "font-medium",
                      (r.composite_buy ?? 0) >= 70 && "text-emerald-400",
                      (r.composite_buy ?? 0) < 70 && (r.composite_buy ?? 0) > 30 && "text-slate-300",
                      (r.composite_buy ?? 0) <= 30 && "text-red-400"
                    )}
                  >
                    {r.composite_buy != null ? r.composite_buy.toFixed(1) : "-"}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-500 text-sm" title="Liquidity score – placeholder for future">
                  –
                </td>
                <td className="px-4 py-3 text-slate-300">{r.rsi != null ? r.rsi.toFixed(1) : "-"}</td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      "px-2 py-0.5 rounded text-xs font-medium",
                      r.regime === "UP" && "bg-emerald-500/20 text-emerald-400",
                      r.regime === "NEUTRAL" && "bg-slate-500/20 text-slate-400",
                      r.regime === "DOWN" && "bg-red-500/20 text-red-400"
                    )}
                  >
                    {r.regime ?? "-"}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      "font-medium",
                      r.signal === "BUY" && "text-emerald-400",
                      r.signal === "HOLD" && "text-slate-400",
                      r.signal === "SELL" && "text-red-400"
                    )}
                  >
                    {r.signal ?? "-"}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-slate-400" title="COT positioning (GLD/SLV/USO)">
                  {cotByTicker?.[r.ticker] ?? "–"}
                </td>
                <td className="px-4 py-3 text-sm">
                  <span className="text-emerald-400/90" title="Add on pullback">{r.suggested_buy_price != null ? `$${r.suggested_buy_price.toFixed(2)}` : "-"}</span>
                  <span className="text-slate-500 mx-1">/</span>
                  <span className="text-red-400/90" title="Consider trim/exit when overbought or weak">{r.suggested_sell_price != null ? `$${r.suggested_sell_price.toFixed(2)}` : "-"}</span>
                  {r.support_level != null && (
                    <>
                      <span className="text-slate-500 mx-1">/</span>
                      <span className="text-amber-400/90" title="Support to watch; break below = caution">${r.support_level.toFixed(2)}</span>
                    </>
                  )}
                </td>
                <td className="px-4 py-3 text-base text-slate-400">
                  <div>
                    {[r.short_suggestion, r.medium_suggestion, r.long_suggestion]
                      .filter(Boolean)
                      .join(" / ") || "-"}
                    {(r.st_band || r.mt_band || r.lt_band) && (
                      <div className="text-xs text-slate-500 mt-1 space-y-0.5" title="ST: stop–target. MT: vol band. LT: fair+consensus">
                        {r.st_band && (
                          <span className="block">ST: ${r.st_band.low.toFixed(1)}–${r.st_band.high.toFixed(1)}</span>
                        )}
                        {r.mt_band && (
                          <span className="block">MT: ${r.mt_band.low.toFixed(1)}–${r.mt_band.high.toFixed(1)}</span>
                        )}
                        {r.lt_band && (
                          <span className="block">
                            LT: ${r.lt_band.low.toFixed(1)}–${r.lt_band.high.toFixed(1)}
                            {r.lt_band_low_confidence && " (low conf)"}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 text-sm text-slate-400">
                  {r.volume_ratio != null && (
                    <span className={r.volume_unusual ? "text-amber-400 font-medium" : ""} title="Volume vs 20d avg">
                      {r.volume_ratio.toFixed(1)}x
                    </span>
                  )}
                  {r.drawdown_52w != null && (
                    <span className="ml-2" title="% below 52w high">
                      {r.drawdown_52w >= 0 ? "" : ""}{r.drawdown_52w}%
                    </span>
                  )}
                  {r.volume_ratio == null && r.drawdown_52w == null && "-"}
                </td>
                <td className="px-4 py-3 text-base">
                  {r.earnings_note && (
                    <span className="text-amber-400">{r.earnings_note}</span>
                  )}
                  {r.story_change && (
                    <span className="text-amber-400 ml-1">• {r.story_change}</span>
                  )}
                  {cotByTicker?.[r.ticker] && (
                    <span className="block text-amber-200/90 text-xs mt-1">
                      <span title={String(cotByTicker[r.ticker]).toLowerCase().includes("long")
                        ? "Crowded Long (CFTC): Speculators (non-commercial traders) hold a very large net long position in the related commodity futures (e.g. gold for GLD, silver for SLV)—typically ≥45% of total open interest. The CFTC publishes this weekly. Historically, such extreme positioning often precedes a pullback, so we flag it as reversal risk and suggest not adding size."
                        : "Crowded Short (CFTC): Speculators hold a very large net short position in the related commodity futures—typically ≥45% of open interest. Extreme shorts have often preceded short-covering rallies. We flag this as reversal risk."}>
                        {String(cotByTicker[r.ticker]).toLowerCase().includes("long")
                          ? "• Positioning: Crowded Long (CFTC) — specs very long, reversal risk."
                          : "• Positioning: Crowded Short (CFTC) — specs very short, reversal risk."}
                      </span>
                      <span className="block text-amber-100/95 text-sm mt-1 font-medium" title="From CFTC Commitment of Traders report: speculative (non-commercial) % of open interest. ≥45% long or short = extreme.">
                        What it means: Speculators’ net position in the related commodity is extreme (≥45% of open interest). Often a contrarian signal; consider not adding size.
                      </span>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
