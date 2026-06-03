"use client";

import { useState, useMemo, useEffect, useCallback, Fragment } from "react";
import type { Signal } from "@/app/page";
import { clsx } from "clsx";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  CompactSignalActionStrip,
  deriveListActionStatus,
  TradingGateMiniPills,
  type SignalListContext,
} from "./retailActionUX";
import {
  groupSignalsByAction,
  loadSignalsViewMode,
  saveSignalsViewMode,
  signalHasEarningsInsight,
  signalHasLiquidity,
  type SignalsViewMode,
} from "@/lib/signalsTableView";
import { gatesForSignal, tradingGateSummaryLabel } from "@/lib/signalsTableViewGates";
import { TickerFilterBar } from "./TickerFilterBar";
import {
  filterTickersBySource,
  loadTickerSourceFilter,
  positionStatusForTicker,
  saveTickerSourceFilter,
  toTickerSet,
  type TickerSourceFilter,
} from "@/lib/tickerSourceFilter";
import { PossessionBadge } from "./PossessionBadge";
import {
  loadSignalsPreset,
  matchesSignalPreset,
  saveSignalsPreset,
  type SignalsPresetId,
} from "@/lib/signalPresets";
import { defaultPresetForLens, type TradingLens } from "@/lib/tradingLens";
import { SwipeableSignalCard, type SwipeRevealAction } from "./SwipeableSignalCard";

export type { SignalsPresetId } from "@/lib/signalPresets";

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

function CatalystBadge({ catalyst }: { catalyst?: Signal["catalyst"] }) {
  if (!catalyst?.active) return null;
  const label = (catalyst.top_event_type || "CATALYST").replace(/_/g, " ");
  const tip = catalyst.headline_summary || catalyst.override_note || "High-impact news catalyst (48h)";
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-amber-500/20 text-amber-200 ring-1 ring-amber-500/40"
      title={tip}
    >
      {label}
    </span>
  );
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

const SIGNALS_SORT_STORAGE_KEY = "thrive-signals-sort";
const SIGNALS_MODEL_DETAIL_KEY = "thrive-signals-model-detail";

function LiquidityCell({ signal: r }: { signal: Signal }) {
  const days = r.liquidity_days_to_exit;
  const score = r.liquidity_score;
  if (days == null && score == null) {
    return <span className="text-slate-600 text-xs">—</span>;
  }
  const color =
    score != null && score >= 4
      ? "text-amber-300"
      : score != null && score <= 2
        ? "text-emerald-300"
        : "text-slate-300";
  return (
    <div className="text-xs space-y-0.5" title={r.liquidity_flag ?? "Days to exit at 20% of average daily volume"}>
      <span className={clsx("font-medium tabular-nums", color)}>
        {days != null ? `${days.toFixed(1)}d` : "—"}
      </span>
      {score != null && <span className="text-[10px] text-slate-500 block">LIS {score}/5</span>}
    </div>
  );
}

export type SignalsSortKey = "ticker" | "score" | "regime" | "rsi";

const POSITIONING_TOOLTIPS: Record<string, string> = {
  long: "Crowded long (CFTC): specs very long, reversal risk.",
  short: "Crowded short (CFTC): specs very short, reversal risk.",
};

function listStatusTone(light: "green" | "yellow" | "red" | "neutral"): string {
  if (light === "green") return "text-emerald-300";
  if (light === "red") return "text-red-300";
  if (light === "neutral") return "text-slate-300";
  return "text-amber-200";
}

