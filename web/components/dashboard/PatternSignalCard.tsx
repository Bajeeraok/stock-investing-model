"use client";

/**
 * PatternSignalCard.tsx
 * Surfaces the UnifiedSignalEngine output: regime + pattern + momentum confluence.
 *
 * Exports:
 *   PatternSignalCard   — single ticker confluence card
 *   PatternSignalList   — list of cards for the whole watchlist
 *
 * Backend data shape mirrors unified_signal_engine.py generate_signal() output.
 * Add to Dashboard.tsx ticker detail or watchlist tab:
 *   import { PatternSignalList } from "./dashboard/PatternSignalCard";
 *   <PatternSignalList signals={data.pattern_signals} />
 */

import { AlertTriangle, TrendingUp, TrendingDown, Minus,
         Activity, Zap, Eye, ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { clsx } from "clsx";

// ─────────────────────────────────────────────────────────────────────────────
//  TYPES  (mirrors unified_signal_engine.py + pattern_signals.py)
// ─────────────────────────────────────────────────────────────────────────────

export interface PatternDetails {
  price:                number;
  ticker:               string;
  total_score:          number;
  dist_from_52w_low_pct?: number;
  low_52w?:             number;
  rsi?:                 number;
  rsi_rising?:          boolean;
  volume_ratio?:        number | null;
  macd_hist?:           number | null;
  macd_hist_turning?:   boolean;
  bollinger_pct_b?:     number;
  bollinger_lower?:     number;
  double_bottom?:       boolean;
}

export interface UnifiedSignalData {
  ticker:                string;
  regime:                string;
  regime_multiplier:     number;
  pattern_score:         number;     // 0-100
  pattern_signals:       string[];
  pattern_details?:      PatternDetails;
  /** When pattern_score was 0, API may set composite_score as fallback and this label */
  pattern_score_source?: "confluence_fallback" | null;
  momentum_score:        number;     // 0-1
  momentum_signals:      string[];
  composite_score:       number;     // 0-100 from existing model
  confluence:            number;     // 0-1
  raw_action:            string;
  action:                string;
  confluence_kelly_mult: number;
  warning?:              string | null;
  narrative:             string[];
}

// ─────────────────────────────────────────────────────────────────────────────
//  Helpers
// ─────────────────────────────────────────────────────────────────────────────

function RegimeBadge({ regime }: { regime: string }) {
  const styles: Record<string, string> = {
    STRONG_BULL: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    BULL:        "bg-green-500/20  text-green-300  border-green-500/40",
    TRANSITION:  "bg-amber-500/20  text-amber-300  border-amber-500/40",
    NEUTRAL:     "bg-slate-500/20  text-slate-300  border-slate-500/40",
    BEAR:        "bg-orange-500/20 text-orange-300 border-orange-500/40",
    STRONG_BEAR: "bg-red-500/20    text-red-300    border-red-500/40",
  };
  const style = styles[regime] ?? styles.NEUTRAL;
  return (
    <span className={clsx("text-xs font-semibold px-2 py-0.5 rounded border", style)}>
      {regime.replace("_", " ")}
    </span>
  );
}

function ActionBadge({ action }: { action: string }) {
  const a = action.toUpperCase();
  const style =
    a.includes("STRONG BUY") ? "bg-emerald-500/20 text-emerald-200 border-emerald-400/50" :
    a.includes("BUY")        ? "bg-green-500/20  text-green-200  border-green-400/50"     :
    a.includes("TRIM") || a.includes("REDUCE")
                             ? "bg-amber-500/20  text-amber-200  border-amber-400/50"     :
    a.includes("SELL")       ? "bg-red-500/20    text-red-200    border-red-400/50"       :
    a.includes("SPECULATIVE") ? "bg-orange-500/20 text-orange-200 border-orange-400/50"  :
    a.includes("WATCH")      ? "bg-blue-500/20   text-blue-200   border-blue-400/50"     :
                               "bg-slate-500/20  text-slate-200  border-slate-400/50";
  const Icon =
    a.includes("BUY")   ? TrendingUp   :
    a.includes("SELL")  ? TrendingDown :
    a.includes("WATCH") ? Eye          : Minus;
  return (
    <span className={clsx("inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded border", style)}>
      <Icon size={11} />
      {action}
    </span>
  );
}

/** Arc-style gauge: 0-100 score displayed as a coloured arc. */
function BottomScoreMeter({ score }: { score: number }) {
  const pct  = Math.min(100, Math.max(0, score));
  const angle = (pct / 100) * 180; // 0° → 180°

  const colour =
    pct >= 70 ? "#10b981" :  // emerald
    pct >= 45 ? "#f59e0b" :  // amber
                "#6b7280";   // grey

  // SVG arc path helper
  const r = 36;
  const cx = 50, cy = 50;
  const startX = cx - r, startY = cy;
  const rad = (angle - 180) * (Math.PI / 180);
  const endX = cx + r * Math.cos(rad);
  const endY = cy + r * Math.sin(rad);
  const largeArc = angle > 180 ? 1 : 0;

  return (
    <div className="flex flex-col items-center gap-0.5">
      <svg viewBox="0 0 100 55" className="w-20 h-10">
        {/* Track */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none" stroke="#334155" strokeWidth="7" strokeLinecap="round"
        />
        {/* Fill */}
        {pct > 0 && (
          <path
            d={`M ${startX} ${startY} A ${r} ${r} 0 ${largeArc} 1 ${endX} ${endY}`}
            fill="none" stroke={colour} strokeWidth="7" strokeLinecap="round"
          />
        )}
        {/* Label */}
        <text x="50" y="50" textAnchor="middle" fontSize="14" fontWeight="700"
              fill={colour} dominantBaseline="auto">
          {pct.toFixed(0)}
        </text>
      </svg>
      <span className="text-[10px] text-slate-400">Pattern Score</span>
    </div>
  );
}

/** Confluence bar: 0-1 rendered as a horizontal progress bar. */
function ConfluenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const colour =
    pct >= 70 ? "bg-emerald-500" :
    pct >= 50 ? "bg-green-500"   :
    pct >= 30 ? "bg-amber-500"   : "bg-slate-500";
  return (
    <div className="flex items-center gap-2 w-full">
      <span className="text-[10px] text-slate-400 w-16 shrink-0">Confluence</span>
      <div className="flex-1 bg-slate-700 rounded-full h-1.5 overflow-hidden">
        <div className={clsx("h-full rounded-full transition-all", colour)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-semibold text-white w-8 text-right">{pct}%</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  Main card
// ─────────────────────────────────────────────────────────────────────────────

export function PatternSignalCard({ data }: { data: UnifiedSignalData }) {
  const [expanded, setExpanded] = useState(false);

  // Defensive defaults — backend may return null instead of []
  const patternSignals  = data.pattern_signals  ?? [];
  const momentumSignals = data.momentum_signals ?? [];
  const confluence      = data.confluence       ?? 0;
  const patternScore    = data.pattern_score    ?? 0;
  const kellyMult       = data.confluence_kelly_mult ?? 1;

  const isHighConviction = confluence >= 0.70 && patternScore >= 70;
  const hasWarning       = !!data.warning;

  const kellyBoost  = kellyMult > 1.05;
  const kellyReduce = kellyMult < 0.95;

  return (
    <div className={clsx(
      "rounded-xl border p-4 bg-slate-900 space-y-3 transition-colors",
      isHighConviction ? "border-emerald-500/50" : "border-slate-700/60"
    )}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-bold text-white text-base">{data.ticker}</span>
          <RegimeBadge regime={data.regime ?? "UNKNOWN"} />
          <ActionBadge action={data.action ?? "WATCH"} />
        </div>
        <BottomScoreMeter score={patternScore} />
      </div>

      {/* High-conviction alert */}
      {isHighConviction && (
        <div className="flex items-start gap-2 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">
          <Zap size={13} className="text-emerald-400 mt-0.5 shrink-0" />
          <span className="text-xs text-emerald-300">
            High-probability reversal setup — confirm with fundamentals before sizing
          </span>
        </div>
      )}

      {/* Warning / regime gate */}
      {hasWarning && (
        <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
          <AlertTriangle size={13} className="text-amber-400 mt-0.5 shrink-0" />
          <span className="text-xs text-amber-300">{data.warning}</span>
        </div>
      )}

      {/* Confluence bar */}
      <ConfluenceBar value={confluence} />

      {/* Scores row */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="bg-slate-800 rounded-lg p-2">
          <div className="text-[10px] text-slate-400 mb-0.5">Technical</div>
          <div className="text-sm font-bold text-white">{(data.composite_score ?? 0).toFixed(0)}</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-2">
          <div className="text-[10px] text-slate-400 mb-0.5" title={data.pattern_score_source === "confluence_fallback" ? "Confluence used when pattern unavailable" : undefined}>
            {data.pattern_score_source === "confluence_fallback" ? "Confluence" : "Pattern"}
          </div>
          <div className={clsx("text-sm font-bold",
            patternScore >= 70 ? "text-emerald-400" :
            patternScore >= 45 ? "text-amber-400"   : "text-slate-400"
          )}>{patternScore.toFixed(0)}</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-2">
          <div className="text-[10px] text-slate-400 mb-0.5">Kelly ×</div>
          <div className={clsx("text-sm font-bold",
            kellyBoost  ? "text-emerald-400" :
            kellyReduce ? "text-red-400"     : "text-slate-300"
          )}>{kellyMult.toFixed(2)}</div>
        </div>
      </div>

      {/* Pattern signals */}
      {patternSignals.length > 0 && (
        <div className="space-y-1">
          {patternSignals.map((s, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-slate-300">
              <TrendingUp size={11} className="text-emerald-400 mt-0.5 shrink-0" />
              {s}
            </div>
          ))}
        </div>
      )}

      {/* Momentum signals */}
      {momentumSignals.length > 0 && (
        <div className="space-y-1">
          {momentumSignals.map((s, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-slate-400">
              <Activity size={11} className="text-blue-400 mt-0.5 shrink-0" />
              {s}
            </div>
          ))}
        </div>
      )}

      {/* Expandable details */}
      {data.pattern_details && (
        <button
          onClick={() => setExpanded(v => !v)}
          className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-300 transition-colors"
        >
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          {expanded ? "Hide" : "Show"} raw indicator values
        </button>
      )}

      {expanded && data.pattern_details && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 bg-slate-800/60 rounded-lg p-3 text-[11px]">
          {data.pattern_details.dist_from_52w_low_pct != null && (
            <Row label="52w low dist" value={`${data.pattern_details.dist_from_52w_low_pct.toFixed(1)}%`} />
          )}
          {data.pattern_details.rsi != null && (
            <Row label="RSI(14)" value={`${data.pattern_details.rsi.toFixed(1)} ${data.pattern_details.rsi_rising ? "↑" : "↓"}`} />
          )}
          {data.pattern_details.volume_ratio != null && (
            <Row label="Vol ratio" value={`${data.pattern_details.volume_ratio.toFixed(2)}×`} />
          )}
          {data.pattern_details.bollinger_pct_b != null && (
            <Row label="Bollinger %B" value={data.pattern_details.bollinger_pct_b.toFixed(2)} />
          )}
          {data.pattern_details.bollinger_lower != null && (
            <Row label="BB lower" value={`$${data.pattern_details.bollinger_lower.toFixed(2)}`} />
          )}
          {data.pattern_details.double_bottom != null && (
            <Row label="Double bottom" value={data.pattern_details.double_bottom ? "Yes ✓" : "No"} />
          )}
          <Row label="Regime ×" value={data.regime_multiplier.toFixed(2)} />
          <Row label="Momentum" value={`${(data.momentum_score * 100).toFixed(0)}%`} />
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-300 font-mono text-right">{value}</span>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  List view for watchlist / dashboard tab
// ─────────────────────────────────────────────────────────────────────────────

export function PatternSignalList({
  signals,
  title = "Pattern & Confluence Signals",
}: {
  signals?: UnifiedSignalData[] | null;
  title?: string;
}) {
  if (!signals || signals.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700/60 bg-slate-900 p-6 text-center text-slate-500 text-sm">
        No pattern signals available
      </div>
    );
  }

  // Sort: high-conviction first, then by pattern_score desc
  const sorted = [...signals].sort((a, b) => {
    const aHigh = a.confluence >= 0.70 && a.pattern_score >= 70 ? 1 : 0;
    const bHigh = b.confluence >= 0.70 && b.pattern_score >= 70 ? 1 : 0;
    if (bHigh !== aHigh) return bHigh - aHigh;
    return b.pattern_score - a.pattern_score;
  });

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-slate-300">{title}</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {sorted.map(s => (
          <PatternSignalCard key={s.ticker} data={s} />
        ))}
      </div>
    </div>
  );
}
