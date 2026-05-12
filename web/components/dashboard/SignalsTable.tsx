"use client";

import { useState, useMemo } from "react";
import type { Signal } from "@/app/page";
import { clsx } from "clsx";

// ── Signal badge — all 6 tiers ────────────────────────────────────────────────
const RETAIL_ACTION_STYLE: Record<string, { bg: string; text: string }> = {
  BUY: { bg: "bg-emerald-500/25", text: "text-emerald-200" },
  WAIT: { bg: "bg-blue-500/20", text: "text-blue-300" },
  TRIM: { bg: "bg-amber-500/20", text: "text-amber-300" },
  HOLD: { bg: "bg-slate-500/20", text: "text-slate-300" },
};

// Replaces the old BUY/HOLD/SELL with a multi-layer signal that requires both
// technical (confluence) AND ML to agree before emitting BUY.
const SIGNAL_STYLES: Record<string, { bg: string; text: string; border: string; title: string }> = {
  "STRONG BUY": {
    bg: "bg-emerald-500/25", text: "text-emerald-200", border: "border-emerald-400/60",
    title: "Confluence ≥72 AND ML prob ≥55% — both technical and ML strongly aligned",
  },
  "BUY": {
    bg: "bg-green-500/20", text: "text-green-300", border: "border-green-400/40",
    title: "Confluence ≥65 AND ML prob ≥40% — technical and ML both confirm entry",
  },
  "WATCH": {
    bg: "bg-blue-500/15", text: "text-blue-300", border: "border-blue-400/40",
    title: "Technical signals strong but ML probability < 40% — wait for ML confirmation before entering",
  },
  "HOLD": {
    bg: "bg-slate-500/20", text: "text-slate-300", border: "border-slate-500/40",
    title: "Mixed signals — neither a clear entry nor exit",
  },
  "REDUCE": {
    bg: "bg-amber-500/20", text: "text-amber-300", border: "border-amber-400/40",
    title: "Confluence or ML turning bearish — consider trimming position",
  },
  "SELL": {
    bg: "bg-red-500/20", text: "text-red-300", border: "border-red-400/40",
    title: "Technical signals bearish (confluence-only mode — no ML yet)",
  },
  "AVOID": {
    bg: "bg-red-600/25", text: "text-red-200", border: "border-red-500/50",
    title: "Confluence ≤35 AND ML prob < 20% — both technical and ML bearish",
  },
};

function SignalBadge({ signal }: { signal: string | null | undefined }) {
  const s = (signal ?? "HOLD").toUpperCase();
  const style = SIGNAL_STYLES[s] ?? SIGNAL_STYLES["HOLD"];
  return (
    <span
      className={clsx(
        "inline-flex items-center px-2 py-0.5 rounded border text-xs font-semibold whitespace-nowrap",
        style.bg, style.text, style.border,
      )}
      title={style.title}
    >
      {s}
    </span>
  );
}

/** 7-layer action — same engine as Roadmaps / ticker detail */
function PlanActionBadge({
  action,
  conf,
}: {
  action: string | null | undefined;
  conf?: number | null;
}) {
  if (!action) {
    return (
      <span className="text-[10px] text-slate-500" title="Run dashboard with watchlist tickers to load 7-layer plan">
        —
      </span>
    );
  }
  const a = action.toUpperCase();
  const style =
    a.includes("STRONG BUY")
      ? SIGNAL_STYLES["STRONG BUY"]
      : a.includes("BUY") && !a.includes("WATCH")
        ? SIGNAL_STYLES["BUY"]
        : a.includes("AVOID")
          ? SIGNAL_STYLES["AVOID"]
          : a.includes("REDUCE")
            ? SIGNAL_STYLES["REDUCE"]
            : a.includes("WATCH")
              ? SIGNAL_STYLES["WATCH"]
              : SIGNAL_STYLES["HOLD"];
  const pct = conf != null ? Math.round(conf * 100) : null;
  const title = [
    `${action}${pct != null ? ` · ${pct}% confidence` : ""}`,
    "Confluence + ML tiers + fundamentals/news where applicable — matches Roadmaps tab.",
  ].join(" ");
  return (
    <span
      className={clsx(
        "inline-flex items-center px-2 py-0.5 rounded border text-[11px] font-semibold max-w-[10rem] text-left leading-snug",
        style.bg,
        style.text,
        style.border,
      )}
      title={title}
    >
      {action}
    </span>
  );
}

function sanitizeEarningsFlag(s: string): string {
  if (/403|401|Forbidden|timeout|Client Error/i.test(s)) {
    return "Earnings quality unavailable (data source)";
  }
  return s.length > 80 ? `${s.slice(0, 77)}…` : s;
}

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

