"use client";

/**
 * ConfidenceBreakdown.tsx
 * Renders the 7-layer confidence breakdown for a single ticker.
 * Data shape mirrors confidence_engine.py ConfidenceEngine.compute() output.
 *
 * Exports:
 *   ConfidenceBreakdown    — full card for a single ticker
 *   ConfidenceBreakdownList — grid of cards for watchlist/dashboard tab
 *
 * Add to Dashboard.tsx:
 *   import { ConfidenceBreakdownList } from "./dashboard/ConfidenceBreakdown";
 *   <ConfidenceBreakdownList items={data.confidence_scores} />
 */

import { useState } from "react";
import {
  AlertTriangle, TrendingUp, TrendingDown, Shield,
  Activity, Eye, Info, ChevronDown, ChevronRight, Zap,
} from "lucide-react";
import { clsx } from "clsx";

// ─────────────────────────────────────────────────────────────────────────────
//  TYPES (mirrors confidence_engine.py output)
// ─────────────────────────────────────────────────────────────────────────────

export interface BreakdownLayer {
  score:     number | null;   // 0-1
  weight:    number;          // 0-1
  label:     string;
  available: boolean;
}

export interface WatchLevels {
  current_price:      number;
  invalidation_below: number;
  key_support_ma50:   number;
  key_support_ma200:  number;
  note:               string;
}

export interface ConfidenceData {
  ticker:          string;
  confidence:      number;          // 0-1
  action:          string;
  breakdown: {
    regime_hmm:        BreakdownLayer;
    pattern_technical: BreakdownLayer;
    lgbm_probability:  BreakdownLayer;
    options_sentiment: BreakdownLayer;
    insider_signal:    BreakdownLayer;
    fundamental_score: BreakdownLayer;
    nlp_sentiment:     BreakdownLayer;
  };
  disqualifiers:   string[];
  risk_factors:    string[];
  watch_levels?:   WatchLevels;
  market_regime:   string;
  n_layers_active: number;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Layer metadata (display names, icons, colour rules)
// ─────────────────────────────────────────────────────────────────────────────

const LAYER_META: Record<string, { name: string; icon: React.ElementType }> = {
  regime_hmm:        { name: "Regime (HMM)",      icon: Activity     },
  pattern_technical: { name: "Pattern Score",     icon: TrendingUp   },
  lgbm_probability:  { name: "ML Probability",    icon: Zap          },
  options_sentiment: { name: "Options Sentiment", icon: Shield       },
  insider_signal:    { name: "Insider Activity",  icon: Eye          },
  fundamental_score: { name: "Fundamentals",      icon: Info         },
  nlp_sentiment:     { name: "News Sentiment",    icon: Activity     },
};

// ─────────────────────────────────────────────────────────────────────────────
//  Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function ConfidenceGauge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const colour =
    pct >= 75 ? "#10b981" :
    pct >= 60 ? "#22c55e" :
    pct >= 45 ? "#f59e0b" :
    pct >= 30 ? "#f97316" : "#ef4444";

