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
  Ban, Tag, Layers, ArrowRight, CheckCircle,
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

export interface MLHorizonEntry {
  prob:            number | null;
  threshold_pct:   number;   // e.g. 5 means "P(5%+ gain)"
  horizon_days:    number;   // 20 / 60 / 120
  label:           string;   // "1 month" / "3 months" / "6 months"
  description:     string;   // "Short-term" / "Medium-term" / "Long-term"
  interpretation:  string;   // "Strong" / "Bullish" / "Neutral" / "Cautious" / "Weak"
}

export interface MLHorizons {
  short:  MLHorizonEntry;
  medium: MLHorizonEntry;
  long:   MLHorizonEntry;
}

// ── Pre-flight types (mirrors signal_fusion.py / asset_classifier.py output) ─

export interface PreFlightFlag {
  type:    "error" | "warn" | "info";
  message: string;
}

export interface CoherenceData {
  level:              "HIGH" | "MODERATE" | "LOW" | "INCOHERENT";
  std_dev:            number | null;
  mean:               number | null;
  spread:             number | null;
  active_layer_count: number;
  tradeable:          boolean;
  is_contrarian:      boolean;
  message:            string;
}

export interface TransitionBonusData {
  bonus_active:    boolean;
  upgrade:         string | null;
  position_bonus:  number | null;
  rationale:       string | null;
  days_to_confirm: number | null;
}

export interface RSIDirectionData {
  signal:        string;
  label:         string;
  rsi_current:   number;
  delta:         number;
  pattern_bonus: number;
  is_oversold:   boolean;
  is_overbought: boolean;
}

export interface DivergenceData {
  score:            number;
  label:            "EXTREME" | "HIGH" | "MODERATE" | "LOW";
  is_high_conflict: boolean;
  direction:        string;
}

export interface RegimeTransitionData {
  shift_probability: number;
  days_estimate:     string;
  label:             string;
}

export interface PlaybookScenario {
  scenario_id:    number;
  name:           string;
  condition_desc: string;
  condition_met:  boolean;
  mode:           string;
  action:         string;
  details:        Record<string, string>;
  conflict_score: string;
}

export interface PreFlightData {
  is_scoreable:      boolean;
  asset_type:        string | null;
  asset_name:        string;
  weight_label:      string;
  flags:             PreFlightFlag[];
  coherence:         CoherenceData | null;
  transition_bonus:  TransitionBonusData | null;
  rsi_direction:     RSIDirectionData | null;
  divergence:        DivergenceData | null;
  regime_transition: RegimeTransitionData | null;
  /** When bull % is high but shift probability is also high — explain tension */
  regime_tension_note?: string | null;
  playbook:          PlaybookScenario[];
  current_mode:      string | null;
  current_action:    string | null;
  position_size:     string | null;
}

