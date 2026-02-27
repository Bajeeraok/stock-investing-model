"use client";

import { useState, useMemo } from "react";
import type { Signal } from "@/app/page";
import { clsx } from "clsx";

// ── Mini signal-dot helper ────────────────────────────────────────────────────
// Shows 3 compact dots (Trend / RSI / MACD) below the confluence number so the
// user can instantly see WHICH signals are aligned without opening the modal.
const DOT_COLOUR: Record<string, string> = {
  UP:      "bg-emerald-400",
  NEUTRAL: "bg-slate-500",
  DOWN:    "bg-red-400",
};
const DOT_TITLE: Record<string, Record<string, string>> = {
  trend: { UP: "Trend: price > MA50 > MA200", NEUTRAL: "Trend: mixed MA structure", DOWN: "Trend: price < MA50 < MA200" },
  rsi:   { UP: "RSI: recovery zone (30–55)", NEUTRAL: "RSI: elevated / neutral", DOWN: "RSI: overbought or panic-down" },
  macd:  { UP: "MACD: histogram bullish",    NEUTRAL: "MACD: flat",               DOWN: "MACD: histogram bearish" },
};

function SignalDot({ type, dir }: { type: "trend" | "rsi" | "macd"; dir: string }) {
  const d = (dir ?? "NEUTRAL").toUpperCase();
  return (
    <span
      title={DOT_TITLE[type]?.[d] ?? d}
      className={clsx("inline-block w-1.5 h-1.5 rounded-full", DOT_COLOUR[d] ?? "bg-slate-500")}
    />
  );
}

