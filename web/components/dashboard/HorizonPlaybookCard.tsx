"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Target,
  Scale,
  Zap,
  Calendar,
  AlertTriangle,
  Ban,
  CheckCircle2,
  BookOpen,
} from "lucide-react";
import { clsx } from "clsx";
import { TierThermometerPanel } from "./levels/TierThermometerPanel";
import type { HorizonSignalPayload } from "./InvestorDecisionSummary";

/** Shared play sheet shape — short/medium swing-style + long thesis variant */
export interface HorizonPlaybookPayload {
  active: boolean;
  horizon: "short" | "medium" | "long";
  kind: "swing" | "position_build" | "thesis_tiers";
  title: string;
  ticker: string;
  go_no_go?: "go" | "no_go";
  stance?: "accumulate" | "watch" | "wait";
  setup_quality?: { passed: number; total: number; label: string };
  headline: string;
  setup_narrative: string[];
  inside_entry_band?: boolean;
  trade?: {
    entry_low: number;
    entry_high: number;
    stop: number;
    target_1: number;
    target_2?: number | null;
    timeline_weeks: string;
    current_price: number;
  };
  tiers?: Array<{
    id?: string;
    label?: string;
    low: number;
    high: number;
    allocation_pct?: number | null;
    conviction?: string;
    active?: boolean;
    target?: boolean;
  }>;
  fair_value?: number | null;
  margin_of_safety_pct?: number | null;
  hold_vs_trade?: {
    title?: string;
    long_term?: string;
    short_term?: string;
    signal_bridge?: string;
    bullets?: string[];
  } | null;
  sizing?: {
    rule: string;
    example_portfolio_usd: number;
    max_loss_usd: number;
    risk_per_share_usd: number;
    shares_example: number;
    notional_usd: number;
    scale_in: string[];
  } | null;
  triggers: {
    add: string[];
    exit: string[];
    reduce: string[];
    wait: string[];
  };
  earnings_caveat?: {
    report_date?: string | null;
    days_until?: number | null;
    action_plan: string[];
  } | null;
  thesis_breaks: string[];
  risk_reward?: {
    ratio_target_1?: number | null;
    risk_pct?: number | null;
    honest_note: string;
  };
  swing_classification?: {
    setup_type?: string;
    setup_label?: string;
    setup_reasons?: string[];
    divergence_note?: string | null;
    swing_score?: {
      score?: number;
      verdict?: "SWING_SIGNAL" | "WATCH" | "NO_SIGNAL";
      technical_component?: number;
      pattern_component?: number;
      signal_basis?: string;
      ml_confirmation_note?: string | null;
    };
    exit_plan?: {
      entry_low?: number;
      entry_high?: number;
      entry_anchor?: number;
      hard_stop?: number;
      target_1?: number;
      target_2?: number;
      runner_target?: number;
      horizon_label?: string;
      time_stop_days?: number;
      risk_reward_t1?: number | null;
      exit_rules?: string[];
    };
  } | null;
  disclaimer: string;
}

export type HorizonPlaybooksBundle = {
  default_primary: "short" | "medium" | "long";
  intent_map: { trade: string; invest: string; unset: string };
  swing?: HorizonPlaybookPayload | null;
  medium?: HorizonPlaybookPayload | null;
  long?: HorizonPlaybookPayload | null;
};

/** @deprecated use HorizonPlaybookPayload */
export type SwingSetupPayload = HorizonPlaybookPayload;

function SectionToggle({
  title,
  icon,
  children,
  defaultOpen = false,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-td-line/70">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-td-surface2/50 touch-manipulation"
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-td-muted shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-td-muted shrink-0" />
        )}
        <span className="text-td-muted shrink-0">{icon}</span>
        <span className="text-xs font-semibold uppercase tracking-wide text-td-text">{title}</span>
      </button>
      {open && <div className="px-4 pb-3 space-y-2">{children}</div>}
    </div>
  );
}

function BulletList({ items, tone = "neutral" }: { items: string[]; tone?: "neutral" | "wait" | "exit" }) {
  if (!items.length) return null;
  const dot =
    tone === "wait" ? "text-td-warn" : tone === "exit" ? "text-td-crit/90" : "text-td-accent/90";
  return (
    <ul className="space-y-1.5 text-sm text-td-text leading-relaxed">
      {items.map((line, i) => (
        <li key={i} className="flex gap-2">
          <span className={clsx("shrink-0 mt-1.5 h-1 w-1 rounded-full bg-current", dot)} aria-hidden />
          <span>{line}</span>
        </li>
      ))}
    </ul>
  );
}

