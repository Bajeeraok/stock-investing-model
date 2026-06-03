"use client";

/**
 * PriceTargetsPanel.tsx
 * Renders consolidated buy/sell zones, expected returns, and scenario analysis
 * for the ML section of the TickerDetailModal.
 *
 * Data shape mirrors price_targets.py run_price_targets() output.
 * Three sections:
 *   1. Horizon table  — entry zone, base/bull/bear targets, stop, RR, expected return
 *   2. Technical levels  — MA50 / MA200 / 52w-low anchors (explanation)
 *   3. Scenario table  — 5-6 scenarios with triggers, targets, returns, probabilities
 */

import { useState } from "react";
import {
  TrendingUp, TrendingDown, Target, Shield, ChevronDown,
  ChevronRight, Info, Zap, AlertTriangle, DollarSign,
  Activity, Calendar,
} from "lucide-react";
import { clsx } from "clsx";
import { UnifiedValuationSummary } from "./UnifiedValuationSummary";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface EntryZone {
  low:    number;
  high:   number;
  anchor: string;
  note:   string;
}

export interface HorizonTargets {
  horizon_key:    string;
  label:          string;
  days:           number;
  ml_prob_pct:    number | null;
  threshold_pct:  number;
  interpretation: string;
  entry_zone:     EntryZone;
  targets: {
    base: number;
    bull: number;
    bear: number;
  };
  returns: {
    base:     number;
    bull:     number;
    bear:     number;
    expected: number | null;
  };
  stop_loss:   number;
  risk_reward: number | null;
  action_hint: string;
}

export interface AnalystTargets {
  median?:         number | null;
  high?:           number | null;
  low?:            number | null;
  analyst_count?:  number | null;
  median_return?:  number | null;
  high_return?:    number | null;
  low_return?:     number | null;
  available?:      boolean;
  note?:           string;
}

export interface Scenario {
  scenario_type:     string;
  name:              string;
  trigger:           string;
  rationale:         string;
  probability:       number;
  price_target:      number;
  return_pct:        number;
  timeframe:         string;
  is_base:           boolean;
  macro_note?:       string;
  analyst_anchored?: boolean;
}

export interface TechnicalLevels {
  ma50:    number | null;
  ma200:   number | null;
  low_52w: number | null;
  high_52w: number | null;
  note:    string;
}

export interface MacroContext {
  vix:         number | null;
  yield_10y:   number | null;
  yield_2y:    number | null;
  yield_curve: number | null;
  fed_rate:    number | null;
  cpi_yoy:     number | null;
  dxy:         number | null;
  note:        string;
}

export interface EarningsInfo {
  next_earnings_date?: string;
  days_until_earnings?: number;
  earnings_note?:       string;
}

export interface EarningsTarget {
  available: boolean;
  next_earnings_date?: string;
  days_until_earnings?: number;
  expected_move_pct?: number;
  upside_target?: number;
  downside_target?: number;
  directional_target?: number;
  bias?: string;
  bias_prob_pct?: number | null;
  historical_events?: number;
  historical_avg_abs_move_pct?: number | null;
  historical_median_abs_move_pct?: number | null;
  calibration_hit_rate?: number | null;
  calibration_mae_pct?: number | null;
  confidence_pct?: number | null;
  backtest_events?: number;
  backtest_summary?: {
    evaluated_events?: number;
    containment_hit_rate?: number | null;
    mean_abs_error_pct?: number | null;
  } | null;
  recent_events?: Array<{
    event_date: string;
    pre_close: number;
    post_close: number;
    realized_move_pct: number;
    abs_move_pct: number;
  }>;
  method_note?: string;
}

