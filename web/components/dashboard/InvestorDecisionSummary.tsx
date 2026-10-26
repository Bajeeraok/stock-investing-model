"use client";

import React, { useState } from "react";
import { clsx } from "clsx";
import {
  CheckCircle,
  XCircle,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  AlertTriangle,
  Info,
  Zap,
  TrendingUp,
  Calendar,
  Target,
  Sun,
  CloudSun,
  CloudRain,
  Cloud,
} from "lucide-react";
import type { TradeRoadmapData } from "./TradeRoadmapCard";
import {
  buildPatternDecisionDriverSummary,
  buildMlHorizonGapExplainer,
  marketWeatherFromRegimeBull,
  type MarketWeather,
} from "./patternDecisionDriver";
import {
  BehavioralActionBadge,
  buildGatesFromInvestorSummary,
  deriveLongTermBehavioralBadge,
  deriveShortTermBehavioralBadge,
  filterPrimaryTradingGates,
  HorizonDivergenceNote,
  LongTermTierLadder,
  PlainEnglishTakeCard,
  resolveLongHorizonEntryZone,
  EntryZonePriceBar,
  LongTermAccumulationScale,
  RiskRewardThermometer,
  StopHierarchyPanel,
  StopTargetRiskBar,
  TradingGateStatus,
} from "./retailActionUX";
import { HorizonProjectionChart, type PriceHistoryPoint } from "./HorizonProjectionChart";
import { StreetVsModelBar } from "./StreetVsModelBar";
import { ValuationDeck } from "./ValuationDeck";
import { ExecutionPlanRationale } from "./ExecutionPlanRationale";
import { StreetSentimentChip } from "./StreetSentimentChip";
import { PositionIntentChip } from "./PositionIntentChip";
import { TickerMarketContextCard, type TickerMarketContext } from "./TickerMarketContextCard";
import type { TacticalEntryPayload } from "./TacticalEntryPanel";
import {
  type DecisionMode,
  primaryHorizonFromMode,
  horizonLabel,
} from "@/lib/decisionMode";

export type { TacticalEntryPayload };

const STRENGTH_CONVICTION_HINT =
  "Strength = this horizon's ML signal tier (how bullish the model read is for that specific window). " +
  "Conviction = how confident the fused stack is about acting on that horizon (timing / sizing). " +
  "They can disagree: e.g. a statistically strong 3-month window can still show Low conviction if regime or other layers want more proof.";

function horizonVerdictPillClass(v: string | undefined): string {
  const u = String(v || "").toUpperCase();
  if (u === "STRONG BUY" || u === "BUY") return "border-td-accent/55 bg-td-accent/15 text-td-accent-ink";
  if (u === "WATCH") return "border-td-accent/55 bg-td-accent/12 text-td-accent-ink";
  if (u === "WAIT") return "border-td-crit/55 bg-td-crit/12 text-td-crit";
  return "border-td-line bg-td-surface2/80 text-td-text";
}

// Use bracket types to avoid ambiguous generics in .tsx (Array<T> can be parsed as JSX)
export interface FairValueMetadata {
  bear_case?: number | null;
  method_used?: string | null;
  methodology_summary?: string | null;
  notes?: string[] | null;
  ttm_eps?: number | null;
  forward_eps?: number | null;
  sector_pe_used?: number | null;
  sector_forward_pe_used?: number | null;
  model_fair_value_usd?: number | null;
  street_anchor_usd?: number | null;
  street_anchor_source?: string | null;
  growth_raw_pct?: number | null;
  growth_used_pct?: number | null;
  growth_was_capped?: boolean;
  fv_suppressed?: boolean;
  fv_suppressed_reason?: string | null;
  fv_street_anchored?: boolean;
  fv_street_anchor_usd?: number | null;
  fv_street_anchor_source?: string | null;
  fv_route_method_label?: string | null;
  gap_badge_type?: string | null;
  divergence_pct?: number | null;
  geopolitical_cap?: boolean;
}

/** One sentence answer: "Should I buy/sell today, and if not, at what price and when?" */
export interface OneAnswer {
  headline: string;
  subline?: string | null;
  verdict: string;
  action_today: string;
  bottom_line?: string | null;
  why_this_call?: string[];
  next_trigger?: string | null;
  execution_plan_lines?: string[];
  signal_reconciliation_notes?: string[];
  /** When bull regime + near highs + rising ML clash with stretched FV (catalyst / momentum risk). */
  momentum_valuation_tension?: {
    active: boolean;
    headline: string;
    detail: string;
    premium_vs_fair_value_pct?: number;
    regime_bull_pct?: number;
    momentum_target?: number;
    momentum_target_method?: string;
    momentum_stop?: number;
    momentum_upside_pct?: number;
    momentum_risk_pct?: number;
    catalyst_active?: boolean;
  } | null;
  /** Strong non-bull HMM vs price at highs — regime is macro-heavy, not necessarily name weakness. */
  ath_macro_regime_disconnect?: {
    active: boolean;
    headline: string;
    detail: string;
    non_bull_pct?: number;
  } | null;
  /** Retail: hold 5–10y vs take profits — education + tie-in to today's signals */
  hold_vs_trade?: {
    title: string;
    long_term: string;
    short_term: string;
    signal_bridge: string;
    disclaimer: string;
  } | null;
  /** MA/RSI screener-style context (no extra API). */
  external_context?: import("./ExternalContextChip").ExternalContextPayload | null;
  /** ST in-zone + enter_now but spot above LT core tier — reconciles conflicting bands. */
  horizon_zone_reconciliation?: import("@/lib/horizonReconcile").HorizonZoneReconciliation | null;
}

/** Trader roadmap: short/medium entry, stop, target, when to act. */
export interface TraderRoadmap {
  verdict: string;
  action_today: string;
  short: {
    entry_zone: { low: number; high: number } | null;
    stop: number | null;
    target: number | null;
    target_pct: number | null;
    timeframe: string;
    trigger: string;
  };
  medium: {
    entry_zone: { low: number; high: number } | null;
    stop: number | null;
    target: number | null;
    timeframe: string;
    trigger: string;
  };
}

/** Investor roadmap: tiered add levels, trim near FV, hold thesis. */
export interface InvestorRoadmap {
  verdict: string;
  action_today: string;
  add_tiers: { id?: string; label?: string; low?: number; high?: number; allocation_pct?: number }[];
  trim_near: number;
  hold_thesis: string;
}

/** Compare headline model fair value to vendor analyst targets (Yahoo + FMP when available). */
export interface FairValueVsExternal {
  yahoo_12m_mean_usd?: number | null;
  pct_model_vs_yahoo_mean?: number | null;
  fmp_consensus_low_usd?: number | null;
  fmp_consensus_high_usd?: number | null;
  fmp_consensus_median_usd?: number | null;
  /** True when median was inferred as (low+high)/2 — label as range midpoint, not analyst median. */
  fmp_median_is_range_midpoint?: boolean | null;
  pct_model_vs_fmp_median?: number | null;
  street_primary_source?: "fmp" | "yahoo" | null;
  note?: string | null;
}

export type { ValuationDeckPayload } from "./valuationDeckTypes";

export interface InvestorDecisionSummary {
  fair_value: number;
  overall_verdict: "WAIT" | "WATCH" | "BUY" | "STRONG BUY";
  /** HMM label when provided by API (e.g. Bull / Non-bull) — optional display */
  regime_hmm_label?: string | null;
  regime_bull_pct?: number | null;
  regime_momentum_extended?: boolean | null;
  model_confidence_pct?: number | null;
  /** 14-day RSI used for short-horizon entry logic. */
  rsi?: number | null;
  /** TTM PE used for fair value (FMP > price/trailingEps > yfinance). Shown so card reflects correct PE, not stale feed. */
  ttm_pe_used?: number;
  /** Forward PE used for fair value when available. */
  forward_pe_used?: number;
  /** Bear case, method, and notes so users can interrogate FV vs lt_band. */
  fair_value_metadata?: FairValueMetadata | null;
  /** Model FV vs Yahoo mean and FMP consensus (when API key present). */
  fair_value_vs_external?: FairValueVsExternal | null;
  /** Street + model + house valuation deck (FMP-primary street). */
  valuation_deck?: import("./valuationDeckTypes").ValuationDeckPayload | null;
  /** Short-term pattern score (0-100); when low, show signal-deterioration banner. */
  pattern_score?: number | null;
  /** Optional half-position insurance (stock below MA200 or SPY risk-off); default stays HOLD. */
  protect_mode?: import("./ProtectModeCard").ProtectModePayload | null;
  /** Confidence-adjusted headline (gates × fused confidence). setup_quality = raw pattern. */
  actionable_score?: {
    setup_quality?: number | null;
    actionable?: number | null;
    stale?: boolean;
    suppressed?: boolean;
    note?: string;
    factors?: Record<string, number | null | undefined>;
  } | null;
  /** Backend-enriched gates, rsi_status, gate_cleared (source of truth for UI styling). */
  retail_action?: import("./retailActionUX").RetailActionPayload | null;
  /** Composed swing play sheet — levels from horizons.short. */
  swing_setup?: import("./HorizonPlaybookCard").HorizonPlaybookPayload | null;
  /** All horizon playbooks: swing, position build, thesis & tiers. */
  horizon_playbooks?: import("./HorizonPlaybookCard").HorizonPlaybooksBundle | null;
  /** Velocity/tactical breakout panel payload (RVOL, BB, T1/T2, T+5). */
  tactical_entry?: TacticalEntryPayload | null;
  /** One Answer + Trader / Investor roadmaps (retail design). */
  one_answer?: OneAnswer | null;
  trader_roadmap?: TraderRoadmap | null;
  investor_roadmap?: InvestorRoadmap | null;
  /** Complete Trade Roadmap: buy/sell stages + trader summary (tabbed card). */
  trade_roadmap?: TradeRoadmapData | null;
  /** Plain-language model reasoning (factors + wait timeframe). Aliased to the Scout persona. */
  signal_reason?: import("./tickerDetail/SignalReasonCard").SignalReasonPayload | null;
  /** Same reasoning, once per persona (Scout/Swing/Owner) — different framing/time horizon. */
  signal_reason_by_persona?: import("./tickerDetail/SignalReasonCard").SignalReasonByPersona | null;
  horizons: {
    short: HorizonSignalPayload;
    medium: HorizonSignalPayload;
    long: HorizonSignalPayload;
  };
  /** Spot extended above FV — all plans are conditional pullbacks. */
  plan_mode?: "pullback_conditional" | string | null;
  chase_banner?: string | null;
  chase_detail?: string | null;
  fv_staleness?: {
    flagged?: boolean;
    sigma_vs_atr?: number;
    spot?: number;
    fair_value?: number;
    note?: string;
  } | null;
}

