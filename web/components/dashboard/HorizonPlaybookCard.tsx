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
  Layers,
  BookOpen,
} from "lucide-react";
import { clsx } from "clsx";

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
    <div className="border-t border-slate-700/70">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-slate-800/50 touch-manipulation"
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-slate-500 shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-slate-500 shrink-0" />
        )}
        <span className="text-slate-400 shrink-0">{icon}</span>
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-300">{title}</span>
      </button>
      {open && <div className="px-4 pb-3 space-y-2">{children}</div>}
    </div>
  );
}

function BulletList({ items, tone = "neutral" }: { items: string[]; tone?: "neutral" | "wait" | "exit" }) {
  if (!items.length) return null;
  const dot =
    tone === "wait" ? "text-amber-400" : tone === "exit" ? "text-red-400/90" : "text-emerald-400/90";
  return (
    <ul className="space-y-1.5 text-sm text-slate-300 leading-relaxed">
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
  swing: { go: "border-emerald-500/25 bg-emerald-950/20", no: "border-amber-500/25 bg-amber-950/15" },
  position_build: { go: "border-teal-500/25 bg-teal-950/20", no: "border-amber-500/25 bg-amber-950/15" },
  thesis_tiers: { go: "border-violet-500/25 bg-violet-950/20", no: "border-slate-600/40 bg-slate-900/40" },
};

export function HorizonPlaybookCard({
  data,
  compact,
}: {
  data: HorizonPlaybookPayload;
  /** Secondary playbooks — collapsed header by default */
  compact?: boolean;
}) {
  if (!data?.active) return null;

  const isThesis = data.kind === "thesis_tiers";
  const isGo = isThesis
    ? data.stance === "accumulate"
    : data.go_no_go === "go";
  const t = data.trade;
  const accent = KIND_ACCENT[data.kind] ?? KIND_ACCENT.swing;

  return (
    <section
      className={clsx("border-b", isGo ? accent.go : accent.no, compact && "opacity-95")}
      aria-label={`${data.title} play sheet`}
    >
      <div className="px-4 sm:px-6 py-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500 mb-1">{data.title}</p>
          <p className="text-base sm:text-lg font-semibold text-slate-100 leading-snug">{data.headline}</p>
          {data.setup_quality && !isThesis && (
            <p className="text-xs text-slate-500 mt-1">
              {data.horizon === "short" ? "Short horizon" : "Medium horizon"} · {data.setup_quality.passed} of{" "}
              {data.setup_quality.total} gates · {data.setup_quality.label}
            </p>
          )}
          {isThesis && data.fair_value != null && (
            <p className="text-xs text-slate-500 mt-1">
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
                ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
                : "border-amber-500/45 bg-amber-500/10 text-amber-200"
            )}
          >
            {isGo ? <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> : <Ban className="h-3.5 w-3.5" aria-hidden />}
            {isGo ? "Go" : "No-Go"}
          </span>
        ) : (
          <span
            className={clsx(
              "inline-flex items-center gap-1.5 text-xs font-bold uppercase px-2.5 py-1 rounded border tracking-wide shrink-0",
              data.stance === "accumulate" && "border-violet-500/50 bg-violet-500/15 text-violet-200",
              data.stance === "watch" && "border-sky-500/45 bg-sky-500/10 text-sky-200",
              data.stance === "wait" && "border-slate-500/45 bg-slate-500/10 text-slate-300"
            )}
          >
            {data.stance ?? "watch"}
          </span>
        )}
      </div>

      {data.setup_narrative.length > 0 && (
        <div className="px-4 sm:px-6 pb-3">
          <ul className="space-y-1.5 text-sm text-slate-300/95 leading-relaxed border-l-2 border-slate-600 pl-3">
            {data.setup_narrative.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mx-4 sm:mx-6 mb-3 rounded-xl border border-slate-600/70 bg-slate-950/60 overflow-hidden">
        {isThesis && data.tiers && data.tiers.length > 0 && (
          <SectionToggle title="Tier ladder" icon={<Layers className="h-3.5 w-3.5" />} defaultOpen={!compact}>
            <ul className="space-y-2">
              {data.tiers.map((tier) => (
                <li
                  key={tier.id ?? tier.label}
                  className={clsx(
                    "rounded-lg border px-2.5 py-2 text-sm",
                    tier.active || tier.target
                      ? "border-emerald-500/40 bg-emerald-500/10"
                      : "border-slate-700/60 bg-slate-900/50"
                  )}
                >
                  <p className="font-medium text-slate-200">{tier.label}</p>
                  <p className="font-mono text-emerald-300/90 tabular-nums">
                    ${tier.low.toFixed(2)}–${tier.high.toFixed(2)}
                  </p>
                  {(tier.active || tier.target) && (
                    <p className="text-[10px] uppercase text-emerald-400/90 mt-0.5">
                      {tier.active
                        ? tier.id === "T2" || tier.id === "tier2"
                          ? "Partial position only"
                          : "Active band"
                        : "Target tier"}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </SectionToggle>
        )}

        {t && (
          <SectionToggle
            title={isGo && !isThesis ? (data.kind === "position_build" ? "Build plan" : "Trade plan") : "Wait plan"}
            icon={<Target className="h-3.5 w-3.5" />}
            defaultOpen={!compact}
          >
            {isGo && !isThesis ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
                <div className="rounded-lg bg-slate-900/80 px-2.5 py-2 border border-slate-700/60">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">Entry</p>
                  <p className="font-mono text-emerald-300 tabular-nums">
                    ${t.entry_low.toFixed(2)}–${t.entry_high.toFixed(2)}
                  </p>
                </div>
                <div className="rounded-lg bg-slate-900/80 px-2.5 py-2 border border-slate-700/60">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">
                    {data.kind === "position_build" ? "Build stop" : "Swing stop"}
                  </p>
                  <p className="font-mono text-red-300 tabular-nums">${t.stop.toFixed(2)}</p>
                  <p className="text-[10px] text-slate-500 mt-0.5">
                    {data.kind === "position_build" ? "pause tranches" : "5% risk band"}
                  </p>
                </div>
                <div className="rounded-lg bg-slate-900/80 px-2.5 py-2 border border-slate-700/60">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">Target</p>
                  <p className="font-mono text-emerald-200 tabular-nums">${t.target_1.toFixed(2)}</p>
                </div>
                {t.target_2 != null && t.target_2 > 0 && (
                  <div className="rounded-lg bg-slate-900/80 px-2.5 py-2 border border-slate-700/60">
                    <p className="text-[10px] uppercase tracking-wider text-slate-500">Target 2</p>
                    <p className="font-mono text-teal-200 tabular-nums">${t.target_2.toFixed(2)}</p>
                  </div>
                )}
              </div>
            ) : (
              <BulletList items={data.triggers.wait} tone="wait" />
            )}
            <p className="text-xs text-slate-500 mt-2">
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
            <p className="text-sm text-slate-300">{data.sizing.rule}</p>
            <p className="text-sm text-slate-400">
              On ${data.sizing.example_portfolio_usd.toLocaleString()} portfolio: ~{data.sizing.shares_example} shares (~$
              {data.sizing.notional_usd.toLocaleString()} notional at mid-band).
            </p>
            <BulletList items={data.sizing.scale_in} />
          </SectionToggle>
        )}

        {data.hold_vs_trade && (data.hold_vs_trade.bullets?.length || data.hold_vs_trade.signal_bridge) && (
          <SectionToggle title="Hold vs trim" icon={<BookOpen className="h-3.5 w-3.5" />} defaultOpen={!compact}>
            {data.hold_vs_trade.signal_bridge ? (
              <p className="text-sm text-sky-200/90 border-l-2 border-sky-500/40 pl-2">
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
              <p className="text-[10px] uppercase tracking-wider text-emerald-500/80 mb-1">Add</p>
              <BulletList items={data.triggers.add} />
            </div>
          )}
          {data.triggers.exit.length > 0 && (
            <div className="mt-2">
              <p className="text-[10px] uppercase tracking-wider text-red-400/80 mb-1">Exit</p>
              <BulletList items={data.triggers.exit} tone="exit" />
            </div>
          )}
          {data.triggers.reduce.length > 0 && (
            <div className="mt-2">
              <p className="text-[10px] uppercase tracking-wider text-amber-400/80 mb-1">Reduce</p>
              <BulletList items={data.triggers.reduce} tone="wait" />
            </div>
          )}
        </SectionToggle>

        {data.earnings_caveat && (
          <SectionToggle title="Earnings" icon={<Calendar className="h-3.5 w-3.5" />}>
            {(data.earnings_caveat.report_date || data.earnings_caveat.days_until != null) && (
              <p className="text-sm text-amber-200/90 mb-2">
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
            <p className="text-sm text-slate-400 mt-3 border-t border-slate-800 pt-2">
              {data.risk_reward.risk_pct != null && (
                <span className="text-slate-300">
                  Risk to stop ~{data.risk_reward.risk_pct}%
                  {data.risk_reward.ratio_target_1 != null
                    ? ` · R:R ≈ ${data.risk_reward.ratio_target_1}:1`
                    : null}
                  {" · "}
                </span>
              )}
              {data.risk_reward.honest_note}
            </p>
          )}
        </SectionToggle>
      </div>

      <p className="px-4 sm:px-6 pb-3 text-[11px] text-slate-600 leading-snug">{data.disclaimer}</p>
    </section>
  );
}

/** Backward-compatible export */
export function SwingSetupCard({ data }: { data: HorizonPlaybookPayload }) {
  return <HorizonPlaybookCard data={data} />;
}