export interface PriceTargetsData {
  ticker:           string;
  analysis_date:    string;
  current_price:    number;
  market_regime:    string;
  asset_type:       string;
  confluence_score: number;
  macro_context?:   MacroContext;
  earnings_info?:   EarningsInfo;
  earnings_target?: EarningsTarget;
  analyst_targets?: AnalystTargets;
  technical_levels: TechnicalLevels;
  horizons: {
    short?:  HorizonTargets;
    medium?: HorizonTargets;
    long?:   HorizonTargets;
  };
  scenarios: Scenario[];
  error?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(n: number | null | undefined, sign = true): string {
  if (n == null) return "—";
  return `${sign && n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function fmtProb(n: number | null | undefined): string {
  if (n == null) return "N/A";
  return `${n.toFixed(0)}%`;
}

function returnColor(r: number | null | undefined): string {
  if (r == null) return "text-slate-400";
  if (r >= 8)  return "text-emerald-400";
  if (r >= 3)  return "text-green-400";
  if (r >= 0)  return "text-amber-400";
  if (r >= -5) return "text-orange-400";
  return "text-red-400";
}

function probColor(p: number | null | undefined): string {
  if (p == null) return "text-slate-500";
  if (p >= 55) return "text-emerald-400";
  if (p >= 35) return "text-amber-400";
  return "text-red-400";
}

function rrColor(rr: number | null | undefined): string {
  if (rr == null) return "text-slate-500";
  if (rr >= 2.5) return "text-emerald-400";
  if (rr >= 1.5) return "text-amber-400";
  return "text-red-400";
}

function normalizeToneLabel(raw: string | null | undefined): "Constructive" | "Neutral" | "Cautionary" | "Unavailable" {
  const s = String(raw || "").trim().toLowerCase();
  if (!s) return "Unavailable";
  if (s === "strong" || s === "bullish" || s === "constructive") return "Constructive";
  if (s === "neutral") return "Neutral";
  if (s === "cautious" || s === "weak" || s === "bearish" || s === "cautionary") return "Cautionary";
  return "Unavailable";
}

function interpBadge(interp: string) {
  const cfg: Record<string, string> = {
    Constructive: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30",
    Neutral:      "text-amber-300   bg-amber-500/10   border-amber-500/30",
    Cautionary:   "text-orange-300  bg-orange-500/10  border-orange-500/30",
    Unavailable:  "text-slate-500   bg-slate-700/20   border-slate-600/20",
  };
  const tone = normalizeToneLabel(interp);
  return cfg[tone] ?? cfg.Unavailable;
}

// ─────────────────────────────────────────────────────────────────────────────
// Live macro context bar
// ─────────────────────────────────────────────────────────────────────────────

function MacroContextBar({ ctx }: { ctx: MacroContext }) {
  const items: { label: string; value: string; color: string }[] = [];

  if (ctx.vix != null) {
    const c = ctx.vix > 28 ? "text-red-400" : ctx.vix > 20 ? "text-amber-400" : "text-emerald-400";
    items.push({ label: "VIX", value: ctx.vix.toFixed(1), color: c });
  }
  if (ctx.yield_10y != null) {
    items.push({ label: "10Y", value: `${ctx.yield_10y.toFixed(2)}%`, color: "text-blue-400" });
  }
  if (ctx.yield_curve != null) {
    const c = ctx.yield_curve < 0 ? "text-red-400" : "text-emerald-400";
    const label = ctx.yield_curve < 0 ? "Curve ⚠️" : "Curve";
    items.push({ label, value: `${ctx.yield_curve > 0 ? "+" : ""}${ctx.yield_curve.toFixed(2)}%`, color: c });
  }
  if (ctx.fed_rate != null) {
    items.push({ label: "Fed Rate", value: `${ctx.fed_rate.toFixed(2)}%`, color: "text-purple-400" });
  }
  if (ctx.cpi_yoy != null) {
    const c = ctx.cpi_yoy > 3.5 ? "text-red-400" : ctx.cpi_yoy > 2.5 ? "text-amber-400" : "text-emerald-400";
    items.push({ label: "CPI YoY", value: `${ctx.cpi_yoy.toFixed(1)}%`, color: c });
  }
  if (ctx.dxy != null) {
    const c = ctx.dxy > 105 ? "text-orange-400" : "text-slate-300";
    items.push({ label: "DXY", value: ctx.dxy.toFixed(1), color: c });
  }

  if (items.length === 0) return null;

  return (
    <div className="bg-slate-800/40 rounded-xl border border-slate-700/30 px-3.5 py-2.5">
      <div className="flex items-center gap-2 mb-2">
        <Activity size={11} className="text-blue-400" />
        <span className="text-[10px] font-semibold text-blue-300 uppercase tracking-widest">
          Live Macro — scenario probabilities gated on these
        </span>
      </div>
      <div className="flex items-center gap-4 flex-wrap">
        {items.map(it => (
          <div key={it.label} className="flex items-baseline gap-1.5">
            <span className="text-[10px] text-slate-500">{it.label}</span>
            <span className={clsx("text-xs font-mono font-bold", it.color)}>{it.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Analyst consensus strip (FMP data)
// ─────────────────────────────────────────────────────────────────────────────

function AnalystConsensusStrip({ at, price }: { at: AnalystTargets; price: number }) {
  if (!at.available || (!at.median && !at.high && !at.low)) return null;

  return (
    <div className="bg-purple-500/5 border border-purple-500/20 rounded-xl px-3.5 py-2.5 space-y-2">
      <div className="flex items-center gap-2">
        <Target size={11} className="text-purple-400" />
        <span className="text-[10px] font-semibold text-purple-300 uppercase tracking-widest">
          Wall Street Analyst Consensus
          {at.analyst_count ? ` · ${at.analyst_count} analysts` : ""}
          <span className="font-normal text-slate-500 ml-1">(FMP · used to anchor Bull/Base scenario targets)</span>
        </span>
      </div>
      <div className="flex items-center gap-5 flex-wrap">
        {at.high != null && (
          <div className="text-center">
            <p className="text-[10px] text-slate-500">Analyst High</p>
            <p className={clsx("text-sm font-mono font-bold", returnColor(at.high_return ?? 0))}>{fmt(at.high)}</p>
            <p className={clsx("text-[10px]", returnColor(at.high_return ?? 0))}>{fmtPct(at.high_return)}</p>
          </div>
        )}
        {at.median != null && (
          <div className="text-center">
            <p className="text-[10px] text-slate-500">Consensus Target</p>
            <p className={clsx("text-sm font-mono font-bold", returnColor(at.median_return ?? 0))}>{fmt(at.median)}</p>
            <p className={clsx("text-[10px]", returnColor(at.median_return ?? 0))}>{fmtPct(at.median_return)}</p>
          </div>
        )}
        {at.low != null && (
          <div className="text-center">
            <p className="text-[10px] text-slate-500">Analyst Low</p>
            <p className={clsx("text-sm font-mono font-bold", returnColor(at.low_return ?? 0))}>{fmt(at.low)}</p>
            <p className={clsx("text-[10px]", returnColor(at.low_return ?? 0))}>{fmtPct(at.low_return)}</p>
          </div>
        )}
        <div className="text-center">
          <p className="text-[10px] text-slate-500">Current</p>
          <p className="text-sm font-mono font-bold text-white">{fmt(price)}</p>
        </div>
      </div>
      {at.note && <p className="text-[10px] text-slate-600 leading-snug">{at.note}</p>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Earnings timing banner
// ─────────────────────────────────────────────────────────────────────────────

function EarningsBanner({ info }: { info: EarningsInfo }) {
  if (!info.earnings_note) return null;
  const days = info.days_until_earnings ?? 999;
  const urgent = days <= 7;
  const soon   = days <= 21;

  return (
    <div className={clsx(
      "flex items-start gap-2 rounded-xl border px-3.5 py-2.5",
      urgent ? "border-red-500/40 bg-red-500/10" :
      soon   ? "border-amber-500/30 bg-amber-500/8" :
               "border-slate-700/30 bg-slate-800/30"
    )}>
      <Calendar size={12} className={clsx(
        "mt-0.5 shrink-0",
        urgent ? "text-red-400" : soon ? "text-amber-400" : "text-slate-400"
      )} />
      <p className={clsx(
        "text-xs leading-relaxed",
        urgent ? "text-red-300" : soon ? "text-amber-300" : "text-slate-400"
      )}>
        {info.earnings_note}
        {soon && (
          <span className="block text-[10px] mt-0.5 text-slate-500">
            Earnings scenarios adjusted for event probability
          </span>
        )}
      </p>
    </div>
  );
}

function EarningsTargetCard({ et, price }: { et: EarningsTarget; price: number }) {
  if (!et.available) return null;
  const hitRatePct = et.calibration_hit_rate != null ? et.calibration_hit_rate * 100 : null;
  const biasLabel = normalizeToneLabel(et.bias);
  const biasTone =
    biasLabel === "Constructive" ? "text-emerald-300" :
    biasLabel === "Cautionary" ? "text-orange-300" :
    "text-amber-300";

  return (
    <div className="bg-indigo-500/5 border border-indigo-500/20 rounded-xl px-3.5 py-3 space-y-2.5">
      <div className="flex items-center gap-2">
        <Target size={11} className="text-indigo-300" />
        <span className="text-[10px] font-semibold text-indigo-200 uppercase tracking-widest">
          Earnings Event Target (1-Day Reaction)
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div>
          <p className="text-[10px] text-slate-500">Expected Move</p>
          <p className="text-sm font-mono font-bold text-indigo-200">{fmtPct(et.expected_move_pct)}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500">Upside</p>
          <p className="text-sm font-mono font-bold text-emerald-300">{fmt(et.upside_target)}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500">Downside</p>
          <p className="text-sm font-mono font-bold text-red-300">{fmt(et.downside_target)}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500">Bias</p>
          <p className={clsx("text-xs font-semibold", biasTone)}>
            {biasLabel === "Unavailable" ? "Neutral" : biasLabel}
            {et.bias_prob_pct != null ? ` (${Math.round(et.bias_prob_pct)}%)` : ""}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500">Directional</p>
          <p className="text-sm font-mono font-bold text-slate-100">{fmt(et.directional_target)}</p>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px]">
        <div>
          <span className="text-slate-500">Current</span>{" "}
          <span className="font-mono text-slate-300">{fmt(price)}</span>
        </div>
        <div>
          <span className="text-slate-500">Events</span>{" "}
          <span className="font-mono text-slate-300">{et.historical_events ?? 0}</span>
        </div>
        <div>
          <span className="text-slate-500">Hit Rate</span>{" "}
          <span className="font-mono text-slate-300">{hitRatePct != null ? `${Math.round(hitRatePct)}%` : "—"}</span>
        </div>
        <div>
          <span className="text-slate-500">Confidence</span>{" "}
          <span className="font-mono text-slate-300">{et.confidence_pct != null ? `${et.confidence_pct}%` : "—"}</span>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-[11px]">
        <div>
          <span className="text-slate-500">Backtest Events</span>{" "}
          <span className="font-mono text-slate-300">{et.backtest_events ?? 0}</span>
        </div>
        <div>
          <span className="text-slate-500">MAE</span>{" "}
          <span className="font-mono text-slate-300">{et.calibration_mae_pct != null ? `${et.calibration_mae_pct.toFixed(2)}%` : "—"}</span>
        </div>
        <div>
          <span className="text-slate-500">Avg Hist Move</span>{" "}
          <span className="font-mono text-slate-300">{et.historical_avg_abs_move_pct != null ? `${et.historical_avg_abs_move_pct.toFixed(1)}%` : "—"}</span>
        </div>
      </div>
      {!!(et.recent_events && et.recent_events.length) && (
        <div className="rounded-lg border border-slate-700/40 bg-slate-900/30 px-2.5 py-2">
          <p className="text-[10px] text-slate-500 mb-1 uppercase tracking-widest">Recent Earnings Outcomes</p>
          <div className="space-y-1">
            {et.recent_events!.slice().reverse().map((ev) => (
              <div key={ev.event_date} className="flex items-center justify-between gap-2 text-[10px]">
                <span className="text-slate-400">{ev.event_date}</span>
                <span className={clsx("font-mono", ev.realized_move_pct >= 0 ? "text-emerald-300" : "text-red-300")}>
                  {ev.realized_move_pct >= 0 ? "+" : ""}{ev.realized_move_pct.toFixed(2)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      {et.method_note && (
        <p className="text-[10px] text-slate-500 leading-snug">{et.method_note}</p>
      )}
    </div>
  );
}

const HORIZON_META: Record<string, { label: string; Icon: React.ElementType; color: string }> = {
  short:  { label: "Short-term",  Icon: Zap,       color: "text-blue-400"    },
  medium: { label: "Medium-term", Icon: TrendingUp, color: "text-amber-400"  },
  long:   { label: "Long-term",   Icon: Target,     color: "text-emerald-400" },
};

// ─────────────────────────────────────────────────────────────────────────────
// Horizon row — full buy/sell breakdown for one time horizon
// ─────────────────────────────────────────────────────────────────────────────

function HorizonCard({ h }: { h: HorizonTargets }) {
  const [open, setOpen] = useState(false);
  const meta = HORIZON_META[h.horizon_key] ?? HORIZON_META.short;
  const Icon = meta.Icon;
  const hasML = h.ml_prob_pct !== null;
  const toneLabel = normalizeToneLabel(h.interpretation);

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-800/60 transition-colors text-left"
      >
        <Icon size={15} className={meta.color} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={clsx("text-sm font-bold", meta.color)}>{meta.label}</span>
            <span className="text-xs text-slate-400">{h.label}</span>
            {hasML && (
              <span className={clsx("text-[10px] font-semibold px-1.5 py-0.5 rounded border", interpBadge(h.interpretation))}>
                {toneLabel === "Unavailable" ? h.interpretation : toneLabel}
              </span>
            )}
          </div>
          {/* Quick summary line */}
          <div className="flex items-center gap-3 mt-0.5 flex-wrap">
            <span className="text-[11px] text-slate-400">
              Entry <span className="text-slate-200 font-mono">{fmt(h.entry_zone.low)}–{fmt(h.entry_zone.high)}</span>
            </span>
            <span className="text-[11px] text-slate-400">
              Target <span className={clsx("font-mono font-semibold", returnColor(h.returns.base))}>{fmt(h.targets.base)}</span>
              <span className={clsx("ml-1", returnColor(h.returns.base))}>(+{h.returns.base.toFixed(1)}%)</span>
            </span>
            {h.ml_prob_pct !== null && (
              <span className="text-[11px] text-slate-400">
                ML <span className={clsx("font-mono font-semibold", probColor(h.ml_prob_pct))}>{fmtProb(h.ml_prob_pct)}</span>
              </span>
            )}
          </div>
        </div>
        {open ? <ChevronDown size={14} className="text-slate-500 shrink-0" /> : <ChevronRight size={14} className="text-slate-500 shrink-0" />}
      </button>

      {/* Expanded detail */}
      {open && (
        <div className="border-t border-slate-700/40 px-4 pb-4 space-y-4 pt-4">

          {/* 3-column grid: Entry | Targets | Risk */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">

            {/* Entry zone */}
            <div className="bg-slate-800/60 rounded-xl p-3.5 space-y-2 border border-emerald-500/15">
              <div className="flex items-center gap-1.5">
                <DollarSign size={12} className="text-emerald-400" />
                <span className="text-[10px] font-semibold text-emerald-300 uppercase tracking-widest">Buy Zone</span>
              </div>
              <div className="space-y-1">
                <DataRow label="Low"    value={fmt(h.entry_zone.low)}  color="text-emerald-300" mono />
                <DataRow label="High"   value={fmt(h.entry_zone.high)} color="text-emerald-300" mono />
                <DataRow label="Anchor" value={h.entry_zone.anchor}    color="text-slate-300"   />
              </div>
              <p className="text-[10px] text-slate-500 leading-snug">{h.entry_zone.note}</p>
            </div>

            {/* Price targets */}
            <div className="bg-slate-800/60 rounded-xl p-3.5 space-y-2 border border-slate-700/30">
              <div className="flex items-center gap-1.5">
                <Target size={12} className="text-blue-400" />
                <span className="text-[10px] font-semibold text-blue-300 uppercase tracking-widest">Price Targets</span>
              </div>
              <div className="space-y-1">
                <DataRow label="🐂 Bull"   value={`${fmt(h.targets.bull)} (${fmtPct(h.returns.bull)})`}  color={returnColor(h.returns.bull)} mono />
                <DataRow label="📊 Base"   value={`${fmt(h.targets.base)} (${fmtPct(h.returns.base)})`}  color={returnColor(h.returns.base)} mono />
                <DataRow label="🐻 Bear"   value={`${fmt(h.targets.bear)} (${fmtPct(h.returns.bear)})`}  color={returnColor(h.returns.bear)} mono />
              </div>
              {h.returns.expected !== null && (
                <div className="border-t border-slate-700/40 pt-1.5">
                  <DataRow
                    label="Expected EV"
                    value={fmtPct(h.returns.expected)}
                    color={returnColor(h.returns.expected)}
                    mono
                    bold
                  />
                  <p className="text-[10px] text-slate-500 mt-0.5">Probability-weighted return</p>
                </div>
              )}
            </div>

            {/* Risk metrics */}
            <div className="bg-slate-800/60 rounded-xl p-3.5 space-y-2 border border-red-500/10">
              <div className="flex items-center gap-1.5">
                <Shield size={12} className="text-red-400" />
                <span className="text-[10px] font-semibold text-red-300 uppercase tracking-widest">Risk</span>
              </div>
              <div className="space-y-1">
                <DataRow
                  label={h.horizon_key === "long" ? "Invalidation (52w)" : "Stop loss"}
                  value={fmt(h.stop_loss)}
                  color="text-red-400"
                  mono
                />
                <DataRow label="Risk/Reward"  value={h.risk_reward != null ? `${h.risk_reward}×` : "—"} color={rrColor(h.risk_reward)} mono />
                <DataRow label="ML Prob"      value={fmtProb(h.ml_prob_pct)} color={probColor(h.ml_prob_pct)} mono />
              </div>
              <p className="text-[10px] text-slate-500 leading-snug">
                {h.horizon_key === "long"
                  ? "~5% below 52-week low — structural invalidation / tail-stress floor, not a tight trailing stop"
                  : `Stop below ${h.horizon_key === "short" ? "MA50" : "MA200"} (×0.97)`}
              </p>
            </div>
          </div>

          {/* Action hint */}
          <div className="flex items-start gap-2 bg-slate-800/40 rounded-lg px-3 py-2.5 border border-slate-700/30">
            <Info size={12} className="text-blue-400 mt-0.5 shrink-0" />
            <p className="text-xs text-slate-300 leading-relaxed">{h.action_hint}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function DataRow({ label, value, color = "text-slate-300", mono = false, bold = false }: {
  label: string; value: string; color?: string; mono?: boolean; bold?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-[10px] text-slate-500 shrink-0">{label}</span>
      <span className={clsx("text-xs truncate text-right", color, mono && "font-mono", bold && "font-bold")}>
        {value}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Technical levels explanation bar
// ─────────────────────────────────────────────────────────────────────────────

export function TechnicalLevelsBar({ lv, price }: { lv: TechnicalLevels; price: number }) {
  if (!lv.ma50 && !lv.ma200) return null;
  const levels = [
    { label: "52w Low",  value: lv.low_52w,  color: "text-red-400",     dot: "bg-red-400"     },
    { label: "MA200",    value: lv.ma200,    color: "text-orange-400",   dot: "bg-orange-400"  },
    { label: "MA50",     value: lv.ma50,     color: "text-amber-400",    dot: "bg-amber-400"   },
    { label: "Current",  value: price,       color: "text-white",        dot: "bg-white"       },
    { label: "52w High", value: lv.high_52w, color: "text-emerald-400",  dot: "bg-emerald-400" },
  ].filter(l => l.value != null);

  return (
    <div className="bg-slate-800/30 rounded-xl border border-slate-700/30 p-3.5 space-y-3">
      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest">
        Technical Level Anchors — Entry Zone Logic
      </p>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        {levels.map(l => (
          <div key={l.label} className="flex items-center gap-1.5 text-xs">
            <span className={clsx("w-1.5 h-1.5 rounded-full shrink-0", l.dot)} />
            <span className="text-slate-500">{l.label}</span>
            <span className={clsx("font-mono font-semibold", l.color)}>{fmt(l.value)}</span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-slate-500 leading-snug">{lv.note}</p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Scenario table
// ─────────────────────────────────────────────────────────────────────────────

function ScenarioRow({ s, price }: { s: Scenario; price: number }) {
  const [open, setOpen] = useState(false);
  const isPositive = s.return_pct >= 0;
  const isBase     = s.is_base;

  return (
    <div className={clsx(
      "rounded-xl border overflow-hidden",
      isBase       ? "border-blue-500/30 bg-blue-500/5"         :
      isPositive   ? "border-emerald-500/20 bg-emerald-500/5"   :
                     "border-red-500/20 bg-red-500/5"
    )}>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/3 transition-colors"
      >
        {/* Return icon */}
        <div className={clsx("w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
          isPositive ? "bg-emerald-500/15" : "bg-red-500/15"
        )}>
          {isPositive
            ? <TrendingUp size={13} className="text-emerald-400" />
            : <TrendingDown size={13} className="text-red-400" />}
        </div>

        {/* Name + trigger */}
        <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-slate-200">{s.name}</span>
            {isBase && (
              <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border text-blue-300 bg-blue-500/10 border-blue-500/30">BASE</span>
            )}
            {s.analyst_anchored && (
              <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border text-purple-300 bg-purple-500/10 border-purple-500/30">ANALYST TARGET</span>
            )}
          </div>
          <p className="text-[11px] text-slate-400 truncate mt-0.5">{s.trigger}</p>
        </div>

        {/* Key numbers */}
        <div className="flex items-center gap-4 shrink-0">
          <div className="text-right hidden sm:block">
            <p className="text-[10px] text-slate-500">Target</p>
            <p className="text-xs font-mono font-semibold text-slate-200">{fmt(s.price_target)}</p>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-slate-500">Return</p>
            <p className={clsx("text-sm font-mono font-bold", returnColor(s.return_pct))}>
              {fmtPct(s.return_pct)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-slate-500">Prob</p>
            <p className={clsx("text-xs font-mono font-semibold", probColor(s.probability * 100))}>
              {Math.round(s.probability * 100)}%
            </p>
          </div>
          {open ? <ChevronDown size={13} className="text-slate-500" /> : <ChevronRight size={13} className="text-slate-500" />}
        </div>
      </button>

      {/* Expanded rationale */}
      {open && (
        <div className="border-t border-slate-700/30 px-4 py-3 space-y-2.5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <p className="text-[10px] text-slate-500 mb-0.5">Price Target</p>
              <p className="text-sm font-mono font-bold text-slate-200">{fmt(s.price_target)}</p>
              <p className={clsx("text-xs font-mono", returnColor(s.return_pct))}>{fmtPct(s.return_pct)} vs current</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 mb-0.5">Scenario Probability</p>
              <p className={clsx("text-sm font-mono font-bold", probColor(s.probability * 100))}>
                {Math.round(s.probability * 100)}%
              </p>
              <p className="text-[10px] text-slate-500">ML-adjusted estimate</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 mb-0.5">Expected Value</p>
              <p className={clsx("text-sm font-mono font-bold", returnColor(s.return_pct * s.probability))}>
                {fmtPct(s.return_pct * s.probability)}
              </p>
              <p className="text-[10px] text-slate-500">Return × Probability</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 mb-0.5">Timeframe</p>
              <p className="text-xs font-semibold text-slate-300">{s.timeframe}</p>
            </div>
          </div>
          <div className="bg-slate-800/50 rounded-lg px-3 py-2.5">
            <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Rationale</p>
            <p className="text-xs text-slate-300 leading-relaxed">{s.rationale}</p>
          </div>
          {s.macro_note && (
            <div className="flex items-start gap-1.5 bg-blue-500/5 border border-blue-500/20 rounded-lg px-3 py-2">
              <Activity size={10} className="text-blue-400 mt-0.5 shrink-0" />
              <p className="text-[11px] text-blue-300 leading-snug">{s.macro_note}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main panel
// ─────────────────────────────────────────────────────────────────────────────

export function PriceTargetsPanel({ data, hideHorizonZones }: { data: PriceTargetsData; hideHorizonZones?: boolean }) {
  const [showScenarios, setShowScenarios] = useState(true);

  if (data.error) {
    return (
      <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3">
        <AlertTriangle size={14} className="text-red-400 shrink-0" />
        <p className="text-xs text-red-300">{data.error}</p>
      </div>
    );
  }

  const horizonOrder = ["short", "medium", "long"] as const;
  const hasHorizons  = horizonOrder.some(k => data.horizons[k]);
  const scenarios    = data.scenarios ?? [];
  const bullScenarios = scenarios.filter(s => s.return_pct >= 0).length;
  const bearScenarios = scenarios.filter(s => s.return_pct < 0).length;

  return (
    <div className="space-y-4">

      {/* ── Header strip ── */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <h3 className="text-sm font-bold text-slate-100">Price Targets & Scenario Analysis</h3>
          <p className="text-[11px] text-slate-400 mt-0.5">
            {hideHorizonZones ? "Entry logic in Investor Decision Summary above · " : "Entry zones anchored to MA50 / MA200 / 52w-low · "}
            {scenarios.length} scenarios ·
            <span className="text-emerald-400 ml-1">{bullScenarios} bullish</span>
            <span className="text-slate-500"> / </span>
            <span className="text-red-400">{bearScenarios} bearish</span>
            <span className="ml-2 text-slate-600">as of {data.analysis_date}</span>
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span className="font-mono font-bold text-white">{fmt(data.current_price)}</span>
          <span className="text-slate-600">current</span>
        </div>
      </div>

      {/* ── Unified valuation (street PT + buy/sell counts + deck) ── */}
      {(valuationDeck || data.analyst_targets) && !hideAnalystStrip && (
        <UnifiedValuationSummary
          deck={valuationDeck}
          analystTargets={data.analyst_targets}
          currentPrice={data.current_price}
          fairValue={fairValue}
          external={fairValueExternal ?? undefined}
          decisionMode={decisionMode}
          showFullDeck={false}
        />
      )}

      {/* ── Live macro context ── */}
      {data.macro_context && <MacroContextBar ctx={data.macro_context} />}

      {/* ── Earnings timing ── */}
      {data.earnings_info && <EarningsBanner info={data.earnings_info} />}
      {data.earnings_target && <EarningsTargetCard et={data.earnings_target} price={data.current_price} />}

      {/* ── Technical level anchors ── */}
      {!hideTechnicalLevels && (
        <TechnicalLevelsBar lv={data.technical_levels} price={data.current_price} />
      )}

      {/* ── Horizon cards (hidden when Investor Decision Summary is shown to avoid conflicting entry logic) ── */}
      {!hideHorizonZones && hasHorizons && (
        <div className="space-y-2">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest">
            Buy / Sell Zones by Horizon
          </p>
          {horizonOrder.map(k => {
            const h = data.horizons[k];
            if (!h) return null;
            return <HorizonCard key={k} h={h} />;
          })}
        </div>
      )}

      {/* ── Scenario analysis ── */}
      {scenarios.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] font-semibold text-violet-300/90 uppercase tracking-widest">
            Scenario analysis ({scenarios.length} scenarios)
          </p>
          <button
            type="button"
            onClick={() => setShowScenarios((v) => !v)}
            className="flex items-center gap-2 text-[10px] text-slate-500 w-full hover:text-slate-300 transition-colors"
          >
            {showScenarios ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {showScenarios ? "Collapse list" : "Expand list"}
          </button>

          {showScenarios && (
            <div className="space-y-2">
              {scenarios.map((s, i) => (
                <ScenarioRow key={i} s={s} price={data.current_price} />
              ))}

              {/* Expected value footer */}
              <div className="bg-slate-800/40 rounded-xl border border-slate-700/30 px-4 py-3">
                <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">
                  Portfolio-Weighted Expected Value
                </p>
                <div className="flex items-center gap-4 flex-wrap">
                  {(() => {
                    const totalWeight = scenarios.reduce((s, sc) => s + sc.probability, 0);
                    const ev = totalWeight > 0
                      ? scenarios.reduce((s, sc) => s + sc.return_pct * sc.probability, 0) / totalWeight
                      : null;
                    const evPct = ev != null ? Math.round(ev * 10) / 10 : null;
                    return (
                      <>
                        <div>
                          <p className={clsx("text-xl font-mono font-bold", returnColor(evPct))}>
                            {evPct != null ? fmtPct(evPct) : "—"}
                          </p>
                          <p className="text-[10px] text-slate-500">Prob-weighted return across all scenarios</p>
                        </div>
                        <div className="text-xs text-slate-400 leading-relaxed max-w-sm">
                          {evPct != null && evPct >= 3 && "Positive expected value — the odds favor entry with proper position sizing and a defined stop."}
                          {evPct != null && evPct >= 0 && evPct < 3 && "Marginally positive — wait for a better entry in the buy zone or a higher ML probability signal."}
                          {evPct != null && evPct < 0 && "Negative expected value — do not enter until regime or ML signal improves."}
                        </div>
                      </>
                    );
                  })()}
                </div>
              </div>

              <p className="text-[10px] text-slate-600 text-center leading-relaxed">
                Scenarios are model-generated estimates based on historical patterns, asset type, and ML signal strength.
                Not financial advice. Always verify with current macro conditions.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
