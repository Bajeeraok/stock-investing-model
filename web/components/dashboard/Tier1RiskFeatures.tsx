"use client";

/**
 * Tier1RiskFeatures.tsx
 * All 5 Tier 1 risk management components for Thrive Alpha.
 *
 * Exports:
 *   PositionSizingPanel     â€” Feature 1: Kelly-based sizing
 *   DrawdownSimulator       â€” Feature 2: What-if loss scenarios
 *   ExitLevelsPanel         â€” Feature 3: Stop/take-profit engine
 *   EarningsImpactPanel     â€” Feature 4: Earnings risk assessment
 *   ConcentrationMonitor    â€” Feature 5: Correlation & concentration
 *   RiskDashboard           â€” Combined panel (all 5 in one ToggleSection each)
 *
 * Add to Dashboard.tsx Portfolio tab:
 *   import { RiskDashboard } from "./dashboard/Tier1RiskFeatures";
 *   <RiskDashboard data={data} portfolioValue={portfolioValue} />
 *
 * TypeScript types to add to DashboardData (page.tsx):
 *   position_sizing?:   PositionSizingData[];
 *   drawdown_sim?:      DrawdownSimData[];
 *   exit_levels?:       ExitLevelsData[];
 *   earnings_impacts?:  EarningsImpactData[];
 *   concentration?:     ConcentrationData;
 */

import { useState } from "react";
import {
  AlertTriangle, TrendingUp, TrendingDown, Target,
  Shield, Activity, ChevronDown, ChevronRight,
  Calendar, BarChart3, Layers, Info,
} from "lucide-react";
import { clsx } from "clsx";

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//  TYPES  (mirror Python dataclasses)
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface PositionSizingData {
  ticker:                  string;
  recommended_dollars:     number;
  recommended_shares:      number;
  max_position_dollars:    number;
  current_pct:             number;
  target_pct:              number;
  risk_per_trade_dollars:  number;
  stop_loss_price:         number;
  take_profit_price:       number;
  kelly_fraction:          number;
  adjusted_fraction:       number;
  sizing_rationale:        string[];
  warning?:                string;
}

export interface DrawdownScenario {
  label:                    string;
  price_target:             number;
  pct_change:               number;
  portfolio_impact_dollars: number;
  portfolio_impact_pct:     number;
  probability:              number;
  support_level?:           number;
  description:              string;
}

export interface DrawdownSimData {
  ticker:                      string;
  current_price:               number;
  position_value:              number;
  scenarios:                   DrawdownScenario[];
  max_loss_dollars:            number;
  max_loss_pct:                number;
  breakeven_price:             number;
  atr_14:                      number;
  historical_max_drawdown_pct: number;
}

export interface ExitLevelsData {
  ticker:              string;
  entry_price:         number;
  stop_loss_hard:      number;
  stop_loss_soft:      number;
  take_profit_1:       number;
  take_profit_2:       number;
  take_profit_3:       number;
  trailing_stop_pct:   number;
  invalidation_price:  number;
  time_stop_days:      number;
  risk_reward_ratio:   number;
  thesis_check_points: string[];
}

export interface EarningsImpactData {
  ticker:                  string;
  next_earnings_date:      string;
  days_to_earnings:        number;
  expected_move_pct:       number;
  historical_avg_move:     number;
  beat_rate_pct:           number;
  position_recommendation: string;
  suggested_action:        string;
  iv_percentile:           number;
  last_4_quarters:         Array<{
    quarter: string; actual: number; estimate: number; beat_pct: number;
  }>;
  risk_rating: "Low" | "Medium" | "High" | "Extreme";
}

export interface CorrelationAlert {
  ticker_a:    string;
  ticker_b:    string;
  correlation: number;
  severity:    "High" | "Extreme";
  note:        string;
}