function SignalsQuickTickerRow({
  r,
  gateContext,
  tickerActions,
  onTickerClick,
  expanded,
  onToggleExpand,
  muted,
  showEarningsCol,
  portfolioSet,
  watchlistSet,
}: {
  r: Signal;
  gateContext: SignalListContext;
  tickerActions?: Record<string, { action: string; one_liner: string }>;
  onTickerClick?: (ticker: string) => void;
  expanded: boolean;
  onToggleExpand: (ticker: string, e: React.MouseEvent) => void;
  muted?: boolean;
  showEarningsCol: boolean;
  portfolioSet: Set<string>;
  watchlistSet: Set<string>;
}) {
  const gates = gatesForSignal(r, gateContext);
  const status = deriveListActionStatus(r);
  const colSpan = 3 + (showEarningsCol ? 1 : 0);

  return (
    <>
      <tr
        className={clsx(
          "group border-t border-slate-700/50 hover:bg-slate-800/40 cursor-pointer",
          r.story_change && "bg-amber-500/5",
          muted && "opacity-80"
        )}
        onClick={() => onTickerClick?.(r.ticker)}
      >
        <td
          className={clsx(
            "sticky left-0 z-[10] min-w-[4.5rem] w-24 px-3 py-1.5 border-r border-slate-700/70",
            r.story_change ? "bg-amber-500/5" : "bg-slate-900 group-hover:bg-slate-800/30"
          )}
        >
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={(e) => onToggleExpand(r.ticker, e)}
              className="p-0.5 text-slate-500 hover:text-slate-200"
              aria-label={expanded ? "Collapse" : "Expand gates"}
            >
              {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onTickerClick?.(r.ticker);
              }}
              className="font-mono font-medium text-emerald-400 hover:underline text-sm"
            >
              {r.ticker}
            </button>
            <PossessionBadge
              status={positionStatusForTicker(r.ticker, portfolioSet, watchlistSet)}
            />
            <CatalystBadge catalyst={r.catalyst} />
          </div>
        </td>
        <td
          className={clsx(
            "sticky left-24 z-[10] min-w-[5rem] w-20 px-3 py-1.5 border-r border-slate-700/70 text-slate-300 tabular-nums text-sm",
            r.story_change ? "bg-amber-500/5" : "bg-slate-900 group-hover:bg-slate-800/30"
          )}
        >
          {r.close != null ? `$${r.close.toFixed(2)}` : "—"}
        </td>
        <td className="px-3 py-1.5 align-middle">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className={clsx("text-xs font-bold uppercase tracking-wide", listStatusTone(status.light))}>
              {status.title}
            </span>
            <span className="text-[10px] font-mono text-slate-500">{tradingGateSummaryLabel(gates)}</span>
          </div>
        </td>
        {showEarningsCol && (
          <td className="px-3 py-1.5 align-middle text-xs">
            <EarningsCell signal={r} />
          </td>
        )}
      </tr>
      {expanded && (
        <tr className="border-t border-slate-800/80 bg-slate-950/50">
          <td colSpan={colSpan} className="px-3 py-2">
            <CompactSignalActionStrip
              signal={r}
              listContext={gateContext}
              oneLiner={tickerActions?.[r.ticker]?.one_liner}
              variant="card"
              onOpenDetail={() => onTickerClick?.(r.ticker)}
            />
          </td>
        </tr>
      )}
    </>
  );
}

function SignalsMobileQuickCard({
  r,
  gateContext,
  tickerActions,
  onTickerClick,
  expanded,
  onToggleExpand,
  muted,
  showEarningsCol,
  activeSwipeKey,
  onSwipeKeyChange,
}: {
  r: Signal;
  gateContext: SignalListContext;
  tickerActions?: Record<string, { action: string; one_liner: string }>;
  onTickerClick?: (ticker: string) => void;
  expanded: boolean;
  onToggleExpand: (ticker: string, e?: React.MouseEvent) => void;
  muted?: boolean;
  showEarningsCol: boolean;
  activeSwipeKey?: string | null;
  onSwipeKeyChange?: (key: string | null) => void;
}) {
  const gates = gatesForSignal(r, gateContext);
  const status = deriveListActionStatus(r);

  const swipeActions: SwipeRevealAction[] = [
    {
      id: "gates",
      label: expanded ? "Hide" : "Gates",
      tone: "sky",
      onClick: () => onToggleExpand(r.ticker),
    },
    {
      id: "open",
      label: "Open",
      tone: "emerald",
      onClick: () => onTickerClick?.(r.ticker),
    },
  ];

  return (
    <SwipeableSignalCard
      cardKey={r.ticker}
      actions={swipeActions}
      activeSwipeKey={activeSwipeKey}
      onSwipeKeyChange={onSwipeKeyChange}
      className={clsx(
        r.story_change && "bg-amber-500/5",
        muted && "bg-slate-900/40",
      )}
    >
      <div className="px-4 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          <button
            type="button"
            onClick={(e) => onToggleExpand(r.ticker, e)}
            className="p-1 text-slate-500 hover:text-slate-200 touch-manipulation shrink-0"
            aria-label={expanded ? "Collapse gates" : "Expand gates"}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
          <button
            type="button"
            onClick={() => onTickerClick?.(r.ticker)}
            className="font-mono font-semibold text-emerald-400 text-base hover:underline touch-manipulation truncate"
          >
            {r.ticker}
          </button>
          <CatalystBadge catalyst={r.catalyst} />
        </div>
        <span className="text-slate-300 text-sm tabular-nums shrink-0">
          {r.close != null ? `$${r.close.toFixed(2)}` : "—"}
        </span>
      </div>
      <div className="mt-1 pl-8 flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span className={clsx("text-xs font-bold uppercase tracking-wide", listStatusTone(status.light))}>
          {status.title}
        </span>
        <span className="text-[10px] font-mono text-slate-500">{tradingGateSummaryLabel(gates)}</span>
      </div>
      {r.story_change && (
        <p className="mt-1 pl-8 text-amber-400/90 text-xs line-clamp-2 leading-snug">{r.story_change}</p>
      )}
      {showEarningsCol && (
        <div className="mt-1 pl-8">
          <EarningsCell signal={r} />
        </div>
      )}
      {expanded && (
        <div className="mt-2 pl-8">
          <CompactSignalActionStrip
            signal={r}
            listContext={gateContext}
            oneLiner={tickerActions?.[r.ticker]?.one_liner}
            variant="card"
            onOpenDetail={() => onTickerClick?.(r.ticker)}
          />
        </div>
      )}
      </div>
    </SwipeableSignalCard>
  );
}