function ConfluenceCell({ signal: r }: { signal: Signal }) {
  const score    = r.confluence_score ?? r.composite_buy;
  const scorePct = score != null ? Math.floor(score) : null;
  const colour   =
    scorePct == null         ? "text-slate-500" :
    scorePct >= 65           ? "text-emerald-400" :
    scorePct <= 35           ? "text-red-400"     : "text-slate-300";

  const trend = (r.trend_signal ?? (r.regime === "UP" ? "UP" : r.regime === "DOWN" ? "DOWN" : "NEUTRAL")).toUpperCase();
  const rsi   = (r.rsi_signal   ?? (r.rsi != null && r.rsi < 40 ? "UP" : r.rsi != null && r.rsi > 70 ? "DOWN" : "NEUTRAL")).toUpperCase();
  const macd  = (r.macd_signal  ?? (r.signal === "BUY" ? "UP" : r.signal === "SELL" ? "DOWN" : "NEUTRAL")).toUpperCase();

  return (
    <div>
      <span
        className={clsx("font-semibold tabular-nums", colour)}
        title="Confluence Score: degree of Trend + RSI + MACD + Regime agreement. Click ticker for 7-layer ML Confidence."
      >
        {scorePct != null ? scorePct : "–"}
      </span>
      {r.confidence_tag === "low (bear/neutral market)" && (
        <span className="text-amber-400 text-[10px] ml-1" title="Score down-weighted in BEAR/NEUTRAL market regime">↓</span>
      )}
      {/* Mini signal dots: Trend · RSI · MACD */}
      <div className="flex items-center gap-1 mt-1" title="Signal alignment: Trend · RSI · MACD">
        <SignalDot type="trend" dir={trend} />
        <SignalDot type="rsi"   dir={rsi}   />
        <SignalDot type="macd"  dir={macd}  />
        <span className="text-[9px] text-slate-600 ml-0.5">T·R·M</span>
      </div>
    </div>
  );
}

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
      // Sort by confluence_score when available, fall back to composite_buy
      if (sortBy === "score") return (b.confluence_score ?? b.composite_buy ?? 0) - (a.confluence_score ?? a.composite_buy ?? 0);
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
      <div className="flex items-center justify-end gap-2 px-3 sm:px-4 py-2 bg-slate-800/50 border-b border-slate-700">
        <span className="text-xs text-slate-400">Sort by:</span>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
          className="text-sm sm:text-xs bg-slate-800 border border-slate-600 rounded px-2 py-2 sm:py-1 text-slate-300 min-h-[44px] sm:min-h-0 touch-manipulation"
        >
          <option value="score">Confluence</option>
          <option value="ticker">Ticker</option>
          <option value="regime">Regime</option>
          <option value="rsi">RSI</option>
        </select>
      </div>

      {/* Mobile: card list */}
      <div className="md:hidden divide-y divide-slate-700/50">
        {sorted.map((r) => (
          <button
            key={r.ticker}
            type="button"
            onClick={() => onTickerClick?.(r.ticker)}
            className={clsx(
              "w-full text-left px-4 py-3 active:bg-slate-800/50 transition-colors",
              r.story_change && "bg-amber-500/5"
            )}
          >
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <span className="font-mono font-semibold text-emerald-400 text-base">{r.ticker}</span>
              <span className="text-slate-400 text-sm">{r.close != null ? `$${r.close.toFixed(2)}` : "-"}</span>
            </div>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className={clsx(
                "font-medium text-sm",
                (r.confluence_score ?? r.composite_buy ?? 0) >= 65 && "text-emerald-400",
                (r.confluence_score ?? r.composite_buy ?? 0) <= 35 && "text-red-400",
                (r.confluence_score ?? r.composite_buy ?? 0) > 35 && (r.confluence_score ?? r.composite_buy ?? 0) < 65 && "text-slate-300"
              )}>
                {((r.confluence_score ?? r.composite_buy) != null
                  ? (r.confluence_score ?? r.composite_buy)!.toFixed(0)
                  : "-")}<span className="text-slate-600"> cf</span>
              </span>
              <span className={clsx(
                "px-2 py-0.5 rounded text-xs font-medium",
                r.regime === "UP" && "bg-emerald-500/20 text-emerald-400",
                r.regime === "NEUTRAL" && "bg-slate-500/20 text-slate-400",
                r.regime === "DOWN" && "bg-red-500/20 text-red-400"
              )}>
                {r.regime ?? "-"}
              </span>
              <span className={clsx(
                "text-sm font-medium",
                r.signal === "BUY" && "text-emerald-400",
                r.signal === "SELL" && "text-red-400",
                r.signal === "HOLD" && "text-slate-400"
              )}>
                {r.signal ?? "-"}
              </span>
              {r.rsi != null && <span className="text-slate-500 text-sm">RSI {r.rsi.toFixed(0)}</span>}
            </div>
            {r.earnings_note && <p className="text-amber-400 text-xs mt-1">{r.earnings_note}</p>}
            {r.story_change && <p className="text-amber-400/90 text-xs mt-0.5">{r.story_change}</p>}
          </button>
        ))}
      </div>

      {/* Desktop: table with sticky header + sticky first column */}
      <div className="hidden md:block overflow-x-auto [-webkit-overflow-scrolling:touch]">
        <table className="w-full min-w-[900px] text-sm border-collapse">
          <thead>
            <tr className="text-left text-base text-slate-400">
              <th className="sticky top-0 left-0 z-[30] min-w-[4.5rem] w-24 bg-slate-800/95 backdrop-blur-sm px-3 py-2.5 font-medium border-b border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]">
                Ticker
              </th>
              <th className="sticky top-0 left-24 z-[25] min-w-[5rem] w-20 px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)]">
                Close
              </th>
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700 cursor-help whitespace-nowrap"
                title="Confluence Score (0–100): how much do Trend + RSI + MACD + Regime agree on direction? ≥65 = aligned bullish · 35–65 = mixed · ≤35 = bearish alignment. NOT a probability — click any ticker to see the 7-layer ML Confidence breakdown."
              >
                Confluence
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">
                LIS
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">
                RSI
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">
                Regime
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">
                Signal
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">
                Positioning
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">
                Buy / Sell / Support
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">
                Short / Med / Long
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">
                Vol / DD
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">
                Notes
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr
                key={r.ticker}
                className={clsx(
                  "group border-t border-slate-700/50 hover:bg-slate-800/30",
                  r.story_change && "bg-amber-500/5"
                )}
              >
                <td
                  className={clsx(
                    "sticky left-0 z-[10] min-w-[4.5rem] w-24 px-3 py-2.5 border-r border-slate-700/70 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)]",
                    r.story_change ? "bg-amber-500/5" : "bg-slate-900 group-hover:bg-slate-800/30"
                  )}
                >
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
                  className={clsx(
                    "sticky left-24 z-[10] min-w-[5rem] w-20 px-3 py-2.5 border-r border-slate-700/70 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)]",
                    r.story_change ? "bg-amber-500/5" : "bg-slate-900 group-hover:bg-slate-800/30"
                  )}
                  title={r.risk_sizing ? `At ${riskSizing?.risk_pct ?? 1}% risk and ${r.risk_sizing.stop_pct}% stop: $${r.risk_sizing.size_dollars.toLocaleString()} (~${r.risk_sizing.shares} shares)` : undefined}
                >
                  {r.close != null ? `$${r.close.toFixed(2)}` : "-"}
                  {r.risk_sizing && (
                    <span className="block text-xs text-slate-500 mt-0.5">
                      ~{r.risk_sizing.shares} sh
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <ConfluenceCell signal={r} />
                </td>
                <td className="px-4 py-3 text-slate-500 text-sm" title="Liquidity score – placeholder for future">
                  –
                </td>
                <td className="px-4 py-3 text-slate-300">{r.rsi != null ? r.rsi.toFixed(1) : "-"}</td>
                <td className="px-3 py-2.5">
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
                <td className="px-3 py-2.5">
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
                  <span className="text-emerald-400/90" title="Add on pullback; confidence = model strength for adding at this level">
                    {r.suggested_buy_price != null ? `$${r.suggested_buy_price.toFixed(2)}` : "-"}
                    {r.buy_target_confidence_pct != null && r.suggested_buy_price != null && (
                      <span className="text-slate-500 text-xs ml-0.5">({r.buy_target_confidence_pct}%)</span>
                    )}
                  </span>
                  <span className="text-slate-500 mx-1">/</span>
                  <span className="text-red-400/90" title="Consider trim/exit when overbought or weak; confidence = strength of sell signal">
                    {r.suggested_sell_price != null ? `$${r.suggested_sell_price.toFixed(2)}` : "-"}
                    {r.sell_target_confidence_pct != null && r.suggested_sell_price != null && (
                      <span className="text-slate-500 text-xs ml-0.5">({r.sell_target_confidence_pct}%)</span>
                    )}
                  </span>
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
                  {r.score_label && ["Extended / high risk of pullback", "Oversold / speculative bounce"].includes(r.score_label) && (
                    <span className={r.score_label.startsWith("Extended") ? "text-amber-400" : "text-slate-400"} title="Regime-aware label">
                      • {r.score_label}
                    </span>
                  )}
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
