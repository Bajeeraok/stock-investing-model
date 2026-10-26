"use client";

import React, { useState, useMemo, useEffect } from "react";
import {
  ChevronDown,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  LayoutGrid,
  Newspaper,
} from "lucide-react";
import { clsx } from "clsx";
import { TD } from "./tickerDetailTypography";
import { traderTypeFromMode, type DecisionMode } from "@/lib/decisionMode";

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
  /** Mid-zone upside vs model FV, downside vs ref stop, R:R — from API */
  risk_reward_context?: {
    upside_to_model_fv_pct?: number | null;
    downside_to_ref_stop_pct?: number | null;
    risk_reward?: number | null;
    ref_stop_level?: number | null;
    ref_stop_kind?: string | null;
  } | null;
  allocation_note?: string | null;
  priority_note?: string | null;
  bridge_zone_low?: number | null;
  bridge_zone_high?: number | null;
  catch_levels?: Array<{ id: string; label: string; price: number; role?: string }>;
  is_gap_row?: boolean;
  sync_note?: string | null;
  gap_kind?: string | null;
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
  /** technical_* | macro_scenario | valuation_* | model_regime */
  exit_category?: string | null;
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
  headlines?: { title: string; score?: number | null; label?: string | null; url?: string | null }[];
  catalyst_cards?: Array<{
    name: string;
    event_type?: string;
    direction: string;
    mechanism: string;
    watch?: string;
    horizon?: string;
    source?: string | null;
    age_label?: string | null;
    url?: string | null;
    headline_count?: number;
    draft_note: string;
  }>;
  display_label?: string | null;
  sentiment_caveat?: string | null;
  sentiment_disagreement?: boolean | null;
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
  /** From score.interpretation (ACF / force lists); mirrors signal payload for transparency */
  score_interpretation_style?: string;
  score_interpretation_meta?: { reason?: string; [key: string]: unknown };
  /** Backend roadmap caveats (overlap, Hurst vs ACF, etc.) */
  consistency_notes?: string[];
  trader_summary: {
    short_term: string;
    medium_term: string;
    long_term: string;
    /** Explains horizon blurbs vs full table (from API) */
    horizon_note?: string;
  };
  news_sentiment_layer?: NewsSentimentLayerPayload | null;
  /** Condensed decision + key level */
  tldr?: {
    bias: string;
    strategy: string;
    key_level: number;
    key_level_label?: string;
    model_confidence_pct?: number | null;
    model_confidence_band?: string | null;
    model_confidence_band_note?: string | null;
    dominant_near_term_action?: string | null;
    dual_signal?: {
      structural?: string;
      tactical?: string;
      display_mode?: string;
      bridge_note?: string | null;
    } | null;
    reconciliation_notes?: string[];
    execution_plan_lines?: string[];
  } | null;
  you_are_here?: {
    timeline_key?: string | null;
    label?: string | null;
    within_zone?: boolean;
    note?: string | null;
  } | null;
  scenario_outlook?: {
    bull_pct: number;
    base_pct: number;
    bear_pct: number;
    method?: string;
  } | null;
  market_regime_layer?: {
    vix?: number | null;
    atr_pct_of_price?: number | null;
    risk_off: boolean;
    vol_bucket: string;
    label: string;
  } | null;
  action_glossary?: Record<string, string>;
  probabilistic_framing?: string | null;
  execution_plan_lines?: string[];
}

const TRADER_FILTER: Record<string, string[]> = {
  day_trader: ["today", "days_1_10", "week_2_4"],
  swing_trader: ["1_3_months", "3_6_months"],
  investor: ["today", "days_1_10", "week_2_4", "3_6_months", "6_12_months"],
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
  if (!c || c === "None") return "text-td-muted";
  if (c.includes("Highest")) return "text-td-accent";
  if (c.includes("High")) return "text-td-accent";
  if (c.includes("Medium")) return "text-td-warn";
  if (c.includes("Low")) return "text-td-muted";
  return "text-td-text";
}

/** Hide meaningless "None" horizon role in the table */
function formatHorizonRoleDisplay(c: string | undefined): string | null {
  const s = (c || "").trim();
  if (!s || s.toLowerCase() === "none") return null;
  return s;
}

function zoneFingerprint(lo: number | null, hi: number | null): string | null {
  if (lo == null || hi == null) return null;
  return `${lo.toFixed(2)}|${hi.toFixed(2)}`;
}

function buyRowTimelineHighlight(row: BuyRoadmapStage, activeKey: string | undefined): boolean {
  if (!activeKey) return false;
  return row.timeline_key === activeKey;
}

/** Emoji + row tint for buy "when to act" (GLD-style cues). */
function buyStageCue(when: string): { emoji: string; rowBg: string } {
  const w = (when || "").toLowerCase();
  if (w.includes("do not buy") || w.includes("don't")) return { emoji: "🔴", rowBg: "bg-td-crit/5" };
  if (w.includes("watch only")) return { emoji: "👀", rowBg: "bg-td-line/5" };
  if (w.includes("split entry")) return { emoji: "🟡", rowBg: "bg-td-warn/5" };
  if (w.includes("start small")) return { emoji: "🟡", rowBg: "bg-td-warn/5" };
  if (w.includes("add position")) return { emoji: "🟢", rowBg: "bg-td-accent/5" };
  if (w.includes("core position")) return { emoji: "🔵", rowBg: "bg-td-info/5" };
  if (w.includes("tail risk") || w.includes("black swan")) return { emoji: "⚡", rowBg: "bg-td-line/15" };
  if (w.includes("back up truck")) return { emoji: "💎", rowBg: "bg-td-accent/10" };
  if (w.includes("patience")) return { emoji: "⏸️", rowBg: "bg-td-line/10" };
  if (w.includes("watch")) return { emoji: "👀", rowBg: "bg-td-line/5" };
  return { emoji: "•", rowBg: "" };
}

