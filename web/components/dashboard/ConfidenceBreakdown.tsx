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
  /** From HMM transition matrix row for latent transition state (direction-agnostic shift prob is separate). */
  hmm_next_step?: {
    p_next_bull: number;
    p_next_bear: number;
    p_next_transition: number;
    p_exit_to_bull?: number;
    p_exit_to_bear?: number;
  };
  /** Multi-step HMM projection + UI payload from ``hmm_regime_shift_direction``. */
  hmm_shift_direction?: {
    shift_probability?: number;
    horizon_days?: number;
    interpretation?: string;
    current_state?: string;
    shift_direction?: {
      bull: number;
      bear: number;
      transition_cycle?: number;
      dominant: string;
      dominant_confidence: number;
      label?: string;
      color?: string;
    };
    detail?: Record<string, unknown>;
  };
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

/** Signal-first reassess line (not a 52w tail “reassess above $X”). */
export interface ReassessGuidance {
  primary_condition: string;
  primary_label:     string;
  price_level:        number | null;
  price_label:        string | null;
  current_price:      number;
  display:            string;
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
  reassess_guidance?: ReassessGuidance | null;
}

/** Layer blend vs multiplicative gates (HMM bear, insider) — from confidence_engine penalty_audit */
export interface PenaltyAudit {
  confidence_blend_only: number;
  confidence_final?: number;
  combined_multiplier?: number | null;
  hmm_bear_penalty: {
    triggered: boolean;
    bear_probability: number | null;
    multiplier: number;
    multiplier_raw?: number;
    variant?: string | null;
    suppressed_pct_if_applied?: number | null;
    ease_toward_one?: number;
  };
  insider_sell_penalty: { triggered: boolean; multiplier: number };
}