export interface HorizonSignalPayload {
  label: string;
  duration: string;
  verdict: string;
  signal: string;
  conviction: string;
  ml_prob: number;
  entry_zone: {
    low: number;
    high: number;
    anchor: string;
    quality: string;
    quality_color: string;
    spot_position?: {
      state?: string;
      band_low?: number;
      band_high?: number;
      gap_pct?: number;
      next_add_at?: number;
      label?: string;
      detail?: string;
      cross_gap?: {
        state?: string;
        floor_horizon?: string;
        ceiling_horizon?: string;
        floor_band_high?: number;
        ceiling_band_low?: number;
        label?: string;
        detail?: string;
        next_scout_add_at?: number;
        next_swing_add_at?: number;
        bridge_band?: {
          low?: number;
          high?: number;
          label?: string;
          levels?: Array<{ id: string; label: string; price: number; role?: string }>;
        };
      };
      in_bridge_band?: boolean;
      bridge_band?: {
        low?: number;
        high?: number;
        label?: string;
        levels?: Array<{ id: string; label: string; price: number; role?: string }>;
      };
    };
    levels?: Array<{
      id: string;
      label: string;
      price: number;
      role?: string;
    }>;
  };
  /** Next support / resistance for this horizon (omitted when none sits nearby). */
  nearby_sr?: {
    next_support?: { price: number; label: string; dist_pct: number } | null;
    next_resistance?: { price: number; label: string; dist_pct: number } | null;
    support_stack?: Array<{ price: number; label: string; dist_pct: number }>;
    resistance_stack?: Array<{ price: number; label: string; dist_pct: number }>;
  } | null;
  /** Historical EOD touch stats for this entry band (not paper trades). */
  entry_touch_forecast?: {
    horizon?: string;
    window_sessions?: number;
    spot_vs_band?: string;
    touch_probability_pct?: number;
    median_sessions_to_touch?: number | null;
    sample_n?: number;
    data_source?: string;
    note?: string;
  } | null;
  target: number;
  target_pct: number;
  stop_loss: number;
  stop_loss_pct: number;
  risk_reward: number;
  /** R:R from entry midpoint (pullback-plan quality) — preferred over spot-based risk_reward when extended. */
  risk_reward_from_entry?: number | null;
  /** False when plan fails edge / R:R / touch gates — UI shows "No setup at this horizon". */
  setup_viable?: boolean | null;
  setup_status?: "ok" | "no_setup" | string | null;
  plan_mode?: "pullback_conditional" | string | null;
  target_basis?: string | null;
  forward_fair_value?: number | null;
  rationale: string;
  trigger_buy: string;
  warnings: string[];
  /** "trailing" for short/medium; long-term uses structural_invalidation for 52w-floor level */
  stop_loss_kind?: string | null;
  /** Explains wide long-term level vs a normal stop */
  stop_loss_framing?: string | null;
  entry_tiers?: {
    active_tier_id?: string | null;
    target_tier_id?: string | null;
    spot_position?: {
      state?: string;
      floor_tier_id?: string;
      ceiling_tier_id?: string;
      floor_band_high?: number;
      ceiling_band_low?: number;
      next_add_tier_id?: string;
      label?: string;
      detail?: string;
      below_all_within_mos?: boolean;
      in_bridge_band?: boolean;
      bridge_band?: {
        low?: number;
        high?: number;
        center?: number;
        gap_low?: number;
        gap_high?: number;
        label?: string;
        max_allocation_pct?: number;
        detail?: string;
        levels?: Array<{ id: string; label: string; price: number; role?: string }>;
      };
    };
    current_assessment: {
      verdict: string;
      label: string;
      color?: string;
      margin_of_safety_pct?: number | null;
      min_price_to_buy?: number | null;
      above_full_mos_ceiling?: boolean;
      within_full_mos_ceiling?: boolean;
      full_size_eligible_at_spot?: boolean;
      full_size_ceiling_label?: string | null;
      position_mode?: string | null;
      reference_levels?: {
        ma50?: number;
        ma200?: number;
        tier1_band?: { low: number; high: number };
      };
    };
    tiers: {
      id: string;
      label: string;
      description: string;
      low: number;
      high: number;
      upside_to_fv_pct: number;
      margin_of_safety_pct: number;
      estimated_rr: string;
      conviction: string;
      color: string;
      reachable: boolean;
      drop_needed_pct: number | null;
      levels?: Array<{ id: string; label: string; price: number; role?: string }>;
    }[];
    position_sizing?: { tier: string; allocation_pct: number; note: string }[];
    structural_invalidation?: {
      price: number;
      kind: string;
      note: string;
    };
  };
  fair_value?: number;
}

function regimeWeatherIcon(weather: MarketWeather) {
  const cls = "h-3.5 w-3.5 shrink-0";
  switch (weather) {
    case "favorable":
      return React.createElement(Sun, { className: `${cls} text-td-warn`, "aria-hidden": true });
    case "mixed":
      return React.createElement(CloudSun, { className: `${cls} text-td-muted`, "aria-hidden": true });
    case "stormy":
      return React.createElement(CloudRain, { className: `${cls} text-td-info`, "aria-hidden": true });
    case "extended":
      return React.createElement(CloudSun, { className: `${cls} text-td-warn`, "aria-hidden": true });
    default:
      return React.createElement(Cloud, { className: `${cls} text-td-muted`, "aria-hidden": true });
  }
}

function verdictIcon(verdict: string) {
  switch (verdict) {
    case "STRONG BUY":
    case "BUY":
      return <CheckCircle className="h-4 w-4 text-td-accent shrink-0" aria-hidden />;
    case "WATCH":
      return <AlertCircle className="h-4 w-4 text-td-accent shrink-0" aria-hidden />;
    case "WAIT":
      return <XCircle className="h-4 w-4 text-td-crit shrink-0" aria-hidden />;
    default:
      return <XCircle className="h-4 w-4 text-td-crit shrink-0" aria-hidden />;
  }
}