export interface ConfidenceData {
  ticker:          string;
  confidence:      number | null;   // null for INCOMPATIBLE instruments
  action:          string;
  // Optional raw HMM payload (from backend) for regime-aware one-liners
  hmm?: {
    dominant_state?: string | null;
    dominant_state_validated?: string | null;
    bull_probability?: number | null;
    transition_probability?: number | null;
    bear_probability?: number | null;
    ma_conflict?: Record<string, unknown> | null;
    earnings_context?: Record<string, unknown> | null;
  } | null;
  breakdown: {
    regime_hmm:        BreakdownLayer;
    pattern_technical: BreakdownLayer;
    lgbm_probability:  BreakdownLayer;
    options_sentiment: BreakdownLayer;
    insider_signal:    BreakdownLayer;
    fundamental_score: BreakdownLayer;
    nlp_sentiment:     BreakdownLayer;
  };
  ml_horizons?:    MLHorizons;
  disqualifiers:   string[];
  risk_factors:    string[];
  watch_levels?:   WatchLevels;
  market_regime:   string;
  n_layers_active: number;
  pre_flight?:     PreFlightData;   // new — asset classification + coherence + playbook
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

function toPct(v: number | null | undefined): number | null {
  if (v == null || Number.isNaN(v)) return null;
  // ML horizons are 0–1; some upstreams can already be 0–100.
  return v <= 1.0 ? Math.round(v * 100) : Math.round(v);
}

function topDriverFromBreakdown(breakdown: ConfidenceData["breakdown"] | undefined | null) {
  if (!breakdown) return null;
  let best: { key: string; contrib: number } | null = null;
  for (const [key, layer] of Object.entries(breakdown)) {
    const l = layer as BreakdownLayer;
    if (!l || !l.available || l.score == null || l.weight == null) continue;
    const contrib = Math.max(0, Math.min(1, l.score)) * Math.max(0, l.weight);
    if (!best || contrib > best.contrib) best = { key, contrib };
  }
  if (!best) return null;
  const meta = LAYER_META[best.key] ?? { name: best.key, icon: Activity };
  return { name: meta.name, key: best.key, contrib: best.contrib };
}

function generateActionSummary(data: ConfidenceData): string | null {
  const actionRaw = data.action || "WATCH";
  const action = actionRaw.toUpperCase();

  const hmmRegime = (
    data.hmm?.dominant_state_validated ||
    data.hmm?.dominant_state ||
    data.market_regime ||
    "UNKNOWN"
  ).toString().replace(/_/g, " ");

  const top = topDriverFromBreakdown(data.breakdown);

  const mlShortProb =
    data.ml_horizons?.short?.prob ??
    (data.breakdown?.lgbm_probability?.score ?? null);
  const mlPct = toPct(mlShortProb);

  const daysToConfirm =
    data.pre_flight?.transition_bonus?.days_to_confirm != null
      ? `${data.pre_flight.transition_bonus.days_to_confirm}d`
      : (data.pre_flight?.regime_transition?.days_estimate ?? null);

  const ma50 = data.watch_levels?.key_support_ma50 ?? null;
  const invalidation = data.watch_levels?.invalidation_below ?? null;

  if (action.includes("WATCH") || action.includes("HOLD")) {
    if (hmmRegime.includes("TRANSITION")) {
      const t = daysToConfirm ? `Watch for regime flip in ~${daysToConfirm} — ` : "Watch for regime flip — ";
      const ml = mlPct != null ? `ML at ${mlPct}% is strong ` : "ML is strong ";
      const level = ma50 != null ? `; enter on dips toward MA50 ($${ma50.toFixed(2)}).` : ".";
      return `${t}${ml}but transition isn’t confirmed yet${level}`;
    }
    const driver = top?.name ? `${top.name} driving the read` : "insufficient confluence";
    const level = ma50 != null ? ` Watch MA50 ($${ma50.toFixed(2)}) for an add level.` : "";
    return `HOLD/WATCH — ${driver}.${level}`.trim();
  }

  if (action.includes("BUY")) {
    const driver = top?.name ? `${top.name} leading` : "layers aligned";
    const ml = mlPct != null ? `${mlPct}% ML` : "ML";
    const stop = invalidation != null ? ` Stop < $${invalidation.toFixed(2)}.` : "";
    return `BUY — ${driver} (${ml}, ${hmmRegime} regime).${stop}`.trim();
  }

  if (action.includes("REDUCE") || action.includes("AVOID") || action.includes("SELL") || action.includes("TRIM")) {
    const driver = top?.name ? `${top.name} weakening` : "signal confluence weakening";
    const level = invalidation != null ? ` Reassess above $${invalidation.toFixed(2)}.` : "";
    return `${actionRaw} — ${driver}.${level}`.trim();
  }

  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Sub-components
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
//  Colour helpers — standardised thresholds across all bars
// ─────────────────────────────────────────────────────────────────────────────

function scoreColourClass(pct: number | null, type: "text" | "bg") {
  if (pct === null) return type === "text" ? "text-slate-600" : "bg-slate-700/50";
  if (pct >= 70)   return type === "text" ? "text-emerald-400" : "bg-emerald-500";
  if (pct >= 40)   return type === "text" ? "text-amber-400"   : "bg-amber-500";
                   return type === "text" ? "text-red-400"     : "bg-red-500";
}

// ─────────────────────────────────────────────────────────────────────────────
//  ML Horizons panel — Short / Medium / Long term probability rows
// ─────────────────────────────────────────────────────────────────────────────

const INTERP_COLOUR: Record<string, { text: string; bg: string; border: string }> = {
  Strong:      { text: "text-emerald-300", bg: "bg-emerald-500/15", border: "border-emerald-500/30" },
  Bullish:     { text: "text-green-300",   bg: "bg-green-500/15",   border: "border-green-500/30"   },
  Neutral:     { text: "text-amber-300",   bg: "bg-amber-500/15",   border: "border-amber-500/30"   },
  Cautious:    { text: "text-orange-300",  bg: "bg-orange-500/15",  border: "border-orange-500/30"  },
  Weak:        { text: "text-red-300",     bg: "bg-red-500/15",     border: "border-red-500/30"     },
  Unavailable: { text: "text-slate-500",   bg: "bg-slate-700/20",   border: "border-slate-600/30"   },
};

function MLHorizonsPanel({ horizons }: { horizons: MLHorizons }) {
  const rows: [string, MLHorizonEntry][] = [
    ["short",  horizons.short],
    ["medium", horizons.medium],
    ["long",   horizons.long],
  ];

  return (
    <div className="mt-2 rounded-lg bg-slate-800/60 border border-slate-700/40 overflow-hidden">
      {/* Header */}
      <div className="grid grid-cols-[100px_1fr_52px_90px] gap-x-3 px-3 py-1.5 bg-slate-800/80 border-b border-slate-700/40">
        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Horizon</span>
        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Probability</span>
        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide text-right">Prob</span>
        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide text-right">Signal</span>
      </div>

      {/* Rows */}
      {rows.map(([key, h]) => {
        const probPct  = h.prob != null ? Math.round(h.prob * 100) : null;
        const barWidth = probPct ?? 0;
        const barColour =
          probPct == null  ? "bg-slate-700" :
          probPct >= 65    ? "bg-emerald-500" :
          probPct >= 50    ? "bg-green-500" :
          probPct >= 35    ? "bg-amber-500" :
          probPct >= 20    ? "bg-orange-500" :
                             "bg-red-500";
        const interpKey  = h.interpretation ?? "Unavailable";
        const ic         = INTERP_COLOUR[interpKey] ?? INTERP_COLOUR.Unavailable;

        return (
          <div key={key} className="grid grid-cols-[100px_1fr_52px_90px] gap-x-3 items-center px-3 py-2.5 border-b border-slate-700/30 last:border-b-0">
            {/* Horizon label */}
            <div>
              <p className="text-xs font-semibold text-slate-200">{h.description}</p>
              <p className="text-[11px] text-slate-500">{h.label} · P({h.threshold_pct}%+)</p>
            </div>

            {/* Progress bar */}
            <div className="h-2 rounded-full bg-slate-700/60 overflow-hidden">
              <div
                className={clsx("h-full rounded-full transition-all duration-500", barColour)}
                style={{ width: `${barWidth}%` }}
              />
            </div>

            {/* Probability % */}
            <span className={clsx("text-xs font-bold font-mono text-right",
              probPct == null  ? "text-slate-500" :
              probPct >= 65    ? "text-emerald-300" :
              probPct >= 50    ? "text-green-300" :
              probPct >= 35    ? "text-amber-300" :
              probPct >= 20    ? "text-orange-300" : "text-red-300"
            )}>
              {probPct != null ? `${probPct}%` : "N/A"}
            </span>

            {/* Interpretation badge */}
            <div className="flex justify-end">
              <span className={clsx(
                "text-[11px] font-semibold px-2 py-0.5 rounded border",
                ic.text, ic.bg, ic.border
              )}>
                {interpKey}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function ConfidenceGauge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const colour =
    pct >= 70 ? "#10b981" :
    pct >= 40 ? "#f59e0b" : "#ef4444";

  const r = 38, cx = 50, cy = 52;
  const angle = (pct / 100) * 180;
  const rad   = (angle - 180) * (Math.PI / 180);
  const endX  = cx + r * Math.cos(rad);
  const endY  = cy + r * Math.sin(rad);
  const lArc  = angle > 180 ? 1 : 0;

  return (
    <div className="flex flex-col items-center shrink-0">
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
      <span className="text-[10px] text-slate-400 -mt-1">ML Confidence</span>
    </div>
  );
}

function ActionBadge({ action, confidence }: { action: string; confidence: number }) {
  const a = action.toUpperCase();
  const cfg =
    a.includes("STRONG BUY") ? { bg: "bg-emerald-500/20", text: "text-emerald-200", border: "border-emerald-400/50", Icon: TrendingUp } :
    a.includes("BUY")        ? { bg: "bg-green-500/20",   text: "text-green-200",   border: "border-green-400/50",   Icon: TrendingUp } :
    a.includes("REDUCE")     ? { bg: "bg-amber-500/20",   text: "text-amber-200",   border: "border-amber-400/50",   Icon: TrendingDown } :
    a.includes("AVOID")      ? { bg: "bg-red-500/20",     text: "text-red-200",     border: "border-red-400/50",     Icon: TrendingDown } :
                               { bg: "bg-slate-500/20",   text: "text-slate-200",   border: "border-slate-400/50",   Icon: Eye };

  // Position size suggestion from confidence
  const sizeHint =
    confidence >= 0.70 ? "up to 8% position" :
    confidence >= 0.55 ? "up to 4% position" :
    confidence >= 0.40 ? "up to 2% position" : "1% max — wait for confirmation";

  // Re-evaluate trigger
  const reeval =
    a.includes("REDUCE") || a.includes("AVOID")
      ? `Re-evaluate if ML prob crosses 25% or pattern score > 60`
      : null;

  return (
    <div className="space-y-1">
      <span className={clsx("inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border text-xs font-bold", cfg.bg, cfg.text, cfg.border)}>
        <cfg.Icon size={12} />
        {action}
      </span>
      <p className="text-xs text-slate-300 pl-0.5">{sizeHint}</p>
      {reeval && <p className="text-[11px] text-slate-400 pl-0.5">{reeval}</p>}
    </div>
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
  const meta = LAYER_META[layerKey] ?? { name: layerKey, icon: Activity };
  const Icon = meta.icon;
  const wPct = Math.round((layer.weight ?? 0) * 100);
  const available = layer.available && layer.score != null;
  const pct = available ? Math.round((layer.score as number) * 100) : null;

  // Simplify the label — strip raw numbers, keep the human-readable part
  const rawLabel = layer.label ?? "";
  const cleanLabel = (() => {
    if (!available) return rawLabel || "Data unavailable — not counted in score";
    // e.g. "Pattern 18/100-technical 61/100 — Volume drying up..." → keep after "—"
    const dashIdx = rawLabel.indexOf(" — ");
    if (dashIdx !== -1) return rawLabel.slice(dashIdx + 3);
    return rawLabel;
  })();

  // Score-aware label colour so the description visually echoes the result
  const labelColour = !available
    ? "text-slate-500 italic"
    : pct != null && pct >= 70 ? "text-emerald-300/90"
    : pct != null && pct >= 40 ? "text-amber-300/90"
    : "text-red-300/80";

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <Icon size={13} className={available ? "text-slate-400" : "text-slate-600"} />
          <span className={clsx("text-xs font-medium truncate", available ? "text-slate-200" : "text-slate-500")}>
            {meta.name}
          </span>
          <span className="text-[11px] text-slate-500 shrink-0">({wPct}%)</span>
        </div>
        <span className={clsx("text-xs font-mono font-bold shrink-0", scoreColourClass(pct, "text"))}>
          {pct != null ? `${pct}%` : "N/A"}
        </span>
      </div>

      {/* Bar — shows dashed outline for unavailable layers */}
      <div className={clsx(
        "w-full rounded-full h-2 overflow-hidden",
        available ? "bg-slate-800" : "bg-slate-800/40 border border-dashed border-slate-700"
      )}>
        {available && pct != null && (
          <div className={clsx("h-full rounded-full transition-all", scoreColourClass(pct, "bg"))}
               style={{ width: `${pct}%` }} />
        )}
      </div>

      {/* Label — larger, score-aware colour */}
      <p className={clsx("text-xs pl-4 leading-snug", labelColour)}>
        {cleanLabel}
      </p>
    </div>
  );
}

/** Weighted math table — shows exactly how 45% is computed from the layers. */
function WeightedMathTable({ breakdown, confidence }: {
  breakdown: Record<string, BreakdownLayer>;
  confidence: number;
}) {
  const [open, setOpen] = useState(false);
  const rows = Object.entries(breakdown).map(([key, layer]) => {
    const meta   = LAYER_META[key] ?? { name: key, icon: Activity };
    const wRaw   = (layer.weight ?? 0) as number;
    const sRaw   = layer.available && layer.score != null ? (layer.score as number) : null;
    const wPct   = Math.round(wRaw * 100);
    const sPct   = sRaw != null ? Math.round(sRaw * 100) : null;
    // IMPORTANT: contrib must use raw decimals (not rounded score buckets) to avoid 20%×48 showing as 8.0.
    const contrib = sRaw != null ? (sRaw * wRaw) : 0;
    return { key, name: meta.name, wPct, sPct, contrib, wRaw, sRaw };
  });

  const activeWeightTotal = Object.values(breakdown)
    .filter(l => l.available && l.score != null)
    .reduce((s, l) => s + (l.weight ?? 0), 0);

  return (
    <div className="border-t border-slate-700/40 pt-3">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors w-full font-medium"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span>How is {Math.round(confidence * 100)}% calculated?</span>
      </button>

      {open && (
        <div className="mt-2 rounded-lg bg-slate-800/50 p-3 text-xs space-y-1.5 font-mono">
          <div className="grid grid-cols-[1fr_44px_44px_56px] gap-x-2 text-slate-400 mb-1.5 uppercase text-[11px] font-sans font-semibold tracking-wide">
            <span>Layer</span><span className="text-right">Wt</span>
            <span className="text-right">Score</span><span className="text-right">Contrib</span>
          </div>
          {rows.map(r => (
            <div key={r.key} className="grid grid-cols-[1fr_44px_44px_56px] gap-x-2">
              <span className={r.sPct != null ? "text-slate-200" : "text-slate-500"}>{r.name}</span>
              <span className="text-right text-slate-400">{r.wPct}%</span>
              <span className={clsx("text-right font-semibold", scoreColourClass(r.sPct, "text"))}>
                {r.sPct != null ? `${r.sPct}%` : "—"}
              </span>
              <span className="text-right text-slate-300">
                {r.sPct != null ? `${r.wPct}%×${r.sPct}% = ${(r.contrib * 100).toFixed(1)}` : "—"}
              </span>
            </div>
          ))}
          <div className="border-t border-slate-600/50 pt-1.5 mt-1 grid grid-cols-[1fr_44px_44px_56px] gap-x-2">
            <span className="text-slate-300 col-span-3 font-sans">Normalised ÷ {Math.round(activeWeightTotal * 100)}% active weight</span>
            <span className="text-right text-emerald-400 font-bold">= {Math.round(confidence * 100)}%</span>
          </div>
          <p className="text-[11px] text-slate-400 pt-1 font-sans">
            Unavailable layers (N/A) are excluded and their weight is redistributed.
          </p>
        </div>
      )}
    </div>
  );
}

/** "What would flip this to BUY?" — most actionable section for a trader. */
function FlipToBuy({ breakdown, action }: {
  breakdown: Record<string, BreakdownLayer>;
  action: string;
}) {
  const isBullish = action.toUpperCase().includes("BUY");
  if (isBullish) return null;

  const TARGETS: Record<string, { threshold: number; label: string }> = {
    lgbm_probability:  { threshold: 0.40, label: "ML Probability" },
    pattern_technical: { threshold: 0.60, label: "Pattern Score" },
    options_sentiment: { threshold: 0.50, label: "Options Sentiment" },
    regime_hmm:        { threshold: 0.60, label: "Regime (HMM)" },
    fundamental_score: { threshold: 0.55, label: "Fundamentals" },
  };

  const gaps = Object.entries(TARGETS)
    .map(([key, target]) => {
      const layer = breakdown[key];
      if (!layer) return null;
      const score = layer.available && layer.score != null ? (layer.score as number) : null;
      const needed = target.threshold;
      if (score !== null && score >= needed) return null; // already passing
      return { label: target.label, needed: Math.round(needed * 100), current: score !== null ? Math.round(score * 100) : null };
    })
    .filter(Boolean) as { label: string; needed: number; current: number | null }[];

  if (gaps.length === 0) return null;

  return (
    <div className="rounded-lg border border-blue-500/25 bg-blue-500/8 p-3.5 space-y-2.5">
      <p className="text-xs font-semibold text-blue-200 flex items-center gap-1.5">
        <Zap size={13} />
        What would upgrade this to BUY?
      </p>
      <div className="space-y-2">
        {gaps.map((g, i) => (
          <div key={i} className="flex items-center justify-between gap-2">
            <span className="text-xs text-slate-300 font-medium">{g.label}</span>
            <div className="flex items-center gap-1.5 text-xs font-mono">
              <span className={clsx("font-semibold", g.current != null ? scoreColourClass(g.current, "text") : "text-slate-500")}>
                {g.current != null ? `${g.current}%` : "N/A"}
              </span>
              <span className="text-slate-500">→</span>
              <span className="text-blue-300 font-semibold">needs {g.needed}%+</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  Pre-flight sub-components
// ─────────────────────────────────────────────────────────────────────────────

/** Red banner for instruments that cannot be scored (UVXY, VXX, VIXY) */
function IncompatibleBanner({ ticker, name, flags }: { ticker: string; name: string; flags: PreFlightFlag[] }) {
  return (
    <div className="rounded-xl border border-red-500/50 bg-red-500/10 p-5 space-y-3">
      <div className="flex items-center gap-2">
        <Ban size={18} className="text-red-400 shrink-0" />
        <div>
          <p className="text-sm font-bold text-red-300">{ticker} — {name}</p>
          <p className="text-xs text-red-400/80">Standard equity model cannot score this instrument</p>
        </div>
      </div>
      <div className="space-y-1.5">
        {flags.map((f, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <AlertTriangle size={12} className="text-red-400 mt-0.5 shrink-0" />
            <span className="text-red-300/90">{f.message}</span>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-slate-400 border-t border-red-500/20 pt-2">
        Volatility ETFs (UVXY, VXX, VIXY) behave inversely to equities. ML models trained on equities
        produce misleading signals. Use a dedicated VIX analysis approach instead.
      </p>
    </div>
  );
}

/** Asset type + weight profile tag in the header */
function AssetTypeBadge({ assetType, weightLabel }: { assetType: string | null; weightLabel: string }) {
  if (!assetType) return null;
  const colour =
    assetType === "ETF_COMMODITY"      ? "text-yellow-300 bg-yellow-500/10 border-yellow-500/30" :
    assetType === "ETF_EQUITY"         ? "text-blue-300   bg-blue-500/10   border-blue-500/30"   :
    assetType === "ETF_VOLATILITY"     ? "text-red-300    bg-red-500/10    border-red-500/30"     :
    assetType === "EQUITY_ADR"         ? "text-purple-300 bg-purple-500/10 border-purple-500/30"  :
    assetType === "EQUITY_SPECULATIVE" ? "text-orange-300 bg-orange-500/10 border-orange-500/30"  :
    assetType === "EQUITY_DEFENSIVE"   ? "text-teal-300   bg-teal-500/10   border-teal-500/30"    :
                                         "text-slate-300  bg-slate-500/10  border-slate-500/30";
  const short = assetType.replace("EQUITY_", "").replace("ETF_", "ETF·");
  return (
    <span className={clsx("inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wide", colour)}
          title={weightLabel}>
      <Tag size={9} />
      {short}
    </span>
  );
}

/** Pre-flight flags (warn/info/error) from asset classifier */
function PreFlightFlags({ flags }: { flags: PreFlightFlag[] }) {
  if (!flags || flags.length === 0) return null;
  return (
    <div className="space-y-1.5">
      {flags.map((f, i) => {
        const isErr  = f.type === "error";
        const isWarn = f.type === "warn";
        return (
          <div key={i} className={clsx(
            "flex items-start gap-2 rounded-lg px-3 py-2 border text-xs",
            isErr  ? "bg-red-500/10 border-red-500/30 text-red-300" :
            isWarn ? "bg-amber-500/10 border-amber-500/30 text-amber-300" :
                     "bg-slate-700/30 border-slate-600/30 text-slate-400"
          )}>
            {isErr  ? <Ban size={11} className="shrink-0 mt-0.5" /> :
             isWarn ? <AlertTriangle size={11} className="shrink-0 mt-0.5" /> :
                      <Info size={11} className="shrink-0 mt-0.5" />}
            {f.message}
          </div>
        );
      })}
    </div>
  );
}

/** Coherence badge — signals agreement level */
function CoherenceBadge({ coherence }: { coherence: CoherenceData }) {
  const cfg =
    coherence.level === "HIGH"       ? { colour: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30", dot: "bg-emerald-400" } :
    coherence.level === "MODERATE"   ? { colour: "text-amber-300   bg-amber-500/10   border-amber-500/30",   dot: "bg-amber-400"   } :
    coherence.level === "LOW"        ? { colour: "text-orange-300  bg-orange-500/10  border-orange-500/30",  dot: "bg-orange-400"  } :
                                       { colour: "text-red-300     bg-red-500/10     border-red-500/30",     dot: "bg-red-400"     };
  return (
    <span className={clsx("inline-flex items-center gap-1.5 text-[10px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wide", cfg.colour)}
          title={coherence.message}>
      <span className={clsx("w-1.5 h-1.5 rounded-full shrink-0", cfg.dot)} />
      {coherence.level}
      {coherence.std_dev != null && <span className="opacity-60 lowercase tracking-normal">·σ{coherence.std_dev}</span>}
    </span>
  );
}

/** ⚡ Transition bonus banner (BABA-type: HMM transition + ML confirming) */
function TransitionBonusBanner({ bonus }: { bonus: TransitionBonusData }) {
  if (!bonus.bonus_active) return null;
  return (
    <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/35 rounded-lg px-3 py-2.5">
      <Zap size={14} className="text-amber-400 mt-0.5 shrink-0" />
      <div className="space-y-0.5">
        <p className="text-xs font-semibold text-amber-200">
          ⚡ Transition Bonus Active
          {bonus.upgrade && <span className="ml-1.5 font-normal text-amber-300/80">→ {bonus.upgrade}</span>}
        </p>
        {bonus.rationale && <p className="text-[11px] text-amber-300/70">{bonus.rationale}</p>}
        {bonus.days_to_confirm && (
          <p className="text-[11px] text-slate-400">Estimated ~{bonus.days_to_confirm} days to bull confirmation</p>
        )}
      </div>
    </div>
  );
}

/** Regime shift outlook row — forward-looking HMM probability */
function RegimeTransitionRow({ rt }: { rt: RegimeTransitionData }) {
  const pct   = rt.shift_probability;
  const watch = rt.label === "WATCH_CLOSELY";
  return (
    <div className={clsx(
      "rounded-lg px-3 py-2.5 border space-y-1.5",
      watch ? "bg-amber-500/8 border-amber-500/25" : "bg-slate-800/40 border-slate-700/30"
    )}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <ArrowRight size={12} className={watch ? "text-amber-400" : "text-slate-500"} />
          <span className="text-xs font-semibold text-slate-200">Regime Shift Outlook</span>
          {watch && <span className="text-[10px] text-amber-400 font-semibold uppercase tracking-wide">Watch Closely</span>}
        </div>
        <span className={clsx("text-xs font-mono font-bold", pct >= 40 ? "text-amber-300" : "text-slate-400")}>
          {pct.toFixed(0)}%
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-slate-700/60 overflow-hidden">
        <div className={clsx("h-full rounded-full", pct >= 40 ? "bg-amber-500" : "bg-slate-600")}
             style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <p className="text-[11px] text-slate-400">
        {pct.toFixed(0)}% probability of regime shift within {rt.days_estimate}
      </p>
    </div>
  );
}

/** Signal divergence (options vs ML conflict) indicator */
function DivergenceRow({ div: d }: { div: DivergenceData }) {
  if (!d) return null;
  const cfg =
    d.label === "EXTREME"  ? { colour: "text-red-300 bg-red-500/10 border-red-500/30" } :
    d.label === "HIGH"     ? { colour: "text-orange-300 bg-orange-500/10 border-orange-500/30" } :
    d.label === "MODERATE" ? { colour: "text-amber-300 bg-amber-500/10 border-amber-500/30" } :
                             { colour: "text-slate-400 bg-slate-700/20 border-slate-600/20" };
  const dirLabel = d.direction === "OPTIONS_BULLISH_ML_BEARISH"
    ? "Options bullish, ML bearish — possible contrarian setup"
    : "ML bullish, Options bearish — model vs smart money conflict";
  return (
    <div className={clsx("flex items-start gap-2 rounded-lg px-3 py-2 border text-xs", cfg.colour)}>
      <Layers size={12} className="mt-0.5 shrink-0" />
      <div>
        <span className="font-semibold">Signal Conflict: {d.label}</span>
        <span className="text-[11px] opacity-75 ml-1.5">({d.score.toFixed(0)}pt gap)</span>
        <p className="text-[11px] opacity-75 mt-0.5">{dirLabel}</p>
      </div>
    </div>
  );
}

/** RSI direction sub-indicator — is RSI turning up from oversold? */
function RSIDirectionPill({ rsi }: { rsi: RSIDirectionData }) {
  const bullish = rsi.signal === "OVERSOLD_REVERSAL" || rsi.signal === "OVERBOUGHT_MOMENTUM";
  const bearish = rsi.signal === "OVERSOLD_FALLING"  || rsi.signal === "OVERBOUGHT_REVERSAL";
  const colour =
    bullish ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/25" :
    bearish ? "text-red-300     bg-red-500/10     border-red-500/25"     :
              "text-slate-400   bg-slate-700/20   border-slate-600/20";
  const bonusLabel = rsi.pattern_bonus > 0 ? `+${rsi.pattern_bonus}pt` : rsi.pattern_bonus < 0 ? `${rsi.pattern_bonus}pt` : null;
  return (
    <div className="flex items-center gap-2 pl-4 mt-1">
      <span className={clsx("inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded border", colour)}>
        RSI {rsi.rsi_current.toFixed(0)} · {rsi.label.split(" — ")[0]}
        {bonusLabel && <span className="ml-1 opacity-70">{bonusLabel}</span>}
      </span>
    </div>
  );
}

/** Collapsible conditional playbook */
function PlaybookSection({ playbook }: { playbook: PlaybookScenario[] }) {
  const [open, setOpen] = useState(false);
  if (!playbook || playbook.length === 0) return null;
  const active = playbook.find(s => s.condition_met);

  return (
    <div className="border-t border-slate-700/40 pt-3">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors w-full font-medium"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span>Conditional Playbook</span>
        {active && (
          <span className="ml-1.5 text-[10px] text-amber-300 bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.5 rounded font-semibold">
            ACTIVE: {active.name}
          </span>
        )}
        {!active && (
          <span className="ml-1.5 text-[10px] text-slate-500">
            {playbook.length} scenarios — none triggered
          </span>
        )}
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {playbook.map(s => (
            <div key={s.scenario_id} className={clsx(
              "rounded-lg border p-3 space-y-2",
              s.condition_met
                ? "bg-amber-500/10 border-amber-500/30"
                : "bg-slate-800/30 border-slate-700/30 opacity-70"
            )}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  {s.condition_met
                    ? <CheckCircle size={13} className="text-amber-400 shrink-0" />
                    : <div className="w-3 h-3 rounded-full border border-slate-600 shrink-0" />}
                  <span className={clsx("text-xs font-semibold", s.condition_met ? "text-amber-200" : "text-slate-400")}>
                    {s.scenario_id}. {s.name}
                  </span>
                </div>
                <span className="text-[10px] text-slate-500 shrink-0">{s.mode.replace(/_/g, " ")}</span>
              </div>
              <p className="text-[11px] text-slate-400 pl-5">{s.condition_desc}</p>
              <p className={clsx("text-xs font-medium pl-5", s.condition_met ? "text-amber-300" : "text-slate-400")}>
                → {s.action}
              </p>
              {s.condition_met && Object.entries(s.details).length > 0 && (
                <div className="pl-5 space-y-1">
                  {Object.entries(s.details).map(([k, v]) => (
                    <div key={k} className="flex items-baseline gap-1.5 text-[11px]">
                      <span className="text-slate-500 capitalize">{k.replace(/_/g, " ")}:</span>
                      <span className="text-slate-300">{v}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  Main card
// ─────────────────────────────────────────────────────────────────────────────

export function ConfidenceBreakdown({ data }: { data: ConfidenceData }) {
  const [showWatchLevels, setShowWatchLevels] = useState(false);

  // Defensive defaults — backend may return null instead of []
  const disqualifiers = data.disqualifiers ?? [];
  const riskFactors   = data.risk_factors   ?? [];
  const breakdown     = data.breakdown      ?? {};
  const confidence    = data.confidence     ?? 0;
  const mlHorizons    = data.ml_horizons    ?? null;
  const pf            = data.pre_flight;

  // INCOMPATIBLE instrument (UVXY etc.) — show blocked banner, nothing else
  if (pf && !pf.is_scoreable) {
    return (
      <IncompatibleBanner
        ticker={data.ticker}
        name={pf.asset_name}
        flags={pf.flags ?? []}
      />
    );
  }

  const isStrongSignal   = confidence >= 0.75;
  const hasDisqualifiers = disqualifiers.length > 0;
  const coherence        = pf?.coherence ?? null;
  const transitionBonus  = pf?.transition_bonus ?? null;
  const rsiDir           = pf?.rsi_direction ?? null;
  const divergence       = pf?.divergence ?? null;
  const regimeTrans      = pf?.regime_transition ?? null;
  const playbook         = pf?.playbook ?? [];
  const pfFlags          = pf?.flags ?? [];
  const actionSummary    = generateActionSummary(data);
  // Only show non-INCOHERENT coherence message since INCOHERENT is in disqualifiers
  const incoherent       = coherence?.level === "INCOHERENT";

  return (
    <div className={clsx(
      "rounded-xl border bg-slate-900 p-5 space-y-4",
      isStrongSignal  ? "border-emerald-500/40" :
      incoherent      ? "border-red-500/40"     :
                        "border-slate-700/60"
    )}>
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-lg font-bold text-white">{data.ticker}</span>
            <RegimePill regime={data.market_regime ?? "UNKNOWN"} />
            {pf?.asset_type && (
              <AssetTypeBadge assetType={pf.asset_type} weightLabel={pf.weight_label} />
            )}
            {coherence && <CoherenceBadge coherence={coherence} />}
          </div>
          <ActionBadge action={data.action ?? "WATCH"} confidence={confidence} />
          {actionSummary && (
            <p className="text-sm text-slate-300 leading-snug max-w-[64ch]">
              {actionSummary}
            </p>
          )}
          <p className="text-[11px] text-slate-500">
            {data.n_layers_active ?? 0}/7 layers active
            {pf?.weight_label && <span className="ml-1.5 opacity-60">· {pf.weight_label}</span>}
          </p>
        </div>
        <ConfidenceGauge value={confidence} />
      </div>

      {/* Pre-flight flags (geopolitical risk, macro driver, sentiment amplification etc.) */}
      {pfFlags.length > 0 && <PreFlightFlags flags={pfFlags} />}

      {/* Incoherent signal warning — blocks trading */}
      {incoherent && (
        <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2.5">
          <AlertTriangle size={13} className="text-red-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-semibold text-red-300">Incoherent signals — do not trade on this</p>
            <p className="text-[11px] text-red-400/70 mt-0.5">{coherence?.message}</p>
          </div>
        </div>
      )}

      {/* Regime tension: bull high but shift prob also high */}
      {pf?.regime_tension_note && (
        <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2.5">
          <AlertTriangle size={13} className="text-amber-400 mt-0.5 shrink-0" />
          <p className="text-xs text-amber-200">{pf.regime_tension_note}</p>
        </div>
      )}

      {/* Transition bonus banner */}
      {transitionBonus && <TransitionBonusBanner bonus={transitionBonus} />}

      {/* Strong signal highlight */}
      {isStrongSignal && !hasDisqualifiers && !incoherent && (
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
          {disqualifiers.map((d, i) => (
            <div key={i} className="flex items-start gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
              <AlertTriangle size={12} className="text-red-400 mt-0.5 shrink-0" />
              <span className="text-xs text-red-300">{d}</span>
            </div>
          ))}
        </div>
      )}

      {/* Signal divergence (options vs ML) */}
      {divergence && divergence.is_high_conflict && <DivergenceRow div={divergence} />}

      {/* Signal breakdown bars — N/A placeholders for unavailable layers */}
      <div className="space-y-3">
        {Object.entries(breakdown).map(([key, layer]) => (
          <div key={key}>
            <LayerBar layerKey={key} layer={layer as BreakdownLayer} />
            {/* RSI direction sub-indicator expands below the pattern_technical bar */}
            {key === "pattern_technical" && rsiDir && (
              <RSIDirectionPill rsi={rsiDir} />
            )}
            {/* ML Horizons panel expands below the lgbm_probability bar */}
            {key === "lgbm_probability" && mlHorizons && (
              <MLHorizonsPanel horizons={mlHorizons} />
            )}
          </div>
        ))}
      </div>

      {/* Regime shift outlook */}
      {regimeTrans && <RegimeTransitionRow rt={regimeTrans} />}

      {/* Weighted math — expandable "how is 45% calculated?" */}
      <WeightedMathTable breakdown={breakdown as Record<string, BreakdownLayer>} confidence={confidence} />

      {/* What would flip this to BUY */}
      <FlipToBuy breakdown={breakdown as Record<string, BreakdownLayer>} action={data.action ?? "WATCH"} />

      {/* Risk factors */}
      {riskFactors.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-semibold text-slate-300 uppercase tracking-wide">Key Risks</p>
          {riskFactors.map((r, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-slate-300">
              <AlertTriangle size={12} className="text-amber-400 mt-0.5 shrink-0" />
              {r}
            </div>
          ))}
        </div>
      )}

      {/* Watch levels — expandable */}
      {data.watch_levels && (
        <div className="border-t border-slate-700/40 pt-3">
          <button
            onClick={() => setShowWatchLevels(v => !v)}
            className="flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-slate-300 transition-colors w-full"
          >
            {showWatchLevels ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            <span>Watch levels & thesis invalidation</span>
          </button>
          {showWatchLevels && (
            <div className="mt-2 bg-slate-800/60 rounded-lg p-3 space-y-2">
              <WatchRow label="Invalidation price" value={`$${data.watch_levels.invalidation_below.toFixed(2)}`} highlight="red" note="Break below = exit" />
              <WatchRow label="Support (MA50)"     value={`$${data.watch_levels.key_support_ma50.toFixed(2)}`}   highlight="amber" />
              <WatchRow label="Support (MA200)"    value={`$${data.watch_levels.key_support_ma200.toFixed(2)}`}  highlight="amber" />
              <WatchRow label="Current price"      value={`$${data.watch_levels.current_price.toFixed(2)}`}      highlight="green" />
              <p className="text-[11px] text-slate-400 leading-snug pt-1">{data.watch_levels.note}</p>
            </div>
          )}
        </div>
      )}

      {/* Conditional playbook */}
      <PlaybookSection playbook={playbook} />
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

  const sorted = [...items].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));

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