const KIND_ACCENT: Record<string, { go: string; no: string }> = {
  swing: { go: "border-td-accent/25 bg-td-accent-weak/20", no: "border-td-warn/25 bg-td-warn-weak/15" },
  position_build: { go: "border-td-accent/25 bg-td-accent-weak/20", no: "border-td-warn/25 bg-td-warn-weak/15" },
  thesis_tiers: { go: "border-td-owner/25 bg-td-owner-weak/20", no: "border-td-line/40 bg-td-surface/40" },
};

export function HorizonPlaybookCard({
  data,
  compact,
  omitNarrativeLines = [],
  entryTiers,
  currentPrice,
  structuralStop,
  ma200,
}: {
  data: HorizonPlaybookPayload;
  /** Secondary playbooks — collapsed header by default */
  compact?: boolean;
  /** Shared context lines rendered once in the panel header */
  omitNarrativeLines?: string[];
  /** Long-term tier ladder (thesis_tiers kind only) — raw source object, see LongTermTierLadder. */
  entryTiers?: NonNullable<HorizonSignalPayload["entry_tiers"]> | null;
  currentPrice?: number | null;
  structuralStop?: number | null;
  ma200?: number | null;
}) {
  if (!data?.active) return null;

  const omitSet = new Set(omitNarrativeLines);
  const narrativeLines = (data.setup_narrative ?? []).filter((line) => !omitSet.has(line.trim()));

  const isThesis = data.kind === "thesis_tiers";
  const isGo = isThesis
    ? data.stance === "accumulate"
    : data.go_no_go === "go";
  const t = data.trade;
  const accent = KIND_ACCENT[data.kind] ?? KIND_ACCENT.swing;
  const swingCls = data.swing_classification;
  const swingScore = swingCls?.swing_score;
  const exitPlan = swingCls?.exit_plan;
  const isSwingSignal = swingScore?.verdict === "SWING_SIGNAL";

  return (
    <section
      className={clsx("border-b", isGo ? accent.go : accent.no, compact && "opacity-95")}
      aria-label={`${data.title} play sheet`}
    >
      {data.kind === "swing" && swingCls?.setup_label && (
        <div
          className={clsx(
            "mx-4 sm:mx-6 mt-3 rounded-xl border px-4 py-3",
            isSwingSignal
              ? "border-td-owner/40 bg-gradient-to-br from-td-owner-weak/50 to-td-bg/80"
              : "border-td-line/60 bg-td-bg/60",
          )}
        >
          <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
            <p className="flex items-center gap-2 text-sm font-bold text-td-owner">
              <Zap className="h-4 w-4 text-td-owner" aria-hidden />
              {isSwingSignal ? "Short-term opportunity" : "Short-term watch"} — {data.ticker}
            </p>
            {swingScore?.score != null && (
              <span
                className={clsx(
                  "text-xs font-black tabular-nums px-2 py-0.5 rounded border",
                  isSwingSignal
                    ? "border-td-accent/50 text-td-accent bg-td-accent/10"
                    : "border-td-warn/40 text-td-warn bg-td-warn/10",
                )}
              >
                {swingScore.score.toFixed(0)}/100
              </span>
            )}
          </div>
          <p className="text-xs uppercase tracking-wider text-td-muted mb-1">Setup</p>
          <p className="text-base font-semibold text-td-text">{swingCls.setup_label}</p>
          {swingScore?.verdict && (
            <p className="text-[11px] text-td-muted mt-1">
              {swingScore.verdict.replace(/_/g, " ")}
              {swingScore.technical_component != null
                ? ` · Tech ${swingScore.technical_component.toFixed(0)} + Pattern ${(swingScore.pattern_component ?? 0).toFixed(0)}`
                : ""}
            </p>
          )}
          {swingCls.divergence_note && (
            <p className="mt-2 text-xs text-td-warn/90 leading-snug border-l-2 border-td-warn/50 pl-2">
              {swingCls.divergence_note}
            </p>
          )}
          {exitPlan && (
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
              <div>
                <p className="text-td-muted">Entry</p>
                <p className="font-mono text-td-text tabular-nums">
                  ${exitPlan.entry_low?.toFixed(0) ?? t?.entry_low?.toFixed(0)}–$
                  {exitPlan.entry_high?.toFixed(0) ?? t?.entry_high?.toFixed(0)}
                </p>
              </div>
              <div>
                <p className="text-td-muted">Hard stop</p>
                <p className="font-mono text-td-crit/90 tabular-nums">${exitPlan.hard_stop?.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-td-muted">Target 1 / 2</p>
                <p className="font-mono text-td-accent/90 tabular-nums">
                  ${exitPlan.target_1?.toFixed(0)} / ${exitPlan.target_2?.toFixed(0)}
                </p>
              </div>
              <div>
                <p className="text-td-muted">R/R · Horizon</p>
                <p className="font-mono text-td-text tabular-nums">
                  {exitPlan.risk_reward_t1 != null ? `${exitPlan.risk_reward_t1.toFixed(1)}:1` : "—"} ·{" "}
                  {exitPlan.horizon_label ?? "10–14d"}
                </p>
              </div>
            </div>
          )}
          {(swingCls.setup_reasons?.length ?? 0) > 0 && (
            <p className="mt-2 text-[11px] text-td-muted leading-snug">
              <span className="text-td-muted">Why: </span>
              {swingCls.setup_reasons!.slice(0, 2).join(" · ")}
            </p>
          )}
          {swingScore?.ml_confirmation_note && (
            <p className="mt-1.5 text-[10px] text-td-muted">{swingScore.ml_confirmation_note}</p>
          )}
        </div>
      )}

      <div className="px-4 sm:px-6 py-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-td-muted mb-1">{data.title}</p>
          <p className="text-base sm:text-lg font-semibold text-td-text leading-snug">{data.headline}</p>
          {data.setup_quality && !isThesis && (
            <p className="text-xs text-td-muted mt-1">
              {data.horizon === "short" ? "Short horizon" : "Medium horizon"} · {data.setup_quality.passed} of{" "}
              {data.setup_quality.total} gates · {data.setup_quality.label}
            </p>
          )}
          {isThesis && data.fair_value != null && (
            <p className="text-xs text-td-muted mt-1">
              Model FV ${data.fair_value.toFixed(2)}
              {data.margin_of_safety_pct != null ? ` · MOS ~${data.margin_of_safety_pct}%` : ""}
            </p>
          )}
        </div>
        {!isThesis ? (
          <span
            className={clsx(
              "inline-flex items-center gap-1.5 text-xs font-bold uppercase px-2.5 py-1 rounded border tracking-wide shrink-0",
              isGo
                ? "border-td-accent/50 bg-td-accent/15 text-td-accent"
                : "border-td-warn/45 bg-td-warn/10 text-td-warn"
            )}
          >
            {isGo ? <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> : <Ban className="h-3.5 w-3.5" aria-hidden />}
            {isGo ? "Go" : "No-Go"}
          </span>
        ) : (
          <span
            className={clsx(
              "inline-flex items-center gap-1.5 text-xs font-bold uppercase px-2.5 py-1 rounded border tracking-wide shrink-0",
              data.stance === "accumulate" && "border-td-owner/50 bg-td-owner/15 text-td-owner",
              data.stance === "watch" && "border-td-info/45 bg-td-info/10 text-td-info",
              data.stance === "wait" && "border-td-line/45 bg-td-line/10 text-td-text"
            )}
          >
            {data.stance ?? "watch"}
          </span>
        )}
      </div>

      {narrativeLines.length > 0 && (
        <div className="px-4 sm:px-6 pb-3">
          <ul className="space-y-1.5 text-sm text-td-text/95 leading-relaxed border-l-2 border-td-line pl-3">
            {narrativeLines.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      {isThesis && entryTiers?.tiers?.length && currentPrice != null && (
        <div className="mx-4 sm:mx-6 mb-3">
          <TierThermometerPanel
            entryTiers={entryTiers}
            currentPrice={currentPrice}
            structuralStop={structuralStop ?? null}
            ma200={ma200 ?? null}
            defaultThermometerOpen={false}
          />
        </div>
      )}

      <div className="mx-4 sm:mx-6 mb-3 rounded-xl border border-td-line/70 bg-td-bg/60 overflow-hidden">
        {t && (
          <SectionToggle
            title={isGo && !isThesis ? (data.kind === "position_build" ? "Build plan" : "Trade plan") : "Wait plan"}
            icon={<Target className="h-3.5 w-3.5" />}
            defaultOpen={!compact}
          >
            {isGo && !isThesis ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
                <div className="rounded-lg bg-td-surface/80 px-2.5 py-2 border border-td-line/60">
                  <p className="text-[10px] uppercase tracking-wider text-td-muted">Entry</p>
                  <p className="font-mono text-td-accent tabular-nums">
                    ${t.entry_low.toFixed(2)}–${t.entry_high.toFixed(2)}
                  </p>
                </div>
                <div className="rounded-lg bg-td-surface/80 px-2.5 py-2 border border-td-line/60">
                  <p className="text-[10px] uppercase tracking-wider text-td-muted">
                    {data.kind === "position_build" ? "Build stop" : "Swing stop"}
                  </p>
                  <p className="font-mono text-td-crit tabular-nums">${t.stop.toFixed(2)}</p>
                  <p className="text-[10px] text-td-muted mt-0.5">
                    {data.kind === "position_build" ? "pause tranches" : "5% risk band"}
                  </p>
                </div>
                <div className="rounded-lg bg-td-surface/80 px-2.5 py-2 border border-td-line/60">
                  <p className="text-[10px] uppercase tracking-wider text-td-muted">Target</p>
                  <p className="font-mono text-td-accent-ink tabular-nums">${t.target_1.toFixed(2)}</p>
                </div>
                {t.target_2 != null && t.target_2 > 0 && (
                  <div className="rounded-lg bg-td-surface/80 px-2.5 py-2 border border-td-line/60">
                    <p className="text-[10px] uppercase tracking-wider text-td-muted">Target 2</p>
                    <p className="font-mono text-td-accent-ink tabular-nums">${t.target_2.toFixed(2)}</p>
                  </div>
                )}
              </div>
            ) : (
              <BulletList items={data.triggers.wait} tone="wait" />
            )}
            <p className="text-xs text-td-muted mt-2">
              Spot ${t.current_price.toFixed(2)}
              {data.inside_entry_band != null &&
                (data.inside_entry_band ? " · inside entry band" : " · outside entry band")}
              {" · timeline "}
              {t.timeline_weeks} wk
            </p>
          </SectionToggle>
        )}

        {!isThesis && isGo && data.sizing && (
          <SectionToggle title="Sizing example" icon={<Scale className="h-3.5 w-3.5" />}>
            <p className="text-sm text-td-text">{data.sizing.rule}</p>
            <p className="text-sm text-td-muted">
              On ${data.sizing.example_portfolio_usd.toLocaleString()} portfolio: ~{data.sizing.shares_example} shares (~$
              {data.sizing.notional_usd.toLocaleString()} notional at mid-band).
            </p>
            <BulletList items={data.sizing.scale_in} />
          </SectionToggle>
        )}

        {data.hold_vs_trade && (data.hold_vs_trade.bullets?.length || data.hold_vs_trade.signal_bridge) && (
          <SectionToggle title="Hold vs trim" icon={<BookOpen className="h-3.5 w-3.5" />} defaultOpen={!compact}>
            {data.hold_vs_trade.signal_bridge ? (
              <p className="text-sm text-td-info/90 border-l-2 border-td-info/40 pl-2">
                {data.hold_vs_trade.signal_bridge}
              </p>
            ) : (
              <BulletList items={data.hold_vs_trade.bullets ?? []} />
            )}
          </SectionToggle>
        )}

        <SectionToggle title="Triggers" icon={<Zap className="h-3.5 w-3.5" />}>
          {data.triggers.add.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-td-accent/80 mb-1">Add</p>
              <BulletList items={data.triggers.add} />
            </div>
          )}
          {data.triggers.exit.length > 0 && (
            <div className="mt-2">
              <p className="text-[10px] uppercase tracking-wider text-td-crit/80 mb-1">Exit</p>
              <BulletList items={data.triggers.exit} tone="exit" />
            </div>
          )}
          {data.triggers.reduce.length > 0 && (
            <div className="mt-2">
              <p className="text-[10px] uppercase tracking-wider text-td-warn/80 mb-1">Reduce</p>
              <BulletList items={data.triggers.reduce} tone="wait" />
            </div>
          )}
        </SectionToggle>

        {data.earnings_caveat && (
          <SectionToggle title="Earnings" icon={<Calendar className="h-3.5 w-3.5" />}>
            {(data.earnings_caveat.report_date || data.earnings_caveat.days_until != null) && (
              <p className="text-sm text-td-warn/90 mb-2">
                {data.earnings_caveat.days_until != null ? `Reports in ${data.earnings_caveat.days_until}d` : null}
                {data.earnings_caveat.report_date ? ` (${data.earnings_caveat.report_date})` : null}
              </p>
            )}
            <BulletList items={data.earnings_caveat.action_plan} tone="wait" />
          </SectionToggle>
        )}

        <SectionToggle title="Thesis & risk" icon={<AlertTriangle className="h-3.5 w-3.5" />}>
          <BulletList items={data.thesis_breaks} tone="exit" />
          {data.risk_reward?.honest_note && (
            <p className="text-sm text-td-muted mt-3 border-t border-td-line pt-2">
              {data.risk_reward.risk_pct != null && (
                <span className="text-td-text">
                  Risk to stop ~{data.risk_reward.risk_pct}%
                  {data.risk_reward.ratio_target_1 != null
                    ? ` · R:R ≈ 1:${data.risk_reward.ratio_target_1}`
                    : null}
                  {" · "}
                </span>
              )}
              {data.risk_reward.honest_note}
            </p>
          )}
        </SectionToggle>
      </div>

      <p className="px-4 sm:px-6 pb-3 text-[11px] text-td-muted leading-snug">{data.disclaimer}</p>
    </section>
  );
}

/** Backward-compatible export */
export function SwingSetupCard({ data }: { data: HorizonPlaybookPayload }) {
  return <HorizonPlaybookCard data={data} />;
}