export interface ConcentrationData {
  holdings:              Array<{ ticker: string; value: number; sector?: string }>;
  effective_positions:   number;
  herfindahl_index:      number;
  correlation_alerts:    CorrelationAlert[];
  sector_weights:        Record<string, number>;
  top_risk_contributors: string[];
  diversification_score: number;
  recommendations:       string[];
  is_concentrated:       boolean;
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//  SHARED PRIMITIVES
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function Badge({ label, color }: { label: string; color: "green" | "amber" | "red" | "slate" | "blue" }) {
  const classes = {
    green: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    amber: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    red:   "bg-red-500/15 text-red-300 border-red-500/30",
    slate: "bg-slate-700/50 text-slate-400 border-slate-600",
    blue:  "bg-blue-500/15 text-blue-300 border-blue-500/30",
  }[color];
  return (
    <span className={clsx("inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border", classes)}>
      {label}
    </span>
  );
}

function MetricCard({ label, value, sub, color = "slate" }: {
  label: string; value: string; sub?: string; color?: "green" | "red" | "amber" | "slate";
}) {
  const valueClass = {
    green: "text-emerald-400", red: "text-red-400",
    amber: "text-amber-400",  slate: "text-slate-200",
  }[color];
  return (
    <div className="rounded-lg border border-slate-700/50 bg-slate-800/40 p-3">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={clsx("text-lg font-bold font-mono", valueClass)}>{value}</p>
      {sub && <p className="text-xs text-slate-600 mt-0.5">{sub}</p>}
    </div>
  );
}

function ProbabilityBar({ pct, color }: { pct: number; color: string }) {
  return (
    <div className="w-full h-1 rounded-full bg-slate-700/50 overflow-hidden">
      <div className={clsx("h-full rounded-full transition-all", color)} style={{ width: `${pct * 100}%` }} />
    </div>
  );
}

function SectionHeader({ icon, title, badge, children }: {
  icon: React.ReactNode; title: string; badge?: React.ReactNode; children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <span className="text-slate-400">{icon}</span>
      <h3 className="text-sm font-semibold text-slate-300">{title}</h3>
      {badge}
      {children && <span className="ml-auto">{children}</span>}
    </div>
  );
}

function Collapsible({ title, children, defaultOpen = true, badgeEl }: {
  title: string; children: React.ReactNode; defaultOpen?: boolean; badgeEl?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/40 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 bg-slate-800/50 hover:bg-slate-800/80 transition-colors text-left"
      >
        {open ? <ChevronDown className="h-4 w-4 text-slate-500" /> : <ChevronRight className="h-4 w-4 text-slate-500" />}
        <span className="text-sm font-semibold text-slate-300 flex-1">{title}</span>
        {badgeEl}
      </button>
      {open && <div className="p-4">{children}</div>}
    </div>
  );
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//  FEATURE 1 â€” POSITION SIZING PANEL
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function PositionSizingPanel({ items }: { items: PositionSizingData[] }) {
  const [selected, setSelected] = useState(items[0]?.ticker ?? "");
  const data = items.find(i => i.ticker === selected) ?? items[0];

  if (!data) return <p className="text-sm text-slate-500">No sizing data available.</p>;

  const hasSize  = data.recommended_dollars > 0;
  const riskColor: "green" | "amber" | "red" = (
    data.risk_per_trade_dollars < 500  ? "green" :
    data.risk_per_trade_dollars < 2000 ? "amber" : "red"
  );

  return (
    <div className="space-y-4">
      {/* Ticker selector */}
      {items.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {items.map(i => (
            <button
              key={i.ticker}
              onClick={() => setSelected(i.ticker)}
              className={clsx(
                "px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors",
                selected === i.ticker
                  ? "bg-emerald-600/20 border-emerald-500/50 text-emerald-300"
                  : "border-slate-700 text-slate-400 hover:bg-slate-800"
              )}
            >
              {i.ticker}
            </button>
          ))}
        </div>
      )}

      {/* Warning banner */}
      {data.warning && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-xs text-amber-200">{data.warning}</p>
        </div>
      )}

      {/* Main recommendation */}
      <div className={clsx(
        "rounded-xl border p-4",
        hasSize
          ? "border-emerald-500/25 bg-emerald-500/5"
          : "border-slate-700 bg-slate-800/30"
      )}>
        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Recommended Add</p>
            <p className={clsx("text-3xl font-bold font-mono", hasSize ? "text-emerald-300" : "text-slate-500")}>
              {hasSize ? `$${data.recommended_dollars.toLocaleString()}` : "No Add"}
            </p>
            {hasSize && (
              <p className="text-sm text-slate-400 mt-0.5">
                {data.recommended_shares} shares Â· {(data.target_pct * 100).toFixed(1)}% of portfolio
              </p>
            )}
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-500 mb-1">Kelly Fraction</p>
            <p className="text-2xl font-mono font-bold text-slate-300">
              {(data.adjusted_fraction * 100).toFixed(1)}%
            </p>
            <p className="text-xs text-slate-600">adjusted</p>
          </div>
        </div>

        {/* Position bar */}
        <div className="space-y-1 mb-3">
          <div className="flex justify-between text-xs text-slate-600">
            <span>Current: {(data.current_pct * 100).toFixed(1)}%</span>
            <span>Target: {(data.target_pct * 100).toFixed(1)}%</span>
            <span>Max: 10%</span>
          </div>
          <div className="relative h-2 rounded-full bg-slate-700/60 overflow-hidden">
            {/* Current */}
            <div
              className="absolute inset-y-0 left-0 bg-slate-500/60 rounded-full"
              style={{ width: `${Math.min(data.current_pct * 10 * 100, 100)}%` }}
            />
            {/* Add */}
            <div
              className="absolute inset-y-0 bg-emerald-500/70 rounded-full"
              style={{
                left: `${Math.min(data.current_pct * 10 * 100, 100)}%`,
                width: `${Math.min((data.target_pct - data.current_pct) * 10 * 100, 100)}%`
              }}
            />
            {/* Max line */}
            <div className="absolute inset-y-0 right-0 w-px bg-red-500/60" />
          </div>
        </div>
      </div>

      {/* Stop / Target / Risk */}
      <div className="grid grid-cols-3 gap-3">
        <MetricCard label="Hard Stop" value={`$${data.stop_loss_price}`} sub="Exit no questions asked" color="red" />
        <MetricCard label="Take Profit" value={`$${data.take_profit_price}`} sub="First target" color="green" />
        <MetricCard label="$ At Risk" value={`$${data.risk_per_trade_dollars.toLocaleString()}`}
          sub={`${((data.risk_per_trade_dollars / (data.recommended_dollars || 1)) * 100).toFixed(1)}% of trade`}
          color={riskColor}
        />
      </div>

      {/* Kelly breakdown */}
      <Collapsible title="Sizing rationale" defaultOpen={false}>
        <ol className="space-y-1">
          {data.sizing_rationale.map((r, i) => (
            <li
              key={i}
              className={clsx(
                "flex items-start gap-2 text-xs",
                r.startsWith("Win rate derived") || r.startsWith("Win rate input")
                  ? "text-emerald-300"
                  : "text-slate-400"
              )}
            >
              <span className="text-slate-600 shrink-0 font-mono w-4">{i + 1}.</span>
              {r}
            </li>
          ))}
        </ol>
      </Collapsible>
    </div>
  );
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//  FEATURE 2 â€” DRAWDOWN SIMULATOR
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function DrawdownSimulatorPanel({ items, portfolioValue }: {
  items: DrawdownSimData[]; portfolioValue: number;
}) {
  const [selected, setSelected] = useState(items[0]?.ticker ?? "");
  const data = items.find(i => i.ticker === selected) ?? items[0];
  if (!data) return <p className="text-sm text-slate-500">No simulation data.</p>;

  const maxLossPct = data.max_loss_pct * 100;
  const impactColor = maxLossPct < -5 ? "red" : maxLossPct < -2 ? "amber" : "green";

  return (
    <div className="space-y-4">
      {items.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {items.map(i => (
            <button key={i.ticker} onClick={() => setSelected(i.ticker)}
              className={clsx("px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors",
                selected === i.ticker
                  ? "bg-red-600/20 border-red-500/50 text-red-300"
                  : "border-slate-700 text-slate-400 hover:bg-slate-800"
              )}>
              {i.ticker}
            </button>
          ))}
        </div>
      )}

      {/* Header stats */}
      <div className="grid grid-cols-3 gap-3">
        <MetricCard label="Current Price"  value={`$${data.current_price}`} />
        <MetricCard label="Position Value" value={`$${data.position_value.toLocaleString()}`} />
        <MetricCard label="Worst Case Loss" value={`$${Math.abs(data.max_loss_dollars).toLocaleString()}`}
          sub={`${(data.max_loss_pct * 100).toFixed(1)}% of portfolio`} color={impactColor} />
      </div>

      {/* Scenario table */}
      <div className="rounded-xl border border-slate-700/50 overflow-hidden">
        <div className="px-4 py-2 bg-slate-800/50 border-b border-slate-700/50">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Loss Scenarios â€” Ask "Can I survive this?"
          </p>
        </div>
        <div className="divide-y divide-slate-700/40">
          {data.scenarios.map((s, i) => {
            const isWorst = i === data.scenarios.length - 1;
            const pctColor = s.pct_change < -15 ? "text-red-400" : s.pct_change < -5 ? "text-amber-400" : "text-slate-400";
            return (
              <div key={i} className={clsx("p-3 space-y-2", isWorst && "bg-red-500/5")}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-slate-300">{s.label}</span>
                      {isWorst && <Badge label="Stress" color="red" />}
                    </div>
                    <p className="text-xs text-slate-600 mt-0.5">{s.description}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className={clsx("text-base font-bold font-mono", pctColor)}>
                      {s.pct_change > 0 ? "+" : ""}{s.pct_change.toFixed(1)}%
                    </p>
                    <p className="text-xs text-slate-500">â†’ ${s.price_target}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <ProbabilityBar pct={s.probability}
                      color={s.probability > 0.4 ? "bg-slate-500" : s.probability > 0.2 ? "bg-amber-500/60" : "bg-red-500/60"} />
                  </div>
                  <span className="text-xs text-slate-500 shrink-0">
                    P={Math.round(s.probability * 100)}%
                  </span>
                  <span className={clsx("text-xs font-mono shrink-0",
                    s.portfolio_impact_dollars < -1000 ? "text-red-400" :
                    s.portfolio_impact_dollars < -200  ? "text-amber-400" : "text-slate-400"
                  )}>
                    Portfolio: ${s.portfolio_impact_dollars.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex items-start gap-2 px-3 py-2 rounded-lg border border-slate-700/40 bg-slate-800/20">
        <Info className="h-3.5 w-3.5 text-slate-600 shrink-0 mt-0.5" />
        <p className="text-xs text-slate-500">
          Breakeven: <span className="text-slate-400 font-mono">${data.breakeven_price}</span> Â·
          ATR(14): <span className="text-slate-400 font-mono">${data.atr_14}</span> Â·
          Historical max drawdown: <span className="text-slate-400">{data.historical_max_drawdown_pct.toFixed(0)}%</span>
        </p>
      </div>
    </div>
  );
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//  FEATURE 3 â€” EXIT LEVELS PANEL
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function ExitLevelsPanel({ items }: { items: ExitLevelsData[] }) {
  const [selected, setSelected] = useState(items[0]?.ticker ?? "");
  const data = items.find(i => i.ticker === selected) ?? items[0];
  if (!data) return <p className="text-sm text-slate-500">No exit data.</p>;

  const rrColor: "green" | "amber" | "red" = data.risk_reward_ratio >= 2 ? "green" : data.risk_reward_ratio >= 1.5 ? "amber" : "red";
  const levels = [
    { label: "Invalidation", price: data.invalidation_price, color: "text-red-500",    note: "Thesis broken â€” exit immediately" },
    { label: "Hard Stop",    price: data.stop_loss_hard,    color: "text-red-400",    note: "No-questions exit" },
    { label: "Soft Stop",    price: data.stop_loss_soft,    color: "text-amber-400",  note: "Review position" },
    { label: "Entry",        price: data.entry_price,       color: "text-slate-300",  note: "Your entry" },
    { label: "Target 1",     price: data.take_profit_1,     color: "text-emerald-400",note: "Trim â…“" },
    { label: "Target 2",     price: data.take_profit_2,     color: "text-emerald-300",note: "Trim â…“" },
    { label: "Target 3",     price: data.take_profit_3,     color: "text-emerald-200",note: "Full exit" },
  ].sort((a, b) => b.price - a.price);

  const priceRange = data.take_profit_3 - data.invalidation_price;

  return (
    <div className="space-y-4">
      {items.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {items.map(i => (
            <button key={i.ticker} onClick={() => setSelected(i.ticker)}
              className={clsx("px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors",
                selected === i.ticker
                  ? "bg-blue-600/20 border-blue-500/50 text-blue-300"
                  : "border-slate-700 text-slate-400 hover:bg-slate-800"
              )}>
              {i.ticker}
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="R/R Ratio" value={`${data.risk_reward_ratio.toFixed(1)}:1`}
          sub="Risk/reward" color={rrColor} />
        <MetricCard label="Trailing Stop" value={`${data.trailing_stop_pct}%`}
          sub="Once in profit" color="amber" />
        <MetricCard label="Time Stop" value={`${data.time_stop_days}d`}
          sub="Exit if no progress" />
        <MetricCard label="Hard Stop" value={`$${data.stop_loss_hard}`}
          sub="ATR-based" color="red" />
      </div>

      {/* Visual price ladder */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/30 p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Price Ladder</p>
        <div className="space-y-1">
          {levels.map((lv, i) => {
            const pct = priceRange > 0 ? ((lv.price - data.invalidation_price) / priceRange) * 100 : 50;
            const isEntry = lv.label === "Entry";
            return (
              <div key={i} className={clsx(
                "flex items-center gap-3 px-2 py-1.5 rounded-lg",
                isEntry && "bg-slate-800/60 border border-slate-700/50"
              )}>
                <div className="w-24 shrink-0">
                  <div className="h-1 rounded-full bg-slate-700/50">
                    <div className={clsx("h-full rounded-full",
                      lv.color.includes("red") ? "bg-red-500/60" :
                      lv.color.includes("amber") ? "bg-amber-500/60" : "bg-emerald-500/60"
                    )} style={{ width: `${pct}%` }} />
                  </div>
                </div>
                <span className={clsx("text-xs font-medium w-20 shrink-0", lv.color)}>{lv.label}</span>
                <span className="text-sm font-mono text-slate-300 w-20 shrink-0">${lv.price}</span>
                <span className="text-xs text-slate-600">{lv.note}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Thesis checkpoints */}
      <Collapsible title="Thesis checkpoints â€” verify regularly" defaultOpen>
        <ul className="space-y-2">
          {data.thesis_check_points.map((chk, i) => (
            <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
              <span className="w-4 h-4 rounded border border-slate-600 shrink-0 mt-0.5 flex items-center justify-center">
                <span className="text-slate-600 text-xs">âœ“</span>
              </span>
              {chk}
            </li>
          ))}
        </ul>
      </Collapsible>
    </div>
  );
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//  FEATURE 4 â€” EARNINGS IMPACT PANEL
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const EARNINGS_RISK_CONFIG = {
  Low:     { color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/25", badge: "green" as const },
  Medium:  { color: "text-amber-400",   bg: "bg-amber-500/10",   border: "border-amber-500/25",   badge: "amber" as const },
  High:    { color: "text-orange-400",  bg: "bg-orange-500/10",  border: "border-orange-500/25",  badge: "amber" as const },
  Extreme: { color: "text-red-300",     bg: "bg-red-500/10",     border: "border-red-500/25",     badge: "red"   as const },
};

export function EarningsImpactPanel({ items }: { items: EarningsImpactData[] }) {
  // Sort by soonest earnings
  const sorted = [...items].sort((a, b) => a.days_to_earnings - b.days_to_earnings);

  return (
    <div className="space-y-3">
      {sorted.map((data) => {
        const cfg = EARNINGS_RISK_CONFIG[data.risk_rating];
        const isUrgent = data.days_to_earnings <= 14;

        return (
          <div key={data.ticker} className={clsx(
            "rounded-xl border p-4 space-y-3",
            cfg.bg, cfg.border
          )}>
            {/* Header */}
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-base font-bold text-slate-200">{data.ticker}</span>
                  <Badge label={`Risk: ${data.risk_rating}`} color={cfg.badge} />
                  {isUrgent && <Badge label={`${data.days_to_earnings}d away`} color="red" />}
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {data.next_earnings_date} Â· {data.days_to_earnings} days to earnings
                </p>
              </div>
              <div className="text-right shrink-0">
                <p className={clsx("text-xl font-bold font-mono", cfg.color)}>
                  Â±{data.expected_move_pct}%
                </p>
                <p className="text-xs text-slate-600">implied move</p>
              </div>
            </div>

            {/* Key stats */}
            <div className="grid grid-cols-3 gap-2">
              <div className="text-center">
                <p className="text-xs text-slate-600">Beat rate</p>
                <p className={clsx("text-base font-bold",
                  data.beat_rate_pct >= 70 ? "text-emerald-400" : data.beat_rate_pct >= 50 ? "text-amber-400" : "text-red-400"
                )}>{data.beat_rate_pct.toFixed(0)}%</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-slate-600">Hist avg move</p>
                <p className="text-base font-bold text-slate-300">Â±{data.historical_avg_move.toFixed(1)}%</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-slate-600">IV percentile</p>
                <p className={clsx("text-base font-bold",
                  data.iv_percentile > 75 ? "text-red-400" : data.iv_percentile > 50 ? "text-amber-400" : "text-emerald-400"
                )}>{data.iv_percentile.toFixed(0)}th</p>
              </div>
            </div>

            {/* Recommendation */}
            <div className="rounded-lg border border-slate-700/40 bg-slate-900/40 px-3 py-2">
              <p className={clsx("text-xs font-semibold mb-1", cfg.color)}>
                {data.position_recommendation}
              </p>
              <p className="text-xs text-slate-400">{data.suggested_action}</p>
            </div>

            {/* Last 4 quarters */}
            {data.last_4_quarters.length > 0 && (
              <div>
                <p className="text-xs text-slate-600 mb-1.5">Last {data.last_4_quarters.length} quarters</p>
                <div className="flex gap-2 flex-wrap">
                  {data.last_4_quarters.map((q, i) => (
                    <div key={i} className="rounded-lg border border-slate-700/40 bg-slate-800/40 px-2 py-1.5 text-center min-w-[80px]">
                      <p className="text-xs text-slate-600">{q.quarter}</p>
                      <p className={clsx("text-xs font-bold",
                        (q.beat_pct ?? 0) > 0 ? "text-emerald-400" : "text-red-400"
                      )}>
                        {(q.beat_pct ?? 0) > 0 ? "Beat" : "Miss"} {Math.abs(q.beat_pct ?? 0).toFixed(1)}%
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//  FEATURE 5 â€” CONCENTRATION MONITOR
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function ConcentrationMonitorPanel({ data }: { data: ConcentrationData }) {
  const scoreColor: "green" | "amber" | "red" = (
    data.diversification_score >= 70 ? "green" :
    data.diversification_score >= 50 ? "amber" : "red"
  );

  return (
    <div className="space-y-4">
      {/* Concentration warning banner */}
      {data.is_concentrated && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-amber-300">Concentration Risk Detected</p>
            <p className="text-xs text-amber-400/70 mt-0.5">Your portfolio has fewer independent bets than it appears. See details below.</p>
          </div>
        </div>
      )}

      {/* Key metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="Diversification Score" value={`${data.diversification_score.toFixed(0)}/100`}
          sub="Higher = better" color={scoreColor} />
        <MetricCard label="Effective Positions" value={data.effective_positions.toFixed(1)}
          sub="Independent bets"
          color={data.effective_positions < 4 ? "red" : data.effective_positions < 7 ? "amber" : "green"} />
        <MetricCard label="HHI Index" value={data.herfindahl_index.toFixed(3)}
          sub="< 0.18 = diversified"
          color={data.herfindahl_index > 0.18 ? "red" : "green"} />
        <MetricCard label="Positions" value={String(data.holdings.length)}
          sub="Total holdings" />
      </div>

      {/* Sector breakdown */}
      {Object.keys(data.sector_weights).length > 0 && (
        <div className="rounded-xl border border-slate-700/50 bg-slate-900/30 p-4">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Sector Weights</p>
          <div className="space-y-2">
            {Object.entries(data.sector_weights)
              .sort(([,a],[,b]) => b - a)
              .map(([sector, weight]) => {
                const pct = weight * 100;
                const overweight = pct > 25;
                return (
                  <div key={sector} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className={overweight ? "text-amber-400" : "text-slate-400"}>{sector}</span>
                      <span className={clsx("font-mono", overweight ? "text-amber-400" : "text-slate-400")}>
                        {pct.toFixed(1)}%
                        {overweight && " âš ï¸"}
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-slate-700/50 overflow-hidden">
                      <div
                        className={clsx("h-full rounded-full transition-all",
                          overweight ? "bg-amber-500" : pct > 15 ? "bg-blue-500/60" : "bg-slate-500/60"
                        )}
                        style={{ width: `${Math.min(pct * 4, 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Correlation alerts */}
      {data.correlation_alerts.length > 0 && (
        <div className="rounded-xl border border-red-500/25 bg-red-500/5 p-4">
          <SectionHeader icon={<Activity className="h-4 w-4" />} title="Correlation Alerts">
            <Badge label={String(data.correlation_alerts.length)} color="red" />
          </SectionHeader>
          <div className="space-y-2">
            {data.correlation_alerts.map((alert, i) => (
              <div key={i} className={clsx(
                "rounded-lg border p-3",
                alert.severity === "Extreme"
                  ? "border-red-500/30 bg-red-500/5"
                  : "border-amber-500/25 bg-amber-500/5"
              )}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-bold text-slate-300">{alert.ticker_a}</span>
                  <span className="text-slate-600">â†”</span>
                  <span className="text-sm font-bold text-slate-300">{alert.ticker_b}</span>
                  <Badge
                    label={`${(alert.correlation * 100).toFixed(0)}% corr`}
                    color={alert.severity === "Extreme" ? "red" : "amber"}
                  />
                </div>
                <p className="text-xs text-slate-400">{alert.note}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top risk contributors */}
      {data.top_risk_contributors.length > 0 && (
        <div className="rounded-lg border border-slate-700/50 bg-slate-800/20 p-3">
          <p className="text-xs text-slate-500 mb-2">Top risk contributors</p>
          <div className="flex flex-wrap gap-2">
            {data.top_risk_contributors.map((c, i) => (
              <span key={i} className="text-xs text-slate-300 bg-slate-800 border border-slate-700 px-2 py-1 rounded-lg">
                {c}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/20 p-4">
        <SectionHeader icon={<Shield className="h-4 w-4" />} title="Recommendations" />
        <ul className="space-y-2">
          {data.recommendations.map((r, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
              <span className={clsx(
                "w-1.5 h-1.5 rounded-full shrink-0 mt-1.5",
                r.includes("healthy") ? "bg-emerald-500" :
                r.includes("Reduce") || r.includes("above") ? "bg-amber-500" : "bg-slate-500"
              )} />
              {r}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//  COMBINED RISK DASHBOARD â€” drop into Portfolio tab
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

type ExitHorizon = "short" | "medium" | "long";

interface RiskDashboardProps {
  positionSizing?:       PositionSizingData[];
  drawdownSim?:          DrawdownSimData[];
  exitLevels?:           ExitLevelsData[];
  exitLevelsByHorizon?:  { short?: ExitLevelsData[]; medium?: ExitLevelsData[]; long?: ExitLevelsData[] };
  earningsImpacts?:      EarningsImpactData[];
  concentration?:        ConcentrationData;
  portfolioValue?:      number;
}

const HORIZON_LABELS: Record<ExitHorizon, string> = {
  short:  "Short-term (~1 mo · 20 trading days)",
  medium: "Medium-term (~3–6 mo · 60d)",
  long:   "Long-term (~12–18 mo · 120d)",
};

export function RiskDashboard({
  positionSizing, drawdownSim, exitLevels, exitLevelsByHorizon,
  earningsImpacts, concentration, portfolioValue = 0,
}: RiskDashboardProps) {
  const [exitHorizon, setExitHorizon] = useState<ExitHorizon>("medium");
  const effectiveExitLevels =
    exitLevelsByHorizon?.[exitHorizon] ?? exitLevels ?? [];
  const hasExitByHorizon = Boolean(exitLevelsByHorizon?.short?.length || exitLevelsByHorizon?.medium?.length || exitLevelsByHorizon?.long?.length);
  const earningsUrgent = (earningsImpacts ?? []).filter(e => e.days_to_earnings <= 14).length;
  const concAlert      = concentration?.is_concentrated;
  const hasAnyData     = positionSizing?.length || drawdownSim?.length ||
                          effectiveExitLevels?.length || exitLevels?.length || earningsImpacts?.length || concentration;

  if (!hasAnyData) {
    return (
      <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-8 text-center">
        <Shield className="h-10 w-10 text-slate-500 mx-auto mb-2 opacity-60" />
        <p className="text-slate-400 font-medium">No risk data for this portfolio yet</p>
        <p className="text-slate-500 text-sm mt-1">
          Add holdings with quantities in config, then click <span className="text-emerald-400">Refresh</span> to compute
          position sizing, drawdown scenarios, and concentration.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Pinned alerts strip */}
      {(earningsUrgent > 0 || concAlert) && (
        <div className="flex flex-wrap gap-2">
          {earningsUrgent > 0 && (
            <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-300">
              <Calendar className="h-3.5 w-3.5" />
              {earningsUrgent} position{earningsUrgent > 1 ? "s" : ""} with earnings in â‰¤14 days
            </div>
          )}
          {concAlert && (
            <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs text-red-300">
              <Layers className="h-3.5 w-3.5" />
              Concentration risk detected
            </div>
          )}
        </div>
      )}

      {/* Feature 1 */}
      {positionSizing?.length ? (
        <Collapsible
          title="Position Sizing (Kelly Criterion)"
          badgeEl={<Badge label={`${positionSizing.length} tickers`} color="green" />}
        >
          <PositionSizingPanel items={positionSizing} />
        </Collapsible>
      ) : null}

      {/* Feature 2 */}
      {drawdownSim?.length ? (
        <Collapsible
          title="Drawdown Simulation â€” What If I'm Wrong?"
          badgeEl={<Badge label={`${drawdownSim.length} tickers`} color="amber" />}
        >
          <DrawdownSimulatorPanel items={drawdownSim} portfolioValue={portfolioValue} />
        </Collapsible>
      ) : null}

      {/* Feature 3 */}
      {(effectiveExitLevels?.length || exitLevels?.length) ? (
        <Collapsible
          title="Exit Levels â€” Stop Loss & Take Profit"
          badgeEl={
            hasExitByHorizon ? (
              <div className="flex items-center gap-2 flex-wrap">
                <select
                  value={exitHorizon}
                  onChange={(e) => setExitHorizon(e.target.value as ExitHorizon)}
                  className="rounded border border-slate-600 bg-slate-800 text-slate-200 text-xs px-2 py-1 focus:border-emerald-500 focus:outline-none"
                  aria-label="Time horizon"
                >
                  {(["short", "medium", "long"] as const).map((h) => (
                    <option key={h} value={h}>{HORIZON_LABELS[h]}</option>
                  ))}
                </select>
                <Badge label={`${effectiveExitLevels.length} tickers`} color="blue" />
              </div>
            ) : (
              <Badge label={`${exitLevels?.length ?? 0} tickers`} color="blue" />
            )
          }
        >
          <ExitLevelsPanel items={effectiveExitLevels.length ? effectiveExitLevels : (exitLevels ?? [])} />
        </Collapsible>
      ) : null}

      {/* Feature 4 */}
      {earningsImpacts?.length ? (
        <Collapsible
          title="Earnings Impact Assessment"
          badgeEl={
            <div className="flex gap-1.5">
              {earningsUrgent > 0 && <Badge label={`${earningsUrgent} urgent`} color="red" />}
              <Badge label={`${earningsImpacts.length} total`} color="amber" />
            </div>
          }
        >
          <EarningsImpactPanel items={earningsImpacts} />
        </Collapsible>
      ) : null}

      {/* Feature 5 */}
      {concentration ? (
        <Collapsible
          title="Concentration & Correlation Monitor"
          badgeEl={
            <Badge
              label={concentration.is_concentrated ? "Alert" : `${concentration.diversification_score.toFixed(0)}/100`}
              color={concentration.is_concentrated ? "red" : "green"}
            />
          }
        >
          <ConcentrationMonitorPanel data={concentration} />
        </Collapsible>
      ) : null}

      <p className="text-xs text-slate-600 text-center pt-2">
        Not financial advice. Sizing models are probabilistic â€” always verify with your own risk tolerance.
      </p>
    </div>
  );
}

