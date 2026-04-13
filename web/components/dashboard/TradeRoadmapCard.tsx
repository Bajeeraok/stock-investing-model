"use client";

import React, { useState, useMemo } from "react";
import {
  ChevronDown,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  LayoutGrid,
  Newspaper,
} from "lucide-react";
import { clsx } from "clsx";

export interface BuyRoadmapStage {
  timeline_key: string;
  label: string;
  when_to_act: string;
  price_zone_low: number | null;
  price_zone_high: number | null;
  condition: string;
  conviction: string;
  position_pct: number;
  cumulative_pct: number;
  /** UI-only (merged near-term row): stacked zones in the price column */
  price_zone_lines?: { label: string; lo: number | null; hi: number | null }[];
}

export interface SellRoadmapStage {
  timeline_key: string;
  label: string;
  when_to_sell: string;
  price_zone_low: number | null;
  price_zone_high: number | null;
  condition: string;
  action: string;
  reason: string;
}

/** Same `run_confidence()` pass as ML/HMM/pattern — headlines + NLP score for transparency */
export interface NewsSentimentLayerPayload {
  pipeline_note?: string;
  score_0_1?: number | null;
  raw_score_neg1_to_1?: number | null;
  summary_label?: string | null;
  sentiment_label?: string | null;
  headline_count?: number | null;
  source?: string | null;
  method?: string | null;
  headlines?: { title: string; score?: number | null; label?: string | null }[];
  layer_weight?: number | null;
  layer_available?: boolean | null;
  message?: string | null;
  /** Whether the running backend loaded FMP / AV keys (booleans only — no secrets) */
  fmp_key_configured?: boolean;
  alpha_vantage_key_configured?: boolean;
  /** Sanitized FMP news error when headline source is AV/Yahoo after FMP failed */
  fmp_request_error?: string | null;
}

export interface TradeRoadmapData {
  current_price: number;
  fair_value: number;
  high_52w: number | null;
  low_52w: number | null;
  regime_label: string;
  display_verdict: string;
  buy_roadmap: BuyRoadmapStage[];
  sell_roadmap: SellRoadmapStage[];
  trader_summary: {
    short_term: string;
    medium_term: string;
    long_term: string;
    /** Explains horizon blurbs vs full table (from API) */
    horizon_note?: string;
  };
  news_sentiment_layer?: NewsSentimentLayerPayload | null;
}

const TRADER_FILTER: Record<string, string[]> = {
  /** `near_term_watch` is a UI-merged row replacing today + days 1–10 + week 2–4 when all are watch / 0% */
  day_trader: ["near_term_watch", "today", "days_1_10", "week_2_4"],
  swing_trader: ["1_3_months", "3_6_months"],
  investor: ["near_term_watch", "today", "3_6_months", "6_12_months"],
};

const SELL_FILTER: Record<string, string[]> = {
  day_trader: ["immediate", "short_term", "anytime"],
  swing_trader: ["1_3_months", "3_6_months", "anytime"],
  investor: ["6_12_months", "anytime"],
};

const TIMELINE_SLIDER_LABELS = [
  { key: "today", label: "Today" },
  { key: "week_2_4", label: "2 weeks" },
  { key: "1_3_months", label: "1 mo" },
  { key: "3_6_months", label: "3 mo" },
  { key: "6_12_months", label: "12 mo" },
];

function formatZone(lo: number | null, hi: number | null): string {
  if (lo != null && hi != null) {
    if (Math.abs(lo - hi) < 0.005) return `$${hi.toFixed(2)}`;
    return `$${lo.toFixed(2)}–$${hi.toFixed(2)}`;
  }
  if (lo != null) return `Below $${lo.toFixed(2)}`;
  if (hi != null) return `Below $${hi.toFixed(2)}`;
  return "—";
}

/** Styling for horizon-role labels (Medium / High / Stress — scenario tone, not size rank). */
function horizonRoleColor(c: string): string {
  if (!c || c === "None") return "text-slate-500";
  if (c.includes("Highest")) return "text-emerald-400";
  if (c.includes("High")) return "text-green-400";
  if (c.includes("Medium")) return "text-amber-400";
  if (c.includes("Low")) return "text-slate-400";
  return "text-slate-300";
}

