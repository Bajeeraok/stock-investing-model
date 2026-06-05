"use client";

import { clsx } from "clsx";
import {
  AlertTriangle,
  Calendar,
  ChevronDown,
  ChevronRight,
  Grid3X3,
  PieChart,
  Shield,
  Target,
  Thermometer,
  TrendingUp,
} from "lucide-react";
import { useState } from "react";
import type { DashboardData } from "@/app/page";
import type { PreMarketData } from "./PreMarketPanel";
import { PremarketMoverStrip } from "./PremarketMoverStrip";
import { PhaseCSessionBlock } from "./PhaseCSessionBlock";
import type { RetailMarketDecisions } from "./RetailMarketDecisionsPanel";
import { ToggleSection } from "./ToggleSection";
import { RetailMarketDecisionsDeepDive } from "./RetailMarketDecisionsDeepDive";
import {
  matrixHorizonOrder,
  primaryHorizonKey,
  tradingLensHint,
  tradingLensLabel,
  type TradingLens,
} from "@/lib/tradingLens";
import { MiniEquityCurve, TrustMetricsStrip } from "./tradingPlatformUX";

const ACTION_STYLE: Record<string, string> = {
  BUY: "bg-emerald-500/25 text-emerald-200 border-emerald-500/45",
  WAIT: "bg-sky-500/20 text-sky-200 border-sky-500/40",
  TRIM: "bg-amber-500/25 text-amber-200 border-amber-500/45",
  HOLD: "bg-slate-600/30 text-slate-200 border-slate-500/50",
  REDUCE: "bg-amber-500/20 text-amber-200 border-amber-500/40",
};

const MATRIX_ACTION: Record<string, string> = {
  BUY: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  HOLD: "bg-slate-600/25 text-slate-200 border-slate-500/40",
  REDUCE: "bg-amber-500/20 text-amber-200 border-amber-500/40",
  WAIT: "bg-violet-500/20 text-violet-200 border-violet-500/40",
};

/** One-line concrete action under abstract stance labels (ST/MT/LT matrix). */
const STANCE_ACTION_HINT: Record<string, string> = {
  "ACCUMULATE DIPS": "Add on red days near support — not chase gaps",
  "CORE BUILDER": "Build size on pullbacks that hold",
  "STAY INVESTED": "Hold core — skip new buys unless tier hit",
  "ACCUMULATE": "Add in band — respect stop",
  "REDUCE EXPOSURE": "Trim winners or cut weak lines",
  "WAIT FOR CLARITY": "No new size until tape confirms",
};

function KpiChip({
  label,
  value,
  sub,
  tone = "neutral",
  title,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "warn" | "good" | "cool";
  title?: string;
}) {
  const toneCls =
    tone === "warn"
      ? "border-amber-500/35 bg-amber-950/20"
      : tone === "good"
        ? "border-emerald-500/30 bg-emerald-950/15"
        : tone === "cool"
          ? "border-sky-500/30 bg-sky-950/20"
          : "border-slate-600/60 bg-slate-800/40";
  return (
    <div
      className={clsx("rounded-lg border px-3 py-2 min-w-[7rem] flex-1", toneCls)}
      title={title}
    >
      <p className="text-[10px] uppercase tracking-wider text-slate-300 font-medium">{label}</p>
      <p className="text-sm font-semibold text-slate-100 mt-0.5 tabular-nums">{value}</p>
      {sub && <p className="text-[11px] text-slate-300 mt-0.5 leading-snug">{sub}</p>}
    </div>
  );
}

