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
} from "lucide-react";
import { clsx } from "clsx";

export interface SwingSetupPayload {
  active: boolean;
  ticker: string;
  go_no_go: "go" | "no_go";
  setup_quality: { passed: number; total: number; label: string };
  headline: string;
  setup_narrative: string[];
  inside_entry_band: boolean;
  trade: {
    entry_low: number;
    entry_high: number;
    stop: number;
    target_1: number;
    target_2?: number | null;
    timeline_weeks: string;
    current_price: number;
  };
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
  risk_reward: {
    ratio_target_1?: number | null;
    risk_pct?: number | null;
    honest_note: string;
  };
  disclaimer: string;
}

function SectionToggle({
  title,
  icon,
  open,
  onToggle,
  children,
  defaultOpen = false,
}: {
  title: string;
  icon: React.ReactNode;
  open?: boolean;
  onToggle?: () => void;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const isOpen = open ?? internalOpen;
  const toggle = onToggle ?? (() => setInternalOpen((o) => !o));

  return (
    <div className="border-t border-slate-700/70">
      <button
        type="button"
        onClick={toggle}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-slate-800/50 touch-manipulation"
        aria-expanded={isOpen}
      >
        {isOpen ? (
          <ChevronDown className="h-4 w-4 text-slate-500 shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-slate-500 shrink-0" />
        )}
        <span className="text-slate-400 shrink-0">{icon}</span>
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-300">{title}</span>
      </button>
      {isOpen && <div className="px-4 pb-3 space-y-2">{children}</div>}
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

export function SwingSetupCard({ data }: { data: SwingSetupPayload }) {
  if (!data?.active) return null;

  const isGo = data.go_no_go === "go";
  const t = data.trade;

  return (
    <section
      className={clsx(
        "border-b",
        isGo ? "border-emerald-500/25 bg-emerald-950/20" : "border-amber-500/25 bg-amber-950/15"
      )}
      aria-label="Swing setup play sheet"
    >
      <div className="px-4 sm:px-6 py-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500 mb-1">Swing setup</p>
          <p className="text-base sm:text-lg font-semibold text-slate-100 leading-snug">{data.headline}</p>
          <p className="text-xs text-slate-500 mt-1">
            Levels from short horizon · {data.setup_quality.passed} of {data.setup_quality.total} gates ·{" "}
            {data.setup_quality.label}
          </p>
        </div>
        <span
          className={clsx(
            "inline-flex items-center gap-1.5 text-xs font-bold uppercase px-2.5 py-1 rounded border tracking-wide shrink-0",
            isGo
              ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
              : "border-amber-500/45 bg-amber-500/10 text-amber-200"
          )}
        >
          {isGo ? (
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
          ) : (
            <Ban className="h-3.5 w-3.5" aria-hidden />
          )}
          {isGo ? "Go" : "No-Go"}
        </span>
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
        <SectionToggle
          title={isGo ? "Trade plan" : "Wait plan"}
          icon={<Target className="h-3.5 w-3.5" />}
          defaultOpen
        >
          {isGo ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
              <div className="rounded-lg bg-slate-900/80 px-2.5 py-2 border border-slate-700/60">
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Entry</p>
                <p className="font-mono text-emerald-300 tabular-nums">
                  ${t.entry_low.toFixed(2)}–${t.entry_high.toFixed(2)}
                </p>
              </div>
              <div className="rounded-lg bg-slate-900/80 px-2.5 py-2 border border-slate-700/60">
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Stop</p>
                <p className="font-mono text-red-300 tabular-nums">${t.stop.toFixed(2)}</p>
              </div>
              <div className="rounded-lg bg-slate-900/80 px-2.5 py-2 border border-slate-700/60">
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Target 1</p>
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
            {data.inside_entry_band ? " · inside entry band" : " · outside entry band"} · timeline{" "}
            {t.timeline_weeks} wk
          </p>
        </SectionToggle>

        {isGo && data.sizing && (
          <SectionToggle title="Sizing example" icon={<Scale className="h-3.5 w-3.5" />}>
            <p className="text-sm text-slate-300">{data.sizing.rule}</p>
            <p className="text-sm text-slate-400">
              On ${data.sizing.example_portfolio_usd.toLocaleString()} portfolio: max loss ~$
              {data.sizing.max_loss_usd.toLocaleString()} → ~{data.sizing.shares_example} shares (~$
              {data.sizing.notional_usd.toLocaleString()} notional at mid-band).
            </p>
            <BulletList items={data.sizing.scale_in} />
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
                {data.earnings_caveat.days_until != null
                  ? `Reports in ${data.earnings_caveat.days_until}d`
                  : null}
                {data.earnings_caveat.report_date ? ` (${data.earnings_caveat.report_date})` : null}
              </p>
            )}
            <BulletList items={data.earnings_caveat.action_plan} tone="wait" />
          </SectionToggle>
        )}

        <SectionToggle title="Thesis & risk" icon={<AlertTriangle className="h-3.5 w-3.5" />}>
          <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Thesis breaks</p>
          <BulletList items={data.thesis_breaks} tone="exit" />
          <p className="text-sm text-slate-400 mt-3 border-t border-slate-800 pt-2">
            {data.risk_reward.risk_pct != null && (
              <span className="text-slate-300">
                Risk to stop ~{data.risk_reward.risk_pct}%
                {data.risk_reward.ratio_target_1 != null
                  ? ` · R:R to T1 ≈ ${data.risk_reward.ratio_target_1}:1`
                  : null}
                {" · "}
              </span>
            )}
            {data.risk_reward.honest_note}
          </p>
        </SectionToggle>
      </div>

      <p className="px-4 sm:px-6 pb-3 text-[11px] text-slate-600 leading-snug">{data.disclaimer}</p>
    </section>
  );
}