/** Hide meaningless "None" horizon role in the table */
function formatHorizonRoleDisplay(c: string | undefined): string | null {
  const s = (c || "").trim();
  if (!s || s.toLowerCase() === "none") return null;
  return s;
}

const NEAR_TERM_KEYS = ["today", "days_1_10", "week_2_4"] as const;

/**
 * When Today, Days 1–10, and Week 2–4 are all watch-only / 0% (common when aligned to core),
 * merge into one row to avoid repetitive inaction messaging. Clarifies when spot already sits
 * in the short-term ±2% band (informational churn, not a buy trigger).
 */
function mergeNearTermWatchRows(rows: BuyRoadmapStage[], spot: number): BuyRoadmapStage[] {
  if (rows.length < 3) return rows;
  const [a, b, c] = rows;
  const keysOk =
    a.timeline_key === "today" &&
    b.timeline_key === "days_1_10" &&
    c.timeline_key === "week_2_4";
  if (!keysOk) return rows;
  const watchish = (w: string) => /watch/i.test(w || "");
  const allWatch =
    a.position_pct === 0 &&
    b.position_pct === 0 &&
    c.position_pct === 0 &&
    watchish(a.when_to_act) &&
    watchish(b.when_to_act) &&
    watchish(c.when_to_act);
  if (!allWatch) return rows;

  const stLo = b.price_zone_low;
  const stHi = b.price_zone_high;
  const inStBand =
    stLo != null && stHi != null && spot >= stLo && spot <= stHi;

  const stZ = formatZone(stLo, stHi);
  const spotClarify = inStBand
    ? ` Spot is already in the short-term ${stZ} window — that is local range around print, not a separate buy trigger while the row stays watch-only.`
    : "";

  const condition = [a.condition, spotClarify.trim(), b.condition, c.condition].filter(Boolean).join(" ");

  const merged: BuyRoadmapStage = {
    timeline_key: "near_term_watch",
    label: "Today → week 4",
    when_to_act: "Watch only — no new size yet",
    price_zone_low: null,
    price_zone_high: null,
    price_zone_lines: [
      { label: "Preferred adds", lo: a.price_zone_low, hi: a.price_zone_high },
      { label: "ST ±2% (around spot)", lo: stLo, hi: stHi },
    ],
    condition,
    conviction: "None",
    position_pct: 0,
    cumulative_pct: a.cumulative_pct,
  };

  return [merged, ...rows.slice(3)];
}

function buyRowTimelineHighlight(row: BuyRoadmapStage, activeKey: string | undefined): boolean {
  if (!activeKey) return false;
  if (row.timeline_key === "near_term_watch") {
    return NEAR_TERM_KEYS.includes(activeKey as (typeof NEAR_TERM_KEYS)[number]);
  }
  return row.timeline_key === activeKey;
}

/** Emoji + row tint for buy "when to act" (GLD-style cues). */
function buyStageCue(when: string): { emoji: string; rowBg: string } {
  const w = (when || "").toLowerCase();
  if (w.includes("do not buy") || w.includes("don't")) return { emoji: "🔴", rowBg: "bg-red-500/5" };
  if (w.includes("watch only")) return { emoji: "👀", rowBg: "bg-slate-500/5" };
  if (w.includes("start small")) return { emoji: "🟡", rowBg: "bg-amber-500/5" };
  if (w.includes("add position")) return { emoji: "🟢", rowBg: "bg-emerald-500/5" };
  if (w.includes("core position")) return { emoji: "🔵", rowBg: "bg-blue-500/5" };
  if (w.includes("tail risk") || w.includes("black swan")) return { emoji: "⚡", rowBg: "bg-slate-600/15" };
  if (w.includes("back up truck")) return { emoji: "💎", rowBg: "bg-emerald-500/10" };
  if (w.includes("watch")) return { emoji: "👀", rowBg: "bg-slate-500/5" };
  return { emoji: "•", rowBg: "" };
}

