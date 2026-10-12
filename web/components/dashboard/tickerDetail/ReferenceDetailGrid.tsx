"use client";

import { useEffect, useState, type ReactNode } from "react";
import { clsx } from "clsx";
import {
  AlertTriangle,
  BarChart3,
  Building2,
  ChevronDown,
  ChevronRight,
  DollarSign,
  Newspaper,
  Percent,
  RefreshCw,
  Scale,
  Target,
  type LucideIcon,
} from "lucide-react";
import type { TickerDetail, PortfolioImpactContext } from "../TickerDetailModal";
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
    <div className="rounded-2xl border border-td-line bg-td-surface p-4 flex flex-col gap-3 shadow-[0_1px_0_rgba(0,0,0,0.4),0_20px_40px_-24px_rgba(0,0,0,0.6)]">
      <h4 className="flex items-center gap-1.5 text-[13px] font-semibold text-td-text">
        <Icon className="h-3.5 w-3.5 text-td-accent shrink-0" aria-hidden />
        {title}
      </h4>
      {description && <p className={TD.footnote}>{description}</p>}
      {stats && stats.length > 0 && (
        <div className="text-xs">
          {stats.map((s, i) => (
            <div
              key={i}
              className="flex items-center justify-between gap-3 py-1.5 border-t border-td-line/70 first:border-t-0"
            >
              <span className="text-td-muted shrink-0">{s.label}</span>
              <span className="font-mono font-semibold text-td-text text-right truncate">{s.value}</span>
            </div>
          ))}
        </div>
      )}
      {body}
      {footer && (
        <button
          type="button"
          onClick={footer.onClick}
          className="text-xs font-semibold text-td-accent hover:text-td-accent-ink text-left mt-auto pt-0.5"
        >
          {footer.label} →
        </button>
      )}
      {children && (
        <div className="pt-1.5 border-t border-td-line/70 -mx-4 px-4">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="w-full flex items-center justify-between gap-2 text-[11px] font-mono uppercase tracking-wide text-td-muted hover:text-td-text py-1"
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
  neutral: "No clear setup",
};

export type CardId =
  | "chartLevels"
  | "valuation"
  | "whyMoved"
  | "nearBottom"
  | "confidence"
  | "options"
  | "shortInterest"
  | "fundamentals"
  | "preTradeImpact";

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
  portfolioImpactContext?: PortfolioImpactContext | null;
  /** Render only this subset (any order you like — rendered in the fixed ALL_CARD_IDS order). Omit for all 9. */
  only?: CardId[];
  /** Hide ChartLevelsCard's "View full chart & levels" footer — pass when this grid is itself rendered inside the Levels tab, so the card doesn't link to the tab it's already in. */
  suppressOpenLevels?: boolean;
  /** Hide FundamentalsCard's "Open context" footer — pass when this grid is itself rendered inside the Context tab. */
  suppressOpenContext?: boolean;
}

const ALL_CARD_IDS: CardId[] = [
  "chartLevels",
  "valuation",
  "whyMoved",
  "nearBottom",
  "confidence",
  "options",
  "shortInterest",
  "fundamentals",
  "preTradeImpact",
];

const CARD_COMPONENTS: Record<CardId, (props: ReferenceDetailGridProps) => ReactNode> = {
  chartLevels: ChartLevelsCard,
  valuation: ValuationCard,
  whyMoved: WhyMovedCard,
  nearBottom: NearBottomCard,
  confidence: ConfidenceCard,
  options: OptionsCard,
  shortInterest: ShortInterestCard,
  fundamentals: FundamentalsCard,
  preTradeImpact: PreTradeImpactCard,
};