function SignalsMobileFullCard({
  r,
  gateContext,
  tickerActions,
  onTickerClick,
  openMobileTicker,
  setOpenMobileTicker,
  h,
  showEarningsCol,
  showModelDetail,
  activeSwipeKey,
  onSwipeKeyChange,
}: {
  r: Signal;
  gateContext: SignalListContext;
  tickerActions?: Record<string, { action: string; one_liner: string }>;
  onTickerClick?: (ticker: string) => void;
  openMobileTicker: string | null;
  setOpenMobileTicker: React.Dispatch<React.SetStateAction<string | null>>;
  h: { short_term: string; medium_term: string; long_term: string };
  showEarningsCol: boolean;
  showModelDetail: boolean;
  activeSwipeKey?: string | null;
  onSwipeKeyChange?: (key: string | null) => void;
}) {
  const levelsOpen = openMobileTicker === r.ticker;
  const swipeActions: SwipeRevealAction[] = [
    {
      id: "levels",
      label: levelsOpen ? "Hide" : "Levels",
      tone: "sky",
      onClick: () => setOpenMobileTicker((t) => (t === r.ticker ? null : r.ticker)),
    },
    {
      id: "open",
      label: "Open",
      tone: "emerald",
      onClick: () => onTickerClick?.(r.ticker),
    },
  ];

  return (
    <SwipeableSignalCard
      cardKey={r.ticker}
      actions={swipeActions}
      activeSwipeKey={activeSwipeKey}
      onSwipeKeyChange={onSwipeKeyChange}
      className={clsx(r.story_change && "bg-amber-500/5")}
    >
      <div className="px-4 py-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <button
          type="button"
          onClick={() => onTickerClick?.(r.ticker)}
          className="font-mono font-semibold text-emerald-400 text-base hover:underline text-left touch-manipulation"
        >
          {r.ticker}
        </button>
        <CatalystBadge catalyst={r.catalyst} />
        <div className="flex flex-col items-end gap-0.5">
          <div className="flex items-center gap-2">
            {r.plan_action ? (
              <PlanActionBadge action={r.plan_action} conf={r.plan_confidence} />
            ) : tickerActions?.[r.ticker] ? (
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
      {showModelDetail && (
        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
          <span
            className={clsx(
              "font-medium text-sm",
              (r.confluence_score ?? r.composite_buy ?? 0) >= 65 && "text-emerald-400",
              (r.confluence_score ?? r.composite_buy ?? 0) <= 35 && "text-red-400",
              (r.confluence_score ?? r.composite_buy ?? 0) > 35 &&
                (r.confluence_score ?? r.composite_buy ?? 0) < 65 &&
                "text-slate-300"
            )}
          >
            {((r.confluence_score ?? r.composite_buy) != null
              ? (r.confluence_score ?? r.composite_buy)!.toFixed(0)
              : "-")}
            <span className="text-slate-600"> cf</span>
          </span>
          <MLProbPill prob={r.ml_short_prob} />
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
          <SignalBadge signal={r.signal} />
          {r.rsi != null && <span className="text-slate-500 text-sm">RSI {r.rsi.toFixed(0)}</span>}
        </div>
      )}
      {r.earnings_note && <p className="text-amber-400 text-xs mt-1">{r.earnings_note}</p>}
      {showEarningsCol && (
        <div className="mt-1">
          <EarningsCell signal={r} />
        </div>
      )}
      {r.story_change && <p className="text-amber-400/90 text-xs mt-0.5">{r.story_change}</p>}
      <div className="mt-2">
        <CompactSignalActionStrip
          signal={r}
          listContext={gateContext}
          oneLiner={tickerActions?.[r.ticker]?.one_liner}
          variant="card"
          onOpenDetail={() => onTickerClick?.(r.ticker)}
        />
      </div>
      <button
        type="button"
        className="mt-2 w-full flex items-center justify-between gap-2 rounded-lg border border-slate-700/80 bg-slate-800/40 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800/70 touch-manipulation"
        aria-expanded={openMobileTicker === r.ticker}
        onClick={() => setOpenMobileTicker((t) => (t === r.ticker ? null : r.ticker))}
      >
        <span>
          Levels &amp; horizons ({h.short_term} / {h.medium_term} / {h.long_term})
        </span>
        <span className="text-slate-500 tabular-nums">{openMobileTicker === r.ticker ? "−" : "+"}</span>
      </button>
      {openMobileTicker === r.ticker && (
        <div className="mt-2 space-y-1.5 rounded-lg border border-slate-700/60 bg-slate-900/50 px-3 py-2 text-[11px] text-slate-300 leading-snug">
          <div className="flex gap-1.5">
            <span className="text-slate-600 shrink-0 w-7">ST</span>
            <span className="min-w-0">{r.short_suggestion || "—"}</span>
          </div>
          <div className="flex gap-1.5">
            <span className="text-slate-600 shrink-0 w-7">MT</span>
            <span className="min-w-0">{r.medium_suggestion || "—"}</span>
          </div>
          <div className="flex gap-1.5">
            <span className="text-slate-600 shrink-0 w-7">LT</span>
            <span className="min-w-0">{r.long_suggestion || "—"}</span>
          </div>
          {(r.st_band || r.mt_band || r.lt_band) && (
            <div
              className="text-[10px] text-slate-500 pt-1 border-t border-slate-700/60 space-y-0.5"
              title="ST: stop–target. MT: vol band. LT: fair+consensus"
            >
              {r.st_band && (
                <span className="block font-mono">
                  ${r.st_band.low.toFixed(1)}–${r.st_band.high.toFixed(1)} ST band
                </span>
              )}
              {r.mt_band && (
                <span className="block font-mono">
                  ${r.mt_band.low.toFixed(1)}–${r.mt_band.high.toFixed(1)} MT band
                </span>
              )}
              {r.lt_band && (
                <span className="block font-mono">
                  ${r.lt_band.low.toFixed(1)}–${r.lt_band.high.toFixed(1)} LT
                  {r.lt_band_low_confidence && " (low conf)"}
                </span>
              )}
            </div>
          )}
        </div>
      )}
      </div>
    </SwipeableSignalCard>
  );
}

export function SignalsTable({
  signals,
  horizons,
  onTickerClick,
  riskSizing,
  cotByTicker,
  tickerActions,
  listContext,
  portfolioTickers,
  watchlistTickers,
  tradingLens,
}: {
  signals: Signal[];
  horizons?: { short_term: string; medium_term: string; long_term: string } | null;
  onTickerClick?: (ticker: string) => void;
  riskSizing?: { risk_pct: number; stop_pct: number };
  cotByTicker?: Record<string, string>;
  tickerActions?: Record<string, { action: string; one_liner: string }>;
  /** Shared macro/HMM context for per-row trading gates on the list view. */
  listContext?: SignalListContext;
  portfolioTickers?: string[];
  watchlistTickers?: string[];
  tradingLens?: TradingLens;
}) {
  const gateContext: SignalListContext = listContext ?? {};
  const h = horizons || DEFAULT_HORIZONS;
  const [sortBy, setSortBy] = useState<SignalsSortKey>("score");
  const [scoreRsiDir, setScoreRsiDir] = useState<"asc" | "desc">("desc");
  const [openMobileTicker, setOpenMobileTicker] = useState<string | null>(null);
  const [showModelDetail, setShowModelDetail] = useState(false);
  const [viewMode, setViewMode] = useState<SignalsViewMode>("quick");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => new Set());
  const [expandedTickers, setExpandedTickers] = useState<Set<string>>(() => new Set());
  const [activeSwipeKey, setActiveSwipeKey] = useState<string | null>(null);
  const [preset, setPreset] = useState<SignalsPresetId>("all");
  const [sourceFilter, setSourceFilter] = useState<TickerSourceFilter>("all");

  useEffect(() => {
    setSourceFilter(loadTickerSourceFilter());
  }, []);

  useEffect(() => {
    if (tradingLens) {
      setPreset(defaultPresetForLens(tradingLens));
    } else {
      setPreset(loadSignalsPreset());
    }
  }, [tradingLens]);

  const applyPreset = (id: SignalsPresetId) => {
    setPreset(id);
    saveSignalsPreset(id);
  };

  const applySourceFilter = (id: TickerSourceFilter) => {
    setSourceFilter(id);
    saveTickerSourceFilter(id);
  };

  useEffect(() => {
    setViewMode(loadSignalsViewMode());
    try {
      const raw = typeof window !== "undefined" ? localStorage.getItem(SIGNALS_MODEL_DETAIL_KEY) : null;
      if (raw === "1") setShowModelDetail(true);
    } catch {
      /* ignore */
    }
  }, []);

  const applyViewMode = (mode: SignalsViewMode) => {
    setViewMode(mode);
    saveSignalsViewMode(mode);
    if (mode === "quick") setShowModelDetail(false);
  };

  const toggleModelDetail = () => {
    setShowModelDetail((v) => {
      const next = !v;
      try {
        localStorage.setItem(SIGNALS_MODEL_DETAIL_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  useEffect(() => {
    try {
      const raw = typeof window !== "undefined" ? localStorage.getItem(SIGNALS_SORT_STORAGE_KEY) : null;
      if (raw === "ticker" || raw === "score" || raw === "regime" || raw === "rsi") setSortBy(raw);
    } catch {
      /* ignore */
    }
  }, []);

  const applySort = (key: SignalsSortKey) => {
    setSortBy((prev) => {
      if (prev === key && (key === "score" || key === "rsi")) {
        setScoreRsiDir((d) => (d === "desc" ? "asc" : "desc"));
        return prev;
      }
      if (prev !== key && (key === "score" || key === "rsi")) {
        setScoreRsiDir("desc");
      }
      if (prev !== key) {
        try {
          localStorage.setItem(SIGNALS_SORT_STORAGE_KEY, key);
        } catch {
          /* ignore */
        }
      }
      return key;
    });
  };

  const sortHint =
    "Sort: click column headers on desktop. Confluence / RSI: click again to flip high→low.";

  const portfolioSet = useMemo(() => toTickerSet(portfolioTickers), [portfolioTickers]);
  const watchlistSet = useMemo(() => toTickerSet(watchlistTickers), [watchlistTickers]);

  const filtered = useMemo(() => {
    const bySource = filterTickersBySource(
      signals.map((s) => s.ticker).filter(Boolean) as string[],
      sourceFilter,
      portfolioSet,
      watchlistSet,
    );
    const allowed = new Set(bySource.map((t) => t.toUpperCase()));
    return signals.filter(
      (s) => allowed.has(String(s.ticker).toUpperCase()) && matchesSignalPreset(s, preset),
    );
  }, [signals, preset, sourceFilter, portfolioTickers, watchlistTickers]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    const dir = scoreRsiDir === "desc" ? 1 : -1;
    arr.sort((a, b) => {
      if (sortBy === "ticker") return (a.ticker ?? "").localeCompare(b.ticker ?? "");
      if (sortBy === "score") {
        return dir * ((b.confluence_score ?? b.composite_buy ?? 0) - (a.confluence_score ?? a.composite_buy ?? 0));
      }
      if (sortBy === "regime") {
        const ord = { UP: 0, NEUTRAL: 1, DOWN: 2 };
        return (ord[a.regime as keyof typeof ord] ?? 1) - (ord[b.regime as keyof typeof ord] ?? 1);
      }
      if (sortBy === "rsi") return dir * ((b.rsi ?? 0) - (a.rsi ?? 0));
      return 0;
    });
    return arr;
  }, [filtered, sortBy, scoreRsiDir]);

  const showLiquidityCol = useMemo(() => sorted.some(signalHasLiquidity), [sorted]);
  const showEarningsCol = useMemo(() => sorted.some(signalHasEarningsInsight), [sorted]);
  const earningsDataGap = useMemo(
    () =>
      sorted.length >= 4 &&
      !showEarningsCol &&
      sorted.some((r) => (r.earnings_quality?.flags ?? []).some((f) => /unavailable/i.test(f))),
    [sorted, showEarningsCol]
  );

  const actionGroups = useMemo(
    () => (viewMode === "quick" ? groupSignalsByAction(sorted, gateContext, tickerActions) : null),
    [viewMode, sorted, gateContext, tickerActions]
  );

  useEffect(() => {
    if (viewMode !== "quick" || !actionGroups) return;
    const next = new Set<string>();
    for (const g of actionGroups) {
      if (g.rows.length > 1) next.add(g.key);
    }
    setCollapsedGroups(next);
    setExpandedTickers(new Set());
  }, [actionGroups, viewMode, preset, sourceFilter]);

  const toggleGroup = useCallback((key: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const toggleTickerExpand = useCallback((ticker: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setExpandedTickers((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }, []);

  const isQuick = viewMode === "quick";

  return (
    <div className="rounded-xl border border-slate-700 overflow-hidden">
      <div className="px-3 sm:px-4 py-2 bg-slate-800 border-b border-slate-700 space-y-2">
        <TickerFilterBar
          source={sourceFilter}
          onSourceChange={applySourceFilter}
          preset={preset}
          onPresetChange={applyPreset}
          tickers={signals.map((s) => s.ticker).filter(Boolean) as string[]}
          portfolioTickers={portfolioTickers}
          watchlistTickers={watchlistTickers}
          shownCount={sorted.length}
          totalCount={signals.length}
          tradingLens={tradingLens}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="hidden lg:block text-[11px] text-slate-500 max-w-md truncate flex-1">
          {isQuick
            ? "Quick view — compact rows; click a ticker to expand gates. Identical actions are grouped."
            : showModelDetail
              ? sortHint
              : "Full detail — Now · Action + gate pills (official read)."}
        </p>
        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <div className="flex rounded border border-slate-600 overflow-hidden">
            <button
              type="button"
              onClick={() => applyViewMode("quick")}
              className={clsx(
                "text-xs px-2.5 py-1.5 sm:py-1 min-h-[44px] sm:min-h-0 touch-manipulation",
                isQuick ? "bg-emerald-600/70 text-white" : "bg-slate-900 text-slate-400 hover:bg-slate-800"
              )}
            >
              Quick view
            </button>
            <button
              type="button"
              onClick={() => applyViewMode("full")}
              className={clsx(
                "text-xs px-2.5 py-1.5 sm:py-1 min-h-[44px] sm:min-h-0 touch-manipulation",
                !isQuick ? "bg-emerald-600/70 text-white" : "bg-slate-900 text-slate-400 hover:bg-slate-800"
              )}
            >
              Full detail
            </button>
          </div>
          {!isQuick && (
          <button
            type="button"
            onClick={toggleModelDetail}
            className={clsx(
              "text-xs px-2.5 py-1.5 sm:py-1 rounded border min-h-[44px] sm:min-h-0 touch-manipulation",
              showModelDetail
                ? "border-violet-500/40 bg-violet-500/10 text-violet-200"
                : "border-slate-600 text-slate-400 hover:text-slate-200"
            )}
          >
            {showModelDetail ? "Retail view" : "Model detail"}
          </button>
          )}
          <span className="text-xs text-slate-400">Sort:</span>
          <select
            value={sortBy}
            onChange={(e) => applySort(e.target.value as SignalsSortKey)}
            className="text-sm sm:text-xs bg-slate-800 border border-slate-600 rounded px-2 py-2 sm:py-1 text-slate-300 min-h-[44px] sm:min-h-0 touch-manipulation"
            aria-label="Sort preset"
          >
          <option value="score">Confluence</option>
          <option value="ticker">Ticker</option>
          <option value="regime">Regime</option>
          <option value="rsi">RSI</option>
        </select>
        </div>
        </div>
        {earningsDataGap && (
          <p className="text-[11px] text-slate-500 border border-slate-600/60 rounded-md px-2.5 py-1.5 bg-slate-800/40">
            Earnings quality (EQ) is not available from the data source right now — column hidden to reduce noise.
          </p>
        )}
      </div>

      {/* Mobile: card list — swipe left for Open / Gates */}
      <p className="md:hidden text-[10px] text-slate-500 px-4 py-1.5 border-b border-slate-700/40 bg-slate-900/30">
        Swipe a card left for quick actions · tap chevron for gate detail
      </p>
      <div className="md:hidden divide-y divide-slate-700/50">
        {isQuick && actionGroups
          ? actionGroups.map((group) => {
              const collapsed = collapsedGroups.has(group.key);
              const multi = group.rows.length > 1;
              if (!multi) {
                const r = group.rows[0];
                return (
                  <SignalsMobileQuickCard
                    key={r.ticker}
                    r={r}
                    gateContext={gateContext}
                    tickerActions={tickerActions}
                    onTickerClick={onTickerClick}
                    expanded={expandedTickers.has(r.ticker)}
                    onToggleExpand={toggleTickerExpand}
                    showEarningsCol={showEarningsCol}
                    activeSwipeKey={activeSwipeKey}
                    onSwipeKeyChange={setActiveSwipeKey}
                  />
                );
              }
              return (
                <Fragment key={group.key}>
                  <button
                    type="button"
                    onClick={() => toggleGroup(group.key)}
                    className="w-full px-4 py-2.5 flex items-center gap-2 text-left bg-slate-800/50 hover:bg-slate-800/80 touch-manipulation"
                  >
                    {collapsed ? (
                      <ChevronRight className="h-4 w-4 text-slate-500 shrink-0" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-slate-500 shrink-0" />
                    )}
                    <span
                      className={clsx(
                        "text-xs font-bold uppercase tracking-wide",
                        listStatusTone(deriveListActionStatus(group.rows[0]).light)
                      )}
                    >
                      {group.title}
                    </span>
                    <span className="text-[10px] text-slate-500">({group.rows.length})</span>
                    {group.subtitle && (
                      <span className="text-xs text-slate-400 truncate flex-1 min-w-0">— {group.subtitle}</span>
                    )}
                  </button>
                  {!collapsed &&
                    group.rows.map((r) => (
                      <SignalsMobileQuickCard
                        key={r.ticker}
                        r={r}
                        gateContext={gateContext}
                        tickerActions={tickerActions}
                        onTickerClick={onTickerClick}
                        expanded={expandedTickers.has(r.ticker)}
                        onToggleExpand={toggleTickerExpand}
                        muted
                        showEarningsCol={showEarningsCol}
                        activeSwipeKey={activeSwipeKey}
                        onSwipeKeyChange={setActiveSwipeKey}
                      />
                    ))}
                </Fragment>
              );
            })
          : sorted.map((r) => (
              <SignalsMobileFullCard
                key={r.ticker}
                r={r}
                gateContext={gateContext}
                tickerActions={tickerActions}
                onTickerClick={onTickerClick}
                openMobileTicker={openMobileTicker}
                setOpenMobileTicker={setOpenMobileTicker}
                h={h}
                showEarningsCol={showEarningsCol}
                showModelDetail={showModelDetail}
                activeSwipeKey={activeSwipeKey}
                onSwipeKeyChange={setActiveSwipeKey}
              />
            ))}
      </div>

      {/* Desktop: table with sticky header + sticky first column */}
      <div className="hidden md:block overflow-x-auto [-webkit-overflow-scrolling:touch]">
        <table
          className={clsx(
            "w-full text-sm border-collapse",
            showModelDetail ? "min-w-[1380px]" : isQuick ? "min-w-[520px]" : "min-w-[720px]"
          )}
        >
          <thead>
            <tr className="text-left text-base text-slate-400">
              <th
                scope="col"
                className="sticky top-0 left-0 z-[30] min-w-[4.5rem] w-24 bg-slate-800 p-0 font-medium border-b border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]"
              >
                <button
                  type="button"
                  className="w-full text-left px-3 py-2.5 text-slate-400 hover:text-slate-100 hover:bg-slate-800/60 transition-colors"
                  onClick={() => applySort("ticker")}
                  aria-sort={sortBy === "ticker" ? "ascending" : "none"}
                >
                  Ticker
                </button>
              </th>
              <th className="sticky top-0 left-24 z-[25] min-w-[5rem] w-20 px-3 py-2.5 font-medium bg-slate-800 border-b border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)]">
                Close
              </th>
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 cursor-help text-left min-w-[12rem]"
                title={
                  isQuick
                    ? "Action label + gate pass count — expand row for full checklist"
                    : "Official read — behavioral action (gates in next column)"
                }
              >
                {isQuick ? "Action · Gates" : "Now · Action"}
              </th>
              {!isQuick && (
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 cursor-help text-left min-w-[8rem]"
                title="Valuation / regime / momentum / ML gate pills"
              >
                Gates
              </th>
              )}
              {!isQuick && showLiquidityCol && (
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 cursor-help text-left min-w-[4.5rem]"
                title="Days to exit at 20% of average daily volume (risk-sized shares or $5k probe)"
              >
                Liquidity
              </th>
              )}
              {showEarningsCol && (
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 cursor-help text-left"
                title="Earnings caution window, days to report, and FMP-based earnings quality (EQ) when available"
              >
                Earnings
              </th>
              )}
              {showModelDetail && (
                <>
              <th
                className="sticky top-0 z-[20] min-w-[7.5rem] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 text-left cursor-help"
                title={`Risk budget = ${riskSizing?.risk_pct ?? 1}% of portfolio if stop hits; notional position = budget ÷ (stop %).`}
              >
                Risk (size)
              </th>
              <th
                scope="col"
                className="sticky top-0 z-[20] px-0 py-0 font-medium bg-slate-800 border-b border-slate-700 whitespace-nowrap"
              >
                <button
                  type="button"
                  className="w-full text-left px-3 py-2.5 text-slate-400 hover:text-slate-100 hover:bg-slate-800/60 cursor-help transition-colors"
                  title="Confluence Score (0–100): how much do Trend + RSI + MACD + Regime agree on direction? ≥65 = aligned bullish · 35–65 = mixed · ≤35 = bearish alignment. NOT a probability — click any ticker to see the 7-layer ML Confidence breakdown."
                  onClick={() => applySort("score")}
                  aria-sort={sortBy === "score" ? (scoreRsiDir === "desc" ? "descending" : "ascending") : "none"}
                >
                  Confluence{sortBy === "score" ? (scoreRsiDir === "desc" ? " ↓" : " ↑") : ""}
                </button>
              </th>
              <th
                scope="col"
                className="sticky top-0 z-[20] p-0 font-medium bg-slate-800 border-b border-slate-700"
              >
                <button
                  type="button"
                  className="w-full text-left px-3 py-2.5 text-slate-400 hover:text-slate-100 hover:bg-slate-800/60 transition-colors"
                  onClick={() => applySort("rsi")}
                  aria-sort={sortBy === "rsi" ? (scoreRsiDir === "desc" ? "descending" : "ascending") : "none"}
                >
                  RSI{sortBy === "rsi" ? (scoreRsiDir === "desc" ? " ↓" : " ↑") : ""}
                </button>
              </th>
              <th
                scope="col"
                className="sticky top-0 z-[20] p-0 font-medium bg-slate-800 border-b border-slate-700"
              >
                <button
                  type="button"
                  className="w-full text-left px-3 py-2.5 text-slate-400 hover:text-slate-100 hover:bg-slate-800/60 transition-colors"
                  onClick={() => applySort("regime")}
                  aria-sort={sortBy === "regime" ? "ascending" : "none"}
                >
                  Regime
                </button>
              </th>
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 cursor-help text-left min-w-[7rem]"
                title="7-layer confidence action — same model as the Roadmaps tab (supporting detail, not the official Now read)."
              >
                Model plan
              </th>
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 cursor-help whitespace-nowrap"
                title="Confluence + ML short-term tier (supporting detail). Can differ from Now · Action when gates block."
              >
                Confluence tier
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700">
                Positioning
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700">
                Buy / Sell / Support
              </th>
              <th
                className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700 min-w-[11rem]"
                title="Horizon cues (ST/MT/LT)"
              >
                Horizons ST / MT / LT
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700">
                Vol / DD
              </th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800 border-b border-slate-700">
                Notes
              </th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {isQuick && actionGroups
              ? actionGroups.map((group) => {
                  const collapsed = collapsedGroups.has(group.key);
                  const multi = group.rows.length > 1;
                  if (!multi) {
                    const r = group.rows[0];
                    return (
                      <SignalsQuickTickerRow
                        key={r.ticker}
                        r={r}
                        gateContext={gateContext}
                        tickerActions={tickerActions}
                        onTickerClick={onTickerClick}
                        expanded={expandedTickers.has(r.ticker)}
                        onToggleExpand={toggleTickerExpand}
                        showEarningsCol={showEarningsCol}
                        portfolioSet={portfolioSet}
                        watchlistSet={watchlistSet}
                      />
                    );
                  }
                  return (
                    <Fragment key={group.key}>
                      <tr className="border-t border-slate-700/60 bg-slate-800/40">
                        <td colSpan={3 + (showEarningsCol ? 1 : 0)} className="px-3 py-2">
                          <button
                            type="button"
                            onClick={() => toggleGroup(group.key)}
                            className="w-full flex items-center gap-2 text-left hover:bg-slate-800/50 rounded-md px-1 py-0.5 touch-manipulation"
                          >
                            {collapsed ? (
                              <ChevronRight className="h-4 w-4 text-slate-500 shrink-0" />
                            ) : (
                              <ChevronDown className="h-4 w-4 text-slate-500 shrink-0" />
                            )}
                            <span className={clsx("text-xs font-bold uppercase tracking-wide", listStatusTone(deriveListActionStatus(group.rows[0]).light))}>
                              {group.title}
                            </span>
                            <span className="text-[10px] text-slate-500 font-mono">
                              ({group.rows.length} tickers)
                            </span>
                            {group.subtitle && (
                              <span className="text-xs text-slate-400 truncate flex-1 min-w-0">
                                — {group.subtitle}
                              </span>
                            )}
                          </button>
                        </td>
                      </tr>
                      {!collapsed &&
                        group.rows.map((r) => (
                          <SignalsQuickTickerRow
                            key={r.ticker}
                            r={r}
                            gateContext={gateContext}
                            tickerActions={tickerActions}
                            onTickerClick={onTickerClick}
                            expanded={expandedTickers.has(r.ticker)}
                            onToggleExpand={toggleTickerExpand}
                            muted
                            showEarningsCol={showEarningsCol}
                            portfolioSet={portfolioSet}
                            watchlistSet={watchlistSet}
                          />
                        ))}
                    </Fragment>
                  );
                })
              : null}
            {!isQuick &&
            sorted.map((r) => (
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
                    <PossessionBadge
                      status={positionStatusForTicker(r.ticker, portfolioSet, watchlistSet)}
                    />
                    <CatalystBadge catalyst={r.catalyst} />
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
                <td className="px-3 py-2.5 align-top">
                  <CompactSignalActionStrip
                    signal={r}
                    listContext={gateContext}
                    oneLiner={tickerActions?.[r.ticker]?.one_liner}
                    variant="column"
                    hideGatePills
                  />
                </td>
                <td className="px-3 py-2.5 align-top">
                  <TradingGateMiniPills gates={gatesForSignal(r, gateContext)} />
                </td>
                {showLiquidityCol && (
                <td className="px-3 py-2.5 align-top">
                  <LiquidityCell signal={r} />
                </td>
                )}
                {showEarningsCol && (
                <td className="px-3 py-2.5 align-top text-xs">
                  <EarningsCell signal={r} />
                </td>
                )}
                {showModelDetail && (
                  <>
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
                        What it means: Speculators' net position in the related commodity is extreme (≥45% of open interest). Often a contrarian signal; consider not adding size.
                      </span>
                    </span>
                  )}
                </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