/** Emoji + row tint for sell "when to sell". */
function sellStageCue(when: string): { emoji: string; rowBg: string } {
  const w = (when || "").toLowerCase();
  if (w.includes("hard stop")) return { emoji: "🛑", rowBg: "bg-red-500/10" };
  if (w.includes("trim") && !w.includes("partial") && !w.includes("major")) return { emoji: "⚠️", rowBg: "bg-amber-500/5" };
  if (w.includes("partial exit")) return { emoji: "🟡", rowBg: "bg-amber-500/5" };
  if (w.includes("major trim")) return { emoji: "🟢", rowBg: "bg-emerald-500/5" };
  if (w.includes("full target")) return { emoji: "💰", rowBg: "bg-emerald-500/10" };
  if (w.includes("regime flip")) return { emoji: "🔴", rowBg: "bg-red-500/5" };
  return { emoji: "•", rowBg: "" };
}

/** Ticker-specific note (e.g. GLD vs spot gold). */
function tickerNote(ticker: string | undefined): string | null {
  if (!ticker) return null;
  const t = ticker.toUpperCase();
  if (t === "GLD") return "GLD ≈ 1/10 oz gold; spot ~$2,900/oz.";
  if (t === "SLV") return "SLV tracks silver spot.";
  if (["IAU", "SGOL"].includes(t)) return "Gold ETF — track spot for context.";
  return null;
}

