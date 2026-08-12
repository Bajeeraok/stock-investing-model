"use client";

import { useEffect, useState, type ReactNode } from "react";
import { clsx } from "clsx";
import {
  BarChart3,
  Building2,
  ChevronDown,
  ChevronRight,
  DollarSign,
  Newspaper,
  RefreshCw,
  Target,
  type LucideIcon,
} from "lucide-react";
import type { TickerDetail } from "../TickerDetailModal";
import type { ConfidenceData } from "../ConfidenceBreakdown";
import type { PriceTargetsData } from "../PriceTargetsPanel";
import type { InstitutionalBundle } from "../InstitutionalInsightsPanel";
import type { ExecutionPlanViewModel } from "../executionPlanModel";
import { type DecisionMode, primaryHorizonFromMode } from "@/lib/decisionMode";
import { TD } from "../tickerDetailTypography";
import { IntradayChart } from "../IntradayChart";
import { AnchorBentoGrid, anchorsFromTechnicalLevels } from "../levels/AnchorBentoGrid";
import { DecisionDeck } from "../DecisionDeck";
import { TacticalEntryPanel } from "../TacticalEntryPanel";
import { InvestorDecisionSummarySection } from "../InvestorDecisionSummary";
import { HorizonDivergenceNote } from "../retailActionUX";
import { ScenarioTeaser } from "../ScenarioTeaser";
import { apiUrl } from "@/lib/apiBase";
import { NarrativeWaterfallCard } from "./NarrativeWaterfallCard";

function fmtUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${n.toFixed(2)}`;
}

export function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n >= 0 ? "+" : "−";
  return `${sign}${Math.abs(n).toFixed(digits)}%`;
}

/** Shared shell for the reference-detail cards — compact stat rows + optional body + jump-link + optional collapsible extra detail. */
export function ReferenceCard({
  icon: Icon,
  title,
  description,
  stats,
  body,
  footer,
  children,
  toggleLabel = "Show execution plan",
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  stats?: { label: string; value: ReactNode }[];
  body?: ReactNode;
  footer?: { label: string; onClick: () => void };
  /** Collapsible extra detail rendered below the footer — used only by Card 1. */
  children?: ReactNode;
  toggleLabel?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-slate-700/70 bg-slate-900/50 p-4 flex flex-col gap-2.5">
      <h4 className="flex items-center gap-1.5 text-[13px] font-semibold text-slate-100">
        <Icon className="h-3.5 w-3.5 text-emerald-400 shrink-0" aria-hidden />
        {title}
      </h4>
      {description && <p className={TD.footnote}>{description}</p>}
      {stats && stats.length > 0 && (
        <div className="text-xs">
          {stats.map((s, i) => (
            <div
              key={i}
              className="flex items-center justify-between gap-3 py-1.5 border-t border-slate-800/80 first:border-t-0"
            >
              <span className="text-slate-500 shrink-0">{s.label}</span>
              <span className="font-mono font-semibold text-slate-200 text-right truncate">{s.value}</span>
            </div>
          ))}
        </div>
      )}
      {body}
      {footer && (
        <button
          type="button"
          onClick={footer.onClick}
          className="text-xs font-semibold text-emerald-400 hover:text-emerald-300 text-left mt-auto pt-0.5"
        >
          {footer.label} →
        </button>
      )}
      {children && (
        <div className="pt-1.5 border-t border-slate-800/80 -mx-4 px-4">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="w-full flex items-center justify-between gap-2 text-[11px] font-mono uppercase tracking-wide text-slate-500 hover:text-slate-300 py-1"
            aria-expanded={open}
          >
            {toggleLabel}
            {open ? <ChevronDown className="h-3.5 w-3.5" aria-hidden /> : <ChevronRight className="h-3.5 w-3.5" aria-hidden />}
          </button>
          {open && <div className="pt-2 space-y-3">{children}</div>}
        </div>
      )}
    </div>
  );
}

const DRIVER_LABEL: Record<string, string> = {
  stock_specific: "Stock-specific",
  broad_market: "Broad market",
  earnings: "Earnings",
  unclear: "Unclear",
};

const DRIVER_CLASS: Record<string, string> = {
  stock_specific: "text-amber-300 border-amber-500/35 bg-amber-500/10",
  broad_market: "text-cyan-300 border-cyan-500/35 bg-cyan-500/10",
  earnings: "text-violet-300 border-violet-500/35 bg-violet-500/10",
  unclear: "text-slate-400 border-slate-600/50 bg-slate-800/40",
};

const NEAR_BOTTOM_MODE_LABEL: Record<string, string> = {
  bottom_reversal: "Bottom reversal",
  trend_continuation: "Trend continuation",
};

interface ReferenceDetailGridProps {
  detail: TickerDetail;
  priceTargets: PriceTargetsData | null;
  confidence: ConfidenceData | null;
  decisionMode: DecisionMode;
  currentPrice: number | null | undefined;
  executionVm: ExecutionPlanViewModel | null;
  ltEntryTiersOpen: boolean;
  onToggleLtTiers: () => void;
  onOpenLevels: () => void;
  onOpenValuation: () => void;
  onOpenProof: () => void;
  onOpenContext: () => void;
}

export function ReferenceDetailGrid(props: ReferenceDetailGridProps) {
  return (
    <div>
      <p className={clsx(TD.sectionLabel, "pt-2 border-t border-slate-800 mb-2.5")}>
        Reference detail — everything for a second look, one card per topic
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <ChartLevelsCard {...props} />
        <ValuationCard {...props} />
        <WhyMovedCard {...props} />
        <NearBottomCard {...props} />
        <ConfidenceCard {...props} />
        <FundamentalsCard {...props} />
        <NarrativeWaterfallCard ticker={props.detail.ticker} mode={props.decisionMode} />
      </div>
    </div>
  );
}

function useSignalReason(detail: TickerDetail, decisionMode: DecisionMode) {
  const summary = detail.investor_summary;
  return summary?.signal_reason_by_persona?.[decisionMode] ?? summary?.signal_reason ?? null;
}

function ChartLevelsCard({
  detail,
  priceTargets,
  decisionMode,
  currentPrice,
  executionVm,
  ltEntryTiersOpen,
  onToggleLtTiers,
  onOpenLevels,
}: ReferenceDetailGridProps) {
  const summary = detail.investor_summary;
  const primaryHorizon = primaryHorizonFromMode(decisionMode);
  const horizon = summary?.horizons?.[primaryHorizon];

  const technicalLevels = priceTargets?.technical_levels ?? {
    ma50: detail.ma50 ?? null,
    ma200: detail.ma200 ?? null,
    low_52w: detail.low_52w ?? null,
    high_52w: detail.high_52w ?? null,
  };
  const anchors = currentPrice != null && currentPrice > 0
    ? anchorsFromTechnicalLevels(technicalLevels, currentPrice)
    : [];

  const levelLines: { label: string; value: number; color?: string }[] = [];
  if (horizon) {
    if (horizon.target != null) levelLines.push({ label: "Target", value: horizon.target, color: "#34d399" });
    if (horizon.stop_loss != null) levelLines.push({ label: "Stop", value: horizon.stop_loss, color: "#fb7185" });
    if (horizon.entry_zone?.low != null) levelLines.push({ label: "Entry", value: horizon.entry_zone.low, color: "#38bdf8" });
  }
  if (detail.ma50 != null) levelLines.push({ label: "MA50", value: detail.ma50, color: "#f59e0b" });
  if (detail.ma200 != null) levelLines.push({ label: "MA200", value: detail.ma200, color: "#a78bfa" });

  return (
    <ReferenceCard
      icon={BarChart3}
      title="Chart & levels"
      description="Price history with entry, stop, and target drawn as reference lines."
      body={
        <div className="space-y-2.5">
          {anchors.length > 0 && (
            <div className="rounded-lg border border-slate-800/70 bg-slate-950/40 px-2.5 py-2">
              <AnchorBentoGrid anchors={anchors} />
            </div>
          )}
          <IntradayChart ticker={detail.ticker} levelLines={levelLines} />
        </div>
      }
      footer={{ label: "View full chart & levels", onClick: onOpenLevels }}
      toggleLabel="Execution plan & compare timeframes"
    >
      {summary && currentPrice != null && currentPrice > 0 && (
        <>
          {summary.horizons?.short && summary.horizons?.long && (
            <HorizonDivergenceNote short={summary.horizons.short} long={summary.horizons.long} />
          )}
          <DecisionDeck
            summary={summary}
            currentPrice={currentPrice}
            mode={decisionMode}
            tacticalActive={Boolean(summary.tactical_entry?.active)}
            ltEntryTiersOpen={ltEntryTiersOpen}
            onToggleLtTiers={onToggleLtTiers}
            hideHero
            hideExecutionEvidence={Boolean(executionVm)}
          />
          {decisionMode === "scout" && summary.tactical_entry && (
            <TacticalEntryPanel payload={summary.tactical_entry} layout="scout" />
          )}
          <InvestorDecisionSummarySection
            summary={summary}
            currentPrice={currentPrice}
            ma200={detail.ma200}
            ma20={detail.ma20}
            ma50={detail.ma50}
            sector={detail.sector}
            companyName={detail.company_name}
            ltEntryTiersOpen={ltEntryTiersOpen}
            onToggleLtTiers={onToggleLtTiers}
            priceHistory={detail.price_history}
            ticker={detail.ticker}
            hideTradingGates
            hideRoadmaps
            compactOverview
            marketContext={detail.market_context}
            decisionMode={decisionMode}
            contentLayer="today"
          />
        </>
      )}
    </ReferenceCard>
  );
}

function ValuationCard({ detail, priceTargets, onOpenValuation }: ReferenceDetailGridProps) {
  const summary = detail.investor_summary;
  const fairValue = summary?.fair_value;
  const analystMedian =
    priceTargets?.analyst_targets?.median ?? summary?.valuation_deck?.street?.median_usd ?? null;

  return (
    <ReferenceCard
      icon={DollarSign}
      title="Valuation"
      description="Fair value model, analyst consensus, and the margin-of-safety ladder this persona is measured against."
      stats={[
        { label: "Fair value (model)", value: fmtUsd(fairValue) },
        { label: "Analyst median", value: fmtUsd(analystMedian) },
      ]}
      body={priceTargets ? <ScenarioTeaser data={priceTargets} onOpenValuation={onOpenValuation} /> : undefined}
      footer={{ label: "Open valuation deck", onClick: onOpenValuation }}
    />
  );
}

function WhyMovedCard({ detail, decisionMode, onOpenContext }: ReferenceDetailGridProps) {
  const reason = useSignalReason(detail, decisionMode);
  const mv = reason?.move_narrative;
  const driver = mv?.driver ?? "unclear";
  const tickerToday = mv?.day_change_pct ?? detail.daily_move_pct ?? null;
  const spyToday = mv?.spy_day_change_pct ?? null;

  return (
    <ReferenceCard
      icon={Newspaper}
      title="Why it moved today"
      description="Rule-based move classification — broad market, stock-specific news, or unclear. No LLM guesswork."
      stats={[
        { label: `${detail.ticker} today`, value: fmtPct(tickerToday) },
        { label: "SPY today", value: fmtPct(spyToday) },
      ]}
      body={
        <div className="space-y-1.5">
          <span
            className={clsx(
              "inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold",
              DRIVER_CLASS[driver],
            )}
          >
            {DRIVER_LABEL[driver] ?? "Unclear"}
          </span>
          {mv?.headline ? (
            <p className="text-xs text-slate-300 leading-relaxed">{mv.headline}</p>
          ) : (
            <p className="text-xs text-slate-500 italic">No move classification available yet.</p>
          )}
          {mv?.detail && <p className="text-xs text-slate-500 leading-relaxed">{mv.detail}</p>}
          {mv?.citation && <p className="text-[10px] text-slate-600 leading-relaxed">{mv.citation}</p>}
        </div>
      }
      footer={detail.thesis ? { label: "Story & catalysts", onClick: onOpenContext } : undefined}
    />
  );
}

function NearBottomCard({ detail, decisionMode, onOpenProof }: ReferenceDetailGridProps) {
  const reason = useSignalReason(detail, decisionMode);
  const nb = reason?.near_bottom;
  const modeLabel = (nb?.mode && NEAR_BOTTOM_MODE_LABEL[nb.mode]) ?? "—";
  const signals = nb?.signals ?? [];

  return (
    <ReferenceCard
      icon={RefreshCw}
      title="Near bottom / breakout read"
      description="Pattern score already computed by the model — surfaced here instead of discarded."
      stats={[
        { label: "Mode", value: modeLabel },
        { label: "Score", value: nb?.score != null ? `${Math.round(nb.score)} / 100` : "—" },
      ]}
      body={
        signals.length > 0 ? (
          <ul className="text-xs text-slate-400 space-y-1 list-disc list-inside">
            {signals.slice(0, 4).map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        ) : undefined
      }
      footer={{ label: "Full pattern signals", onClick: onOpenProof }}
    />
  );
}

function ConfidenceCard({ detail, confidence, onOpenProof }: ReferenceDetailGridProps) {
  const fusedPct = confidence?.confidence != null ? Math.round(confidence.confidence * 100) : null;
  const unlockText =
    detail.investor_summary?.retail_action?.unlock_summary ??
    detail.investor_summary?.retail_action?.unlock_sequence ??
    null;

  return (
    <ReferenceCard
      icon={Target}
      title="Confidence breakdown"
      description="The 7-layer fused confidence model, one place — not duplicated across tabs."
      stats={[
        { label: "Fused confidence", value: fusedPct != null ? `${fusedPct}%` : "—" },
        { label: "Layers active", value: confidence ? `${confidence.n_layers_active} / 7` : "—" },
      ]}
      body={
        <div className="space-y-1.5">
          {confidence?.action && <p className="text-xs text-slate-400">{confidence.action}</p>}
          {unlockText?.trim() && (
            <p className="text-xs text-emerald-300/90 leading-snug">
              <span aria-hidden>🔓</span> {unlockText.replace(/^Unlocks when:\s*/i, "Unlocks when: ")}
            </p>
          )}
        </div>
      }
      footer={{ label: "See layer weights", onClick: onOpenProof }}
    />
  );
}

const INSIGHTS_TIMEOUT_MS = 90000;

function FundamentalsCard({ detail, onOpenContext }: ReferenceDetailGridProps) {
  const [institutional, setInstitutional] = useState<InstitutionalBundle | null>(null);
  const ticker = detail.ticker;

  useEffect(() => {
    if (!ticker) return;
    setInstitutional(null);
    const ac = new AbortController();
    const timer = window.setTimeout(() => ac.abort(), INSIGHTS_TIMEOUT_MS);
    fetch(apiUrl(`/api/insights/${ticker.toUpperCase()}`), { signal: ac.signal, cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (j?.institutional) setInstitutional(j.institutional as InstitutionalBundle);
      })
      .catch(() => {/* optional stat — quietly stay at "—" */})
      .finally(() => window.clearTimeout(timer));
    return () => {
      ac.abort();
      window.clearTimeout(timer);
    };
  }, [ticker]);

  const trend = institutional?.edgar_13f?.trend;
  const peers = (detail.peers ?? []).slice(0, 4).join(", ");

  return (
    <ReferenceCard
      icon={Building2}
      title="Fundamentals & context"
      description="Peers, sector, earnings calendar, institutional 13F conviction — low-frequency context, correctly placed last."
      stats={[
        { label: "Next earnings", value: detail.earnings?.days_until != null ? `${detail.earnings.days_until}d` : "—" },
        { label: "13F trend (qtr)", value: trend ?? "—" },
      ]}
      body={
        <p className="text-xs text-slate-500 leading-relaxed">
          {detail.sector ?? "—"}
          {peers ? ` · Peers: ${peers}` : ""}
        </p>
      }
      footer={{ label: "Open context", onClick: onOpenContext }}
    />
  );
}