/** Emoji + row tint for sell "when to sell". */
function sellStageCue(when: string): { emoji: string; rowBg: string } {
  const w = (when || "").toLowerCase();
  if (w.includes("hard stop")) return { emoji: "🛑", rowBg: "bg-td-crit/10" };
  if (w.includes("trim") && !w.includes("partial") && !w.includes("major")) return { emoji: "⚠️", rowBg: "bg-td-warn/5" };
  if (w.includes("partial exit")) return { emoji: "🟡", rowBg: "bg-td-warn/5" };
  if (w.includes("major trim")) return { emoji: "🟢", rowBg: "bg-td-accent/5" };
  if (w.includes("full target")) return { emoji: "💰", rowBg: "bg-td-accent/10" };
  if (w.includes("regime flip")) return { emoji: "🔴", rowBg: "bg-td-crit/5" };
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

/** Readable condition copy — long API strings collapse with expand. */
function ConditionText({ text, className }: { text: string; className?: string }) {
  const [expanded, setExpanded] = useState(false);
  const trimmed = (text || "").trim();
  if (!trimmed) return null;
  const long = trimmed.length > 200;
  const shown = long && !expanded ? `${trimmed.slice(0, 200).trim()}…` : trimmed;
  return (
    <div className={clsx(TD.body, className)}>
      <p>{shown}</p>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((o) => !o)}
          className="mt-1 text-xs font-medium text-td-accent hover:text-td-accent"
        >
          {expanded ? "Show less" : "Show full detail"}
        </button>
      )}
    </div>
  );
}