export function TradeRoadmapCard({ data, ticker }: { data: TradeRoadmapData; ticker?: string }) {
  const [tab, setTab] = useState<"buy" | "sell" | "full">("buy");
  const [traderType, setTraderType] = useState<"day_trader" | "swing_trader" | "investor">("swing_trader");
  const [timelineIndex, setTimelineIndex] = useState(0);
  const [expanded, setExpanded] = useState(true);
  /** News block collapsed by default — expand to verify headlines / NLP inputs */
  const [newsExpanded, setNewsExpanded] = useState(false);

  const allowedKeys = TRADER_FILTER[traderType] || [];
  const activeTimelineKey = TIMELINE_SLIDER_LABELS[timelineIndex]?.key;

  const buyFiltered = useMemo(() => {
    if (tab === "full") return data.buy_roadmap;
    return data.buy_roadmap.filter((r) => allowedKeys.includes(r.timeline_key));
  }, [data.buy_roadmap, allowedKeys, tab]);

  const buyRowsDisplay = useMemo(
    () => mergeNearTermWatchRows(buyFiltered, data.current_price),
    [buyFiltered, data.current_price]
  );

  const sellAllowedKeys = SELL_FILTER[traderType] || [];
  const sellFiltered = useMemo(() => {
    if (tab === "full") return data.sell_roadmap;
    return data.sell_roadmap.filter((r) => sellAllowedKeys.includes(r.timeline_key));
  }, [data.sell_roadmap, sellAllowedKeys, tab]);

  const currentSummary =
    traderType === "day_trader"
      ? data.trader_summary.short_term
      : traderType === "swing_trader"
        ? data.trader_summary.medium_term
        : data.trader_summary.long_term;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800/50 overflow-hidden">
      {/* Header: verdict + current price / fair value / regime */}
      <div className="p-4 border-b border-slate-700 bg-slate-900/60">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={clsx(
                "text-sm font-bold px-2 py-0.5 rounded",
                data.display_verdict === "AVOID" || data.display_verdict === "REDUCE"
                  ? "bg-red-500/20 text-red-300"
                  : data.display_verdict === "BUY" || data.display_verdict === "STRONG BUY"
                    ? "bg-emerald-500/20 text-emerald-300"
                    : "bg-amber-500/20 text-amber-300"
              )}
            >
              {data.display_verdict}
            </span>
            <span className="text-slate-400 text-sm">
              Current: ${data.current_price.toFixed(2)}
              {data.fair_value != null && ` | Fair value: $${data.fair_value.toFixed(2)}`}
              {data.regime_label && ` | Regime: ${data.regime_label}`}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="p-1 rounded hover:bg-slate-700 text-slate-400"
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {expanded && (
        <>
          {/* Tabs: Buy Roadmap | Sell Roadmap | Full Plan */}
          <div className="flex border-b border-slate-700">
            {(["buy", "sell", "full"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={clsx(
                  "flex-1 px-4 py-2.5 text-sm font-medium transition-colors",
                  tab === t
                    ? "bg-emerald-500/10 text-emerald-400 border-b-2 border-emerald-500"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-700/30"
                )}
              >
                {t === "buy" && <><TrendingUp className="inline h-3.5 w-3.5 mr-1.5" /> Buy Roadmap</>}
                {t === "sell" && <><TrendingDown className="inline h-3.5 w-3.5 mr-1.5" /> Sell Roadmap</>}
                {t === "full" && <><LayoutGrid className="inline h-3.5 w-3.5 mr-1.5" /> Full Plan</>}
              </button>
            ))}
          </div>

          {/* Trader type selector */}
          <div className="px-4 py-2 border-b border-slate-700/70 flex items-center gap-2 flex-wrap">
            <span className="text-xs text-slate-500 uppercase tracking-wide">View:</span>
            {(["day_trader", "swing_trader", "investor"] as const).map((tt) => (
              <button
                key={tt}
                type="button"
                onClick={() => setTraderType(tt)}
                className={clsx(
                  "text-xs px-2.5 py-1 rounded font-medium",
                  traderType === tt
                    ? "bg-slate-600 text-white"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-700/50"
                )}
              >
                {tt === "day_trader" && "Day / Short-term"}
                {tt === "swing_trader" && "Swing (1–3 mo)"}
                {tt === "investor" && "Investor (6–12 mo)"}
              </button>
            ))}
          </div>

          {/* Timeline slider */}
          <div className="px-4 py-2 border-b border-slate-700/70">
            <div className="flex items-center gap-1 flex-wrap">
              {TIMELINE_SLIDER_LABELS.map(({ key, label }, i) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setTimelineIndex(i)}
                  className={clsx(
                    "text-xs px-2 py-1 rounded",
                    activeTimelineKey === key
                      ? "bg-amber-500/20 text-amber-300 font-medium"
                      : "text-slate-500 hover:text-slate-300"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="p-4 space-y-4">
            {/* Trader summary one-liner */}
            <div className="rounded-lg bg-slate-800/80 border border-slate-600/50 px-3 py-2">
              <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Summary for your horizon</p>
              <p className="text-sm text-slate-200">{currentSummary}</p>
              {data.trader_summary.horizon_note && (
                <p className="text-[11px] text-slate-500 mt-2 leading-snug border-t border-slate-600/40 pt-2">
                  {data.trader_summary.horizon_note}
                </p>
              )}
              {tickerNote(ticker) && (
                <p className="text-xs text-slate-500 mt-1.5 border-t border-slate-600/50 pt-1.5">{tickerNote(ticker)}</p>
              )}
            </div>

            {data.news_sentiment_layer && (
              <div className="rounded-lg border border-cyan-500/20 bg-cyan-950/25 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setNewsExpanded((n) => !n)}
                  className="w-full px-3 py-2.5 flex items-start gap-2 text-left hover:bg-cyan-950/40 transition-colors"
                  aria-expanded={newsExpanded}
                >
                  <Newspaper className="h-3.5 w-3.5 shrink-0 text-cyan-200/90 mt-0.5" aria-hidden />
                  <span className="flex-1 min-w-0">
                    <span className="text-xs text-cyan-200/90 font-medium block">Headlines (news sentiment layer)</span>
                    <span className="text-[11px] text-slate-500 block mt-0.5">
                      {data.news_sentiment_layer.sentiment_label && (
                        <span className="text-slate-400">{data.news_sentiment_layer.sentiment_label}</span>
                      )}
                      {data.news_sentiment_layer.score_0_1 != null && (
                        <span className={data.news_sentiment_layer.sentiment_label ? " · " : ""}>
                          Score {(data.news_sentiment_layer.score_0_1 * 100).toFixed(0)}%
                        </span>
                      )}
                      {data.news_sentiment_layer.headline_count != null && (
                        <span>
                          {" "}
                          · {data.news_sentiment_layer.headline_count} articles sampled
                        </span>
                      )}
                      {!newsExpanded && <span className="text-slate-600"> · Tap to expand</span>}
                    </span>
                  </span>
                  {newsExpanded ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-slate-500 mt-0.5" aria-hidden />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-slate-500 mt-0.5" aria-hidden />
                  )}
                </button>
                {newsExpanded && (
                  <div className="px-3 pb-2.5 pt-0 border-t border-cyan-500/15">
                    {data.news_sentiment_layer.pipeline_note && (
                      <p className="text-[11px] text-slate-500 mb-2 leading-snug">{data.news_sentiment_layer.pipeline_note}</p>
                    )}
                    {(data.news_sentiment_layer.fmp_key_configured != null ||
                      data.news_sentiment_layer.alpha_vantage_key_configured != null) && (
                      <p className="text-[11px] text-slate-500 mb-2 font-mono">
                        Keys loaded on server: FMP{" "}
                        {data.news_sentiment_layer.fmp_key_configured ? "yes" : "no"} · Alpha Vantage{" "}
                        {data.news_sentiment_layer.alpha_vantage_key_configured ? "yes" : "no"}
                      </p>
                    )}
                    {data.news_sentiment_layer.fmp_request_error && (
                      <p className="text-[11px] text-amber-200/85 mb-2 leading-snug font-mono">
                        FMP news: {data.news_sentiment_layer.fmp_request_error}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-400 mb-2 font-mono">
                      {data.news_sentiment_layer.score_0_1 != null && (
                        <span>
                          Layer score:{" "}
                          <span className="text-slate-200">{(data.news_sentiment_layer.score_0_1 * 100).toFixed(0)}%</span>
                        </span>
                      )}
                      {data.news_sentiment_layer.sentiment_label && (
                        <span>Label: {data.news_sentiment_layer.sentiment_label}</span>
                      )}
                      {data.news_sentiment_layer.source && <span>Source: {data.news_sentiment_layer.source}</span>}
                      {data.news_sentiment_layer.method && <span>Method: {data.news_sentiment_layer.method}</span>}
                      {data.news_sentiment_layer.layer_weight != null && (
                        <span>Weight in confidence: {(Number(data.news_sentiment_layer.layer_weight) * 100).toFixed(0)}%</span>
                      )}
                      {data.news_sentiment_layer.layer_available === false && (
                        <span className="text-amber-400/90">Layer omitted (redistributed)</span>
                      )}
                    </div>
                    {data.news_sentiment_layer.message && (
                      <p className="text-[11px] text-amber-200/80 mb-2">{data.news_sentiment_layer.message}</p>
                    )}
                    {data.news_sentiment_layer.summary_label && (
                      <p className="text-xs text-slate-400 mb-2 leading-snug">{data.news_sentiment_layer.summary_label}</p>
                    )}
                    {(data.news_sentiment_layer.headlines?.length ?? 0) > 0 && (
                      <ul className="space-y-1.5 text-xs text-slate-300 border-t border-slate-600/40 pt-2">
                        {(data.news_sentiment_layer.headlines ?? []).map((h, i) => (
                          <li key={i} className="leading-snug pl-2 border-l-2 border-slate-600/60">
                            {h.title}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Buy Roadmap table */}
            {(tab === "buy" || tab === "full") && (
              <div>
                <h4 className="flex items-center gap-2 text-sm font-semibold text-emerald-400 mb-2">
                  <TrendingUp className="h-4 w-4" /> Buy roadmap
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr className="text-slate-500 border-b border-slate-600">
                        <th className="text-left py-2 pr-2">Timeline</th>
                        <th className="text-left py-2 pr-2">When to act</th>
                        <th className="text-left py-2 pr-2">Price zone</th>
                        <th className="text-left py-2 pr-2">Condition</th>
                        <th
                          className="text-left py-2 pr-2 cursor-help underline decoration-slate-600 decoration-dotted underline-offset-2"
                          title="Qualitative label for this horizon’s role (e.g. tactical add vs. core vs. stress). Not a ranking against the tranche % column."
                        >
                          Horizon role
                        </th>
                        <th
                          className="text-right py-2 cursor-help underline decoration-slate-600 decoration-dotted underline-offset-2"
                          title="Tranche % of planned position — staged deployment slice in the ladder. Not ordered by horizon role; tail rows can be larger when completing the plan."
                        >
                          Tranche %
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {buyRowsDisplay.map((row) => {
                        const cue = buyStageCue(row.when_to_act);
                        const conv = formatHorizonRoleDisplay(row.conviction);
                        const hl = buyRowTimelineHighlight(row, activeTimelineKey);
                        return (
                        <tr
                          key={row.timeline_key}
                          className={clsx(
                            "border-b border-slate-700/50",
                            cue.rowBg,
                            hl && "ring-1 ring-amber-500/30"
                          )}
                        >
                          <td className="py-2 pr-2 text-slate-300">{row.label}</td>
                          <td className="py-2 pr-2 text-slate-200">
                            <span className="mr-1" aria-hidden>{cue.emoji}</span>
                            {row.when_to_act}
                          </td>
                          <td className="py-2 pr-2 font-mono text-slate-300 align-top">
                            {row.price_zone_lines && row.price_zone_lines.length > 0 ? (
                              <div className="space-y-1 text-[10px] leading-snug">
                                {row.price_zone_lines.map((z, zi) => (
                                  <div key={zi}>
                                    <span className="text-slate-500 font-sans">{z.label}: </span>
                                    {formatZone(z.lo, z.hi)}
                                  </div>
                                ))}
                              </div>
                            ) : (
                              formatZone(row.price_zone_low, row.price_zone_high)
                            )}
                          </td>
                          <td className="py-2 pr-2 text-slate-400 max-w-[min(100vw,260px)] sm:max-w-[320px] text-[11px] leading-snug">
                            {row.condition}
                          </td>
                          <td className={clsx("py-2 pr-2 align-top", conv ? horizonRoleColor(row.conviction) : "")}>
                            {conv ? conv : null}
                          </td>
                          <td className="py-2 text-right text-slate-300 align-top">{row.position_pct}%</td>
                        </tr>
                      ); })}
                    </tbody>
                  </table>
                </div>
                <p className="text-[10px] text-slate-500 mt-2 leading-snug max-w-3xl">
                  <strong className="text-slate-400">How to read this:</strong> Horizon role describes the scenario for that
                  row (not “bigger % = higher conviction”). Tranche % is the slice of your planned position for that leg of
                  the staged entry ladder—risk-budget style—not a sort order by the role labels.
                </p>
              </div>
            )}

            {/* Sell Roadmap table */}
            {(tab === "sell" || tab === "full") && (
              <div>
                <h4 className="flex items-center gap-2 text-sm font-semibold text-amber-400 mb-2">
                  <TrendingDown className="h-4 w-4" /> Sell roadmap
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr className="text-slate-500 border-b border-slate-600">
                        <th className="text-left py-2 pr-2">Timeline</th>
                        <th className="text-left py-2 pr-2">When to sell</th>
                        <th className="text-left py-2 pr-2">Price zone</th>
                        <th className="text-left py-2 pr-2">Condition</th>
                        <th className="text-left py-2 pr-2">Action</th>
                        <th className="text-left py-2">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sellFiltered.map((row) => {
                        const cue = sellStageCue(row.when_to_sell);
                        return (
                        <tr
                          key={row.timeline_key}
                          className={clsx(
                            "border-b border-slate-700/50",
                            cue.rowBg,
                            activeTimelineKey === row.timeline_key && "ring-1 ring-amber-500/30"
                          )}
                        >
                          <td className="py-2 pr-2 text-slate-300">{row.label}</td>
                          <td className="py-2 pr-2 text-slate-200">
                            <span className="mr-1" aria-hidden>{cue.emoji}</span>
                            {row.when_to_sell}
                          </td>
                          <td className="py-2 pr-2 font-mono text-slate-300">
                            {formatZone(row.price_zone_low, row.price_zone_high)}
                          </td>
                          <td className="py-2 pr-2 text-slate-400 max-w-[160px] truncate" title={row.condition}>
                            {row.condition}
                          </td>
                          <td className="py-2 pr-2 text-amber-200/90">{row.action}</td>
                          <td className="py-2 text-slate-500">{row.reason}</td>
                        </tr>
                      ); })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