  // SVG half-ring gauge
  const r = 38, cx = 50, cy = 52;
  const angle  = (pct / 100) * 180;
  const rad    = (angle - 180) * (Math.PI / 180);
  const endX   = cx + r * Math.cos(rad);
  const endY   = cy + r * Math.sin(rad);
  const lArc   = angle > 180 ? 1 : 0;

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 100 58" className="w-28 h-14">
        <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
              fill="none" stroke="#1e293b" strokeWidth="9" strokeLinecap="round" />
        {pct > 0 && (
          <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 ${lArc} 1 ${endX} ${endY}`}
                fill="none" stroke={colour} strokeWidth="9" strokeLinecap="round" />
        )}
        <text x="50" y="49" textAnchor="middle" fontSize="17" fontWeight="800"
              fill={colour} dominantBaseline="auto">{pct}%</text>
      </svg>
      <span className="text-[10px] text-slate-400 -mt-1">Confidence</span>
    </div>
  );
}

function ActionBadge({ action }: { action: string }) {
  const a = action.toUpperCase();
  const cfg =
    a === "STRONG BUY" ? { bg: "bg-emerald-500/20", text: "text-emerald-200", border: "border-emerald-400/50", Icon: TrendingUp } :
    a === "BUY"        ? { bg: "bg-green-500/20",   text: "text-green-200",   border: "border-green-400/50",   Icon: TrendingUp } :
    a === "REDUCE"     ? { bg: "bg-amber-500/20",   text: "text-amber-200",   border: "border-amber-400/50",   Icon: TrendingDown } :
    a === "AVOID"      ? { bg: "bg-red-500/20",     text: "text-red-200",     border: "border-red-400/50",     Icon: TrendingDown } :
                         { bg: "bg-slate-500/20",   text: "text-slate-200",   border: "border-slate-400/50",   Icon: Eye };
  return (
    <span className={clsx("inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border text-xs font-bold", cfg.bg, cfg.text, cfg.border)}>
      <cfg.Icon size={12} />
      {action}
    </span>
  );
}

function RegimePill({ regime }: { regime: string }) {
  const colour =
    regime.includes("STRONG_BULL") ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" :
    regime.includes("BULL")        ? "text-green-400   bg-green-500/10   border-green-500/30"   :
    regime.includes("STRONG_BEAR") ? "text-red-400     bg-red-500/10     border-red-500/30"     :
    regime.includes("BEAR")        ? "text-orange-400  bg-orange-500/10  border-orange-500/30"  :
                                     "text-slate-400   bg-slate-500/10   border-slate-500/30";
  return (
    <span className={clsx("text-[11px] font-semibold px-2 py-0.5 rounded border", colour)}>
      {regime.replace(/_/g, " ")}
    </span>
  );
}

function LayerBar({ layerKey, layer }: { layerKey: string; layer: BreakdownLayer }) {
  const meta  = LAYER_META[layerKey] ?? { name: layerKey, icon: Activity };
  const Icon  = meta.icon;
  const pct   = layer.score != null ? Math.round(layer.score * 100) : null;
  const wPct  = Math.round(layer.weight * 100);

  const barColour =
    pct == null       ? "bg-slate-700"    :
    pct >= 70         ? "bg-emerald-500"  :
    pct >= 50         ? "bg-green-500"    :
    pct >= 35         ? "bg-amber-500"    : "bg-red-500";

  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <Icon size={12} className="text-slate-400 shrink-0" />
          <span className="text-[11px] text-slate-300 truncate">{meta.name}</span>
          <span className="text-[10px] text-slate-600 shrink-0">({wPct}%)</span>
        </div>
        <span className={clsx(
          "text-[11px] font-mono font-semibold shrink-0",
          pct == null       ? "text-slate-600" :
          pct >= 70         ? "text-emerald-400" :
          pct >= 50         ? "text-green-400"   :
          pct >= 35         ? "text-amber-400"   : "text-red-400"
        )}>
          {pct != null ? `${pct}%` : "—"}
        </span>
      </div>
      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
        <div
          className={clsx("h-full rounded-full transition-all", barColour)}
          style={{ width: pct != null ? `${pct}%` : "0%" }}
        />
      </div>
      {layer.label && (
        <p className="text-[10px] text-slate-500 pl-4 leading-snug">{layer.label}</p>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  Main card
// ─────────────────────────────────────────────────────────────────────────────

export function ConfidenceBreakdown({ data }: { data: ConfidenceData }) {
  const [showDetails, setShowDetails] = useState(false);

  const isStrongSignal = data.confidence >= 0.75;
  const hasDisqualifiers = data.disqualifiers.length > 0;

  return (
    <div className={clsx(
      "rounded-xl border bg-slate-900 p-5 space-y-4",
      isStrongSignal ? "border-emerald-500/40" : "border-slate-700/60"
    )}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-lg font-bold text-white">{data.ticker}</span>
            <RegimePill regime={data.market_regime} />
          </div>
          <ActionBadge action={data.action} />
          <p className="text-[11px] text-slate-500">
            {data.n_layers_active}/7 signal layers active
          </p>
        </div>
        <ConfidenceGauge value={data.confidence} />
      </div>

      {/* Strong signal highlight */}
      {isStrongSignal && !hasDisqualifiers && (
        <div className="flex items-start gap-2 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2.5">
          <Zap size={13} className="text-emerald-400 mt-0.5 shrink-0" />
          <span className="text-xs text-emerald-300">
            High-conviction setup across multiple independent signal layers
          </span>
        </div>
      )}

      {/* Hard disqualifiers */}
      {hasDisqualifiers && (
        <div className="space-y-1.5">
          {data.disqualifiers.map((d, i) => (
            <div key={i} className="flex items-start gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
              <AlertTriangle size={12} className="text-red-400 mt-0.5 shrink-0" />
              <span className="text-xs text-red-300">{d}</span>
            </div>
          ))}
        </div>
      )}

      {/* Signal breakdown bars */}
      <div className="space-y-3">
        {Object.entries(data.breakdown).map(([key, layer]) => (
          <LayerBar key={key} layerKey={key} layer={layer} />
        ))}
      </div>

      {/* Risk factors */}
      {data.risk_factors.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide">
            Key Risks
          </p>
          {data.risk_factors.map((r, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-slate-400">
              <AlertTriangle size={11} className="text-amber-500 mt-0.5 shrink-0" />
              {r}
            </div>
          ))}
        </div>
      )}

      {/* Watch levels (expandable) */}
      {data.watch_levels && (
        <>
          <button
            onClick={() => setShowDetails(v => !v)}
            className="flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-slate-300 transition-colors w-full"
          >
            {showDetails ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            <span>Watch levels & thesis invalidation</span>
          </button>

          {showDetails && (
            <div className="bg-slate-800/60 rounded-lg p-3 space-y-2">
              <WatchRow
                label="Invalidation price"
                value={`$${data.watch_levels.invalidation_below.toFixed(2)}`}
                highlight="red"
                note="Break below = exit"
              />
              <WatchRow
                label="Support (MA50)"
                value={`$${data.watch_levels.key_support_ma50.toFixed(2)}`}
                highlight="amber"
              />
              <WatchRow
                label="Support (MA200)"
                value={`$${data.watch_levels.key_support_ma200.toFixed(2)}`}
                highlight="amber"
              />
              <WatchRow
                label="Current price"
                value={`$${data.watch_levels.current_price.toFixed(2)}`}
                highlight="green"
              />
              <p className="text-[10px] text-slate-500 leading-snug pt-1">
                {data.watch_levels.note}
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function WatchRow({
  label, value, highlight, note,
}: {
  label: string; value: string; highlight: "red" | "amber" | "green"; note?: string;
}) {
  const textColour =
    highlight === "red"   ? "text-red-400"    :
    highlight === "amber" ? "text-amber-400"  : "text-emerald-400";
  return (
    <div className="flex items-center justify-between gap-2">
      <div>
        <span className="text-[11px] text-slate-400">{label}</span>
        {note && <span className="text-[10px] text-slate-600 ml-1.5">— {note}</span>}
      </div>
      <span className={clsx("text-xs font-mono font-semibold", textColour)}>{value}</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  List view
// ─────────────────────────────────────────────────────────────────────────────

export function ConfidenceBreakdownList({
  items,
  title = "Confidence Breakdown",
}: {
  items?: ConfidenceData[] | null;
  title?: string;
}) {
  if (!items || items.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700/60 bg-slate-900 p-6 text-center text-slate-500 text-sm">
        No confidence data available
      </div>
    );
  }

  const sorted = [...items].sort((a, b) => b.confidence - a.confidence);

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-slate-300">{title}</h3>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {sorted.map(item => (
          <ConfidenceBreakdown key={item.ticker} data={item} />
        ))}
      </div>
    </div>
  );
}