export function ReferenceDetailGrid(props: ReferenceDetailGridProps) {
  const ids = (props.only ?? ALL_CARD_IDS).filter((id) => ALL_CARD_IDS.includes(id));
  const cols = Math.min(3, ids.length);
  return (
    <div>
      <p className={clsx(TD.sectionLabel, "pt-2 border-t border-td-line mb-2.5")}>
        Reference detail — everything for a second look, one card per topic
      </p>
      <div
        className={clsx(
          "grid grid-cols-1 gap-3",
          cols >= 2 && "sm:grid-cols-2",
          cols >= 3 && "lg:grid-cols-3",
        )}
      >
        {ids.map((id) => {
          const Card = CARD_COMPONENTS[id];
          return <Card key={id} {...props} />;
        })}
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
  suppressOpenLevels,
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
    const ns = horizon.nearby_sr?.next_support;
    const nr = horizon.nearby_sr?.next_resistance;
    if (ns?.price) levelLines.push({ label: ns.label || "Support", value: ns.price, color: "#f59e0b" });
    if (nr?.price) levelLines.push({ label: nr.label || "Resist", value: nr.price, color: "#22d3ee" });
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
          {detail.session_vwap && (
            <p className="text-[11px] text-slate-500 leading-relaxed">
              Session VWAP{" "}
              <span className="font-mono text-slate-300">{fmtUsd(detail.session_vwap.vwap)}</span>
              {" — price is "}
              <span
                className={
                  detail.session_vwap.close_vs_vwap_pct >= 0 ? "text-emerald-400" : "text-red-400"
                }
              >
                {fmtPct(detail.session_vwap.close_vs_vwap_pct)}
              </span>{" "}
              vs. VWAP today.
            </p>
          )}
        </div>
      }
      footer={suppressOpenLevels ? undefined : { label: "View full chart & levels", onClick: onOpenLevels }}
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

const SQUEEZE_RISK_CLASS: Record<string, string> = {
  none: "text-slate-400 bg-slate-500/10 border-slate-500/30",
  low: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30",
  moderate: "text-amber-300 bg-amber-500/10 border-amber-500/30",
  elevated: "text-orange-300 bg-orange-500/10 border-orange-500/30",
  high: "text-red-300 bg-red-500/10 border-red-500/30",
  extreme: "text-rose-300 bg-rose-600/15 border-rose-500/40",
};

function SqueezeBadge({ risk }: { risk: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wide",
        SQUEEZE_RISK_CLASS[risk] ?? SQUEEZE_RISK_CLASS.none,
      )}
    >
      {risk} squeeze risk
    </span>
  );
}

/** Put/call ratio, IV rank, and max pain from the options chain — free (yfinance), already
 * computed for every ticker-detail request via confidence_engine.py. Hidden entirely when
 * the ticker has no listed options (confidence.options.error set). */
function OptionsCard({ confidence, onOpenProof }: ReferenceDetailGridProps) {
  const opts = confidence?.options;
  if (!opts || opts.error) return null;

  const pcRatio = opts.pc_ratio;
  const leaning =
    pcRatio == null
      ? null
      : pcRatio >= 1.2
        ? "put-heavy — traders positioned for downside or hedging"
        : pcRatio <= 0.7
          ? "call-heavy — traders leaning bullish"
          : "roughly balanced between calls and puts";

  return (
    <ReferenceCard
      icon={Percent}
      title="Options market"
      description="Put/call positioning and implied volatility from the options chain — a smart-money positioning signal, not a stand-alone buy/sell call."
      stats={[
        { label: "Put/call ratio", value: pcRatio != null ? pcRatio.toFixed(2) : "—" },
        { label: "IV rank", value: opts.iv_rank != null ? `${Math.round(opts.iv_rank)} / 100` : "—" },
        { label: "Max pain", value: fmtUsd(opts.max_pain) },
      ]}
      body={
        <p className="text-xs text-slate-400 leading-relaxed">
          {opts.options_label || (leaning ? `Options are ${leaning}.` : "No options read available yet.")}
        </p>
      }
      footer={{ label: "See layer weights", onClick: onOpenProof }}
    />
  );
}

/** Short % of float, days-to-cover, and squeeze-risk classification from FINRA data (free,
 * via yfinance) — already computed for every ticker-detail request. Hidden when the ticker
 * has no short-interest data available. */