/** Mobile-only card row — key columns + expandable tranche / condition text */
function BuyRoadmapMobileCard({
  row,
  sameBandAsPrior,
  activeTimelineKey,
  youAreHereKey,
  withinZone,
}: {
  row: BuyRoadmapStage;
  sameBandAsPrior: boolean;
  activeTimelineKey: string | undefined;
  youAreHereKey?: string | null;
  withinZone?: boolean;
}) {
  const cue = buyStageCue(row.when_to_act);
  const conv = formatHorizonRoleDisplay(row.conviction);
  const hl = buyRowTimelineHighlight(row, activeTimelineKey);
  const rr = row.risk_reward_context;
  return (
    <div
      className={clsx(
        "rounded-xl border border-td-line/70 bg-td-surface/70 p-3 text-sm space-y-2 shadow-sm",
        cue.rowBg,
        hl && "ring-1 ring-td-warn/35"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-td-text">{row.label}</p>
          {youAreHereKey === row.timeline_key && withinZone && (
            <span className="mt-1 inline-block text-[9px] font-semibold uppercase tracking-wide text-td-warn bg-td-warn/15 px-1 py-0.5 rounded">
              You are here
            </span>
          )}
        </div>
        <span className="shrink-0 text-right font-mono text-td-text tabular-nums">{row.position_pct}%</span>
      </div>
      <p className="text-td-text leading-snug">
        <span className="mr-1" aria-hidden>
          {cue.emoji}
        </span>
        {row.when_to_act}
      </p>
      <div>
        <p className="text-xs uppercase tracking-wide text-td-muted font-semibold mb-0.5">Price zone</p>
        {row.price_zone_lines && row.price_zone_lines.length > 0 ? (
          <div className="space-y-1 font-mono text-sm text-td-text">
            {row.price_zone_lines.map((z, zi) => (
              <div key={zi}>
                <span className="text-td-muted font-td-sans">{z.label}: </span>
                {formatZone(z.lo, z.hi)}
              </div>
            ))}
          </div>
        ) : (
          <p className="font-mono text-td-text">{formatZone(row.price_zone_low, row.price_zone_high)}</p>
        )}
        {sameBandAsPrior && (
          <p className="text-xs text-td-muted mt-1 leading-tight">
            Same band as prior row — horizon role / tranche step up over time.
          </p>
        )}
      </div>
      {(rr?.risk_reward != null || row.priority_note) && (
        <div>
          <p className="text-xs uppercase tracking-wide text-td-muted font-semibold mb-0.5">Risk / reward</p>
          {row.priority_note && <p className="text-xs text-td-warn/90 mb-1">{row.priority_note}</p>}
          {rr?.risk_reward != null && (
            <p className="text-sm text-td-muted leading-snug">
              R:R ~{rr.risk_reward}× · upside ~{rr.upside_to_model_fv_pct ?? "—"}% / downside ~{rr.downside_to_ref_stop_pct ?? "—"}%
              {rr.ref_stop_kind && <span className="text-td-muted"> ({String(rr.ref_stop_kind).replace(/_/g, " ")})</span>}
            </p>
          )}
        </div>
      )}
      {conv && (
        <p className="text-sm">
          <span className="text-td-muted">Horizon role: </span>
          <span className={horizonRoleColor(row.conviction)}>{conv}</span>
        </p>
      )}
      <details className="group border-t border-td-line/60 pt-2">
        <summary className="cursor-pointer text-td-info/90 text-sm font-medium list-none flex items-center gap-1 [&::-webkit-details-marker]:hidden">
          <ChevronRight className="h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-90" aria-hidden />
          Condition & tranche detail (T1/T2/T3 text)
        </summary>
        <div className="mt-2 space-y-2 pl-1">
          <ConditionText text={row.condition} />
          {row.allocation_note && <p className={TD.footnote}>{row.allocation_note}</p>}
        </div>
      </details>
    </div>
  );
}

function SellRoadmapMobileCard({
  row,
  activeTimelineKey,
}: {
  row: SellRoadmapStage;
  activeTimelineKey: string | undefined;
}) {
  const cue = sellStageCue(row.when_to_sell);
  const hl = activeTimelineKey === row.timeline_key;
  return (
    <div className={clsx("rounded-xl border border-td-line/70 bg-td-surface/70 p-3 text-sm space-y-2", cue.rowBg, hl && "ring-1 ring-td-warn/35")}>
      <div className="flex items-start justify-between gap-2">
        <p className="font-semibold text-td-text">{row.label}</p>
        <span className="text-xs text-td-muted font-mono">{row.exit_category?.replace(/_/g, " ") ?? ""}</span>
      </div>
      <p className="text-td-text leading-snug">
        <span className="mr-1" aria-hidden>
          {cue.emoji}
        </span>
        {row.when_to_sell}
      </p>
      <p className="font-mono text-td-text">{formatZone(row.price_zone_low, row.price_zone_high)}</p>
      <p className="text-td-warn/90 font-medium">{row.action}</p>
      <details className="group border-t border-td-line/60 pt-2">
        <summary className="cursor-pointer text-td-info/90 text-sm font-medium list-none flex items-center gap-1 [&::-webkit-details-marker]:hidden">
          <ChevronRight className="h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-90" aria-hidden />
          Condition & reason
        </summary>
        <div className="mt-2 space-y-2 text-sm text-td-muted leading-relaxed pl-1">
          <p>{row.condition}</p>
          {row.reason && <p className="text-td-muted">{row.reason}</p>}
        </div>
      </details>
    </div>
  );
}

export function TradeRoadmapCard({
  data,
  ticker,
  decisionMode,
  tablesOnly = false,
}: {
  data: TradeRoadmapData;
  ticker?: string;
  /** Defaults the "View" selector to match the persona already chosen in the modal. */
  decisionMode?: DecisionMode;
  /**
   * Slim mode used on the Levels tab when a horizon playbook is rendered above —
   * the playbook already carries the narrative (verdict, action, next trigger,
   * why-this-call), so this renders only what the playbook lacks: the staged
   * buy/sell tranche tables plus the news layer.
   */
  tablesOnly?: boolean;
}) {
  const [tab, setTab] = useState<"buy" | "sell" | "full">("buy");
  const [traderType, setTraderType] = useState<"day_trader" | "swing_trader" | "investor">(
    () => (decisionMode ? traderTypeFromMode(decisionMode) : "swing_trader"),
  );
  const [timelineIndex, setTimelineIndex] = useState(0);
  const [expanded, setExpanded] = useState(true);
  /** News block collapsed by default — expand to verify headlines / NLP inputs */
  const [newsExpanded, setNewsExpanded] = useState(false);
  /** Full roadmap vs TL;DR-first (retail) — default simple for faster decisions */
  const [advancedRoadmap, setAdvancedRoadmap] = useState(false);
  /** tablesOnly is always the table view — the narrative it replaces lives in the playbook. */
  const showTables = advancedRoadmap || tablesOnly;
  /** Default open — this is the Action/Next-trigger/Why-this-call/scenario-mix block,
   * exactly the "proof behind the call" a retail trader needs without hunting for it.
   * Previously defaulted closed, so a second click was required below the one-line
   * verdict badge to see any of it. Still collapsible for anyone who wants it out of the way. */
  const [showRoadmapAnalysis, setShowRoadmapAnalysis] = useState(true);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const sync = () => {
      if (mq.matches) setAdvancedRoadmap(true);
    };
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  /** Compact evidence rows for fast decision flow */
  const [evidenceOpen, setEvidenceOpen] = useState<{
    market: boolean;
    chart: boolean;
    flow: boolean;
    business: boolean;
  }>({
    market: false,
    chart: false,
    flow: false,
    business: false,
  });

  const allowedKeys = TRADER_FILTER[traderType] || [];
  const activeTimelineKey = TIMELINE_SLIDER_LABELS[timelineIndex]?.key;

  const buyFiltered = useMemo(() => {
    if (tab === "full") return data.buy_roadmap;
    return data.buy_roadmap.filter((r) => allowedKeys.includes(r.timeline_key));
  }, [data.buy_roadmap, allowedKeys, tab]);

  const buyRowsWithZoneHints = useMemo(() => {
    let lastZone: string | null = null;
    return buyFiltered.map((row) => {
      const z = zoneFingerprint(row.price_zone_low, row.price_zone_high);
      const sameBandAsPrior = z !== null && z === lastZone;
      if (z !== null) lastZone = z;
      return { row, sameBandAsPrior };
    });
  }, [buyFiltered]);

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

  const decisionAction =
    data.tldr?.dominant_near_term_action ||
    (data.display_verdict === "BUY" || data.display_verdict === "STRONG BUY"
      ? "Actionable buy"
      : data.display_verdict === "REDUCE" || data.display_verdict === "AVOID"
        ? "Risk-control mode"
        : "Hold / watch");
  const whyLines = [
    data.tldr?.dual_signal?.bridge_note,
    data.tldr?.strategy ? `Strategy context: ${data.tldr.strategy}` : null,
    ...(data.tldr?.reconciliation_notes ?? []),
  ].filter((x): x is string => Boolean(x)).slice(0, 3);
  const nextTrigger =
    (data.tldr?.execution_plan_lines ?? [])[0] ||
    (data.execution_plan_lines ?? [])[0] ||
    currentSummary;

  return (
    <div className="rounded-2xl border border-td-line/80 bg-td-surface2/55 overflow-hidden shadow-xl shadow-black/20">
      {tablesOnly && (
        <div className="px-4 py-2.5 border-b border-td-line/80 bg-td-surface/40">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-td-muted">
            Stage plan — tranche tables
            <span className="ml-2 normal-case tracking-normal font-normal">
              — verdict &amp; triggers are in the playbook above
            </span>
          </p>
        </div>
      )}
      {/* Header: verdict + current price / fair value / regime */}
      {!tablesOnly && (
      <div className="p-4 border-b border-td-line/80 bg-gradient-to-b from-td-surface/80 to-td-surface/40">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={clsx(
                "text-sm font-bold px-2 py-0.5 rounded border",
                data.display_verdict === "AVOID" || data.display_verdict === "REDUCE"
                  ? "bg-td-crit/20 text-td-crit border-td-crit/45"
                  : data.display_verdict === "BUY" || data.display_verdict === "STRONG BUY"
                    ? "bg-td-accent/20 text-td-accent border-td-accent/45"
                    : data.display_verdict === "WATCH"
                      ? "bg-td-accent/15 text-td-accent-ink border-td-accent/50"
                      : data.display_verdict === "WAIT"
                        ? "bg-td-crit/15 text-td-crit border-td-crit/50"
                        : "bg-td-warn/20 text-td-warn border-td-warn/45"
              )}
            >
              {data.display_verdict}
            </span>
            <div className="min-w-0">
              <span className="text-td-muted text-sm">
                Current: ${data.current_price.toFixed(2)}
                {data.fair_value != null && (
                  <>
                    {" "}
                    <span
                      className="cursor-help border-b border-dotted border-td-line/60"
                      title="Fair value is a model anchor (e.g. earnings × multiple). It answers ‘cheap vs expensive?’ — not ‘safe to buy today?’"
                    >
                      | Fair value: ${data.fair_value.toFixed(2)}
                    </span>
                  </>
                )}
                {data.regime_label && (
                  <>
                    {" "}
                    <span
                      className="cursor-help border-b border-dotted border-td-line/60"
                      title="Regime is risk-on vs risk-off from the model. A cautious regime can override ‘cheap’ until levels or breadth improve."
                    >
                      | Regime: {data.regime_label}
                    </span>
                  </>
                )}
              </span>
            </div>
          </div>
          {(data.score_interpretation_style || "").toUpperCase() === "MEAN_REVERTING" && (
            <p className="text-sm text-td-muted mt-1.5 w-full">
              Score labels use mean-reversion bucket mapping (score.interpretation).
              {data.score_interpretation_meta?.reason === "force_mean_reverting" && (
                <> The model uses conservative signal interpretation for this ticker (mean-reversion buckets).</>
              )}
            </p>
          )}
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="p-1 rounded hover:bg-td-surface2 text-td-muted"
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </div>
      </div>
      )}

      {(expanded || tablesOnly) && (
        <>
          {/* Tabs: Buy Roadmap | Sell Roadmap | Full Plan */}
          <div className="flex border-b border-td-line">
            {(["buy", "sell", "full"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={clsx(
                  "flex-1 px-4 py-2.5 text-sm font-medium transition-colors",
                  tab === t
                    ? "bg-td-accent/10 text-td-accent border-b-2 border-td-accent"
                    : "text-td-muted hover:text-td-text hover:bg-td-surface2/30"
                )}
              >
                {t === "buy" && <><TrendingUp className="inline h-3.5 w-3.5 mr-1.5" /> Buy Roadmap</>}
                {t === "sell" && <><TrendingDown className="inline h-3.5 w-3.5 mr-1.5" /> Sell Roadmap</>}
                {t === "full" && <><LayoutGrid className="inline h-3.5 w-3.5 mr-1.5" /> Full Plan</>}
              </button>
            ))}
          </div>

          {/* TL;DR + market regime (probabilistic, not deterministic) —
              tablesOnly: the playbook above already carries action/trigger/why */}
          {!tablesOnly && (data.tldr || data.market_regime_layer || data.scenario_outlook) && (
            <div className="px-4 py-3 border-b border-td-line/70 space-y-2 bg-td-surface/40">
              <div className="rounded-lg border border-td-line/70 bg-td-surface/40 px-3 py-2 flex items-center gap-3 flex-wrap">
                <span
                  className={clsx(
                    "text-xs font-bold px-2 py-0.5 rounded border",
                    data.display_verdict === "AVOID" || data.display_verdict === "REDUCE"
                      ? "bg-td-crit/20 text-td-crit border-td-crit/45"
                      : data.display_verdict === "BUY" || data.display_verdict === "STRONG BUY"
                        ? "bg-td-accent/20 text-td-accent border-td-accent/45"
                        : data.display_verdict === "WATCH"
                          ? "bg-td-accent/15 text-td-accent-ink border-td-accent/50"
                          : data.display_verdict === "WAIT"
                            ? "bg-td-crit/15 text-td-crit border-td-crit/50"
                            : "bg-td-warn/20 text-td-warn border-td-warn/45"
                  )}
                >
                  {data.display_verdict}
                </span>
                <span
                  className="text-xs text-td-muted cursor-help"
                  title="FV = model fair value from fundamentals (e.g. EPS × P/E). This line is price vs that anchor — not the same as the 7-layer confidence gauge on Details."
                >
                  ${data.current_price.toFixed(2)} · FV ${data.fair_value.toFixed(2)} · {data.regime_label}
                </span>
                <span className="text-sm text-td-muted ml-auto">See Overview for full analysis</span>
              </div>
              <button
                type="button"
                onClick={() => setShowRoadmapAnalysis((s) => !s)}
                className="text-sm text-td-muted hover:text-td-text flex items-center gap-1"
              >
                {showRoadmapAnalysis ? "Hide expanded analysis" : "Show expanded analysis"}
                {showRoadmapAnalysis ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              </button>
              {showRoadmapAnalysis && data.tldr && (
                <div className="rounded-lg border border-td-accent/25 bg-td-accent-weak/20 px-3 py-2">
                  <p className="text-xs text-td-accent-ink/80 uppercase tracking-wide font-medium">TL;DR</p>
                  <p className="text-sm text-td-muted mt-1">
                    Action
                  </p>
                  <p className="text-sm text-td-accent-ink/95 font-semibold">
                    {decisionAction}
                  </p>
                  {nextTrigger && (
                    <>
                      <p className="text-sm text-td-muted mt-2">Next trigger</p>
                      <p className="text-xs text-td-info/90 border-l-2 border-td-info/50 pl-2 mt-0.5">{nextTrigger}</p>
                    </>
                  )}
                  {(whyLines.length > 0) && (
                    <>
                      <p className="text-sm text-td-muted mt-2">Why this call</p>
                      <ul className="mt-1 space-y-1 text-sm text-td-text list-disc list-inside">
                        {whyLines.map((n, i) => (
                          <li key={i}>{n}</li>
                        ))}
                      </ul>
                    </>
                  )}
                  <div className="mt-2 rounded border border-td-line/70 bg-td-surface/30 overflow-hidden">
                    <button
                      type="button"
                      onClick={() => setEvidenceOpen((s) => ({ ...s, market: !s.market }))}
                      className="w-full px-2.5 py-1.5 text-left text-sm text-td-text hover:bg-td-surface2/60 flex items-center justify-between"
                    >
                      <span>Market structure</span>
                      {evidenceOpen.market ? <ChevronDown className="h-3.5 w-3.5 text-td-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-td-muted" />}
                    </button>
                    {evidenceOpen.market && (
                      <p className="px-2.5 pb-2 text-sm text-td-text border-t border-td-line/60 pt-1.5">
                        {data.market_regime_layer?.label || data.tldr.bias}
                      </p>
                    )}
                    <button
                      type="button"
                      onClick={() => setEvidenceOpen((s) => ({ ...s, chart: !s.chart }))}
                      className="w-full px-2.5 py-1.5 text-left text-sm text-td-text hover:bg-td-surface2/60 flex items-center justify-between border-t border-td-line/60"
                    >
                      <span>Chart and momentum</span>
                      {evidenceOpen.chart ? <ChevronDown className="h-3.5 w-3.5 text-td-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-td-muted" />}
                    </button>
                    {evidenceOpen.chart && (
                      <p className="px-2.5 pb-2 text-sm text-td-text border-t border-td-line/60 pt-1.5">
                        {data.you_are_here?.note || "Use current roadmap row and key level for timing."}
                      </p>
                    )}
                    <button
                      type="button"
                      onClick={() => setEvidenceOpen((s) => ({ ...s, flow: !s.flow }))}
                      className="w-full px-2.5 py-1.5 text-left text-sm text-td-text hover:bg-td-surface2/60 flex items-center justify-between border-t border-td-line/60"
                    >
                      <span>Smart money</span>
                      {evidenceOpen.flow ? <ChevronDown className="h-3.5 w-3.5 text-td-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-td-muted" />}
                    </button>
                    {evidenceOpen.flow && (
                      <p className="px-2.5 pb-2 text-sm text-td-text border-t border-td-line/60 pt-1.5">
                        {data.tldr.model_confidence_band ? `Confidence band ${data.tldr.model_confidence_band}.` : "Model confidence context is mixed; stage entries."}
                      </p>
                    )}
                    <button
                      type="button"
                      onClick={() => setEvidenceOpen((s) => ({ ...s, business: !s.business }))}
                      className="w-full px-2.5 py-1.5 text-left text-sm text-td-text hover:bg-td-surface2/60 flex items-center justify-between border-t border-td-line/60"
                    >
                      <span>Business and news</span>
                      {evidenceOpen.business ? <ChevronDown className="h-3.5 w-3.5 text-td-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-td-muted" />}
                    </button>
                    {evidenceOpen.business && (
                      <p className="px-2.5 pb-2 text-sm text-td-text border-t border-td-line/60 pt-1.5">
                        {data.probabilistic_framing || "Review scenario mix and roadmap tiers before sizing."}
                      </p>
                    )}
                  </div>
                  <div className="mt-2 rounded border border-td-line/70 bg-td-surface/30 px-2.5 py-2">
                    <p className="text-sm text-td-muted">What would change this?</p>
                    <p className="text-sm text-td-text font-mono mt-1">
                      Key level: ${data.tldr.key_level.toFixed(2)}
                    </p>
                    {data.tldr.model_confidence_band && (
                      <p className="text-sm text-td-text font-mono">
                        Confidence: {data.tldr.model_confidence_band}
                      </p>
                    )}
                    {data.scenario_outlook && (
                      <p className="text-sm text-td-muted mt-1">
                        Bull {data.scenario_outlook.bull_pct}% | Base {data.scenario_outlook.base_pct}% | Bear {data.scenario_outlook.bear_pct}%
                      </p>
                    )}
                  </div>
                  <p className="text-sm text-td-text mt-1">
                    <span className="text-td-muted">Bias:</span> {data.tldr.bias}
                  </p>
                  <p className="text-sm text-td-text mt-0.5">
                    <span className="text-td-muted">Strategy:</span> {data.tldr.strategy}
                  </p>
                  <p className="text-sm text-td-text mt-0.5 font-mono">
                    <span className="text-td-muted font-td-sans">Key level:</span> ${data.tldr.key_level.toFixed(2)}
                    {data.tldr.key_level_label && (
                      <span className="text-td-muted font-td-sans text-xs ml-1">— {data.tldr.key_level_label}</span>
                    )}
                  </p>
                  {data.tldr.dominant_near_term_action && (
                    <p className="text-xs text-td-warn/90 mt-1">
                      Dominant near-term action: <strong>{data.tldr.dominant_near_term_action}</strong>
                      {data.you_are_here?.label && data.you_are_here.within_zone && (
                        <span className="text-td-muted"> · YOU ARE HERE: {data.you_are_here.label}</span>
                      )}
                    </p>
                  )}
                  {data.tldr.model_confidence_pct != null && (
                    <p className="text-sm text-td-muted mt-1">Model confidence (fused): {data.tldr.model_confidence_pct}%</p>
                  )}
                  {data.tldr.model_confidence_band && (
                    <p className="text-sm text-td-muted">
                      Confidence band: {data.tldr.model_confidence_band}
                    </p>
                  )}
                  {data.tldr.model_confidence_band_note && (
                    <p className="text-xs text-td-muted leading-snug mt-0.5">{data.tldr.model_confidence_band_note}</p>
                  )}
                  {data.tldr.dual_signal && (
                    <p className="text-sm text-td-info/90 mt-1">
                      Structural: <strong>{data.tldr.dual_signal.structural || "N/A"}</strong> · Tactical:{" "}
                      <strong>{data.tldr.dual_signal.tactical || "N/A"}</strong>
                    </p>
                  )}
                  {data.tldr.dual_signal?.bridge_note && (
                    <p className="text-sm text-td-info/90 mt-0.5">{data.tldr.dual_signal.bridge_note}</p>
                  )}
                  {(data.tldr.reconciliation_notes?.length ?? 0) > 0 && (
                    <ul className="mt-2 space-y-1 text-sm text-td-text list-disc list-inside">
                      {(data.tldr.reconciliation_notes ?? []).map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {showRoadmapAnalysis && data.market_regime_layer && (
                <p className="text-xs text-td-text leading-snug">
                  <span className="text-td-info/90 font-medium">Market regime layer:</span> {data.market_regime_layer.label}
                </p>
              )}
              {showRoadmapAnalysis && data.scenario_outlook && (
                <p className="text-xs text-td-muted leading-snug">
                  <span className="text-td-text">Scenario mix (illustrative):</span> Bull ~{data.scenario_outlook.bull_pct}% · Base ~{data.scenario_outlook.base_pct}% · Bear ~{data.scenario_outlook.bear_pct}%
                </p>
              )}
              {showRoadmapAnalysis && data.probabilistic_framing && (
                <p className="text-xs text-td-muted leading-snug">{data.probabilistic_framing}</p>
              )}
            </div>
          )}

          {/* Simple vs full roadmap — tablesOnly always shows tables */}
          {!tablesOnly && (
          <div className="px-4 py-2 border-b border-td-line/70 flex items-center gap-2 flex-wrap">
            <span className="text-xs text-td-muted uppercase tracking-wide">Detail:</span>
            <button
              type="button"
              onClick={() => setAdvancedRoadmap(false)}
              className={clsx(
                "text-xs px-2.5 py-1 rounded font-medium",
                !advancedRoadmap ? "bg-td-line text-td-text" : "text-td-muted hover:text-td-text hover:bg-td-surface2/50"
              )}
            >
              Simple
            </button>
            <button
              type="button"
              onClick={() => setAdvancedRoadmap(true)}
              className={clsx(
                "text-xs px-2.5 py-1 rounded font-medium",
                advancedRoadmap ? "bg-td-line text-td-text" : "text-td-muted hover:text-td-text hover:bg-td-surface2/50"
              )}
            >
              Advanced (full tables)
            </button>
          </div>
          )}

          {/* Trader type selector */}
          <div className="px-4 py-2 border-b border-td-line/70 flex items-center gap-2 flex-wrap">
            <span className="text-xs text-td-muted uppercase tracking-wide">View:</span>
            {(["day_trader", "swing_trader", "investor"] as const).map((tt) => (
              <button
                key={tt}
                type="button"
                onClick={() => setTraderType(tt)}
                className={clsx(
                  "text-xs px-2.5 py-1 rounded font-medium",
                  traderType === tt
                    ? "bg-td-line text-td-text"
                    : "text-td-muted hover:text-td-text hover:bg-td-surface2/50"
                )}
              >
                {tt === "day_trader" && "Day / Short-term"}
                {tt === "swing_trader" && "Swing (1–3 mo)"}
                {tt === "investor" && "Investor (6–12 mo)"}
              </button>
            ))}
          </div>

          {/* Timeline slider (advanced) */}
          {showTables && (
            <div className="px-4 py-2 border-b border-td-line/70">
              <div className="flex items-center gap-1 flex-wrap">
                {TIMELINE_SLIDER_LABELS.map(({ key, label }, i) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setTimelineIndex(i)}
                    className={clsx(
                      "text-xs px-2 py-1 rounded",
                      activeTimelineKey === key
                        ? "bg-td-warn/20 text-td-warn font-medium"
                        : "text-td-muted hover:text-td-text"
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="p-4 space-y-4">
            {/* Trader summary — tablesOnly: playbook headline/setup_narrative covers it */}
            {!tablesOnly && (
            <div className={TD.summaryCard}>
              <p className={TD.sectionLabel}>Summary for your horizon</p>
              <p className={clsx(TD.body, "mt-2")}>{currentSummary}</p>
              {((data.execution_plan_lines?.length ?? 0) > 0 || (data.tldr?.execution_plan_lines?.length ?? 0) > 0) && (
                <ul className="mt-3 space-y-1.5 text-sm text-td-text leading-relaxed list-disc list-inside border-t border-td-line/40 pt-3">
                  {(data.execution_plan_lines && data.execution_plan_lines.length > 0
                    ? data.execution_plan_lines
                    : (data.tldr?.execution_plan_lines ?? [])
                  ).map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              )}
              {advancedRoadmap && data.trader_summary.horizon_note && (
                <p className={clsx(TD.bodyMuted, "mt-3 border-t border-td-line/40 pt-3")}>
                  {data.trader_summary.horizon_note}
                </p>
              )}
              {advancedRoadmap && tickerNote(ticker) && (
                <p className={clsx(TD.footnote, "mt-2 border-t border-td-line/50 pt-2")}>{tickerNote(ticker)}</p>
              )}
              {advancedRoadmap && (data.consistency_notes?.length ?? 0) > 0 && (
                <ul className="text-sm text-td-muted mt-3 space-y-1 border-t border-td-line/40 pt-3 list-disc list-inside">
                  {(data.consistency_notes ?? []).map((n, i) => (
                    <li key={i} className="leading-relaxed">
                      {n}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            )}

            {data.news_sentiment_layer && (
              <div className="rounded-lg border border-td-info/20 bg-td-info/10/25 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setNewsExpanded((n) => !n)}
                  className="w-full px-3 py-2.5 flex items-start gap-2 text-left hover:bg-td-info/10/40 transition-colors"
                  aria-expanded={newsExpanded}
                >
                  <Newspaper className="h-3.5 w-3.5 shrink-0 text-td-info/90 mt-0.5" aria-hidden />
                  <span className="flex-1 min-w-0">
                    <span className="text-xs text-td-info/90 font-medium block">Headlines (news sentiment layer)</span>
                    <span className="text-sm text-td-muted block mt-0.5">
                      {data.news_sentiment_layer.display_label && (
                        <span className="text-td-muted">{data.news_sentiment_layer.display_label}</span>
                      )}
                      {!data.news_sentiment_layer.display_label && data.news_sentiment_layer.sentiment_label && (
                        <span className="text-td-muted">{data.news_sentiment_layer.sentiment_label}</span>
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
                      {data.news_sentiment_layer.layer_weight != null && (
                        <span className="text-td-info/95 font-semibold">
                          {" "}
                          · {(Number(data.news_sentiment_layer.layer_weight) * 100).toFixed(0)}% fused-model weight
                        </span>
                      )}
                      {!newsExpanded && <span className="text-td-muted"> · Tap to expand</span>}
                    </span>
                  </span>
                  {newsExpanded ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-td-muted mt-0.5" aria-hidden />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-td-muted mt-0.5" aria-hidden />
                  )}
                </button>
                {newsExpanded && (
                  <div className="px-3 pb-2.5 pt-0 border-t border-td-info/15">
                    {data.news_sentiment_layer.sentiment_caveat && (
                      <p className="text-sm text-td-warn/85 mb-2 leading-snug">
                        {data.news_sentiment_layer.sentiment_caveat}
                      </p>
                    )}
                    {data.news_sentiment_layer.pipeline_note && (
                      <p className="text-sm text-td-muted mb-2 leading-snug">{data.news_sentiment_layer.pipeline_note}</p>
                    )}
                    {(data.news_sentiment_layer.fmp_key_configured != null ||
                      data.news_sentiment_layer.alpha_vantage_key_configured != null) && (
                      <p className="text-sm text-td-muted mb-2 font-mono">
                        Keys loaded on server: FMP{" "}
                        {data.news_sentiment_layer.fmp_key_configured ? "yes" : "no"} · Alpha Vantage{" "}
                        {data.news_sentiment_layer.alpha_vantage_key_configured ? "yes" : "no"}
                      </p>
                    )}
                    {data.news_sentiment_layer.fmp_request_error && (
                      <p className="text-sm text-td-warn/85 mb-2 leading-snug font-mono">
                        FMP news: {data.news_sentiment_layer.fmp_request_error}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-td-muted mb-2 font-mono">
                      {data.news_sentiment_layer.score_0_1 != null && (
                        <span>
                          Layer score:{" "}
                          <span className="text-td-text">{(data.news_sentiment_layer.score_0_1 * 100).toFixed(0)}%</span>
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
                        <span className="text-td-warn/90">Layer omitted (redistributed)</span>
                      )}
                    </div>
                    {data.news_sentiment_layer.message && (
                      <p className="text-sm text-td-warn/80 mb-2">{data.news_sentiment_layer.message}</p>
                    )}
                    {data.news_sentiment_layer.summary_label && (
                      <p className="text-xs text-td-muted mb-2 leading-snug">{data.news_sentiment_layer.summary_label}</p>
                    )}
                    {(data.news_sentiment_layer.catalyst_cards ?? []).length > 0 && (
                      <ul className="space-y-1.5 text-xs text-td-text mb-2">
                        {(data.news_sentiment_layer.catalyst_cards ?? []).map((c) => (
                          <li key={c.event_type || c.name} className="leading-snug">
                            <span className="uppercase text-[10px] text-td-muted mr-1">{c.direction}</span>
                            {c.name}: {c.mechanism}
                          </li>
                        ))}
                      </ul>
                    )}
                    {(data.news_sentiment_layer.headlines?.length ?? 0) > 0 && (
                      <ul className="space-y-1.5 text-xs text-td-text border-t border-td-line/40 pt-2">
                        {(data.news_sentiment_layer.headlines ?? []).map((h, i) => (
                          <li key={i} className="leading-snug pl-2 border-l-2 border-td-line/60">
                            {h.url ? (
                              <a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:text-td-info">
                                {h.title}
                              </a>
                            ) : (
                              h.title
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}

            {!showTables && (
              <div className="rounded-lg border border-td-line/50 bg-td-surface2/60 px-3 py-2 text-xs text-td-muted leading-relaxed">
                <p>
                  <strong className="text-td-text">Simple mode</strong> shows the TL;DR, scenario mix, and market regime above.
                  Switch to <strong className="text-td-text">Advanced</strong> for full buy/sell tables, R:R context, tranche rationale, and structured exit categories.
                </p>
                {data.action_glossary && Object.keys(data.action_glossary).length > 0 && (
                  <details className="mt-2 border-t border-td-line/40 pt-2">
                    <summary className="cursor-pointer text-td-text text-sm">Action phrases (glossary)</summary>
                    <ul className="mt-1.5 space-y-1 text-xs list-disc list-inside text-td-muted">
                      {Object.entries(data.action_glossary).map(([k, v]) => (
                        <li key={k}>
                          <span className="text-td-muted">{k}:</span> {v}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}

            {/* Buy Roadmap table */}
            {showTables && (tab === "buy" || tab === "full") && (
              <div>
                <h4 className="flex items-center gap-2 text-sm font-semibold text-td-accent mb-2">
                  <TrendingUp className="h-4 w-4" /> Buy roadmap
                </h4>
                <p className="text-xs text-td-muted mb-2 md:hidden">
                  Timeline cards below — full table on desktop.
                </p>
                <div className="md:hidden space-y-3">
                  {buyRowsWithZoneHints.map(({ row, sameBandAsPrior }) => (
                    <BuyRoadmapMobileCard
                      key={row.timeline_key}
                      row={row}
                      sameBandAsPrior={sameBandAsPrior}
                      activeTimelineKey={activeTimelineKey}
                      youAreHereKey={data.you_are_here?.timeline_key}
                      withinZone={data.you_are_here?.within_zone}
                    />
                  ))}
                </div>
                <div className="hidden md:block overflow-x-auto -mx-1 px-1 pb-1 overscroll-x-contain touch-pan-x">
                  <table className="min-w-[980px] w-full text-sm border-collapse table-fixed">
                    <colgroup>
                      <col className="w-[100px]" />
                      <col className="w-[140px]" />
                      <col className="w-[130px]" />
                      <col className="w-[360px]" />
                      <col className="w-[110px]" />
                      <col className="w-[72px]" />
                    </colgroup>
                    <thead>
                      <tr className="text-td-muted border-b border-td-line">
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
                      {buyRowsWithZoneHints.map(({ row, sameBandAsPrior }) => {
                        const cue = buyStageCue(row.when_to_act);
                        const conv = formatHorizonRoleDisplay(row.conviction);
                        const hl = buyRowTimelineHighlight(row, activeTimelineKey);
                        return (
                        <tr
                          key={row.timeline_key}
                          className={clsx(
                            "border-b border-td-line/50",
                            cue.rowBg,
                            hl && "ring-1 ring-td-warn/30"
                          )}
                        >
                          <td className="py-2 pr-2 text-td-text">
                            {row.label}
                            {data.you_are_here?.timeline_key === row.timeline_key && data.you_are_here?.within_zone && (
                              <span className="ml-1 inline-block text-[9px] font-semibold uppercase tracking-wide text-td-warn bg-td-warn/15 px-1 py-0.5 rounded">
                                You are here
                              </span>
                            )}
                          </td>
                          <td className="py-2 pr-2 text-td-text">
                            <span className="mr-1" aria-hidden>{cue.emoji}</span>
                            {row.when_to_act}
                          </td>
                          <td className="py-2 pr-2 font-mono text-td-text align-top">
                            {row.price_zone_lines && row.price_zone_lines.length > 0 ? (
                              <div className="space-y-1 text-xs leading-snug">
                                {row.price_zone_lines.map((z, zi) => (
                                  <div key={zi}>
                                    <span className="text-td-muted font-td-sans">{z.label}: </span>
                                    {formatZone(z.lo, z.hi)}
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <div>
                                {formatZone(row.price_zone_low, row.price_zone_high)}
                                {sameBandAsPrior && (
                                  <span className="block text-[9px] text-td-muted font-td-sans mt-0.5 leading-tight">
                                    Same accumulation band — conviction / horizon role steps up over time.
                                  </span>
                                )}
                              </div>
                            )}
                          </td>
                          <td className="py-2 pr-2 align-top break-words min-w-[200px] max-w-[360px]">
                            {row.priority_note && (
                              <span className="block text-td-warn/90 text-xs font-medium mb-1.5">{row.priority_note}</span>
                            )}
                            <ConditionText text={row.condition} />
                            {row.risk_reward_context?.risk_reward != null && (
                              <p className={clsx(TD.footnote, "mt-2")}>
                                R:R ~{row.risk_reward_context.risk_reward}× · upside ~{row.risk_reward_context.upside_to_model_fv_pct ?? "—"}% / downside ~{row.risk_reward_context.downside_to_ref_stop_pct ?? "—"}%
                              </p>
                            )}
                            {row.allocation_note && (
                              <p className={clsx(TD.footnote, "mt-1")}>{row.allocation_note}</p>
                            )}
                          </td>
                          <td className={clsx("py-2 pr-2 align-top", conv ? horizonRoleColor(row.conviction) : "")}>
                            {conv ? conv : null}
                          </td>
                          <td className="py-2 text-right text-td-text align-top">{row.position_pct}%</td>
                        </tr>
                      ); })}
                    </tbody>
                  </table>
                </div>
                <p className={clsx(TD.footnote, "mt-3 max-w-3xl")}>
                  <span className="text-td-muted font-medium">How to read this: </span>
                  Horizon role is the scenario for that row. Tranche % is your planned slice for that leg—not a sort order.
                </p>
              </div>
            )}

            {/* Sell Roadmap table */}
            {showTables && (tab === "sell" || tab === "full") && (
              <div>
                <h4 className="flex items-center gap-2 text-sm font-semibold text-td-warn mb-2">
                  <TrendingDown className="h-4 w-4" /> Sell roadmap
                </h4>
                <div className="md:hidden space-y-3">
                  {sellFiltered.map((row) => (
                    <SellRoadmapMobileCard key={row.timeline_key} row={row} activeTimelineKey={activeTimelineKey} />
                  ))}
                </div>
                <div className="hidden md:block overflow-x-auto -mx-1 px-1 pb-1 overscroll-x-contain touch-pan-x">
                  <table className="min-w-[880px] w-full text-sm border-collapse">
                    <thead>
                      <tr className="text-td-muted border-b border-td-line">
                        <th className="text-left py-2 pr-2">Timeline</th>
                        <th className="text-left py-2 pr-2">When to sell</th>
                        <th className="text-left py-2 pr-2">Price zone</th>
                        <th className="text-left py-2 pr-2">Condition</th>
                        <th className="text-left py-2 pr-2">Exit type</th>
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
                            "border-b border-td-line/50",
                            cue.rowBg,
                            activeTimelineKey === row.timeline_key && "ring-1 ring-td-warn/30"
                          )}
                        >
                          <td className="py-2 pr-2 text-td-text">{row.label}</td>
                          <td className="py-2 pr-2 text-td-text">
                            <span className="mr-1" aria-hidden>{cue.emoji}</span>
                            {row.when_to_sell}
                          </td>
                          <td className="py-2 pr-2 font-mono text-td-text">
                            {formatZone(row.price_zone_low, row.price_zone_high)}
                          </td>
                          <td className="py-2 pr-2 text-td-muted min-w-[200px] max-w-[320px] text-sm leading-snug break-words" title={row.condition}>
                            {row.condition}
                          </td>
                          <td className="py-2 pr-2 text-td-muted font-mono text-xs">
                            {row.exit_category?.replace(/_/g, " ") ?? "—"}
                          </td>
                          <td className="py-2 pr-2 text-td-warn/90">{row.action}</td>
                          <td className="py-2 text-td-muted">{row.reason}</td>
                        </tr>
                      ); })}
                    </tbody>
                  </table>
                </div>
                <p className="text-xs text-td-muted mt-2 leading-snug max-w-3xl">
                  <strong className="text-td-muted">Overlapping trim windows:</strong> Short-term and longer trims can share
                  price ranges when targets align. Earlier rows are the first tranche to consider; later rows size what is
                  left — not a separate trigger that only fires if you skipped an earlier leg.
                </p>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