function RiskMeter({ score, scale }: { score?: number; scale?: string }) {
  const s = Math.min(10, Math.max(0, score ?? 0));
  const pct = (s / 10) * 100;
  const color = s >= 7 ? "bg-amber-400" : s >= 4 ? "bg-emerald-400" : "bg-emerald-500";
  return (
    <div className="flex-1 min-w-[10rem]">
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <span className="text-[10px] uppercase tracking-wider text-slate-300 font-medium">Portfolio risk</span>
        <span className="text-sm font-bold text-slate-100 tabular-nums">
          {score ?? "—"}
          <span className="text-xs font-normal text-slate-400 ml-1">{scale}</span>
        </span>
      </div>
      <div className="h-2 rounded-full bg-slate-700/80 overflow-hidden">
        <div className={clsx("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

interface Props {
  briefing: DashboardData["retail_briefing"] | null | undefined;
  market: RetailMarketDecisions | null | undefined;
  marketQuadrant?: string | null;
  macroBackdrop?: { bullets?: string[]; disclaimer?: string } | null;
  preMarketFull?: PreMarketData | null;
  preMarket?: DashboardData["pre_market"];
  todayMoveTickers?: Set<string>;
  tradingLens?: TradingLens;
  /** Rendered after hero for Scout (e.g. tactical breakouts). */
  tacticalSlot?: React.ReactNode;
  guestUniverseNote?: string | null;
  onTickerClick?: (ticker: string) => void;
  forwardTracking?: DashboardData["forward_tracking"];
  modelHealth?: DashboardData["model_health"];
  modelValidation?: DashboardData["model_validation"];
  paperTrading?: DashboardData["paper_trading"];
}

const HORIZON_TAG: Record<string, string> = {
  short_term: "ST",
  medium_term: "MT",
  long_term: "LT",
};

const HORIZON_LABEL: Record<string, string> = {
  short_term: "Short",
  medium_term: "Medium",
  long_term: "Long",
};

export function OverviewAtAGlance({
  briefing,
  market,
  marketQuadrant,
  macroBackdrop,
  preMarketFull,
  preMarket,
  todayMoveTickers: coveredTickers,
  tradingLens = "scout",
  tacticalSlot,
  guestUniverseNote,
  onTickerClick,
  forwardTracking,
  modelHealth,
  modelValidation,
  paperTrading,
}: Props) {
  const [analogOpen, setAnalogOpen] = useState(false);

  if (!briefing && !market) return null;

  const rb = briefing;
  const db = rb?.daily_briefing;
  const ctx = market?.market_context;
  const temp = market?.market_temperature;
  const matrix = market?.strategy_matrix;
  const risk = market?.portfolio_risk;
  const allSuggested = db?.suggested_actions ?? [];
  const suggested = coveredTickers?.size
    ? allSuggested.filter((a) => !coveredTickers.has(a.ticker.toUpperCase()))
    : allSuggested;
  const skippedSuggested = allSuggested.length - suggested.length;
  const heat = rb?.portfolio_heat_pct ?? 0;
  const top3 = rb?.concentration?.concentration_pct;
  const nudges: { icon: typeof Shield; text: string; tone: string }[] = [];
  if (rb?.drawdown_guard) nudges.push({ icon: Shield, text: rb.drawdown_guard, tone: "border-amber-500/30 bg-amber-500/10 text-amber-100" });
  if (rb?.sector_gap) nudges.push({ icon: PieChart, text: rb.sector_gap, tone: "border-slate-600/70 bg-slate-800/50 text-slate-200" });
  if (rb?.concentration?.message) nudges.push({ icon: AlertTriangle, text: rb.concentration.message, tone: "border-amber-500/25 bg-amber-950/15 text-amber-100" });
  if (rb?.overtrading_nudge) nudges.push({ icon: TrendingUp, text: rb.overtrading_nudge, tone: "border-sky-500/25 bg-sky-950/15 text-sky-100" });

  const vixStr = temp?.vix != null ? temp.vix.toFixed(1) : null;
  const hyDriver = temp?.drivers?.find((d) => d.toLowerCase().includes("spread") || d.toLowerCase().includes("hy"));
  const macroDriver = temp?.drivers?.find((d) => d.toLowerCase().includes("macro") || d.toLowerCase().includes("risk"));
  const primaryKey = primaryHorizonKey(tradingLens);
  const matrixOrder = matrixHorizonOrder(tradingLens);
  const showPortfolioKpis = tradingLens === "owner" || tradingLens === "swing";
  const matrixBlock = matrix ? (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
      {matrixOrder.map((key) => {
        const row = matrix[key];
        if (!row) return null;
        const tag = HORIZON_TAG[key];
        const label = HORIZON_LABEL[key];
        const isPrimary =
          (key === "short_term" && primaryKey === "short") ||
          (key === "medium_term" && primaryKey === "medium") ||
          (key === "long_term" && primaryKey === "long");
        return (
          <div
            key={key}
            className={clsx(
              "rounded-xl border bg-slate-800/50 p-3 flex flex-col gap-2",
              isPrimary ? "border-emerald-500/50 ring-1 ring-emerald-500/25" : "border-slate-600/70"
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                {tag} · {label}
                {isPrimary && (
                  <span className="ml-1 text-[10px] text-emerald-400 font-normal normal-case">focus</span>
                )}
              </span>
              {row.action && (
                <span
                  className={clsx(
                    "text-[10px] font-bold uppercase px-2 py-0.5 rounded border",
                    MATRIX_ACTION[row.action] ?? MATRIX_ACTION.HOLD
                  )}
                >
                  {row.action}
                </span>
              )}
            </div>
            {row.stance && <p className="text-sm font-medium text-slate-100">{row.stance}</p>}
            {(STANCE_ACTION_HINT[row.stance ?? ""] ?? (row.bullets ?? [])[0]) && (
              <p className="text-xs text-emerald-200/90 leading-snug">
                {STANCE_ACTION_HINT[row.stance ?? ""] ?? (row.bullets ?? [])[0]}
              </p>
            )}
          </div>
        );
      })}
    </div>
  ) : null;

  const priorityBlock =
    suggested.length > 0 ? (
      <div className="rounded-xl border border-slate-600/80 bg-slate-800/40 px-4 py-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200 mb-2 flex items-center gap-1.5">
          <Grid3X3 className="h-3.5 w-3.5 text-emerald-400" />
          {skippedSuggested > 0 || coveredTickers?.size ? "More priority actions" : "Priority actions"}
        </h3>
        {skippedSuggested > 0 && (
          <p className="text-[11px] text-slate-400 mb-2">
            {skippedSuggested} ticker{skippedSuggested === 1 ? "" : "s"} already in Today&apos;s 3 moves above.
          </p>
        )}
        <ul className="space-y-2">
          {suggested.slice(0, 4).map((a, i) => (
            <li key={`${a.ticker}-${i}`} className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => onTickerClick?.(a.ticker)}
                className="font-semibold text-emerald-300 hover:text-emerald-200 hover:underline"
              >
                {a.ticker}
              </button>
              <span
                className={clsx(
                  "text-[10px] font-bold uppercase px-2 py-0.5 rounded border",
                  ACTION_STYLE[a.action] ?? ACTION_STYLE.HOLD
                )}
              >
                {a.action}
              </span>
              <span className="text-sm text-slate-300">{a.reason}</span>
            </li>
          ))}
        </ul>
      </div>
    ) : null;

  const nudgesBlock =
    nudges.length > 0 ? (
      <ul className="space-y-2">
        {nudges.map((n, i) => (
          <li key={i} className={clsx("flex items-start gap-2 rounded-lg border px-3 py-2 text-sm", n.tone)}>
            <n.icon className="h-4 w-4 shrink-0 mt-0.5 opacity-80" />
            <span>{n.text}</span>
          </li>
        ))}
      </ul>
    ) : null;

  const gateFourFour = forwardTracking?.summary_by_gates?.["4/4"];
  const holdAddHit =
    modelHealth?.forward_hold_add_hit_rate_20d ??
    forwardTracking?.summary_by_signal?.HOLD?.hit_rate_pct ??
    forwardTracking?.summary_by_signal?.ADD?.hit_rate_pct ??
    null;
  const forwardObs =
    modelHealth?.forward_observations_20d ??
    forwardTracking?.summary_by_signal?.HOLD?.n_observations ??
    null;
  const gateCohortEdge =
    gateFourFour?.avg_return_pct != null && gateFourFour.n_observations
      ? `+${gateFourFour.avg_return_pct.toFixed(1)}% avg`
      : null;

  return (
    <div className="space-y-4">
      {/* Hero + KPI strip */}
      <section className="rounded-xl border border-emerald-500/25 bg-gradient-to-br from-slate-900/90 to-emerald-950/20 overflow-hidden">
        <div className="px-4 py-3 border-b border-emerald-500/15 flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-emerald-400 shrink-0" />
            <h2 className="text-base font-semibold text-slate-50">Today at a glance</h2>
          </div>
          {ctx?.quadrant && (
            <span className="text-[11px] font-medium uppercase tracking-wide text-emerald-300/90 px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-950/30">
              {ctx.quadrant.replace(/_/g, " ")}
            </span>
          )}
        </div>

        <div className="p-4 space-y-4">
          <div className="flex flex-col sm:flex-row gap-3 sm:items-start">
            <TrustMetricsStrip
              className="flex-1"
              forwardHitRate={holdAddHit}
              forwardObservations={forwardObs}
              gateCohortEdge={gateCohortEdge}
              directionAccuracy={modelValidation?.summary?.direction_accuracy_pct ?? null}
              paperWinRate={paperTrading?.summary?.win_rate_pct ?? null}
            />
            <MiniEquityCurve
              points={paperTrading?.equity_curve ?? []}
              className="sm:w-52 shrink-0"
            />
          </div>
          <p className="text-[11px] text-slate-400 -mt-1">{tradingLensHint(tradingLens)}</p>
          {guestUniverseNote && (
            <p className="text-[11px] text-sky-200/90 rounded-md border border-sky-500/25 bg-sky-950/20 px-2.5 py-1.5">
              {guestUniverseNote}
            </p>
          )}
          {ctx?.primary_message && (
            <div>
              <p className="text-base sm:text-lg font-bold text-emerald-100 leading-snug tracking-tight">
                {ctx.primary_message}
              </p>
              {ctx.explanation && (
                <p className="text-sm text-slate-200 mt-2 leading-relaxed max-w-3xl">{ctx.explanation}</p>
              )}
              <div className="flex flex-wrap gap-2 mt-3">
                {ctx.temperature_label && (
                  <span className="text-xs font-medium px-2.5 py-1 rounded-md border border-sky-500/40 bg-sky-950/40 text-sky-100">
                    ST sentiment: {ctx.temperature_label}
                  </span>
                )}
                {ctx.regime_label && (
                  <span className="text-xs font-medium px-2.5 py-1 rounded-md border border-emerald-500/40 bg-emerald-950/35 text-emerald-100">
                    Regime: {ctx.regime_label}
                    {ctx.hmm_bull_pct != null && ` · ${ctx.hmm_bull_pct}% bull`}
                  </span>
                )}
              </div>
              {(ctx.bull_case_trigger || ctx.bear_case_trigger) && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {ctx.bull_case_trigger && (
                    <span
                      className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-950/40 px-3 py-1 text-xs text-emerald-100"
                      title={ctx.bull_case_trigger}
                    >
                      <span className="font-bold text-emerald-300 shrink-0">Bull</span>
                      <span className="truncate">{ctx.bull_case_trigger}</span>
                    </span>
                  )}
                  {ctx.bear_case_trigger && (
                    <span
                      className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-950/35 px-3 py-1 text-xs text-amber-100"
                      title={ctx.bear_case_trigger}
                    >
                      <span className="font-bold text-amber-300 shrink-0">Bear</span>
                      <span className="truncate">{ctx.bear_case_trigger}</span>
                    </span>
                  )}
                </div>
              )}
              {ctx.historical_analog && (
                <button
                  type="button"
                  onClick={() => setAnalogOpen((o) => !o)}
                  className="mt-2 text-xs text-slate-300 hover:text-slate-100 flex items-center gap-1"
                >
                  {analogOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  Historical analog
                </button>
              )}
              {analogOpen && ctx.historical_analog && (
                <p className="text-xs text-slate-300 mt-1 pl-5 border-l-2 border-slate-600">{ctx.historical_analog}</p>
              )}
            </div>
          )}

          {!ctx?.primary_message && db?.summary_sentence && (
            <p className="text-sm text-slate-200 leading-relaxed">{db.summary_sentence}</p>
          )}

          {marketQuadrant === "best_buy_zone" && (
            <p className="text-sm text-emerald-100 rounded-lg border border-emerald-500/25 bg-emerald-950/20 px-3 py-2">
              Short-term macro may read Risk-Off — favor quality dips; avoid blanket trim.
            </p>
          )}

          {/* KPI row */}
          <div className="flex flex-wrap gap-2">
            {temp?.label && (
              <KpiChip
                label="Sentiment"
                value={temp.label}
                sub={vixStr ? `VIX ${vixStr}` : undefined}
                tone="cool"
              />
            )}
            {ctx?.hmm_bull_pct != null && (
              <KpiChip label="HMM bull" value={`${ctx.hmm_bull_pct}%`} tone="good" />
            )}
            {showPortfolioKpis && heat > 0 && (
              <KpiChip
                label="Portfolio heat"
                value={`${heat}%`}
                tone={heat > 15 ? "warn" : "neutral"}
                title="Share of portfolio in names flagged for trim or high risk. Above ~15% suggests reviewing sizing."
              />
            )}
            {showPortfolioKpis && top3 != null && top3 > 0 && (
              <KpiChip label="Top 3 weight" value={`${top3}%`} tone={top3 > 40 ? "warn" : "neutral"} />
            )}
            {showPortfolioKpis && risk?.score != null && (
              <div className="flex-[2] min-w-[12rem] rounded-lg border border-slate-600/60 bg-slate-800/40 px-3 py-2">
                <RiskMeter score={risk.score} scale={risk.score_scale} />
              </div>
            )}
          </div>

          <PhaseCSessionBlock
            preMarketFull={preMarketFull}
            preMarket={preMarket}
            market={market}
            tradingLens={tradingLens}
            onTickerClick={onTickerClick}
          />

          {(vixStr || macroDriver || hyDriver || temp?.macro_overlay) && (
            <p className="text-xs text-slate-300">
              {[vixStr && `VIX ${vixStr}`, macroDriver, hyDriver, temp?.macro_overlay].filter(Boolean).join(" · ")}
            </p>
          )}

          {tacticalSlot}
        </div>
      </section>

      {priorityBlock}
      {matrixBlock}
      {nudgesBlock}
      {tradingLens !== "scout" && tradingLens !== "swing" && (
        <PremarketMoverStrip full={preMarketFull} simple={preMarket} onTickerClick={onTickerClick} />
      )}

      {(rb?.tax_approaching_ltcg ?? db?.tax_approaching_ltcg ?? []).length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100">
          <Calendar className="h-4 w-4 shrink-0 mt-0.5" />
          <span>
            <span className="font-medium">LTCG window: </span>
            {(rb?.tax_approaching_ltcg ?? db?.tax_approaching_ltcg ?? [])
              .map((t) => `${t.ticker} (${t.days_to_ltcg}d)`)
              .join(", ")}
          </span>
        </div>
      )}

      {rb?.win_loss_recap && (rb.win_loss_recap.wins != null || rb.win_loss_recap.losses != null) && (
        <div className="flex items-center gap-2 text-sm text-slate-300 px-1">
          <Thermometer className="h-4 w-4 text-slate-400" />
          Paper: {rb.win_loss_recap.wins ?? 0}W / {rb.win_loss_recap.losses ?? 0}L
          {rb.win_loss_recap.win_rate_pct != null && ` · ${rb.win_loss_recap.win_rate_pct}% win`}
          {rb.win_loss_recap.net_pnl_pct != null &&
            ` · ${rb.win_loss_recap.net_pnl_pct >= 0 ? "+" : ""}${rb.win_loss_recap.net_pnl_pct}% net`}
        </div>
      )}

      {(market?.morning_checklist?.length ?? 0) > 0 && (
        <ToggleSection
          id="overview-checklist"
          title="Today's checklist"
          icon={<Calendar className="h-5 w-5" />}
          defaultOpen
        >
          <ul className="space-y-2">
            {market!.morning_checklist!.map((c, i) => (
              <li key={i} className="text-sm flex gap-3 rounded-lg border border-slate-600/60 bg-slate-800/40 px-3 py-2">
                <span className="text-sky-300 shrink-0 text-xs font-mono font-semibold min-w-[6.5rem]">{c.time}</span>
                <span className="text-slate-100 leading-snug">{c.task}</span>
              </li>
            ))}
          </ul>
        </ToggleSection>
      )}

      {market && (
        <ToggleSection
          id="overview-playbook"
          title="Playbook & context"
          icon={<Shield className="h-5 w-5" />}
          defaultOpen={false}
        >
          <RetailMarketDecisionsDeepDive data={market} macroBackdrop={macroBackdrop} omitChecklist />
        </ToggleSection>
      )}
    </div>
  );
}