function HorizonCard({
  horizon,
  horizonKind,
  entryTiers,
  tiersOpen,
  onToggleTiers,
  showTierLadder = true,
  currentPrice,
  regimeBullPct,
  assessmentPct,
  shortHorizon,
  rsi,
  density = "detail",
}: {
  horizon: HorizonSignalPayload;
  horizonKind: "short" | "medium" | "long";
  entryTiers?: HorizonSignalPayload["entry_tiers"];
  tiersOpen?: boolean;
  onToggleTiers?: () => void;
  showTierLadder?: boolean;
  currentPrice: number;
  regimeBullPct?: number | null;
  assessmentPct: number;
  shortHorizon?: HorizonSignalPayload;
  rsi?: number | null;
  density?: "scan" | "detail";
}) {
  const scan = density === "scan";
  const behavioralBadge =
    horizonKind === "short"
      ? deriveShortTermBehavioralBadge(horizon, regimeBullPct, rsi)
      : horizonKind === "long" && shortHorizon
        ? deriveLongTermBehavioralBadge(horizon, shortHorizon, assessmentPct, currentPrice)
        : null;
  const showMediumBadge = horizonKind === "medium";
  const mediumBadgeLabel =
    horizon.verdict === "BUY" || horizon.verdict === "STRONG BUY"
      ? { emoji: "🟢", label: "SWING ADD ZONE", tone: "green" as const }
      : horizon.verdict === "WATCH"
        ? { emoji: "🟡", label: "STAGE ON PULLBACK", tone: "amber" as const }
        : { emoji: "🔴", label: "WAIT — NO ADD", tone: "red" as const };
  const [showCaveats, setShowCaveats] = useState(false);
  const ezResolved =
    horizonKind === "long" && entryTiers
      ? resolveLongHorizonEntryZone(horizon, entryTiers, currentPrice)
      : null;
  const ez = ezResolved
    ? { ...horizon.entry_zone, low: ezResolved.low, high: ezResolved.high }
    : horizon.entry_zone;
  const entryTierPrefix =
    ezResolved?.tierId && horizonKind === "long"
      ? `Entry (${ezResolved.tierId}): `
      : "Entry: ";
  const verdictClass =
    horizon.verdict === "BUY" || horizon.verdict === "STRONG BUY"
      ? "text-td-accent"
      : horizon.verdict === "WATCH"
        ? "text-td-accent"
        : horizon.verdict === "WAIT"
          ? "text-td-crit"
          : "text-td-crit";
  const hasRationale = horizon.rationale && horizon.rationale.trim().length > 0;
  const hasTrigger = horizon.trigger_buy && horizon.trigger_buy.trim().length > 0;
  const warnings = Array.isArray(horizon.warnings) ? horizon.warnings.filter((w) => w && String(w).trim()) : [];
  const triggerLine = hasTrigger ? String(horizon.trigger_buy).trim() : "Wait for setup confirmation.";
  const hasStop = horizon.stop_loss != null && horizon.stop_loss > 0;
  const structuralStop = horizon.stop_loss_kind === "structural_invalidation";
  const noSetup = horizon.setup_status === "no_setup" || horizon.setup_viable === false;
  const touchPct = horizon.entry_touch_forecast?.touch_probability_pct;

  return React.createElement(
    "div",
    {
      className: clsx(
        "bg-td-surface2 border rounded-lg p-3 text-sm",
        noSetup ? "border-td-line/80 opacity-80" : "border-td-line",
      ),
    },
    noSetup &&
      React.createElement(
        "div",
        { className: "mb-2 rounded border border-td-warn/30 bg-td-warn-weak/20 px-2 py-1.5" },
        React.createElement(
          "p",
          { className: "text-[11px] font-semibold uppercase tracking-wide text-td-warn" },
          "No setup at this horizon",
        ),
        React.createElement(
          "p",
          { className: "text-[11px] text-td-warn/70 mt-0.5 leading-snug" },
          "Edge or R:R from the entry band fails the quality gate — levels kept for context only.",
        ),
      ),
    !noSetup &&
      touchPct != null &&
      React.createElement(
        "p",
        { className: "mb-2 text-[10px] text-td-muted" },
        `Historical band touch ~${Number(touchPct).toFixed(0)}%` +
          (horizon.entry_touch_forecast?.median_sessions_to_touch != null
            ? ` · median ${horizon.entry_touch_forecast.median_sessions_to_touch} sessions`
            : ""),
      ),
    (behavioralBadge || showMediumBadge) &&
      React.createElement(
        "div",
        { className: "mb-2" },
        behavioralBadge
          ? React.createElement(BehavioralActionBadge, { badge: behavioralBadge })
          : React.createElement(BehavioralActionBadge, { badge: mediumBadgeLabel })
      ),
    horizonKind === "short" &&
      hasStop &&
      horizon.target > 0 &&
      currentPrice > 0 &&
      React.createElement(
        "div",
        { className: "mb-2 rounded-lg border border-td-line/70 bg-td-bg/50 p-2" },
        horizon.target > horizon.stop_loss
          ? React.createElement(StopTargetRiskBar, {
              stopLoss: horizon.stop_loss,
              target: horizon.target,
              currentPrice,
            })
          : React.createElement(RiskRewardThermometer, { riskReward: horizon.risk_reward })
      ),
    React.createElement(
      "div",
      { className: "flex items-center justify-between gap-2 mb-2" },
      React.createElement("span", { className: "font-medium text-td-text" }, horizon.label),
      React.createElement(
        "span",
        { className: "flex items-center gap-1" },
        verdictIcon(horizon.verdict),
        React.createElement("span", { className: verdictClass }, horizon.verdict)
      )
    ),
    React.createElement(
      "p",
      {
        className: "text-td-muted text-xs flex items-center gap-1.5 flex-wrap",
      },
      React.createElement(
        "span",
        {
          className: "cursor-help border-b border-dotted border-td-line/50",
          title: STRENGTH_CONVICTION_HINT,
        },
        `${horizon.signal} strength · ${horizon.conviction} conviction`
      ),
      React.createElement(
        "span",
        { className: "inline-flex shrink-0", title: STRENGTH_CONVICTION_HINT, "aria-label": "Strength vs conviction" },
        React.createElement(Info, { className: "h-3.5 w-3.5 text-td-muted cursor-help" })
      )
    ),
    ez.low > 0 &&
      ez.high > ez.low &&
      currentPrice > 0 &&
      React.createElement(
        "div",
        { className: "mt-2 rounded-lg border border-td-accent/25 bg-td-bg/50 p-2" },
        horizonKind === "long" && entryTiers?.tiers?.length
          ? React.createElement(LongTermAccumulationScale, {
              horizon,
              entryTiers,
              currentPrice,
              stopLoss: hasStop ? horizon.stop_loss : null,
              target: horizon.target > 0 ? horizon.target : null,
            })
          : React.createElement(EntryZonePriceBar, {
              entryLow: ez.low,
              entryHigh: ez.high,
              currentPrice,
              stopLoss: hasStop ? horizon.stop_loss : null,
              target: horizon.target > 0 ? horizon.target : null,
              bandLabel: entryTierPrefix.replace(/:\s*$/, "").trim() || "Buy zone",
              quality: horizon.entry_zone?.quality,
              anchorNote:
                !scan && horizon.entry_zone?.anchor ? String(horizon.entry_zone.anchor) : null,
              touchForecast: horizon.entry_touch_forecast,
              spotPosition: horizon.entry_zone?.spot_position,
              levels: horizon.entry_zone?.levels,
            })
      ),
    scan
      ? React.createElement(
          "div",
          { className: "grid grid-cols-2 gap-2 mt-2 text-xs font-mono" },
          hasStop &&
            React.createElement(
              "div",
              { className: "rounded-md bg-td-surface/70 border border-td-crit/20 px-2 py-1.5" },
              React.createElement("p", { className: "text-[10px] text-td-muted uppercase" }, "Stop"),
              React.createElement(
                "p",
                { className: "text-td-crit tabular-nums" },
                `$${Number(horizon.stop_loss).toFixed(2)}`
              )
            ),
          horizon.target > 0 &&
            React.createElement(
              "div",
              { className: "rounded-md bg-td-surface/70 border border-td-accent/20 px-2 py-1.5" },
              React.createElement("p", { className: "text-[10px] text-td-muted uppercase" }, "Target"),
              React.createElement(
                "p",
                { className: "text-td-accent tabular-nums" },
                `$${horizon.target.toFixed(2)} (+${horizon.target_pct.toFixed(0)}%)`
              )
            )
        )
      : React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "p",
            {
              className: "text-td-muted text-xs",
              title:
                "ML probabilities can vary day-to-day as new price and volume data are included; large moves may reflect updated features rather than a change in thesis.",
            },
            `Target: +${horizon.target_pct.toFixed(0)}% · ML prob: ${Number(horizon.ml_prob).toFixed(0)}%`
          ),
          hasStop &&
            React.createElement(
              "p",
              {
                className: "text-td-muted text-xs mt-0.5",
                title: structuralStop
                  ? horizon.stop_loss_framing || "52-week stress floor — not a day-to-day trailing stop"
                  : undefined,
              },
              horizonKind === "short"
                ? horizon.stop_loss_framing ||
                  `Swing stop: $${Number(horizon.stop_loss).toFixed(2)}${
                    horizon.stop_loss_pct != null && Number.isFinite(horizon.stop_loss_pct)
                      ? ` (${Math.abs(horizon.stop_loss_pct).toFixed(0)}% risk)`
                      : ""
                  }`
                : horizonKind === "medium"
                  ? horizon.stop_loss_framing ||
                    `Build stop: $${Number(horizon.stop_loss).toFixed(2)} (pause tranches)`
                  : structuralStop
                    ? entryTiers?.structural_invalidation?.note ||
                      horizon.stop_loss_framing ||
                      `Thesis stop: $${Number(horizon.stop_loss).toFixed(2)} (exit thesis)`
                    : horizon.stop_loss_framing || `Stop below $${Number(horizon.stop_loss).toFixed(2)}`
            )
        ),
    React.createElement(
      "p",
      {
        className: clsx("text-td-muted mt-1.5 leading-snug", scan ? "text-xs line-clamp-2" : "text-sm"),
      },
      React.createElement("span", { className: "text-td-muted font-medium" }, "Act when: "),
      triggerLine
    ),
    (warnings.length > 0 || hasRationale) &&
      React.createElement(
        React.Fragment,
        null,
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setShowCaveats((s) => !s),
            className: "mt-2 text-sm text-td-warn/90 flex items-center gap-1 hover:text-td-warn",
          },
          React.createElement(AlertTriangle, { className: "h-3 w-3 shrink-0" }),
          `${warnings.length + (hasRationale ? 1 : 0)} caveat${warnings.length + (hasRationale ? 1 : 0) > 1 ? "s" : ""}`,
          showCaveats
            ? React.createElement(ChevronUp, { className: "h-3 w-3 shrink-0" })
            : React.createElement(ChevronDown, { className: "h-3 w-3 shrink-0" })
        ),
        showCaveats &&
          React.createElement(
            "div",
            { className: "mt-2 space-y-1 border-t border-td-line/50 pt-2" },
            hasRationale &&
              React.createElement("p", { className: "text-sm text-td-text leading-snug" }, horizon.rationale),
            warnings.map((w, i) =>
              React.createElement(
                "div",
                { key: i, className: "flex items-start gap-1.5 text-sm text-td-warn/90" },
                React.createElement(AlertTriangle, { className: "h-3 w-3 shrink-0 mt-0.5" }),
                React.createElement("span", null, w)
              )
            )
          )
      ),
    entryTiers &&
      showTierLadder &&
      onToggleTiers &&
      React.createElement(
        React.Fragment,
        null,
        React.createElement(
          "button",
          {
            type: "button",
            onClick: onToggleTiers,
            className: "mt-2 flex items-center gap-1 text-xs text-td-accent hover:text-td-accent",
          },
          tiersOpen ? React.createElement(ChevronDown, { className: "h-3 w-3" }) : React.createElement(ChevronRight, { className: "h-3 w-3" }),
          tiersOpen ? " Hide Entry Tiers" : "+ Entry Tiers"
        ),
        tiersOpen &&
          entryTiers.tiers &&
          React.createElement(
            React.Fragment,
            null,
            React.createElement(LongTermTierLadder, {
              entryTiers,
              currentPrice,
              modeLabel: entryTiers.current_assessment?.label,
            }),
            entryTiers.structural_invalidation &&
              React.createElement(
                "div",
                { className: "mt-1 px-3 py-2 rounded-lg border border-td-line/50 bg-td-surface2/30" },
                React.createElement(
                  "p",
                  { className: "text-xs text-td-muted leading-snug" },
                  React.createElement("span", { className: "font-medium text-td-muted" }, "Structural floor: "),
                  `$${entryTiers.structural_invalidation.price.toFixed(2)} — ${entryTiers.structural_invalidation.note}`
                )
              )
          )
      )
  );
}


function anchorSnippet(anchor: string | undefined, max = 160): string {
  if (!anchor || !anchor.trim()) return "";
  const t = anchor.trim();
  return t.length <= max ? t : `${t.slice(0, max).trim()}…`;
}