function ShortInterestCard({ confidence, onOpenProof }: ReferenceDetailGridProps) {
  const si = confidence?.short_interest;
  if (!si) return null;

  return (
    <ReferenceCard
      icon={AlertTriangle}
      title="Short interest"
      description="Short position sizing and days-to-cover from FINRA data — flags squeeze setups and crowded-short risk."
      stats={[
        { label: "Short % of float", value: si.short_pct_display ?? "—" },
        {
          label: "Days to cover",
          value: si.dtc_label ?? (si.days_to_cover != null ? si.days_to_cover.toFixed(1) : "—"),
        },
      ]}
      body={
        <div className="space-y-1.5">
          <SqueezeBadge risk={si.squeeze_risk ?? "none"} />
          {si.label && <p className="text-xs text-slate-400 leading-relaxed">{si.label}</p>}
          {si.bear_signal && (
            <p className="text-[11px] text-red-300/90 leading-relaxed">
              Heavy short interest with no bullish technical setup — a risk factor, not a squeeze signal.
            </p>
          )}
        </div>
      }
      footer={{ label: "See layer weights", onClick: onOpenProof }}
    />
  );
}

const CORRELATION_TIMEOUT_MS = 15000;
/** Illustrative hypothetical add size for the pre-trade impact estimate — 5% of current
 * portfolio value, rounded to the nearest $100. Not a sizing recommendation (Tier-1's
 * Kelly panel and Portfolio Doctor's add table own that); this card only answers "if I put
 * a normal-sized position here, what would it do to my sector weight and correlation?" */
function hypotheticalAddDollars(totalValue: number): number {
  return Math.max(100, Math.round((totalValue * 0.05) / 100) * 100);
}

interface CorrelationToHoldingsResponse {
  available: boolean;
  correlations?: { ticker: string; correlation: number }[];
  avg_correlation?: number | null;
}

/**
 * Pre-trade portfolio impact — "if I add here, what happens to my book?" Sector-weight and
 * top-3-concentration deltas are pure arithmetic on data Dashboard.tsx already has in scope
 * (selectedReport's per_holding/sector_allocation/total_value — see portfolioImpactContext
 * in Dashboard.tsx), computed client-side with no extra fetch. Only the correlation-to-
 * holdings number needs a backend round trip (it needs price history), via the new
 * GET /api/ticker/{ticker}/correlation-to-holdings endpoint. Hidden entirely when the
 * ticker is already held or no portfolio is configured/selected.
 */