export interface ConfidenceData {
  ticker:          string;
  confidence:      number | null;   // null for INCOMPATIBLE instruments
  action:          string;
  /** Blend vs stacked penalties — for charts / transparency (API passes through from run_confidence) */
  penalty_audit?:  PenaltyAudit | null;
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
  /** Raw options-chain read (yfinance, free) — siblings of breakdown.options_sentiment's
   * scored layer. `error` set when the ticker has no listed options. */
  options?: {
    error?:              string | null;
    options_label?:      string;
    pc_ratio?:           number;
    atm_iv?:             number | null;
    iv_rank?:            number | null;
    max_pain?:           number | null;
    options_score?:      number;
    pc_interpretation?:  "contrarian" | "directional";
  } | null;
  /** Raw short-interest read (FINRA via yfinance, free). Null when unavailable for this ticker. */
  short_interest?: {
    short_pct_display?: string;
    days_to_cover?:     number | null;
    dtc_label?:          string | null;
    trend?:              "increasing" | "decreasing" | "stable" | "unknown";
    squeeze_risk?:        "none" | "low" | "moderate" | "elevated" | "high" | "extreme";
    bear_signal?:         boolean;
    label?:               string;
  } | null;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Layer metadata (display names, icons, colour rules)
// ─────────────────────────────────────────────────────────────────────────────

const LAYER_META: Record<string, { name: string; icon: React.ElementType }> = {
  regime_hmm:        { name: "Regime (HMM)",      icon: Activity     },
  pattern_technical: { name: "Technical setup", icon: TrendingUp   },
  lgbm_probability:  { name: "ML Probability",    icon: Zap          },
  options_sentiment: { name: "Options Sentiment", icon: Shield       },
  insider_signal:    { name: "Insider Activity",  icon: Eye          },
  fundamental_score: { name: "Fundamentals",      icon: Info         },
  nlp_sentiment:     { name: "News Sentiment",    icon: Activity     },
};

/** Hover text: what each layer is (and is not) in plain English */
const LAYER_PLAIN_ENGLISH: Partial<Record<string, string>> = {
  regime_hmm:
    "Bull / bear / transition from our regime model. A bearish read here is mostly “backdrop and tape,” not “this company just failed earnings.”",
  pattern_technical:
    "Chart trend and pattern quality. This can look good while regime or fundamentals still argue for smaller size or patience.",
  lgbm_probability:
    "Short-horizon odds from price history (momentum / similar past setups). Timing layer — not the same as fair value or a single headline.",
  options_sentiment:
    "Options skew and flow as one input. Usually confirmatory, not a stand-alone reason to buy or sell.",
  insider_signal:
    "Reported insider buying vs selling. Often a light weight unless there is a clear cluster of activity.",
  fundamental_score:
    "Growth, margins, and estimate trend blended into one score. “Weakening” means this layer is soft vs our bar — you can still be below fair value on price; cheap and cautious can coexist.",
  nlp_sentiment:
    "Tone of recent headlines. News can brighten or darken faster than the valuation line on Roadmaps.",
};

const PRIMARY_ACTION_SUMMARY_HINT =
  "This line picks the layer that contributed the most to the fused score right now. It is not the same as “last quarter beat or miss,” and it can disagree with “cheap vs fair value” until regime and timing line up.";

const RISK_OFF_ACTION_HINT =
  "Plain English: “Weakening” points at the layer dragging the fused score — not a full company obituary. A good earnings print can still sit next to a softer multi-month fundamental trend or a defensive regime gate.";

function toPct(v: number | null | undefined): number | null {
  if (v == null || Number.isNaN(v)) return null;
  // ML horizons are 0–1; some upstreams can already be 0–100.
  return v <= 1.0 ? Math.round(v * 100) : Math.round(v);
}

const LAYER_STABLE_ORDER = [
  "regime_hmm",
  "lgbm_probability",
  "pattern_technical",
  "options_sentiment",
  "fundamental_score",
  "nlp_sentiment",
  "insider_signal",
] as const;

function topDriverFromBreakdown(breakdown: ConfidenceData["breakdown"] | undefined | null) {
  if (!breakdown) return null;
  const candidates: { key: string; contrib: number }[] = [];
  for (const [key, layer] of Object.entries(breakdown)) {
    const l = layer as BreakdownLayer;
    if (!l || !l.available || l.score == null || l.weight == null) continue;
    const contrib = Math.max(0, Math.min(1, l.score)) * Math.max(0, l.weight);
    candidates.push({ key, contrib });
  }
  if (candidates.length === 0) return null;
  const orderRank = (k: string) => {
    const i = LAYER_STABLE_ORDER.indexOf(k as (typeof LAYER_STABLE_ORDER)[number]);
    return i === -1 ? 999 : i;
  };
  candidates.sort((a, b) => {
    if (Math.abs(b.contrib - a.contrib) > 1e-7) return b.contrib - a.contrib;
    return orderRank(a.key) - orderRank(b.key);
  });
  const best = candidates[0];
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
    const floor =
      invalidation != null
        ? ` Structural / tail-risk floor ~$${invalidation.toFixed(2)} (≈52w-based) — full thesis exit if broken, not a “buy above” trigger.`
        : "";
    return `${actionRaw} — ${driver}.${floor}`.trim();
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
  if (pct === null) return type === "text" ? "text-td-muted" : "bg-td-surface2/50";
  if (pct >= 70)   return type === "text" ? "text-td-accent" : "bg-td-accent";
  if (pct >= 40)   return type === "text" ? "text-td-warn"   : "bg-td-warn";
                   return type === "text" ? "text-td-crit"     : "bg-td-crit";
}

// ─────────────────────────────────────────────────────────────────────────────
//  ML Horizons panel — Short / Medium / Long term probability rows
// ─────────────────────────────────────────────────────────────────────────────

const INTERP_COLOUR: Record<string, { text: string; bg: string; border: string }> = {
  Constructive: { text: "text-td-accent", bg: "bg-td-accent/15", border: "border-td-accent/30" },
  Neutral:      { text: "text-td-warn",   bg: "bg-td-warn/15",   border: "border-td-warn/30"   },
  Cautionary:   { text: "text-td-warn",  bg: "bg-td-warn/15",  border: "border-td-warn/30"  },
  Unavailable:  { text: "text-td-muted",   bg: "bg-td-surface2/20",   border: "border-td-line/30"   },
};

function normalizeToneLabel(raw: string | null | undefined): "Constructive" | "Neutral" | "Cautionary" | "Unavailable" {
  const s = String(raw || "").trim().toLowerCase();
  if (!s) return "Unavailable";
  if (s === "strong" || s === "bullish" || s === "constructive") return "Constructive";
  if (s === "neutral") return "Neutral";
  if (s === "cautious" || s === "weak" || s === "bearish" || s === "cautionary") return "Cautionary";
  return "Unavailable";
}

function MLHorizonsPanel({ horizons }: { horizons: MLHorizons }) {
  const rows: [string, MLHorizonEntry][] = [
    ["short",  horizons.short],
    ["medium", horizons.medium],
    ["long",   horizons.long],
  ];

  return (
    <div className="mt-2 rounded-lg bg-td-surface2/60 border border-td-line/40 overflow-hidden">
      {/* Header */}
      <div className="grid grid-cols-[100px_1fr_52px_90px] gap-x-3 px-3 py-1.5 bg-td-surface2/80 border-b border-td-line/40">
        <span className="text-[11px] font-semibold text-td-muted uppercase tracking-wide">Horizon</span>
        <span className="text-[11px] font-semibold text-td-muted uppercase tracking-wide">Probability</span>
        <span className="text-[11px] font-semibold text-td-muted uppercase tracking-wide text-right">Prob</span>
        <span className="text-[11px] font-semibold text-td-muted uppercase tracking-wide text-right">Signal</span>
      </div>

      {/* Rows */}
      {rows.map(([key, h]) => {
        const inMlWeight = key === "short";
        const probPct  = h.prob != null ? Math.round(h.prob * 100) : null;
        const barWidth = probPct ?? 0;
        const barColour =
          probPct == null  ? "bg-td-surface2" :
          probPct >= 65    ? "bg-td-accent" :
          probPct >= 50    ? "bg-td-accent" :
          probPct >= 35    ? "bg-td-warn" :
          probPct >= 20    ? "bg-td-warn" :
                             "bg-td-crit";
        const interpKey  = normalizeToneLabel(h.interpretation);
        const ic         = INTERP_COLOUR[interpKey] ?? INTERP_COLOUR.Unavailable;

        return (
          <div
            key={key}
            className={clsx(
              "grid grid-cols-[100px_1fr_52px_90px] gap-x-3 items-center px-3 py-2.5 border-b border-td-line/30 last:border-b-0",
              !inMlWeight && "opacity-[0.78]"
            )}
          >
            {/* Horizon label */}
            <div>
              <p className="text-xs font-semibold text-td-text">{h.description}</p>
              <p className="text-[11px] text-td-muted">{h.label} · P({h.threshold_pct}%+)</p>
              <p
                className={clsx(
                  "text-[10px] mt-0.5 font-medium",
                  inMlWeight ? "text-td-accent/90" : "text-td-muted"
                )}
              >
                {inMlWeight ? "Feeds 20% ML layer" : "Context only — not in weighted score"}
              </p>
            </div>

            {/* Progress bar — dashed / muted track when not the scored horizon */}
            <div
              className={clsx(
                "h-2 rounded-full overflow-hidden",
                inMlWeight ? "bg-td-surface2/60" : "bg-td-surface2/80 border border-dashed border-td-line/50"
              )}
            >
              <div
                className={clsx(
                  "h-full rounded-full transition-all duration-500",
                  barColour,
                  !inMlWeight && "opacity-55"
                )}
                style={{ width: `${barWidth}%` }}
              />
            </div>

            {/* Probability % */}
            <span className={clsx(
              "text-xs font-bold font-mono text-right",
              !inMlWeight && "opacity-80",
              probPct == null  ? "text-td-muted" :
              probPct >= 65    ? "text-td-accent" :
              probPct >= 50    ? "text-td-accent" :
              probPct >= 35    ? "text-td-warn" :
              probPct >= 20    ? "text-td-warn" : "text-td-crit"
            )}>
              {probPct != null ? `${probPct}%` : "N/A"}
            </span>

            {/* Interpretation badge */}
            <div className="flex justify-end">
              <span className={clsx(
                "text-[11px] font-semibold px-2 py-0.5 rounded border",
                ic.text, ic.bg, ic.border,
                !inMlWeight && "opacity-75"
              )}>
                {interpKey}
              </span>
            </div>
          </div>
        );
      })}
      <p className="text-[10px] text-td-muted px-3 py-2 border-t border-td-line/40 leading-snug">
        Only the <span className="text-td-muted font-medium">short</span> row feeds the ML contribution above.
        Medium and long are for context (different horizons, same models) — not averaged into the 20% weight.
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function ConfidenceGauge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const colour =
    pct >= 70 ? "#00C896" :  // fintech.green
    pct >= 40 ? "#F59E0B" : "#FF6B6B"; // fintech.amber / fintech.red

  const r = 38, cx = 50, cy = 52;
  const angle = (pct / 100) * 180;
  const rad   = (angle - 180) * (Math.PI / 180);
  const endX  = cx + r * Math.cos(rad);
  const endY  = cy + r * Math.sin(rad);
  const lArc  = angle > 180 ? 1 : 0;

  return (
    <div
      className="flex flex-col items-center shrink-0"
      title="One 0–100 fuse of regime, chart, ML, options, insiders, fundamentals, and news. Different from the roadmap’s fair value line and from “did they beat EPS last week.”"
    >
      <svg viewBox="0 0 100 58" className="w-28 h-14">
        <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
              fill="none" stroke="#161c2b" strokeWidth="9" strokeLinecap="round" />
        {pct > 0 && (
          <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 ${lArc} 1 ${endX} ${endY}`}
                fill="none" stroke={colour} strokeWidth="9" strokeLinecap="round" />
        )}
        <text x="50" y="49" textAnchor="middle" fontSize="17" fontWeight="800"
              fill={colour} dominantBaseline="auto">{pct}%</text>
      </svg>
      <span className="text-[10px] text-td-muted -mt-1">Model confidence</span>
      <span className="text-[9px] text-td-muted -mt-0.5 max-w-[9rem] text-center leading-tight">7-layer fused (primary)</span>
    </div>
  );
}

function ActionBadge({ action, confidence }: { action: string; confidence: number }) {
  const a = action.toUpperCase();
  const cfg =
    a.includes("STRONG BUY") ? { bg: "bg-td-accent/20", text: "text-td-accent-ink", border: "border-td-accent/50", Icon: TrendingUp } :
    a.includes("BUY")        ? { bg: "bg-td-accent/20",   text: "text-td-accent-ink",   border: "border-td-accent/50",   Icon: TrendingUp } :
    a.includes("REDUCE")     ? { bg: "bg-td-warn/20",   text: "text-td-warn",   border: "border-td-warn/50",   Icon: TrendingDown } :
    a.includes("AVOID")      ? { bg: "bg-td-crit/20",     text: "text-td-crit",     border: "border-td-crit/50",     Icon: TrendingDown } :
    a.includes("WAIT")       ? { bg: "bg-td-crit/15",     text: "text-td-crit",     border: "border-td-crit/55",     Icon: Ban } :
    a.includes("WATCH")      ? { bg: "bg-td-accent/15",    text: "text-td-accent-ink",    border: "border-td-accent/55",    Icon: Eye } :
                               { bg: "bg-td-line/20",   text: "text-td-text",   border: "border-td-line/50",   Icon: Eye };

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
      <span
        className={clsx("inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border text-xs font-bold", cfg.bg, cfg.text, cfg.border)}
        title="Verdict from the fused 7-layer engine (after gates and penalties). REDUCE / WATCH does not automatically mean the stock is “bad forever” — often it means wait for regime or levels to improve."
      >
        <cfg.Icon size={12} />
        {action}
      </span>
      <p className="text-xs text-td-text pl-0.5">{sizeHint}</p>
      {reeval && <p className="text-[11px] text-td-muted pl-0.5">{reeval}</p>}
    </div>
  );
}

function RegimePill({ regime, action }: { regime: string; action?: string }) {
  const a = (action || "").toUpperCase();
  const trimReduce =
    a.includes("REDUCE") || a.includes("TRIM") || a.includes("AVOID") || a.includes("SELL");
  const looksBull = regime.includes("BULL") && !regime.includes("BEAR");
  if (trimReduce && looksBull) {
    return (
      <span
        className="text-[11px] font-semibold px-2 py-0.5 rounded border text-td-warn bg-td-warn/12 border-td-warn/35"
        title="Regime label can lag the action badge — sizing follows the verdict"
      >
        Mixed tape
      </span>
    );
  }
  const colour =
    regime.includes("STRONG_BULL") ? "text-td-accent bg-td-accent/10 border-td-accent/30" :
    regime.includes("BULL")        ? "text-td-accent   bg-td-accent/10   border-td-accent/30"   :
    regime.includes("STRONG_BEAR") ? "text-td-crit     bg-td-crit/10     border-td-crit/30"     :
    regime.includes("BEAR")        ? "text-td-warn  bg-td-warn/10  border-td-warn/30"  :
                                     "text-td-muted   bg-td-line/10   border-td-line/30";
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

  const patternTechnicalSplit = (() => {
    if (layerKey !== "pattern_technical") return null;
    const m = rawLabel.match(/Pattern\s*(\d+)\/100[\s\-–;,:]*technical\s*(\d+)\/100/i);
    if (!m) return null;
    const patternScore = Number.parseInt(m[1], 10);
    const technicalScore = Number.parseInt(m[2], 10);
    if (!Number.isFinite(patternScore) || !Number.isFinite(technicalScore)) return null;
    const gap = technicalScore - patternScore;
    if (gap < 30) return null;
    return `Momentum is improving (${technicalScore}/100), but setup quality is still weak (${patternScore}/100). Indicators track momentum; patterns confirm structure. For a higher-conviction entry, both should align.`;
  })();

  // Score-aware label colour so the description visually echoes the result
  const labelColour = !available
    ? "text-td-muted italic"
    : pct != null && pct >= 70 ? "text-td-accent/90"
    : pct != null && pct >= 40 ? "text-td-warn/90"
    : "text-td-crit/80";

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <Icon size={13} className={available ? "text-td-muted" : "text-td-muted"} />
          <span
            className={clsx("text-xs font-medium truncate cursor-help", available ? "text-td-text" : "text-td-muted")}
            title={LAYER_PLAIN_ENGLISH[layerKey] ?? `Weight in fuse: ${wPct}%.`}
          >
            {meta.name}
          </span>
          <span className="text-[11px] text-td-muted shrink-0">({wPct}%)</span>
        </div>
        <span className={clsx("text-xs font-mono font-bold shrink-0", scoreColourClass(pct, "text"))}>
          {pct != null ? `${pct}%` : "N/A"}
        </span>
      </div>

      {/* Bar — shows dashed outline for unavailable layers */}
      <div className={clsx(
        "w-full rounded-full h-2 overflow-hidden",
        available ? "bg-td-surface2" : "bg-td-surface2/40 border border-dashed border-td-line"
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
      {patternTechnicalSplit && (
        <p className="text-[11px] pl-4 leading-snug text-td-muted">
          {patternTechnicalSplit}
        </p>
      )}
    </div>
  );
}

/** Stacked multipliers after layer blend (HMM bear gate, insider) — from API penalty_audit */
function PenaltyAuditPanel({ pa }: { pa: PenaltyAudit }) {
  const [open, setOpen] = useState(false);
  const hmm = pa.hmm_bear_penalty;
  const ins = pa.insider_sell_penalty;
  const hasStack =
    (hmm?.triggered && hmm.multiplier < 0.999) ||
    (ins?.triggered && ins.multiplier < 0.999);
  if (!hasStack && pa.combined_multiplier == null) return null;

  return (
    <div className="border-t border-td-line/40 pt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs text-td-muted hover:text-td-text transition-colors w-full font-medium text-left"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span>
          Penalty stack
          {pa.combined_multiplier != null && pa.combined_multiplier < 1 && (
            <span className="text-td-warn/90 font-mono ml-1.5">×{pa.combined_multiplier.toFixed(3)}</span>
          )}
        </span>
      </button>
      {open && (
        <div className="mt-2 rounded-lg bg-td-surface2/50 border border-td-line/40 p-3 text-[11px] text-td-muted space-y-2 font-mono">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <span>
              Layer blend: <span className="text-td-text">{Math.round(pa.confidence_blend_only * 100)}%</span>
            </span>
            {pa.confidence_final != null && (
              <span>
                Final: <span className="text-td-accent/90">{Math.round(pa.confidence_final * 100)}%</span>
              </span>
            )}
          </div>
          {hmm?.triggered && (
            <div className="border-t border-td-line/40 pt-2 space-y-0.5">
              <span className="text-td-muted font-td-sans uppercase text-[10px]">HMM bear &gt;80%</span>
              <div className="text-td-text">
                mult {hmm.multiplier_raw != null ? `${hmm.multiplier_raw.toFixed(3)} → ` : ""}
                {hmm.multiplier.toFixed(3)} effective
                {hmm.variant && <span className="text-td-muted"> · {hmm.variant}</span>}
              </div>
              {hmm.bear_probability != null && (
                <div>Bear prob: {(hmm.bear_probability * 100).toFixed(0)}%</div>
              )}
            </div>
          )}
          {ins?.triggered && (
            <div className="border-t border-td-line/40 pt-2">
              <span className="text-td-muted font-td-sans uppercase text-[10px]">Insider sell</span>
              <div className="text-td-text">×{ins.multiplier.toFixed(2)}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Weighted math table — shows exactly how 45% is computed from the layers. */
function WeightedMathTable({ breakdown, confidence, penalty_audit }: {
  breakdown: Record<string, BreakdownLayer>;
  confidence: number;
  penalty_audit?: PenaltyAudit | null;
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
    <div className="border-t border-td-line/40 pt-3">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-xs text-td-muted hover:text-td-text transition-colors w-full font-medium"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span>How is {Math.round(confidence * 100)}% calculated?</span>
      </button>

      {open && (
        <div className="mt-2 rounded-lg bg-td-surface2/50 p-3 text-xs space-y-1.5 font-mono">
          <div className="grid grid-cols-[1fr_44px_44px_56px] gap-x-2 text-td-muted mb-1.5 uppercase text-[11px] font-td-sans font-semibold tracking-wide">
            <span>Layer</span><span className="text-right">Wt</span>
            <span className="text-right">Score</span><span className="text-right">Contrib</span>
          </div>
          {rows.map(r => (
            <div key={r.key} className="grid grid-cols-[1fr_44px_44px_56px] gap-x-2">
              <span className={r.sPct != null ? "text-td-text" : "text-td-muted"}>{r.name}</span>
              <span className="text-right text-td-muted">{r.wPct}%</span>
              <span className={clsx("text-right font-semibold", scoreColourClass(r.sPct, "text"))}>
                {r.sPct != null ? `${r.sPct}%` : "—"}
              </span>
              <span className="text-right text-td-text">
                {r.sPct != null ? `${r.wPct}%×${r.sPct}% = ${(r.contrib * 100).toFixed(1)}` : "—"}
              </span>
            </div>
          ))}
          <div className="border-t border-td-line/50 pt-1.5 mt-1 grid grid-cols-[1fr_44px_44px_56px] gap-x-2">
            <span className="text-td-text col-span-3 font-td-sans">Normalised ÷ {Math.round(activeWeightTotal * 100)}% active weight</span>
            <span className="text-right text-td-accent font-bold">
              = {Math.round((penalty_audit?.confidence_blend_only ?? confidence) * 100)}%
            </span>
          </div>
          {penalty_audit != null &&
            Math.abs(penalty_audit.confidence_blend_only - confidence) > 0.003 && (
            <p className="text-[11px] text-td-warn/85 pt-1 font-td-sans border-t border-td-line/30 mt-1">
              After HMM/insider penalties → <span className="font-mono font-semibold">{Math.round(confidence * 100)}%</span> final
              (see Penalty stack below).
            </p>
          )}
          <p className="text-[11px] text-td-muted pt-1 font-td-sans">
            Unavailable layers (N/A) are excluded and their weight is redistributed.
          </p>
        </div>
      )}
    </div>
  );
}

/** "What would flip this to BUY?" — most actionable section for a trader. */
function FlipToBuy({ breakdown, action, preFlight }: {
  breakdown: Record<string, BreakdownLayer>;
  action: string;
  preFlight?: PreFlightData | null;
}) {
  const isBullish = action.toUpperCase().includes("BUY");
  if (isBullish) return null;

  const TARGETS: Record<string, { threshold: number; label: string }> = {
    lgbm_probability:  { threshold: 0.40, label: "ML Probability" },
    pattern_technical: { threshold: 0.60, label: "Technical setup" },
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

  const regimeGap = gaps.find((g) => g.label === "Regime (HMM)");
  const regimeIsHardBlock =
    regimeGap != null &&
    regimeGap.current != null &&
    regimeGap.current < 25 &&
    regimeGap.needed >= 55;

  const displayGaps = regimeIsHardBlock
    ? [
        ...gaps.filter((g) => g.label === "Regime (HMM)"),
        ...gaps.filter((g) => g.label !== "Regime (HMM)"),
      ]
    : gaps;

  const gateTimeEstimate = (() => {
    const blockingMap: Record<string, string> = {
      "Regime (HMM)": "regime",
      "ML Probability": "ml",
      "Technical setup": "technical",
      "Options Sentiment": "options",
      Fundamentals: "fundamentals",
    };
    const blockingGates = displayGaps.map((g) => blockingMap[g.label] ?? g.label.toLowerCase());
    const rt = preFlight?.regime_transition;
    const shift = rt?.hmm_shift_direction;
    const shiftProbRaw = shift?.shift_probability ?? rt?.shift_probability ?? null;
    const shiftProb = shiftProbRaw != null ? Number(shiftProbRaw) : null;
    const direction = (shift?.shift_direction?.label || shift?.interpretation || rt?.label || "").toString();
    const isLikelyBull = /likely bull/i.test(direction);
    const days = shift?.horizon_days ?? preFlight?.transition_bonus?.days_to_confirm ?? null;

    if (shiftProb != null && shiftProb >= 0.9 && isLikelyBull && days != null) {
      return `${(shiftProb * 100).toFixed(0)}% chance of a likely-bull regime shift within ${days} days — upgrade could come sooner than usual.`;
    }
    if (shiftProb != null && shiftProb >= 0.7 && days != null) {
      return `If regime confirms, upgrade timing is roughly ${days} trading days.`;
    }
    if (blockingGates.length === 1 && blockingGates[0] === "regime") {
      return "Likely needs 15–30 trading days of sustained follow-through.";
    }
    return null;
  })();

  return (
    <div className="rounded-lg border border-td-info/25 bg-td-info/8 p-3.5 space-y-2.5">
      <p className="text-xs font-semibold text-td-info flex items-center gap-1.5">
        <Zap size={13} />
        What would upgrade this to BUY?
      </p>
      {regimeIsHardBlock && (
        <p className="text-[10px] text-td-warn/85 font-medium leading-snug">
          Regime (HMM) is listed first — it is usually the slowest gate. Pattern or ML can improve over days; regime
          alignment typically needs weeks of sustained tape.
        </p>
      )}
      <div className="space-y-2">
        {displayGaps.map((g, i) => {
          const isRegime = g.label === "Regime (HMM)" && regimeIsHardBlock;
          return (
            <div
              key={`${g.label}-${i}`}
              className={clsx(
                "flex items-center justify-between gap-2 rounded-md",
                isRegime && "border-l-2 border-td-warn/70 pl-2 -ml-0.5 bg-td-warn/5 py-1.5"
              )}
            >
              <span className={clsx("text-xs font-medium", isRegime ? "text-td-warn" : "text-td-text")}>
                {g.label}
              </span>
              <div className="flex items-center gap-1.5 text-xs font-mono">
                <span className={clsx("font-semibold", g.current != null ? scoreColourClass(g.current, "text") : "text-td-muted")}>
                  {g.current != null ? `${g.current}%` : "N/A"}
                </span>
                <span className="text-td-muted">→</span>
                <span className="text-td-info font-semibold">needs {g.needed}%+</span>
              </div>
            </div>
          );
        })}
      </div>
      {gateTimeEstimate && (
        <p className="text-[11px] text-td-info/90 border-t border-td-info/20 pt-2.5 leading-snug">
          Estimated time: {gateTimeEstimate}
        </p>
      )}
      {regimeIsHardBlock && (
        <p className="text-[11px] text-td-muted border-t border-td-info/20 pt-2.5 leading-snug">
          <span className="text-td-text font-medium">Regime (HMM)</span> encodes multi-week structure (bull vs bear
          state), not a tweak to chart pattern or ML. Getting from deep bear toward the score this layer needs often takes
          roughly <span className="text-td-text">15–30 trading days</span> of supportive follow-through — not a one- or
          two-day bounce. Expect pattern or ML to move before regime does.
        </p>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  Pre-flight sub-components
// ─────────────────────────────────────────────────────────────────────────────

/** Red banner for instruments that cannot be scored (UVXY, VXX, VIXY) */
function IncompatibleBanner({ ticker, name, flags }: { ticker: string; name: string; flags: PreFlightFlag[] }) {
  return (
    <div className="rounded-xl border border-td-crit/50 bg-td-crit/10 p-5 space-y-3">
      <div className="flex items-center gap-2">
        <Ban size={18} className="text-td-crit shrink-0" />
        <div>
          <p className="text-sm font-bold text-td-crit">{ticker} — {name}</p>
          <p className="text-xs text-td-crit/80">Standard equity model cannot score this instrument</p>
        </div>
      </div>
      <div className="space-y-1.5">
        {flags.map((f, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <AlertTriangle size={12} className="text-td-crit mt-0.5 shrink-0" />
            <span className="text-td-crit/90">{f.message}</span>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-td-muted border-t border-td-crit/20 pt-2">
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
    assetType === "ETF_COMMODITY"      ? "text-td-warn bg-td-warn/10 border-td-warn/30" :
    assetType === "ETF_EQUITY"         ? "text-td-info   bg-td-info/10   border-td-info/30"   :
    assetType === "ETF_VOLATILITY"     ? "text-td-crit    bg-td-crit/10    border-td-crit/30"     :
    assetType === "EQUITY_ADR"         ? "text-td-owner bg-td-owner/10 border-td-owner/30"  :
    assetType === "EQUITY_SPECULATIVE" ? "text-td-warn bg-td-warn/10 border-td-warn/30"  :
    assetType === "EQUITY_DEFENSIVE"   ? "text-td-accent   bg-td-accent/10   border-td-accent/30"    :
                                         "text-td-text  bg-td-line/10  border-td-line/30";
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
            isErr  ? "bg-td-crit/10 border-td-crit/30 text-td-crit" :
            isWarn ? "bg-td-warn/10 border-td-warn/30 text-td-warn" :
                     "bg-td-surface2/30 border-td-line/30 text-td-muted"
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
    coherence.level === "HIGH"       ? { colour: "text-td-accent bg-td-accent/10 border-td-accent/30", dot: "bg-td-accent" } :
    coherence.level === "MODERATE"   ? { colour: "text-td-warn   bg-td-warn/10   border-td-warn/30",   dot: "bg-td-warn"   } :
    coherence.level === "LOW"        ? { colour: "text-td-warn  bg-td-warn/10  border-td-warn/30",  dot: "bg-td-warn"  } :
                                       { colour: "text-td-crit     bg-td-crit/10     border-td-crit/30",     dot: "bg-td-crit"     };
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
    <div className="flex items-start gap-2 bg-td-warn/10 border border-td-warn/35 rounded-lg px-3 py-2.5">
      <Zap size={14} className="text-td-warn mt-0.5 shrink-0" />
      <div className="space-y-0.5">
        <p className="text-xs font-semibold text-td-warn">
          ⚡ Transition Bonus Active
          {bonus.upgrade && <span className="ml-1.5 font-normal text-td-warn/80">→ {bonus.upgrade}</span>}
        </p>
        {bonus.rationale && <p className="text-[11px] text-td-warn/70">{bonus.rationale}</p>}
        {bonus.days_to_confirm && (
          <p className="text-[11px] text-td-muted">Estimated ~{bonus.days_to_confirm} days to bull confirmation</p>
        )}
      </div>
    </div>
  );
}

/** Regime change display — separate blended score vs raw HMM shift probability */
function RegimeTransitionRow({ rt }: { rt: RegimeTransitionData }) {
  const pct   = rt.shift_probability;
  const watch = rt.label === "WATCH_CLOSELY";
  const hm = rt.hmm_next_step;
  const hsd = rt.hmm_shift_direction;
  const exitB = hm?.p_exit_to_bull != null ? hm.p_exit_to_bull * 100 : null;
  const exitBr = hm?.p_exit_to_bear != null ? hm.p_exit_to_bear * 100 : null;
  const stayT = hm?.p_next_transition != null ? hm.p_next_transition * 100 : null;
  const dir = hsd?.shift_direction;
  const spRaw = hsd?.shift_probability;
  const spPct = spRaw != null && spRaw <= 1 ? spRaw * 100 : spRaw;
  return (
    <div className={clsx(
      "rounded-lg px-3 py-2.5 border space-y-1.5",
      watch ? "bg-td-warn/8 border-td-warn/25" : "bg-td-surface2/40 border-td-line/30"
    )}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <ArrowRight size={12} className={watch ? "text-td-warn" : "text-td-muted"} />
          <span className="text-xs font-semibold text-td-text">Regime change score</span>
          {watch && <span className="text-[10px] text-td-warn font-semibold uppercase tracking-wide">Watch Closely</span>}
        </div>
        <span className={clsx("text-xs font-mono font-bold", pct >= 40 ? "text-td-warn" : "text-td-muted")}>
          {pct.toFixed(0)}%
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-td-surface2/60 overflow-hidden">
        <div className={clsx("h-full rounded-full", pct >= 40 ? "bg-td-warn" : "bg-td-line")}
             style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <p className="text-[11px] text-td-muted">
        {pct.toFixed(0)}% blended composite score. Low score can reflect uncertain direction, not low probability of movement.
      </p>
      {hsd?.interpretation && dir && (
        <div className="rounded-md bg-td-surface/60 border border-td-accent/20 px-2.5 py-2 space-y-1">
          <p className="text-[10px] font-semibold text-td-muted uppercase tracking-wide">
            HMM shift projection ({hsd.horizon_days ?? 10}d)
            {spPct != null && (
              <span className="text-td-muted font-normal normal-case">
                {" "}· leave dominant bucket ~{spPct.toFixed(0)}%
              </span>
            )}
          </p>
          {dir.label && (
            <p className={clsx(
              "text-xs font-semibold",
              dir.color === "green" && "text-td-accent",
              dir.color === "red" && "text-td-crit",
              dir.color === "amber" && "text-td-warn",
            )}>
              {dir.label}
            </p>
          )}
          <p className="text-[11px] text-td-text leading-snug">
            {hsd.interpretation}
          </p>
          {spPct != null && (
            <p className="text-[10px] text-td-muted leading-snug">
              Plain English: HMM sees about {spPct.toFixed(0)}% chance the current regime shifts within{" "}
              {hsd.horizon_days ?? 10} days; uncertainty in direction is why blended regime change score is {pct.toFixed(0)}%.
            </p>
          )}
          <p className="text-[10px] text-td-muted">
            Mass after horizon (excl. sticky bucket): Bull {(dir.bull * 100).toFixed(0)}% · Bear {(dir.bear * 100).toFixed(0)}%
            {dir.transition_cycle != null && dir.transition_cycle > 0.02 && (
              <> · Transition cycle {(dir.transition_cycle * 100).toFixed(0)}%</>
            )}
          </p>
        </div>
      )}
      {hm && exitB != null && exitBr != null && (
        <div className="rounded-md bg-td-surface/50 border border-td-line/40 px-2.5 py-2 space-y-1">
          <p className="text-[10px] font-semibold text-td-muted uppercase tracking-wide">HMM one-step (from transition state)</p>
          <p className="text-[11px] text-td-text leading-snug">
            If latent state were transition: next bar → Bull{" "}
            <span className="font-mono text-td-accent/90">{(hm.p_next_bull * 100).toFixed(0)}%</span>
            {" · "}Bear{" "}
            <span className="font-mono text-td-crit/90">{(hm.p_next_bear * 100).toFixed(0)}%</span>
            {stayT != null && (
              <>
                {" · "}Stay transition{" "}
                <span className="font-mono text-td-text">{stayT.toFixed(0)}%</span>
              </>
            )}
          </p>
          <p className="text-[10px] text-td-muted leading-snug">
            Conditional on exiting transition (Bull vs Bear only):{" "}
            <span className="text-td-accent/85 font-mono">{exitB.toFixed(0)}%</span>
            {" / "}
            <span className="text-td-crit/85 font-mono">{exitBr.toFixed(0)}%</span>
          </p>
        </div>
      )}
    </div>
  );
}

/** Signal divergence (options vs ML conflict) indicator */
function DivergenceRow({ div: d }: { div: DivergenceData }) {
  if (!d) return null;
  const cfg =
    d.label === "EXTREME"  ? { colour: "text-td-crit bg-td-crit/10 border-td-crit/30" } :
    d.label === "HIGH"     ? { colour: "text-td-warn bg-td-warn/10 border-td-warn/30" } :
    d.label === "MODERATE" ? { colour: "text-td-warn bg-td-warn/10 border-td-warn/30" } :
                             { colour: "text-td-muted bg-td-surface2/20 border-td-line/20" };
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
    bullish ? "text-td-accent bg-td-accent/10 border-td-accent/25" :
    bearish ? "text-td-crit     bg-td-crit/10     border-td-crit/25"     :
              "text-td-muted   bg-td-surface2/20   border-td-line/20";
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
    <div className="border-t border-td-line/40 pt-3">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-xs text-td-muted hover:text-td-text transition-colors w-full font-medium"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span>Conditional Playbook</span>
        {active && (
          <span className="ml-1.5 text-[10px] text-td-warn bg-td-warn/15 border border-td-warn/30 px-1.5 py-0.5 rounded font-semibold">
            ACTIVE: {active.name}
          </span>
        )}
        {!active && (
          <span className="ml-1.5 text-[10px] text-td-muted">
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
                ? "bg-td-warn/10 border-td-warn/30"
                : "bg-td-surface2/30 border-td-line/30 opacity-70"
            )}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  {s.condition_met
                    ? <CheckCircle size={13} className="text-td-warn shrink-0" />
                    : <div className="w-3 h-3 rounded-full border border-td-line shrink-0" />}
                  <span className={clsx("text-xs font-semibold", s.condition_met ? "text-td-warn" : "text-td-muted")}>
                    {s.scenario_id}. {s.name}
                  </span>
                </div>
                <span className="text-[10px] text-td-muted shrink-0">{s.mode.replace(/_/g, " ")}</span>
              </div>
              <p className="text-[11px] text-td-muted pl-5">{s.condition_desc}</p>
              <p className={clsx("text-xs font-medium pl-5", s.condition_met ? "text-td-warn" : "text-td-muted")}>
                → {s.action}
              </p>
              {s.condition_met && Object.entries(s.details).length > 0 && (
                <div className="pl-5 space-y-1">
                  {Object.entries(s.details).map(([k, v]) => (
                    <div key={k} className="flex items-baseline gap-1.5 text-[11px]">
                      <span className="text-td-muted capitalize">{k.replace(/_/g, " ")}:</span>
                      <span className="text-td-text">{v}</span>
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
  const actionUpper = (data.action || "").toUpperCase();
  const showRiskOffHint =
    actionUpper.includes("REDUCE") ||
    actionUpper.includes("TRIM") ||
    actionUpper.includes("AVOID") ||
    actionUpper.includes("SELL");
  // Only show non-INCOHERENT coherence message since INCOHERENT is in disqualifiers
  const incoherent       = coherence?.level === "INCOHERENT";

  return (
    <div className={clsx(
      "rounded-xl border bg-td-surface p-5 space-y-4",
      isStrongSignal  ? "border-td-accent/40" :
      incoherent      ? "border-td-crit/40"     :
                        "border-td-line/60"
    )}>
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-lg font-bold text-td-text">{data.ticker}</span>
            <RegimePill regime={data.market_regime ?? "UNKNOWN"} action={data.action} />
            {breakdown.regime_hmm?.label && (
              <span
                className="text-[10px] text-td-muted max-w-[14rem] leading-snug"
                title="Same HMM label as the Regime (HMM) layer below"
              >
                {breakdown.regime_hmm.label}
              </span>
            )}
            {pf?.asset_type && (
              <AssetTypeBadge assetType={pf.asset_type} weightLabel={pf.weight_label} />
            )}
            {coherence && <CoherenceBadge coherence={coherence} />}
          </div>
          <ActionBadge action={data.action ?? "WATCH"} confidence={confidence} />
          <p className="text-[11px] text-td-muted leading-snug max-w-[68ch] border-l-2 border-td-line/60 pl-2.5 py-1">
            <span className="text-td-muted font-medium">Model confidence vs roadmap:</span> the gauge is the 7-layer fused
            score (regime, technical setup layer, short-horizon ML, options, fundamentals, etc.). It is not the same number
            as the rule-based “technical composite” on the price card. The roadmap is a <span className="text-td-muted">conditional staged plan</span> (MA tiers, targets). Low model confidence means today’s fused read is cautious — not that a future add at a lower tier is impossible.
          </p>
          {actionSummary && (
            <div className="space-y-1">
              <p
                className="text-sm text-td-text leading-snug max-w-[64ch] cursor-help"
                title={PRIMARY_ACTION_SUMMARY_HINT}
              >
                {actionSummary}
              </p>
              {showRiskOffHint && (
                <p className="text-[10px] text-td-muted leading-snug max-w-[68ch] pl-0.5">
                  {RISK_OFF_ACTION_HINT}
                </p>
              )}
            </div>
          )}
          {pf?.reassess_guidance?.display && (
            <p className="text-[11px] text-td-muted leading-snug max-w-[68ch] border-l border-td-warn/30 pl-2.5">
              <span className="text-td-warn/90 font-medium">Re-evaluate: </span>
              {pf.reassess_guidance.display}
            </p>
          )}
          <p className="text-[11px] text-td-muted">
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
        <div className="flex items-start gap-2 bg-td-crit/10 border border-td-crit/30 rounded-lg px-3 py-2.5">
          <AlertTriangle size={13} className="text-td-crit mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-semibold text-td-crit">Incoherent signals — do not trade on this</p>
            <p className="text-[11px] text-td-crit/70 mt-0.5">{coherence?.message}</p>
          </div>
        </div>
      )}

      {/* Regime tension: bull high but shift prob also high */}
      {pf?.regime_tension_note && (
        <div className="flex items-start gap-2 bg-td-warn/10 border border-td-warn/30 rounded-lg px-3 py-2.5">
          <AlertTriangle size={13} className="text-td-warn mt-0.5 shrink-0" />
          <p className="text-xs text-td-warn">{pf.regime_tension_note}</p>
        </div>
      )}

      {/* Transition bonus banner */}
      {transitionBonus && <TransitionBonusBanner bonus={transitionBonus} />}

      {/* Strong signal highlight */}
      {isStrongSignal && !hasDisqualifiers && !incoherent && (
        <div className="flex items-start gap-2 bg-td-accent/10 border border-td-accent/30 rounded-lg px-3 py-2.5">
          <Zap size={13} className="text-td-accent mt-0.5 shrink-0" />
          <span className="text-xs text-td-accent">
            High-conviction setup across multiple independent signal layers
          </span>
        </div>
      )}

      {/* Hard disqualifiers */}
      {hasDisqualifiers && (
        <div className="space-y-1.5">
          {disqualifiers.map((d, i) => (
            <div key={i} className="flex items-start gap-2 bg-td-crit/10 border border-td-crit/30 rounded-lg px-3 py-2">
              <AlertTriangle size={12} className="text-td-crit mt-0.5 shrink-0" />
              <span className="text-xs text-td-crit">{d}</span>
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
            {key === "nlp_sentiment" &&
              (layer as BreakdownLayer).weight != null &&
              Number((layer as BreakdownLayer).weight) > 0 && (
                <p className="text-[10px] text-td-info/85 pl-4 -mt-0.5 leading-snug">
                  Headlines feed in as a <span className="font-semibold">weighted</span> input (
                  {Math.round(Number((layer as BreakdownLayer).weight) * 100)}% of the fuse) — not a standalone
                  buy/sell vote; keep this row visible when judging tone vs price action.
                </p>
              )}
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
      <WeightedMathTable
        breakdown={breakdown as Record<string, BreakdownLayer>}
        confidence={confidence}
        penalty_audit={data.penalty_audit ?? null}
      />

      {/* Layer blend vs multiplicative penalties (for charts / transparency) */}
      {data.penalty_audit && <PenaltyAuditPanel pa={data.penalty_audit} />}

      {/* What would flip this to BUY */}
      <FlipToBuy
        breakdown={breakdown as Record<string, BreakdownLayer>}
        action={data.action ?? "WATCH"}
        preFlight={data.pre_flight ?? null}
      />

      {/* Risk factors */}
      {riskFactors.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-semibold text-td-text uppercase tracking-wide">Key Risks</p>
          {riskFactors.map((r, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-td-text">
              <AlertTriangle size={12} className="text-td-warn mt-0.5 shrink-0" />
              {r}
            </div>
          ))}
        </div>
      )}

      {/* Watch levels — expandable */}
      {data.watch_levels && (
        <div className="border-t border-td-line/40 pt-3">
          <button
            onClick={() => setShowWatchLevels(v => !v)}
            className="flex items-center gap-1.5 text-[11px] text-td-muted hover:text-td-text transition-colors w-full"
          >
            {showWatchLevels ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            <span>Watch levels & thesis invalidation</span>
          </button>
          {showWatchLevels && (
            <div className="mt-2 bg-td-surface2/60 rounded-lg p-3 space-y-2">
              <WatchRow label="Invalidation price" value={`$${data.watch_levels.invalidation_below.toFixed(2)}`} highlight="red" note="Break below = exit" />
              <WatchRow label="Support (MA50)"     value={`$${data.watch_levels.key_support_ma50.toFixed(2)}`}   highlight="amber" />
              <WatchRow label="Support (MA200)"    value={`$${data.watch_levels.key_support_ma200.toFixed(2)}`}  highlight="amber" />
              <WatchRow label="Current price"      value={`$${data.watch_levels.current_price.toFixed(2)}`}      highlight="green" />
              <p className="text-[11px] text-td-muted leading-snug pt-1">{data.watch_levels.note}</p>
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
    highlight === "red"   ? "text-td-crit"    :
    highlight === "amber" ? "text-td-warn"  : "text-td-accent";
  return (
    <div className="flex items-center justify-between gap-2">
      <div>
        <span className="text-[11px] text-td-muted">{label}</span>
        {note && <span className="text-[10px] text-td-muted ml-1.5">— {note}</span>}
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
      <div className="rounded-xl border border-td-line/60 bg-td-surface p-6 text-center text-td-muted text-sm">
        No confidence data available
      </div>
    );
  }

  const sorted = [...items].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-td-text">{title}</h3>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {sorted.map(item => (
          <ConfidenceBreakdown key={item.ticker} data={item} />
        ))}
      </div>
    </div>
  );
}