/** Retail-focused buy band vs spot vs risk floors — uses short-term horizon entry_zone + stops from API. */
function BuyRangeRetailCard({
  currentPrice,
  short,
  long,
  overallVerdict,
}: {
  currentPrice: number;
  short: HorizonSignalPayload;
  long: HorizonSignalPayload;
  overallVerdict: "WAIT" | "WATCH" | "BUY" | "STRONG BUY";
}): React.ReactElement | null {
  const ez = short?.entry_zone;
  if (!ez || !(ez.low > 0) || !(ez.high > 0)) return null;
  const low = Math.min(ez.low, ez.high);
  const high = Math.max(ez.low, ez.high);
  const range = high - low;
  const stStop = short.stop_loss != null && short.stop_loss > 0 ? short.stop_loss : null;
  const activeTier2 =
    long?.entry_tiers?.active_tier_id === "T2" &&
    (long?.entry_tiers?.tiers?.some(
      (t) =>
        (t.id === "T2" || t.id === "tier2") &&
        currentPrice >= t.low &&
        currentPrice <= t.high
    ) ??
      false);

  let statusLabel = "—";
  let statusBadgeClass =
    "text-sm px-2 py-0.5 rounded border font-semibold border-td-line/40 bg-td-line/20 text-td-text";
  if (currentPrice > 0) {
    if (currentPrice >= low && currentPrice <= high) {
      statusLabel = "Inside buy zone";
      statusBadgeClass =
        "text-sm px-2 py-0.5 rounded border font-semibold border-td-accent/45 bg-td-accent/15 text-td-accent";
    } else if (currentPrice > high) {
      statusLabel = "Above buy zone";
      statusBadgeClass =
        "text-sm px-2 py-0.5 rounded border font-semibold border-td-warn/45 bg-td-warn/15 text-td-warn";
    } else {
      statusLabel = "Below modeled band";
      statusBadgeClass =
        "text-sm px-2 py-0.5 rounded border font-semibold border-td-info/40 bg-td-info/10 text-td-info";
    }
  }

  const pad = Math.max(range * 0.25, Math.max(low, high) * 0.008, 0.5);
  const scaleMin = low - pad;
  const scaleMax = high + pad;
  const denom = scaleMax - scaleMin;
  const pctRaw = denom > 0 && currentPrice > 0 ? ((currentPrice - scaleMin) / denom) * 100 : 50;
  const pct = Math.max(0, Math.min(100, pctRaw));
  const zoneStartPct = denom > 0 ? ((low - scaleMin) / denom) * 100 : 0;
  const zoneWidthPct = denom > 0 ? ((high - low) / denom) * 100 : 100;

  const anchorNote = anchorSnippet(ez.anchor);

  const maxBuyMos = long?.entry_tiers?.current_assessment?.min_price_to_buy;
  const aboveFullMos = long?.entry_tiers?.current_assessment?.above_full_mos_ceiling === true;
  const rr = short?.risk_reward != null && Number(short.risk_reward) > 0 ? Number(short.risk_reward) : null;
  const insideBandButNotBuy =
    statusLabel === "Inside buy zone" &&
    (overallVerdict === "WAIT" || overallVerdict === "WATCH");

  return React.createElement(
    "section",
    {
      className:
        "p-4 border-b border-td-accent/30 bg-gradient-to-br from-td-accent-weak/50 via-td-surface/60 to-td-bg/80",
      "aria-label": "Buy range and stress levels",
    },
    React.createElement(
      "div",
      { className: "flex items-start justify-between gap-3 flex-wrap mb-3" },
      React.createElement(
        "div",
        { className: "flex items-center gap-2 min-w-0" },
        React.createElement(Target, { className: "h-5 w-5 text-td-accent shrink-0", "aria-hidden": true }),
        React.createElement(
          "div",
          { className: "min-w-0" },
          React.createElement(
            "h3",
            { className: "text-xs font-semibold text-td-accent-ink/95 uppercase tracking-wide" },
            "Buy zone vs stress"
          ),
          React.createElement(
            "p",
            { className: "text-sm text-td-muted mt-0.5" },
            "Near-term buy band vs today's price — green range comes from the same support / VWAP logic as your stops."
          )
        )
      ),
      React.createElement("span", { className: statusBadgeClass }, statusLabel)
    ),
    insideBandButNotBuy &&
      React.createElement(
        "p",
        { className: "text-sm text-td-warn/90 mb-3 px-3 py-2 rounded-lg border border-td-warn/30 bg-td-warn-weak/50 leading-snug" },
        `Price is inside the near-term band but the overall signal is ${overallVerdict} because regime and confidence gates haven\u2019t cleared \u2014 the band shows where you\u2019d buy if conditions improve, not a current buy signal.`
      ),
    aboveFullMos &&
      activeTier2 &&
      maxBuyMos != null &&
      React.createElement(
        "p",
        {
          className:
            "text-sm text-td-owner/95 mb-3 px-3 py-2 rounded-lg border border-td-owner/35 bg-td-owner-weak/40 leading-snug",
        },
        `Spot $${currentPrice.toFixed(2)} is inside Tier 2 (partial MOS band) but above the full-position ceiling $${maxBuyMos.toFixed(2)} — scale a partial tranche only, not a full allocation.`
      ),
    React.createElement(
      "div",
      { className: "grid grid-cols-1 sm:grid-cols-2 gap-4 mb-3" },
      React.createElement(
        "div",
        {
          className:
            "rounded-xl border border-td-accent/35 bg-td-accent-weak/25 px-3.5 py-3 shadow-inner shadow-black/20",
        },
        React.createElement(
          "p",
          { className: "text-sm text-td-accent-ink/80 uppercase tracking-wide font-semibold mb-1" },
          "Optimal entry (near-term)"
        ),
        React.createElement(
          "p",
          { className: "text-xl font-bold font-mono text-td-accent-ink tracking-tight" },
          `$${low.toFixed(2)} – $${high.toFixed(2)}`
        ),
        ez.quality
          ? React.createElement(
              "div",
              { className: "mt-1" },
              React.createElement(
                "p",
                { className: "text-sm text-td-muted" },
                React.createElement("span", { className: "text-td-muted" }, "Band quality: "),
                React.createElement(
                  "span",
                  { className: String(ez.quality).toLowerCase() === "stretched" ? "text-td-crit/90" : String(ez.quality).toLowerCase() === "ideal" ? "text-td-accent/90" : "" },
                  ez.quality
                )
              ),
              String(ez.quality).toLowerCase() === "stretched" &&
                React.createElement(
                  "p",
                  { className: "text-xs text-td-warn/80 mt-0.5 leading-snug" },
                  "\"Stretched\" means price is above its key support level (VWAP or MA50). In our 10-year S&P 500 test, stocks above their band did not do worse than average \u2014 a pullback toward the band low is a cheaper fill, not a better outcome. Splitting the entry (part now, optional limit for the rest) is a reasonable default."
                ),
              String(ez.quality).toLowerCase() === "waiting" &&
                React.createElement(
                  "p",
                  { className: "text-xs text-td-muted mt-0.5 leading-snug" },
                  "\"Waiting\" means conditions haven\u2019t aligned yet \u2014 check back after a pullback or regime shift."
                )
            )
          : null
      ),
      React.createElement(
        "div",
        {
          className:
            "rounded-xl border border-td-line/70 bg-td-bg/50 px-3.5 py-3",
        },
        React.createElement(
          "p",
          { className: "text-sm text-td-muted uppercase tracking-wide font-semibold mb-1" },
          "Current price"
        ),
        React.createElement(
          "p",
          { className: "text-xl font-bold font-mono text-td-text tracking-tight" },
          currentPrice > 0 ? `$${currentPrice.toFixed(2)}` : "—"
        ),
        React.createElement(
          "p",
          { className: "mt-2 text-sm font-medium text-td-text" },
          React.createElement("span", { className: "text-td-muted font-normal text-xs mr-2" }, "Status:"),
          statusLabel
        )
      )
    ),
    React.createElement(
      "div",
      { className: "mb-3" },
      React.createElement(
        "p",
        { className: "text-xs text-td-muted mb-1 flex justify-between font-mono gap-2" },
        React.createElement("span", null, `$${low.toFixed(2)} band low`),
        React.createElement("span", null, `$${high.toFixed(2)} band high`)
      ),
      React.createElement(
        "div",
        { className: "relative h-4 rounded-full bg-td-surface2/90 border border-td-line/80" },
        React.createElement("div", {
          className: "absolute top-0 bottom-0 rounded-full bg-td-accent/30 border border-td-accent/25",
          style: { left: `${zoneStartPct}%`, width: `${zoneWidthPct}%` },
        }),
        React.createElement("div", {
          className:
            "absolute top-1/2 w-2.5 h-2.5 rounded-full bg-white border-2 border-td-accent shadow-md z-10",
          style: {
            left: `${pct}%`,
            transform: "translate(-50%, -50%)",
            top: "50%",
          },
          title: currentPrice > 0 ? `Spot $${currentPrice.toFixed(2)}` : "Spot",
        })
      ),
      React.createElement(
        "p",
        { className: "text-xs text-td-muted mt-1 text-center" },
        "Dot = last price vs modeled buy band (not a forecast)."
      )
    ),
    long?.entry_tiers?.tiers?.length &&
      currentPrice > 0 &&
      React.createElement(
        "div",
        { className: "mb-3 rounded-xl border border-td-accent/25 bg-td-bg/40 p-3" },
        React.createElement(
          "p",
          { className: "text-xs text-td-accent-ink/90 uppercase tracking-wide font-semibold mb-2" },
          "Long-term tiers & full-position MOS"
        ),
        React.createElement(LongTermAccumulationScale, {
          horizon: long,
          entryTiers: long.entry_tiers!,
          currentPrice,
          stopLoss:
            long.stop_loss != null && long.stop_loss > 0 ? long.stop_loss : null,
          target: long.target > 0 ? long.target : null,
        })
      ),
    ((maxBuyMos != null && maxBuyMos > 0) || rr != null || (stStop != null && short.target > 0)) &&
      React.createElement(
        "div",
        { className: "mb-3 grid grid-cols-1 sm:grid-cols-2 gap-3" },
        maxBuyMos != null &&
          maxBuyMos > 0 &&
          React.createElement(
            "div",
            {
              className:
                "rounded-xl border border-td-info/35 bg-td-info/10/20 px-3.5 py-3",
            },
            React.createElement(
              "p",
              { className: "text-sm text-td-info/85 uppercase tracking-wide font-semibold mb-1" },
              "Full-size ceiling (25% MOS)"
            ),
            React.createElement(
              "p",
              { className: "text-lg font-bold font-mono text-td-info tracking-tight" },
              `$${maxBuyMos.toFixed(2)}`
            ),
            React.createElement(
              "p",
              { className: "text-xs text-td-muted mt-1 leading-snug" },
              activeTier2
                ? "Full margin-of-safety ceiling — stricter than Tier 2 band above (partial position only)."
                : "Rough ceiling from long-term margin-of-safety rule — stricter than the near-term band."
            )
          ),
        (rr != null || (stStop != null && short.target > 0)) &&
          React.createElement(
            "div",
            {
              className:
                "rounded-xl border border-td-line/70 bg-td-bg/50 px-3.5 py-3 sm:col-span-2",
            },
            React.createElement(
              "p",
              { className: "text-sm text-td-muted uppercase tracking-wide font-semibold mb-2" },
              "Short-term risk thermometer"
            ),
            stStop != null && short.target > stStop && currentPrice > 0
              ? React.createElement(StopTargetRiskBar, {
                  stopLoss: stStop,
                  target: short.target,
                  currentPrice,
                })
              : rr != null
                ? React.createElement(RiskRewardThermometer, { riskReward: rr })
                : null,
            rr != null &&
              rr < 0.5 &&
              React.createElement(
                "p",
                { className: "text-xs text-td-warn/90 mt-1.5 leading-snug border-t border-td-warn/20 pt-1.5" },
                "Asymmetric risk: large downside slice vs thin upside to target \u2014 size smaller or use long-term tiers."
              )
          )
      ),
    anchorNote &&
      React.createElement(
        "p",
        {
          className: "text-sm text-td-muted leading-snug border-t border-td-line/60 pt-2 mt-1",
          title: ez.anchor,
        },
        React.createElement("span", { className: "text-td-muted" }, "Why this band: "),
        anchorNote
      )
  );
}