function PreTradeImpactCard({ detail, portfolioImpactContext }: ReferenceDetailGridProps) {
  const ctx = portfolioImpactContext;
  const ticker = detail.ticker;
  const isHeld = !!ctx && ctx.heldTickers.has((ticker || "").toUpperCase());

  const [corrData, setCorrData] = useState<CorrelationToHoldingsResponse | null>(null);

  useEffect(() => {
    if (!ctx || isHeld || !ticker || ctx.topHoldings.length === 0) {
      setCorrData(null);
      return;
    }
    const ac = new AbortController();
    const timer = window.setTimeout(() => ac.abort(), CORRELATION_TIMEOUT_MS);
    const tickersParam = ctx.topHoldings.map((h) => h.ticker).join(",");
    fetch(apiUrl(`/api/ticker/${ticker}/correlation-to-holdings?tickers=${encodeURIComponent(tickersParam)}`), {
      signal: ac.signal,
      cache: "no-store",
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (j) setCorrData(j as CorrelationToHoldingsResponse);
      })
      .catch(() => {
        /* optional — quietly stay empty */
      })
      .finally(() => window.clearTimeout(timer));
    return () => {
      ac.abort();
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, isHeld, ctx?.topHoldings.map((h) => h.ticker).join(",")]);

  if (!ctx || isHeld) return null;

  const dollarAmount = hypotheticalAddDollars(ctx.totalValue);
  const newTotal = ctx.totalValue + dollarAmount;
  const sector = detail.sector || "Unknown";
  const currentSectorPct = ctx.sectorAllocation.find((s) => s.sector === sector)?.pct ?? 0;
  const currentSectorValue = (currentSectorPct / 100) * ctx.totalValue;
  const newSectorPct = ((currentSectorValue + dollarAmount) / newTotal) * 100;
  const newPositionPct = (dollarAmount / newTotal) * 100;

  const strongCorrelations = (corrData?.correlations ?? []).filter((p) => Math.abs(p.correlation) >= 0.6);

  return (
    <ReferenceCard
      icon={Scale}
      title="Pre-trade portfolio impact"
      description={`Not held yet. Illustrative $${dollarAmount.toLocaleString()} add (~5% of your book) — what it would do to your allocation.`}
      body={
        <div className="space-y-2">
          <div className="rounded-lg border border-slate-800/70 bg-slate-950/40 px-2.5 py-2 space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500">New position size</span>
              <span className="font-mono text-slate-200">{newPositionPct.toFixed(1)}% of book</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500">{sector} weight</span>
              <span className="font-mono text-slate-200">
                {currentSectorPct.toFixed(1)}% → <span className="text-amber-300">{newSectorPct.toFixed(1)}%</span>
              </span>
            </div>
          </div>
          {corrData?.available && (corrData.correlations?.length ?? 0) > 0 && (
            <p className="text-[11px] text-slate-500 leading-relaxed">
              1y correlation to top holdings:{" "}
              {corrData.correlations!.map((p, i) => (
                <span key={p.ticker}>
                  {i > 0 && ", "}
                  <span className="font-mono text-slate-400">{p.ticker}</span>{" "}
                  <span className={Math.abs(p.correlation) >= 0.6 ? "text-amber-300" : "text-slate-500"}>
                    {p.correlation.toFixed(2)}
                  </span>
                </span>
              ))}
              {strongCorrelations.length > 0 && " — moves closely with what you already own."}
            </p>
          )}
        </div>
      }
    />
  );
}

const INSIGHTS_TIMEOUT_MS = 90000;

function FundamentalsCard({ detail, onOpenContext, suppressOpenContext }: ReferenceDetailGridProps) {
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

  // Relative-strength ranking — current ticker + every peer with a usable 1-month
  // return (a ~20-trading-day figure, the closest bucket to "20-day momentum" already
  // computed; see _returns_over_periods in ticker_detail.py). Needs at least one peer
  // return alongside our own to be a ranking, not just a solo number.
  const ownReturn1m = detail.returns?.["1m"];
  const rankRows = [
    { ticker: detail.ticker, ret: ownReturn1m, isSelf: true },
    ...(detail.peer_returns ?? []).map((p) => ({
      ticker: p.ticker,
      ret: p.returns?.["1m"],
      isSelf: false,
    })),
  ].filter((r): r is { ticker: string; ret: number; isSelf: boolean } => r.ret != null);
  rankRows.sort((a, b) => b.ret - a.ret);
  const selfRank = rankRows.findIndex((r) => r.isSelf) + 1;

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
        <div className="space-y-2">
          <p className="text-xs text-slate-500 leading-relaxed">
            {detail.sector ?? "—"}
            {peers ? ` · Peers: ${peers}` : ""}
          </p>
          {rankRows.length >= 2 && (
            <div className="rounded-lg border border-slate-800/70 bg-slate-950/40 px-2.5 py-2">
              <p className="text-[10px] uppercase tracking-wide text-slate-500 mb-1.5">
                1-month relative strength — {detail.ticker} ranks #{selfRank} of {rankRows.length}
              </p>
              <ul className="space-y-0.5">
                {rankRows.map((r, i) => (
                  <li
                    key={r.ticker}
                    className={clsx(
                      "flex items-center justify-between gap-2 text-[11px]",
                      r.isSelf ? "text-slate-100 font-semibold" : "text-slate-500",
                    )}
                  >
                    <span className="flex items-center gap-1.5 min-w-0">
                      <span className="text-slate-600 w-3 shrink-0 text-right tabular-nums">{i + 1}</span>
                      <span className="font-mono truncate">{r.ticker}</span>
                    </span>
                    <span className={clsx("tabular-nums shrink-0", r.ret >= 0 ? "text-emerald-400" : "text-red-400")}>
                      {fmtPct(r.ret)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      }
      footer={suppressOpenContext ? undefined : { label: "Open context", onClick: onOpenContext }}
    />
  );
}