function MLProbPill({ prob }: { prob: number | null | undefined }) {
  if (prob == null) return (
    <span className="text-[10px] text-slate-600 font-mono" title="ML model not yet trained for this ticker — run daily training to populate">
      ML –
    </span>
  );
  const pct = Math.round(prob * 100);
  const colour =
    pct >= 60 ? "text-emerald-300 bg-emerald-500/15 border-emerald-500/30" :
    pct >= 40 ? "text-amber-300  bg-amber-500/15  border-amber-500/30"  :
                "text-red-300    bg-red-500/15    border-red-500/30";
  return (
    <span
      className={clsx("text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded border", colour)}
      title={`ML short-term: ${pct}% probability of gaining threshold% in 20 days (LightGBM). Click ticker for full 7-layer breakdown.`}
    >
      ML {pct}%
    </span>
  );
}

function EarningsCell({ signal: r }: { signal: Signal }) {
  const q = r.earnings_quality;
  const grade = q?.grade;
  const flags = (q?.flags ?? []).filter(Boolean);
  const flagStr = flags.slice(0, 2).join(" · ");
  if (!r.earnings_caution && !grade && !flagStr && r.earnings_days_until == null) {
    return <span className="text-slate-600">–</span>;
  }
  return (
    <div className="space-y-1 max-w-[9rem]">
      {r.earnings_caution && (
        <span
          className="inline-flex px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40"
          title="Within earnings caution window — extra score reduction applied"
        >
          Caution{r.earnings_days_until != null ? ` · ${r.earnings_days_until}d` : ""}
        </span>
      )}
      {!r.earnings_caution && r.earnings_days_until != null && r.earnings_days_until <= 14 && (
        <span className="text-[10px] text-slate-500" title="Days until next earnings (when known)">
          {r.earnings_days_until}d
        </span>
      )}
      {grade && (
        <div className="text-slate-300 text-xs" title={flags.length ? flags.join("; ") : undefined}>
          <span className="font-semibold">EQ {grade}</span>
          {q?.quality_score != null && (
            <span className="text-slate-500 ml-1 tabular-nums">({Math.round(q.quality_score)})</span>
          )}
        </div>
      )}
      {flagStr ? (
        <span
          className="text-[10px] text-slate-500 block truncate"
          title={flags.join("; ")}
        >
          {sanitizeEarningsFlag(flagStr)}
        </span>
      ) : null}
    </div>
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
    <div className="space-y-1">
      {/* Row 1: confluence score + ML probability pill side-by-side */}
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className={clsx("font-semibold tabular-nums text-sm", colour)}
          title="Confluence: how much do Trend + RSI + MACD + Regime agree on direction? Click ticker for full 7-layer ML Confidence."
        >
          {scorePct != null ? scorePct : "–"}
          {r.confidence_tag === "low (bear/neutral market)" && (
            <span className="text-amber-400 text-[10px] ml-0.5" title="Score down-weighted in BEAR/NEUTRAL regime">↓</span>
          )}
        </span>
        <MLProbPill prob={r.ml_short_prob} />
      </div>
      {/* Row 2: mini signal dots */}
      <div className="flex items-center gap-1" title="Signal alignment: Trend · RSI · MACD">
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
  long_term: "~12–18 mo",
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
  tickerActions,
}: {
  signals: Signal[];
  horizons?: { short_term: string; medium_term: string; long_term: string } | null;
  onTickerClick?: (ticker: string) => void;
  riskSizing?: { risk_pct: number; stop_pct: number };
  cotByTicker?: Record<string, string>;
  tickerActions?: Record<string, { action: string; one_liner: string }>;
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
      <div className="flex items-center justify-end gap-2 px-3 sm:px-4 py-2 bg-slate-800 border-b border-slate-700">
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
              <div className="flex flex-col items-end gap-0.5">
                <div className="flex items-center gap-2">
                  {r.plan_action ? (
                    <PlanActionBadge action={r.plan_action} conf={r.plan_confidence} />
                  ) : tickerActions?.[r.ticker] ? (
                    <span
                      className={clsx("text-[10px] font-semibold px-1.5 py-0.5 rounded", RETAIL_ACTION_STYLE[tickerActions[r.ticker].action]?.bg ?? "bg-slate-600", RETAIL_ACTION_STYLE[tickerActions[r.ticker].action]?.text ?? "text-slate-300")}
                      title={tickerActions[r.ticker].one_liner}
                    >
                      {tickerActions[r.ticker].action}
                    </span>
                  ) : null}
                  <span className="text-slate-400 text-sm">{r.close != null ? `$${r.close.toFixed(2)}` : "-"}</span>
                </div>
                {r.risk_sizing && (
                  <span className="text-[10px] text-slate-500" title="Risk budget if stop hits">
                    Risk ~$
                    {(r.risk_sizing.risk_budget_dollars != null
                      ? r.risk_sizing.risk_budget_dollars
                      : Math.round((r.risk_sizing.size_dollars * r.risk_sizing.stop_pct) / 100)
                    ).toLocaleString(undefined, { maximumFractionDigits: 0 })}{" "}
                    · {r.risk_sizing.shares} sh · {r.risk_sizing.stop_pct}% stop
                  </span>
                )}
              </div>
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
              <MLProbPill prob={r.ml_short_prob} />
              <span className={clsx(
                "px-2 py-0.5 rounded text-xs font-medium",
                r.regime === "UP" && "bg-emerald-500/20 text-emerald-400",
                r.regime === "NEUTRAL" && "bg-slate-500/20 text-slate-400",
                r.regime === "DOWN" && "bg-red-500/20 text-red-400"
              )}>
                {r.regime ?? "-"}
              </span>
              <span className="text-[9px] text-slate-600 uppercase tracking-wide">Tech+ML</span>
              <SignalBadge signal={r.signal} />
              {r.rsi != null && <span className="text-slate-500 text-sm">RSI {r.rsi.toFixed(0)}</span>}
            </div>
            {r.earnings_note && <p className="text-amber-400 text-xs mt-1">{r.earnings_note}</p>}
            <div className="mt-1">
              <EarningsCell signal={r} />
            </div>
            {r.story_change && <p className="text-amber-400/90 text-xs mt-0.5">{r.story_change}</p>}
          </button>
        ))}
      </div>

      {/* Desktop: table with sticky header + sticky first column */}
      <div className="hidden md:block overflow-x-auto [-webkit-overflow-scrolling:touch]">
        <table className="w-full min-w-[1240px] text-sm border-collapse">
          <thead>
            <tr className="text-left text-base text-slate-400">
              <th className="sticky top-0 left-0 z-[30] min-w-[4.5rem] w-24 bg-slate-800 px-3 py-2.5 font-medium border-b border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]">
                Ticker
              </th>
              <th className="sticky top-0 left-24 z-[25] min-w-[5rem] w-20 px-3 py-2.5 font-medium bg-slate-800 border-b border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)]">
                Close
              </th>
              <th
                className="sticky top-0 z-[20] min-w-[7.5rem] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 text-left cursor-help"
                title={`Risk budget = ${riskSizing?.risk_pct ?? 1}% of portfolio if stop hits; notional position = budget ÷ (stop %).`}
              >
                Risk (size)
              </th>
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 cursor-help whitespace-nowrap"
                title="Confluence Score (0–100): how much do Trend + RSI + MACD + Regime agree on direction? ≥65 = aligned bullish · 35–65 = mixed · ≤35 = bearish alignment. NOT a probability — click any ticker to see the 7-layer ML Confidence breakdown."
              >
                Confluence
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700">
                LIS
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700">
                RSI
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700">
                Regime
              </th>
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 cursor-help text-left min-w-[7rem]"
                title="7-layer confidence action — same model as the Roadmaps tab and ticker detail (not the old confluence-only tier)."
              >
                Plan (7L)
              </th>
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 cursor-help whitespace-nowrap"
                title="Confluence + ML short-term tier (technical alignment). Can differ from Plan when ML is weak or regime gates apply."
              >
                Tech+ML
              </th>
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 cursor-help text-left"
                title="Earnings caution window, days to report, and FMP-based earnings quality (EQ) when available"
              >
                Earnings
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700">
                Positioning
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700">
                Buy / Sell / Support
              </th>
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 min-w-[11rem]"
                title="Horizon cues (ST/MT/LT) — aligned with Plan when plan says reduce/avoid."
              >
                Horizons ST / MT / LT
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700">
                Vol / DD
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700">
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
                  <div className="flex items-center gap-1.5 flex-wrap">
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
                    {!r.plan_action && tickerActions?.[r.ticker] && (
                      <span
                        className={clsx(
                          "text-[10px] font-semibold px-1.5 py-0.5 rounded",
                          RETAIL_ACTION_STYLE[tickerActions[r.ticker].action]?.bg ?? "bg-slate-600",
                          RETAIL_ACTION_STYLE[tickerActions[r.ticker].action]?.text ?? "text-slate-300"
                        )}
                        title={tickerActions[r.ticker].one_liner}
                      >
                        {tickerActions[r.ticker].action}
                      </span>
                    )}
                  </div>
                </td>
                <td
                  className={clsx(
                    "sticky left-24 z-[10] min-w-[5rem] w-20 px-3 py-2.5 border-r border-slate-700/70 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)]",
                    r.story_change ? "bg-amber-500/5" : "bg-slate-900 group-hover:bg-slate-800/30"
                  )}
                  title="Last close from daily data"
                >
                  {r.close != null ? `$${r.close.toFixed(2)}` : "-"}
                </td>
                <td
                  className="px-3 py-2.5 text-xs text-slate-300 align-top"
                  title={
                    r.risk_sizing
                      ? `Risk $${(r.risk_sizing.risk_budget_dollars ?? "").toString()} if ${r.risk_sizing.stop_pct}% stop hits; notional ~$${r.risk_sizing.size_dollars.toLocaleString()}`
                      : "Add portfolio value + configure risk_sizing in config for per-ticker size"
                  }
                >
                  {r.risk_sizing ? (
                    <div className="space-y-0.5">
                      <div className="text-emerald-400/95 font-medium">
                        $
                        {(r.risk_sizing.risk_budget_dollars != null
                          ? r.risk_sizing.risk_budget_dollars
                          : Math.round((r.risk_sizing.size_dollars * r.risk_sizing.stop_pct) / 100)
                        ).toLocaleString(undefined, { maximumFractionDigits: 0 })}{" "}
                        <span className="text-slate-500 font-normal">at risk</span>
                      </div>
                      <div className="text-slate-500">
                        ~{r.risk_sizing.shares} sh · {r.risk_sizing.stop_pct}% stop
                        {r.risk_sizing.risk_pct != null && ` · ${r.risk_sizing.risk_pct}% port`}
                      </div>
                    </div>
                  ) : (
                    "–"
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
                <td className="px-3 py-2.5 align-top max-w-[10.5rem]">
                  <PlanActionBadge action={r.plan_action} conf={r.plan_confidence} />
                </td>
                <td className="px-3 py-2.5 align-top">
                  <SignalBadge signal={r.signal} />
                </td>
                <td className="px-3 py-2.5 align-top text-xs">
                  <EarningsCell signal={r} />
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
                <td className="px-3 py-2.5 align-top text-slate-400 max-w-[min(100vw,20rem)]">
                  <div className="space-y-1.5 text-[11px] leading-snug">
                    <div className="flex gap-1.5">
                      <span className="text-slate-600 shrink-0 w-7">ST</span>
                      <span className="text-slate-300 min-w-0">{r.short_suggestion || "—"}</span>
                    </div>
                    <div className="flex gap-1.5">
                      <span className="text-slate-600 shrink-0 w-7">MT</span>
                      <span className="text-slate-300 min-w-0">{r.medium_suggestion || "—"}</span>
                    </div>
                    <div className="flex gap-1.5">
                      <span className="text-slate-600 shrink-0 w-7">LT</span>
                      <span className="text-slate-300 min-w-0">{r.long_suggestion || "—"}</span>
                    </div>
                    {(r.st_band || r.mt_band || r.lt_band) && (
                      <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-700/60 space-y-0.5" title="ST: stop–target. MT: vol band. LT: fair+consensus">
                        {r.st_band && (
                          <span className="block font-mono">${r.st_band.low.toFixed(1)}–${r.st_band.high.toFixed(1)} ST band</span>
                        )}
                        {r.mt_band && (
                          <span className="block font-mono">${r.mt_band.low.toFixed(1)}–${r.mt_band.high.toFixed(1)} MT band</span>
                        )}
                        {r.lt_band && (
                          <span className="block font-mono">
                            ${r.lt_band.low.toFixed(1)}–${r.lt_band.high.toFixed(1)} LT
                            {r.lt_band_low_confidence && " (low conf)"}
                          </span>
                        )}
                        {r.uncertainty?.st_band_width_pct != null && (
                          <span className="block text-slate-600">ST width {r.uncertainty.st_band_width_pct}% spot</span>
                        )}
                        {r.uncertainty?.typical_range_label && (
                          <span className="block text-slate-600">{r.uncertainty.typical_range_label}</span>
                        )}
                        {r.uncertainty?.mt_narrative && (
                          <span className="block text-slate-600">{r.uncertainty.mt_narrative}</span>
                        )}
                        {r.uncertainty?.lt_narrative && (
                          <span className="block text-slate-600">{r.uncertainty.lt_narrative}</span>
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