export function InvestorDecisionSummarySection({
  summary,
  currentPrice,
  sector,
  companyName,
  ltEntryTiersOpen,
  onToggleLtTiers,
  priceHistory,
  ticker,
  ma20,
  ma50,
  hideTradingGates = false,
  hideRoadmaps = false,
  compactOverview = false,
  marketContext,
  decisionMode = "scout",
  contentLayer = "full",
}: {
  summary: InvestorDecisionSummary;
  currentPrice: number;
  ma200?: number | null;
  ma20?: number | null;
  ma50?: number | null;
  sector?: string | null;
  companyName?: string | null;
  ltEntryTiersOpen: boolean;
  onToggleLtTiers: () => void;
  priceHistory?: PriceHistoryPoint[];
  ticker?: string;
  /** When GlobalActionHeader already shows gates, skip duplicate block. */
  hideTradingGates?: boolean;
  /** Roadmaps live on Levels tab in ticker modal — skip duplicate collapsibles. */
  hideRoadmaps?: boolean;
  /** Modal layout: header + playbooks already shown — trim duplicate blocks. */
  compactOverview?: boolean;
  /** Macro/earnings context — shown compactly after horizon action row. */
  marketContext?: TickerMarketContext | null;
  /** Scout / swing / owner — which horizon card to foreground on Today. */
  decisionMode?: DecisionMode;
  /** today = scan deck + one horizon; why = charts & proof; full = legacy layout. */
  contentLayer?: "today" | "why" | "full";
}) {
  const {
    fair_value,
    fair_value_vs_external: fve,
    valuation_deck: valuationDeck,
    overall_verdict,
    regime_bull_pct,
    regime_momentum_extended,
    model_confidence_pct,
    horizons,
    ttm_pe_used,
    forward_pe_used,
    fair_value_metadata,
    pattern_score,
    rsi,
    one_answer,
    trader_roadmap,
    investor_roadmap,
    plan_mode,
    chase_banner,
    chase_detail,
    fv_staleness,
  } = summary;
  const assessmentPct = currentPrice > 0 && fair_value > 0 ? ((fair_value - currentPrice) / fair_value) * 100 : 0; // MOS vs FV (not upside-to-FV)
  const short = horizons.short;
  const medium = horizons.medium;
  const long = horizons.long;

  const isToday = contentLayer === "today";
  const isWhy = contentLayer === "why";
  const isFull = contentLayer === "full";
  const primaryHorizonKey = primaryHorizonFromMode(decisionMode);
  const [compareHorizonsOpen, setCompareHorizonsOpen] = useState(false);
  const [horizonDetailOpen, setHorizonDetailOpen] = useState(isWhy || (isFull && !compactOverview));
  const [methodologyOpen, setMethodologyOpen] = useState(false);
  const [traderOpen, setTraderOpen] = useState(false);
  const [investorOpen, setInvestorOpen] = useState(false);
  const [holdVsTradeOpen, setHoldVsTradeOpen] = useState(false);
  const [advancedDiagnosticsOpen, setAdvancedDiagnosticsOpen] = useState(false);
  const [gatesDetailOpen, setGatesDetailOpen] = useState(false);
  const verdicts = [short?.verdict, medium?.verdict, long?.verdict].filter(Boolean);
  const hasDivergence = verdicts.length >= 2 && new Set(verdicts).size > 1;
  const divergenceMessage =
    short?.verdict === "WATCH" && medium?.verdict === "BUY" && long?.verdict === "WATCH"
      ? "Short and long are cautious; medium-term setup is stronger — consider entry on pullbacks."
      : hasDivergence
        ? "Horizons disagree — short/medium/long use different inputs (RSI, volume, ML). Prefer the horizon that matches your holding period."
        : null;
  const swingVsShortLift =
    String(short?.verdict || "").toUpperCase() === "WAIT" &&
    String(medium?.verdict || "").toUpperCase() === "WATCH";
  // When pattern_score is 0, the card already shows "Confluence" fallback — avoid duplicate "Pattern score low (0/100)" block
  const patternLow = pattern_score != null && pattern_score > 0 && pattern_score < 50;
  const tldr = summary.trade_roadmap?.tldr ?? null;
  const confidenceBand = tldr?.model_confidence_band ?? null;
  const confidenceBandMatch = confidenceBand?.match(/(\d+)\s*-\s*(\d+)%?/);
  const confidenceBandMid =
    confidenceBandMatch && confidenceBandMatch[1] && confidenceBandMatch[2]
      ? (Number(confidenceBandMatch[1]) + Number(confidenceBandMatch[2])) / 2
      : (model_confidence_pct ?? tldr?.model_confidence_pct ?? null);

  const combinedNotes = [
    ...(Array.isArray(one_answer?.why_this_call) ? one_answer!.why_this_call : []),
    ...(Array.isArray(one_answer?.signal_reconciliation_notes) ? one_answer!.signal_reconciliation_notes : []),
  ];
  const etaNote = combinedNotes.find((n) => /trading days/i.test(n));
  const etaDaysMatch = etaNote?.match(/(\d+)\s*trading days/i);
  const etaDays = etaDaysMatch ? Number(etaDaysMatch[1]) : null;
  const shortWaitOverallBuy =
    (String(short?.verdict || "").toUpperCase() === "WAIT" || String(short?.verdict || "").toUpperCase() === "WATCH") &&
    (overall_verdict === "BUY" || overall_verdict === "STRONG BUY");
  const mlHighHmmBlocks: Array<{ label: string; ml: number; bullPct: number }> = (
    [
      ["Short", short] as const,
      ["Medium", medium] as const,
      ["Long", long] as const,
    ] as const
  )
    .filter(([, h]) =>
      h &&
      String(h.verdict || "").toUpperCase() === "WAIT" &&
      h.ml_prob >= 80 &&
      regime_bull_pct != null &&
      regime_bull_pct < 60
    )
    .map(([label, h]) => ({
      label,
      ml: h!.ml_prob,
      bullPct: regime_bull_pct!,
    }));
  const contextFlags: Array<{ severity: "warning" | "info"; message: string }> = [
    ...(shortWaitOverallBuy
      ? [{
          severity: "info" as const,
          message: "Long-term thesis is actionable even though the short-term setup is weak \u2014 the overall BUY is driven by medium/long horizon strength, not a 1-month trade signal.",
        }]
      : []),
    ...mlHighHmmBlocks.map((m) => ({
      severity: "info" as const,
      message: `${m.label} ML is ${m.ml}% constructive but the regime gate requires HMM Bull \u2265 60% before activating \u2014 current Bull is ~${Math.round(m.bullPct)}%, so the signal is blocked. The ML read is stored; once regime clears, the verdict will upgrade automatically.`,
    })),
    ...((short?.ml_prob != null && short.ml_prob < 30 && regime_bull_pct != null && regime_bull_pct >= 80)
      ? [{
          severity: "info" as const,
          message: `Near-term ML is only ${Math.round(short.ml_prob)}% despite ${Math.round(regime_bull_pct)}% bull regime \u2014 ML is trained on price-momentum patterns (RSI, chart structure), not news or regime. It\u2019s seeing conditions that historically precede consolidation before breakouts. Regime and fundamentals are the longer-term anchor; ML is the short-term timing layer.`,
        }]
      : []),
    ...(patternLow
      ? [{
          severity: "info" as const,
          message: `Chart pattern ${Math.round(Number(pattern_score))}/100 — often regime-weighted; see Why tab for drivers.`,
        }]
      : []),
    ...(hasDivergence && divergenceMessage
      ? [{ severity: "warning" as const, message: divergenceMessage }]
      : []),
    ...((Array.isArray(one_answer?.signal_reconciliation_notes) ? one_answer.signal_reconciliation_notes : [])
      .slice(0, 2)
      .map((m) => ({ severity: "info" as const, message: m }))),
  ];
  const gateRows: Array<{ label: string; value: number | null; target: number; unit: "%" | "pts" }> = [
    { label: "Regime", value: regime_bull_pct ?? null, target: 60, unit: "%" },
    { label: "Pattern", value: pattern_score ?? null, target: 60, unit: "pts" },
    { label: "Confidence (sizing, not in 4-of-4)", value: confidenceBandMid ?? null, target: 55, unit: "%" },
  ];
  const gateTone = (v: number | null, t: number): string =>
    v == null
      ? "text-td-muted"
      : v >= t
        ? "text-td-accent"
        : v >= Math.max(t - 10, 0)
          ? "text-td-warn"
          : "text-td-crit";

  const regimeWeather = marketWeatherFromRegimeBull(regime_bull_pct, regime_momentum_extended);
  const patternDecisionOneLiner = buildPatternDecisionDriverSummary({
    patternScore: pattern_score,
    regimeBullPct: regime_bull_pct,
    undervaluationPct: assessmentPct,
    shortVerdict: short?.verdict,
  });

  const CONFIDENCE_GATE_TARGET = 55;
  const ptsToConfidenceGate =
    confidenceBandMid != null && !Number.isNaN(Number(confidenceBandMid))
      ? CONFIDENCE_GATE_TARGET - Number(confidenceBandMid)
      : null;
  const confidenceNearlyThere =
    ptsToConfidenceGate != null && ptsToConfidenceGate > 0 && ptsToConfidenceGate <= 10;

  const mlHorizonGapExplainer = buildMlHorizonGapExplainer(
    short?.ml_prob,
    medium?.ml_prob,
    long?.ml_prob
  );

  const horizonCardShared = {
    currentPrice,
    regimeBullPct: regime_bull_pct,
    assessmentPct,
    shortHorizon: short,
    rsi: rsi ?? null,
  };

  const tradingGates = buildGatesFromInvestorSummary(summary, currentPrice);
  const primaryTradingGates = filterPrimaryTradingGates(tradingGates);
  const passedPrimary = primaryTradingGates.filter((g) => g.pass).length;

  return React.createElement(
    "div",
    {
      role: "region",
      "aria-label": "Investor Decision Summary",
      className: "bg-td-surface2/55 border border-td-line/80 rounded-2xl overflow-hidden shadow-xl shadow-black/20",
    },
    !hideTradingGates &&
      !compactOverview &&
      !isToday &&
      React.createElement(
        "div",
        { className: "p-4 border-b border-td-owner/25 bg-gradient-to-b from-td-owner-weak/40 to-td-surface/60 space-y-3" },
        React.createElement(TradingGateStatus, { gates: primaryTradingGates }),
        React.createElement(
          "p",
          { className: "text-sm text-td-warn/90 leading-snug px-1" },
          `Investor takeaway: ${passedPrimary} of ${primaryTradingGates.length} checks are green` +
            (passedPrimary >= 3
              ? " — review sizing on Roadmaps before adding."
              : " — sit on your hands until more gates clear.")
        )
      ),
    hideTradingGates &&
      !compactOverview &&
      !isToday &&
      primaryTradingGates.length > 0 &&
      React.createElement(
        "div",
        { className: "px-4 pt-3 pb-1 border-b border-td-line/60" },
        React.createElement(
          "p",
          { className: "text-sm text-td-warn/90 leading-snug" },
          `Investor takeaway: ${passedPrimary} of ${primaryTradingGates.length} checks are green` +
            (passedPrimary >= 3
              ? " — review sizing on Roadmaps before adding."
              : " — sit on your hands until more gates clear.")
        )
      ),
    ticker &&
      !compactOverview &&
      isFull &&
      React.createElement(
        "div",
        { className: "px-4 pt-2 pb-0 border-b border-td-line/80" },
        React.createElement(PositionIntentChip, { ticker })
      ),
    (chase_banner || plan_mode === "pullback_conditional") &&
      !compactOverview &&
      React.createElement(
        "div",
        { className: "mx-4 mt-3 rounded-lg border border-td-crit/40 bg-td-crit-weak/25 px-3 py-2" },
        React.createElement(
          "p",
          { className: "text-[11px] font-semibold uppercase tracking-wide text-td-crit" },
          chase_banner || "ABOVE FAIR VALUE",
        ),
        React.createElement(
          "p",
          { className: "text-[11px] text-td-crit/75 mt-0.5 leading-snug" },
          chase_detail ||
            "Spot is extended vs model FV — treat horizon plans as conditional pullbacks.",
        ),
      ),
    fv_staleness?.flagged &&
      !compactOverview &&
      React.createElement(
        "div",
        { className: "mx-4 mt-2 rounded-lg border border-td-warn/35 bg-td-warn-weak/20 px-3 py-2" },
        React.createElement(
          "p",
          { className: "text-[11px] font-semibold uppercase tracking-wide text-td-warn" },
          "FV may be stale",
        ),
        React.createElement(
          "p",
          { className: "text-[11px] text-td-warn/75 mt-0.5 leading-snug" },
          fv_staleness.note ||
            "Price has moved far from model FV vs ATR — recheck consensus before treating today's FV as a 12-month target.",
        ),
      ),
    !isToday &&
      one_answer &&
      React.createElement(
        "div",
        { className: "p-4 border-b border-td-line/80 bg-gradient-to-br from-td-accent/10 via-td-surface/60 to-td-surface/40" },
        React.createElement(
          "div",
          { className: "flex items-center justify-between gap-2 flex-wrap mb-2" },
          React.createElement(
            "h3",
            { className: "flex items-center gap-2 text-xs font-semibold text-td-muted uppercase tracking-wide" },
            React.createElement(Zap, { className: "h-3.5 w-3.5 text-td-accent" }),
            " One answer"
          ),
          React.createElement(
            "span",
            {
              className:
                overall_verdict === "STRONG BUY" || overall_verdict === "BUY"
                  ? "text-sm px-2 py-0.5 rounded border border-td-accent/40 bg-td-accent/15 text-td-accent font-semibold"
                  : overall_verdict === "WATCH"
                    ? "text-sm px-2 py-0.5 rounded border border-td-accent/55 bg-td-accent/10 text-td-accent-ink font-semibold"
                    : overall_verdict === "WAIT"
                      ? "text-sm px-2 py-0.5 rounded border border-td-crit/55 bg-td-crit/10 text-td-crit font-semibold"
                      : "text-sm px-2 py-0.5 rounded border border-td-line/40 bg-td-line/15 text-td-text font-semibold",
            },
            overall_verdict
          )
        ),
        one_answer.bottom_line &&
          React.createElement(
            "p",
            { className: "text-sm font-semibold text-td-accent-ink/95 leading-snug mb-1" },
            one_answer.bottom_line
          ),
        !compactOverview &&
          React.createElement("p", { className: "text-base font-medium text-td-text leading-snug" }, one_answer.headline),
        !compactOverview &&
          one_answer.subline &&
          React.createElement("p", { className: "mt-1 text-sm text-td-warn/90" }, one_answer.subline)
      ),
    (isWhy || isFull) &&
      (short?.target || medium?.target || long?.target) &&
      React.createElement(
        "div",
        { className: "px-4 pb-4 border-b border-td-line/80" },
        React.createElement(HorizonProjectionChart, {
          ticker,
          currentPrice,
          priceHistory: priceHistory ?? [],
          short,
          medium,
          long,
          fairValue: fair_value,
          ma20,
          ma50,
          planMode: plan_mode,
          chaseBanner: chase_banner,
          chaseDetail: chase_detail,
        })
      ),
    (isFull) &&
      !compactOverview &&
      valuationDeck &&
      React.createElement(
        "div",
        { className: "px-4 pb-4 border-b border-td-line/80" },
        React.createElement(ValuationDeck, {
          deck: valuationDeck,
          currentPrice,
          modelFairValue: fair_value,
          external: fve ?? undefined,
          mode: decisionMode,
          variant: "full",
        })
      ),
    (isWhy || isFull) &&
      !compactOverview &&
      !valuationDeck &&
      fve &&
      React.createElement(
        "div",
        { className: "px-4 pb-4 border-b border-td-line/80" },
        React.createElement(StreetVsModelBar, {
          modelFairValue: fair_value,
          currentPrice,
          external: fve,
        })
      ),
    isToday &&
      compactOverview &&
      decisionMode === "swing" &&
      valuationDeck &&
      React.createElement(
        "div",
        { className: "px-4 pb-3 border-b border-td-line/80" },
        React.createElement(ValuationDeck, {
          deck: valuationDeck,
          currentPrice,
          modelFairValue: fair_value,
          external: fve ?? undefined,
          mode: "swing",
          variant: "compact",
        })
      ),
    isToday &&
      compactOverview &&
      decisionMode === "scout" &&
      valuationDeck &&
      React.createElement(
        "div",
        { className: "px-4 pb-3 border-b border-td-line/80" },
        React.createElement(StreetSentimentChip, {
          deck: valuationDeck,
          executionLabel:
            one_answer?.action_today === "enter_now"
              ? "Enter now"
              : one_answer?.action_today === "hold"
                ? "Hold"
                : one_answer?.action_today === "wait_for_pullback"
                  ? "Split entry"
                  : one_answer?.action_today === "no_new_position"
                    ? "No new position"
                    : null,
        })
      ),
    (isWhy || isFull) &&
      !compactOverview &&
      React.createElement(
        "div",
        { className: "p-4 border-b border-td-line/80" },
        React.createElement(PlainEnglishTakeCard, {
          summary,
          currentPrice,
          prominent: true,
          defaultOpen: false,
        })
      ),
    (isToday || compactOverview) &&
      React.createElement(
        "div",
        { className: "p-4 border-b border-td-line/80" },
        React.createElement(HorizonDivergenceNote, { short, long })
      ),
    !isToday &&
      React.createElement(BuyRangeRetailCard, { currentPrice, short, long, overallVerdict: overall_verdict }),
    !isToday &&
      React.createElement(
        "div",
        { className: "px-4 pb-4 border-b border-td-line/80" },
        React.createElement(StopHierarchyPanel, {
          short,
          medium,
          long,
          currentPrice,
          stockRegimeBullPct: summary.retail_action?.stock_regime_bull_pct ?? regime_bull_pct,
          marketRegimeBullPct: summary.retail_action?.market_regime_bull_pct,
        })
      ),
    marketContext?.headline &&
      React.createElement(
        "div",
        { className: "px-4 pb-4 border-b border-td-line/80" },
        React.createElement(TickerMarketContextCard, { data: marketContext, variant: "compact" })
      ),
    long?.entry_tiers?.tiers?.length &&
      (isWhy || isFull) &&
      !compactOverview
      ? React.createElement(
          "div",
          { className: "px-4 pb-4 border-b border-td-line/80" },
          React.createElement(LongTermTierLadder, {
            entryTiers: long.entry_tiers,
            currentPrice,
            modeLabel: long.entry_tiers.current_assessment?.label,
          })
        )
      : null,
    isToday &&
      React.createElement(
        "div",
        { className: "p-4 border-b border-td-line/80 space-y-3" },
        decisionMode === "owner" &&
          primaryHorizonKey === "long" &&
          React.createElement(
            "p",
            { className: "text-sm text-td-muted leading-relaxed" },
            "Primary plan is in the card above. Compare other horizons below or open Levels for full roadmaps."
          ),
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setCompareHorizonsOpen((o) => !o),
            className:
              "w-full text-sm text-td-text hover:text-td-text py-2 rounded-lg border border-td-line/80 hover:bg-td-surface2/50 transition-colors",
          },
          compareHorizonsOpen ? "Hide other timeframes" : "Compare all timeframes"
        ),
        compareHorizonsOpen &&
          React.createElement(
            "div",
            { className: "grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1" },
            primaryHorizonKey !== "short" &&
              React.createElement(HorizonCard, {
                horizon: short,
                horizonKind: "short",
                ...horizonCardShared,
                density: "scan",
              }),
            primaryHorizonKey !== "medium" &&
              React.createElement(HorizonCard, {
                horizon: medium,
                horizonKind: "medium",
                ...horizonCardShared,
                density: "scan",
              }),
            primaryHorizonKey !== "long" &&
              React.createElement(HorizonCard, {
                horizon: long,
                horizonKind: "long",
                ...horizonCardShared,
                entryTiers: long.entry_tiers,
                showTierLadder: false,
                density: "scan",
              })
          )
      ),
    (isWhy || isFull) &&
      React.createElement(
        "div",
        { className: "border-b border-td-line/80 bg-td-surface/30" },
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setHorizonDetailOpen((o) => !o),
            className:
              "w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-td-surface2/40 transition-colors",
          },
          React.createElement(
            "span",
            { className: "text-sm text-td-muted uppercase tracking-wide" },
            isWhy ? "All horizons (detail)" : "Horizon detail (short · medium · long)"
          ),
          horizonDetailOpen
            ? React.createElement(ChevronDown, { className: "h-4 w-4 text-td-muted" })
            : React.createElement(ChevronRight, { className: "h-4 w-4 text-td-muted" })
        ),
        (isWhy || horizonDetailOpen) &&
          React.createElement(
            "div",
            { className: "p-4 pt-0" },
            React.createElement(
              "div",
              { className: "grid grid-cols-1 sm:grid-cols-3 gap-3" },
              React.createElement(HorizonCard, {
                horizon: short,
                horizonKind: "short",
                ...horizonCardShared,
                density: "detail",
              }),
              React.createElement(HorizonCard, {
                horizon: medium,
                horizonKind: "medium",
                ...horizonCardShared,
                density: "detail",
              }),
              React.createElement(HorizonCard, {
                horizon: long,
                horizonKind: "long",
                ...horizonCardShared,
                entryTiers: long.entry_tiers,
                showTierLadder: true,
                tiersOpen: ltEntryTiersOpen,
                onToggleTiers: onToggleLtTiers,
                density: "detail",
              })
            )
          )
      ),
    !isToday &&
      one_answer &&
      React.createElement(ExecutionPlanRationale, {
        summary,
        currentPrice,
        companyName,
        sector,
        mode: decisionMode,
        variant: "panel",
        collapsible: compactOverview,
        defaultOpen: !compactOverview,
      }),
    !isToday &&
      one_answer &&
      React.createElement(
        "div",
        { className: "mt-3 space-y-3" },
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => setGatesDetailOpen((o) => !o),
            className: "w-full text-left text-sm text-td-muted hover:text-td-text flex items-center gap-1",
          },
          gatesDetailOpen ? React.createElement(ChevronDown, { className: "h-3.5 w-3.5" }) : React.createElement(ChevronRight, { className: "h-3.5 w-3.5" }),
          gatesDetailOpen ? "Hide detailed gate bars" : "Show detailed gate bars (Regime / Pattern / Confidence)"
        ),
        gatesDetailOpen &&
          React.createElement(
            "div",
            { className: "rounded-xl border border-td-line/80 bg-td-surface/35 px-3.5 py-3 space-y-3" },
            React.createElement("p", { className: "text-sm text-td-muted uppercase tracking-wide font-semibold" }, "What would change this"),
            React.createElement(
              "div",
              { className: "space-y-2" },
              gateRows.map((g) => {
            const val = g.value;
            const shown = val == null ? "N/A" : `${Math.round(val)}${g.unit}`;
            const tgt = `${Math.round(g.target)}${g.unit}`;
            const barPct = val == null ? 0 : Math.max(0, Math.min(100, (val / g.target) * 100));
            const pass = val != null && val >= g.target;
            const isRegime = g.label === "Regime";
            const isPattern = g.label === "Pattern";
            const isConfidenceRow = g.label.startsWith("Confidence");
            const confidenceRowHot = isConfidenceRow && confidenceNearlyThere;
            return React.createElement(
              "div",
              {
                key: g.label,
                className:
                  "rounded-lg border px-2.5 py-2 " +
                  (confidenceRowHot
                    ? "border-td-owner/65 bg-td-owner-weak/30 ring-1 ring-td-owner/35 shadow-[0_0_18px_-8px_rgba(167,139,250,0.5)]"
                    : "border-td-line/70 bg-td-bg/40"),
              },
              React.createElement(
                "div",
                { className: "flex items-center justify-between text-sm gap-2" },
                React.createElement(
                  "span",
                  { className: "text-td-text font-medium flex items-center gap-1.5 min-w-0" },
                  isRegime ? regimeWeatherIcon(regimeWeather.weather) : null,
                  isRegime
                    ? React.createElement(
                        "span",
                        { className: "flex flex-col gap-0.5 min-w-0" },
                        React.createElement("span", null, g.label),
                        React.createElement(
                          "span",
                          { className: "text-xs font-normal text-td-muted leading-tight" },
                          regimeWeather.headline
                        )
                      )
                    : g.label
                ),
                React.createElement(
                  "span",
                  { className: `${gateTone(val, g.target)} shrink-0 text-right` },
                  `${shown} -> needs ${tgt}`
                )
              ),
              isRegime &&
                React.createElement(
                  "p",
                  { className: "text-xs text-td-muted mt-1 leading-snug pl-5" },
                  regimeWeather.detail
                ),
              React.createElement(
                "div",
                { className: "mt-1.5 h-1.5 rounded-full bg-td-surface2 overflow-hidden" },
                React.createElement("div", {
                  className: pass ? "h-full bg-td-accent" : "h-full bg-td-warn",
                  style: { width: `${barPct}%` },
                })
              ),
              isPattern &&
                React.createElement(
                  "p",
                  {
                    className:
                      "text-xs text-td-muted mt-1.5 leading-snug border-t border-td-line/50 pt-1.5",
                  },
                  "Raw score measures chart structure — see ",
                  React.createElement(
                    "span",
                    { className: "text-td-info/90 font-medium" },
                    "Why this score?"
                  ),
                  " below for what actually drives it."
                )
            );
          })
            ),
          ),
        React.createElement(
          "div",
          {
            className:
              "mt-3 rounded-lg border border-td-info/30 bg-td-info/10/30 px-3 py-2.5",
            role: "note",
          },
          React.createElement(
            "p",
            { className: "text-xs text-td-info/85 uppercase tracking-wide font-semibold mb-1" },
            "Why this score?"
          ),
          React.createElement(
            "p",
            { className: "text-sm text-td-info/95 leading-snug" },
            patternDecisionOneLiner
          )
        ),
        React.createElement(
          "p",
          { className: "text-sm text-td-muted mt-2 leading-snug" },
          etaDays != null
            ? `Estimated time: about ${etaDays} trading days if regime confirms.`
            : "Estimated time: uncertain — wait for gate progress above."
        )
      ),
    !isToday &&
      one_answer &&
      one_answer.hold_vs_trade &&
        React.createElement(
          "div",
          { className: "mt-3 rounded-lg border border-td-line/80 bg-td-surface/40 overflow-hidden" },
          React.createElement(
            "button",
            {
              type: "button",
              onClick: () => setHoldVsTradeOpen((o) => !o),
              className: "w-full flex items-center justify-between gap-2 px-3 py-2 text-left hover:bg-td-surface2/30 transition-colors",
            },
            React.createElement(
              "span",
              { className: "flex items-center gap-2 text-xs font-semibold text-td-text" },
              React.createElement(Info, { className: "h-3.5 w-3.5 text-td-info shrink-0" }),
              one_answer.hold_vs_trade.title
            ),
            holdVsTradeOpen
              ? React.createElement(ChevronDown, { className: "h-4 w-4 text-td-muted shrink-0" })
              : React.createElement(ChevronRight, { className: "h-4 w-4 text-td-muted shrink-0" })
          ),
          holdVsTradeOpen &&
            React.createElement(
              "div",
              { className: "px-3 pb-3 pt-0 space-y-2 text-xs text-td-muted leading-relaxed border-t border-td-line/50" },
              React.createElement("p", { className: "text-td-text mt-2" }, React.createElement("span", { className: "font-medium text-td-text" }, "Long-term (5–10+ yr): "), one_answer.hold_vs_trade.long_term),
              React.createElement("p", { className: "text-td-text" }, React.createElement("span", { className: "font-medium text-td-text" }, "Shorter-term / trading: "), one_answer.hold_vs_trade.short_term),
              React.createElement("p", { className: "text-td-info/90 border-l-2 border-td-info/50 pl-2" }, one_answer.hold_vs_trade.signal_bridge),
              React.createElement("p", { className: "text-xs text-td-muted leading-snug border-t border-td-line/50 pt-2 mt-2" }, one_answer.hold_vs_trade.disclaimer)
            )
        ),
    !compactOverview &&
    React.createElement(
      "div",
      { className: "p-4 border-b border-td-line/80 bg-td-surface/30" },
      React.createElement("p", { className: "text-xs text-td-muted uppercase tracking-wide mb-2" }, "Which timeframe fits you?"),
      React.createElement(
        "div",
        {
          className:
            "mb-3 rounded-xl border px-3 py-2.5 " +
            (hasDivergence || swingVsShortLift
              ? "border-td-warn/45 bg-td-warn/10"
              : "border-td-line/70 bg-td-bg/50"),
        },
        React.createElement(
          "p",
          { className: "text-xs text-td-muted uppercase tracking-wide font-semibold mb-2" },
          "Horizon verdicts — compare tickers at a glance"
        ),
        React.createElement(
          "div",
          { className: "flex flex-wrap gap-2 items-center" },
          (
            [
              ["Short", short?.verdict] as const,
              ["Medium", medium?.verdict] as const,
              ["Long", long?.verdict] as const,
            ] as const
          ).map(([label, v]) =>
            React.createElement(
              "span",
              {
                key: label,
                className:
                  "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-sm font-semibold " +
                  horizonVerdictPillClass(v),
              },
              React.createElement("span", { className: "text-td-muted font-normal" }, `${label}:`),
              v || "—"
            )
          )
        ),
        swingVsShortLift &&
          React.createElement(
            "p",
            {
              className:
                "mt-2 text-sm text-td-info/95 leading-snug border-t border-td-info/25 pt-2",
              role: "note",
            },
            React.createElement("span", { className: "font-semibold text-td-info" }, "Swing vs short-term: "),
            "Medium is WATCH while Short is WAIT — the 3-month ladder can still allow staged adds on pullbacks even when the 1-month tape is guarded (e.g. growth vs a defensive where both horizons sit on WAIT). Match the row to your actual holding period."
          ),
        hasDivergence &&
          divergenceMessage &&
          React.createElement(
            "p",
            { className: "mt-2 text-sm text-td-warn/90 leading-snug border-t border-td-warn/20 pt-2" },
            divergenceMessage
          )
      ),
      mlHorizonGapExplainer &&
        React.createElement(
          "p",
          {
            className:
              "text-sm text-td-text leading-snug mb-3 rounded-lg border border-td-line/70 bg-td-bg/50 px-3 py-2",
            role: "note",
          },
          React.createElement(
            "span",
            { className: "font-semibold text-td-info/95" },
            "Why ML % differs by horizon: "
          ),
          mlHorizonGapExplainer
        )
    ),
    contextFlags.length > 0 &&
      !(isToday && compactOverview) &&
      React.createElement(
        "div",
        { className: "p-4 border-b border-td-line/80 space-y-2 bg-td-surface/20" },
        contextFlags.map((flag, i) =>
          React.createElement(
            "div",
            {
              key: i,
              className:
                flag.severity === "warning"
                  ? "flex items-start gap-2 rounded-lg border border-td-warn/35 bg-td-warn/10 px-3 py-2.5 text-sm text-td-warn leading-relaxed"
                  : "flex items-start gap-2 rounded-lg border border-td-line/60 bg-td-surface2/60 px-3 py-2.5 text-sm text-td-text leading-relaxed",
            },
            React.createElement("span", { className: "shrink-0 font-semibold text-td-muted" }, flag.severity === "warning" ? "!" : "i"),
            React.createElement("span", null, flag.message)
          )
        )
      ),
    /* Trader roadmap (collapsible) */
    !hideRoadmaps &&
    trader_roadmap && React.createElement(
      "div",
      { className: "border-b border-td-line" },
      React.createElement(
        "button",
        {
          type: "button",
          onClick: () => setTraderOpen((o) => !o),
          className: "w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-td-surface2/30 transition-colors",
        },
        React.createElement("span", { className: "flex items-center gap-2 text-sm font-semibold text-td-text" },
          React.createElement(TrendingUp, { className: "h-4 w-4 text-td-warn" }),
          " Trader roadmap (short / medium)"
        ),
        traderOpen ? React.createElement(ChevronDown, { className: "h-4 w-4 text-td-muted" }) : React.createElement(ChevronRight, { className: "h-4 w-4 text-td-muted" })
      ),
      traderOpen && React.createElement(
        "div",
        { className: "px-4 pb-4 pt-0 space-y-3 text-sm" },
        React.createElement("p", { className: "text-td-text" },
          "Today: ", React.createElement("span", { className: "font-medium text-td-text" }, trader_roadmap.action_today.replace(/_/g, " ")), "."
        ),
        trader_roadmap.short.entry_zone && React.createElement("p", { className: "text-td-muted" },
          "Short (~1 mo): Entry $", trader_roadmap.short.entry_zone.low?.toFixed(2), "–$", trader_roadmap.short.entry_zone.high?.toFixed(2),
          trader_roadmap.short.target != null ? ` â†’ target $${trader_roadmap.short.target.toFixed(2)}` : "",
          trader_roadmap.short.stop != null ? ` · stop $${trader_roadmap.short.stop.toFixed(2)}` : "",
          ". ", trader_roadmap.short.trigger
        ),
        trader_roadmap.medium.entry_zone && React.createElement("p", { className: "text-td-muted" },
          "Medium (3–6 mo): Entry $", trader_roadmap.medium.entry_zone.low?.toFixed(2), "–$", trader_roadmap.medium.entry_zone.high?.toFixed(2),
          trader_roadmap.medium.target != null ? ` â†’ target $${trader_roadmap.medium.target.toFixed(2)}` : "",
          trader_roadmap.medium.stop != null ? ` · stop $${trader_roadmap.medium.stop.toFixed(2)}` : "",
          ". ", trader_roadmap.medium.trigger
        )
      )
    ),
    /* Investor roadmap (collapsible) */
    !hideRoadmaps &&
    investor_roadmap && React.createElement(
      "div",
      { className: "border-b border-td-line" },
      React.createElement(
        "button",
        {
          type: "button",
          onClick: () => setInvestorOpen((o) => !o),
          className: "w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-td-surface2/30 transition-colors",
        },
        React.createElement("span", { className: "flex items-center gap-2 text-sm font-semibold text-td-text" },
          React.createElement(Calendar, { className: "h-4 w-4 text-td-accent" }),
          " Investor roadmap (medium / long)"
        ),
        investorOpen ? React.createElement(ChevronDown, { className: "h-4 w-4 text-td-muted" }) : React.createElement(ChevronRight, { className: "h-4 w-4 text-td-muted" })
      ),
      investorOpen && React.createElement(
        "div",
        { className: "px-4 pb-4 pt-0 space-y-3 text-sm" },
        React.createElement("p", { className: "text-td-text" },
          "Today: ", React.createElement("span", { className: "font-medium text-td-text" }, investor_roadmap.action_today), "."
        ),
        investor_roadmap.add_tiers.length > 0 && React.createElement("p", { className: "text-td-muted" },
          "Add: ",
          investor_roadmap.add_tiers
            .filter((t) => t.low != null && t.high != null)
            .map((t) => `${t.label ?? t.id}: $${(t.low as number).toFixed(2)}–$${(t.high as number).toFixed(2)} (${t.allocation_pct ?? 0}%)`)
            .join(" · ")
        ),
        React.createElement("p", { className: "text-td-muted" },
          "Trim near $", investor_roadmap.trim_near.toFixed(2), ". ", investor_roadmap.hold_thesis
        )
      )
    ),
    (!isToday || isWhy || isFull) &&
    React.createElement(
      "div",
      { className: "p-4 space-y-4" },
      React.createElement(
        "button",
        {
          type: "button",
          onClick: () => setAdvancedDiagnosticsOpen((o) => !o),
          className: "w-full rounded-lg border border-td-line/80 bg-td-surface/40 px-3 py-2.5 text-left hover:bg-td-surface2/50 flex items-center justify-between gap-2",
        },
        React.createElement("span", { className: "text-sm font-medium text-td-text" }, "Methodology & street checks"),
        advancedDiagnosticsOpen ? React.createElement(ChevronDown, { className: "h-4 w-4 text-td-muted" }) : React.createElement(ChevronRight, { className: "h-4 w-4 text-td-muted" })
      ),
      advancedDiagnosticsOpen &&
        React.createElement(
          "div",
          { className: "space-y-3 rounded-lg border border-td-line/70 bg-td-surface/40 p-4" },
          fve &&
            (fve.yahoo_12m_mean_usd != null ||
              fve.fmp_consensus_median_usd != null ||
              fve.fmp_consensus_low_usd != null) &&
            React.createElement(
              "div",
              { className: "rounded-lg border border-td-line/50 bg-td-surface/40 px-3 py-3 text-sm leading-relaxed text-td-text space-y-1.5" },
              React.createElement("p", { className: "text-xs font-semibold uppercase tracking-wide text-td-text" }, "Street price targets"),
              fve.yahoo_12m_mean_usd != null &&
                React.createElement("p", null, `Yahoo 12m mean: $${fve.yahoo_12m_mean_usd.toFixed(2)}`),
              (fve.fmp_consensus_low_usd != null || fve.fmp_consensus_median_usd != null) &&
                React.createElement(
                  "p",
                  null,
                  "Analyst consensus: ",
                  fve.fmp_consensus_low_usd != null && fve.fmp_consensus_high_usd != null
                    ? `$${fve.fmp_consensus_low_usd.toFixed(2)}–$${fve.fmp_consensus_high_usd.toFixed(2)}`
                    : "N/A",
                  fve.fmp_consensus_median_usd != null
                    ? `${fve.fmp_median_is_range_midpoint ? " · midpoint " : " · median "}$${fve.fmp_consensus_median_usd.toFixed(2)}`
                    : ""
                ),
              fve.note && React.createElement("p", { className: "text-sm text-td-muted" }, fve.note)
            ),
          fair_value_metadata &&
            (fair_value_metadata.bear_case != null || fair_value_metadata.methodology_summary || fair_value_metadata.method_used) &&
            React.createElement(
              "div",
              { className: "text-sm" },
              React.createElement(
                "button",
                {
                  type: "button",
                  onClick: () => setMethodologyOpen((o) => !o),
                  className: "flex items-center gap-1.5 text-td-text hover:text-td-text font-medium",
                },
                methodologyOpen ? React.createElement(ChevronDown, { className: "h-3.5 w-3.5" }) : React.createElement(ChevronRight, { className: "h-3.5 w-3.5" }),
                React.createElement(Info, { className: "h-3.5 w-3.5 text-td-info" }),
                "Model methodology & bear case"
              ),
              methodologyOpen &&
                React.createElement(
                  "div",
                  { className: "mt-2 space-y-2 text-sm text-td-text leading-relaxed" },
                  fair_value_metadata.bear_case != null &&
                    React.createElement("p", null, `Bear case: $${fair_value_metadata.bear_case.toFixed(2)}`),
                  fair_value_metadata.method_used &&
                    React.createElement("p", { className: "text-td-text" }, `Method: ${fair_value_metadata.method_used}`),
                  fair_value_metadata.methodology_summary &&
                    React.createElement("p", { className: "text-td-text" }, fair_value_metadata.methodology_summary),
                  Array.isArray(fair_value_metadata.notes) &&
                    fair_value_metadata.notes.map((note: string, i: number) =>
                      React.createElement("p", { key: i, className: "text-td-muted" }, note)
                    )
                )
            ),
          long.entry_tiers &&
            React.createElement(
              "p",
              { className: "text-sm text-td-muted" },
              "Long-tier allocations: open the long-term card → Entry Tiers."
            )
        )
    )
  );
}
