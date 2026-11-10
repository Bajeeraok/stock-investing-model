"use client";

/**
 * One decision band: verdict, plain-English reason, price levels, and gate status —
 * everything needed to call buy/watch/sell without scrolling. Persona swaps the data
 * (band, framing, MOS ladder), never the shape. Replaces TickerCommandCard,
 * SignalReasonCard, SignalBreakdownGrid, the contextOnly GlobalActionHeader block, and
 * StreetVsExecutionCard, which each rendered their own version of the same verdict.
 */

import { clsx } from "clsx";
import { ChevronRight } from "lucide-react";
import type { DecisionMode } from "@/lib/decisionMode";
import { horizonLabel, primaryHorizonFromMode } from "@/lib/decisionMode";
import type { InvestorDecisionSummary, HorizonSignalPayload } from "../InvestorDecisionSummary";
import type { TradingGateRow } from "../retailActionUX";
import type { SignalReasonPayload } from "./SignalReasonCard";
import { useTickerTrackRecord } from "@/lib/useTickerTrackRecord";
import { pickCal } from "./TrackErrorCard";

/** Matches RetailActionLight / RetailActionStatus in TickerDetailModal.tsx — kept local
 * (not imported) to avoid a circular import between the modal and this component. */
type RetailActionLight = "red" | "yellow" | "green" | "neutral";
type RetailActionStatus = { light: RetailActionLight; title: string; subtitle: string };

const LIGHT_BADGE: Record<RetailActionLight, string> = {
  green: "border-td-accent/50 bg-td-accent-weak text-td-accent",
  yellow: "border-td-warn/50 bg-td-warn-weak text-td-warn",
  red: "border-td-crit/50 bg-td-crit-weak text-td-crit",
  neutral: "border-td-line bg-td-surface2 text-td-muted",
};
const LIGHT_DOT: Record<RetailActionLight, string> = {
  green: "bg-td-accent",
  yellow: "bg-td-warn",
  red: "bg-td-crit",
  neutral: "bg-td-muted",
};
const STANCE_CHIP: Record<"helps" | "hurts" | "neutral", string> = {
  helps: "text-td-accent border-td-accent/35 bg-td-accent-weak",
  hurts: "text-td-warn border-td-warn/35 bg-td-warn-weak",
  neutral: "text-td-muted border-td-line bg-td-surface2/60",
};
const MODE_ACCENT: Record<DecisionMode, string> = {
  scout: "border-td-info/25",
  swing: "border-td-owner/25",
  owner: "border-td-accent/25",
};

const TIER_ANCHOR: Record<string, string> = { T1: "MA200 zone", T2: "value (MOS)", T3: "stress tail" };

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${n.toFixed(digits)}`;
}

function pctFromSpot(level: number | null | undefined, spot: number | null | undefined): string {
  if (level == null || spot == null || !(spot > 0)) return "";
  const pct = ((level - spot) / spot) * 100;
  return `${pct >= 0 ? "+" : "−"}${Math.abs(pct).toFixed(1)}%`;
}

/** Levels row: long/owner uses the tier ladder when present, everyone else uses entry_zone/target/stop. */
function srSideTag(
  side: "Support" | "Resist",
  level: { label: string } | null | undefined,
): "Support" | "Resist" | "Pivot" {
  const lbl = (level?.label || "").toLowerCase();
  if (lbl.includes("pivot") || lbl.includes("20d")) return "Pivot";
  return side;
}

function SrRow({
  tag,
  level,
}: {
  tag: "Support" | "Resist";
  level: { price: number; label: string; dist_pct: number } | null | undefined;
}) {
  if (!level || !(level.price > 0)) return null;
  const below = level.dist_pct < 0;
  const shown = srSideTag(tag, level);
  return (
    <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface2/50 border border-td-line">
      <span className="text-[11px] font-mono font-bold uppercase tracking-wide text-td-muted">{shown}</span>
      <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">
        {fmt(level.price)}
        <span className="ml-1.5 text-[11px] font-td-sans font-medium text-td-muted normal-case">{level.label}</span>
      </span>
      <span className={clsx("text-[11px] font-mono tabular-nums", below ? "text-td-crit/80" : "text-td-accent/80")}>
        {level.dist_pct >= 0 ? "+" : "−"}
        {Math.abs(level.dist_pct).toFixed(1)}%
      </span>
    </div>
  );
}

function NearbySrRows({ horizon }: { horizon: HorizonSignalPayload }) {
  const sr = horizon.nearby_sr;
  if (!sr?.next_support && !sr?.next_resistance) return null;
  return (
    <>
      <SrRow tag="Support" level={sr.next_support} />
      <SrRow tag="Resist" level={sr.next_resistance} />
    </>
  );
}

function StopTargetRows({
  horizon,
  currentPrice,
}: {
  horizon: HorizonSignalPayload;
  currentPrice: number | null | undefined;
}) {
  return (
    <>
      <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface2/70 border border-td-line">
        <span className="text-[11px] font-mono font-bold uppercase tracking-wide text-td-muted">Stop</span>
        <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">{fmt(horizon.stop_loss)}</span>
        <span className="text-[11px] font-mono text-td-crit/80 tabular-nums">
          {pctFromSpot(horizon.stop_loss, currentPrice)}
        </span>
      </div>
      <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface2/70 border border-td-line">
        <span className="text-[11px] font-mono font-bold uppercase tracking-wide text-td-muted">Target</span>
        <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">{fmt(horizon.target)}</span>
        <span className="text-[11px] font-mono text-td-accent/80 tabular-nums">
          {pctFromSpot(horizon.target, currentPrice)}
          {/* Same R:R (and basis) as the Verdict tile — entry-mid when the plan has one, else spot. */}
          {(horizon.risk_reward_from_entry ?? horizon.risk_reward)
            ? ` · R:R 1:${(horizon.risk_reward_from_entry ?? horizon.risk_reward)!.toFixed(1)}${horizon.risk_reward_from_entry != null ? " band mid" : " spot"}`
            : ""}
        </span>
      </div>
    </>
  );
}

export interface DayLow {
  low: number;
  /** Session date (YYYY-MM-DD, ET) the low belongs to. */
  date: string;
}

function hitLabel(dayLow: DayLow): string {
  const todayEt = new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  if (dayLow.date === todayEt) return "hit today";
  const d = new Date(`${dayLow.date}T12:00:00`);
  return `hit ${d.toLocaleDateString("en-US", { weekday: "short" })}`;
}

type LevelStats = NonNullable<HorizonSignalPayload["entry_zone"]["levels"]>[number];

function LevelStatChips({ lvl, hit, horizon }: { lvl: LevelStats; hit: boolean; horizon: HorizonSignalPayload }) {
  const chips: { text: string; title: string; cls: string }[] = [];
  const ss = horizon.entry_zone?.similar_setup;
  if (!hit && lvl.similar_touch_pct != null && lvl.similar_n) {
    chips.push({
      text: `${lvl.similar_touch_pct}% in similar setups`,
      title: `Hit rate only on past days like today (price ${ss ? `${ss.stretch_vs_ma50_pct > 0 ? "+" : ""}${ss.stretch_vs_ma50_pct}% vs MA50 ±3 pts, ${ss.above_ma200 ? "above" : "below"} MA200` : "similar trend and stretch"}), ${lvl.similar_n} days.`,
      cls: hitPill(lvl.similar_touch_pct),
    });
  }
  if (lvl.after_touch_up_pct != null && lvl.after_touch_n) {
    const r = lvl.after_touch_median_ret_pct;
    const bad = lvl.after_touch_p25_ret_pct;
    const sg = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(1)}%`;
    chips.push({
      text: `${lvl.after_touch_up_pct}% higher ${lvl.after_touch_days ?? 20}d after${r != null ? ` · median ${sg(r)}` : ""}${bad != null ? ` · bad case ${sg(bad)}` : ""}`,
      title: `Past touches of a level this far below price (${lvl.after_touch_n}): how often the close ${lvl.after_touch_days ?? 20} trading days later was above the fill (any gain counts). Median = typical return from the fill; bad case = 1 in 4 did worse than this.`,
      cls: lvl.after_touch_up_pct >= 60 ? "bg-td-accent/15 text-td-accent" : lvl.after_touch_up_pct >= 45 ? "bg-td-warn/15 text-td-warn" : "bg-td-crit/15 text-td-crit",
    });
  }
  if (lvl.stop_first_pct != null && lvl.target_first_pct != null && lvl.outcome_n) {
    const neither = Math.max(0, 100 - lvl.stop_first_pct - lvl.target_first_pct);
    chips.push({
      text: `stop first ${lvl.stop_first_pct}% · target ${lvl.target_first_pct}% · neither ${neither}%`,
      title: `Entering at this level in past touches (${lvl.outcome_n}): which came first within ${lvl.outcome_window ?? ""} trading days, this plan's stop or its target. Neither = still between them at the end.`,
      cls: lvl.target_first_pct > lvl.stop_first_pct ? "bg-td-accent/15 text-td-accent" : "bg-td-crit/15 text-td-crit",
    });
  }
  if (!chips.length) return null;
  return (
    <div className="col-span-3 flex flex-wrap gap-1 pt-0.5">
      {chips.map((c) => (
        <span key={c.text} title={c.title} className={clsx("rounded-full px-1.5 py-0.5 text-[11px] font-mono tabular-nums", c.cls)}>
          {c.text}
        </span>
      ))}
    </div>
  );
}

function ModelOddsLine({ ticker, horizon, horizonKey }: { ticker: string; horizon: HorizonSignalPayload; horizonKey: string }) {
  const { data } = useTickerTrackRecord(ticker);
  const lvl = data?.level_odds_check;
  const pick = pickCal(lvl?.ticker, lvl?.pooled, horizonKey === "short" ? "20" : "63");
  const scored = horizon.ml_scored !== false && horizon.ml_prob != null;
  const gain = horizon.ml_target_gain_pct;
  return (
    <div className="mb-1.5 flex flex-col gap-1">
      <p className="text-[12px] leading-relaxed rounded-md border-l-2 border-td-info/60 bg-td-info/5 px-2.5 py-1.5 text-td-text/80">
        <span className="font-semibold text-td-info">Model</span>{" "}
        {scored
          ? `${Math.round(horizon.ml_prob)}% chance of ${gain != null ? `+${gain}% or more` : "rising"} within ${horizon.duration}. Applies to the stock, not to a level.`
          : "no model score for this horizon yet."}
      </p>
      {pick?.cal && pick.cal.actual_hit_pct != null && (
        <p
          className="text-[12px] leading-relaxed rounded-md border-l-2 border-td-accent/40 bg-td-surface2/60 px-2.5 py-1.5 text-td-text/80"
          title="Daily saved hit % predictions, checked against what price actually did."
        >
          <span className="font-semibold text-td-text">Hit % accuracy</span>: said {Math.round(pick.cal.avg_predicted_pct)}%, happened{" "}
          {Math.round(pick.cal.actual_hit_pct)}% ({pick.cal.n} checks, {pick.scope})
        </p>
      )}
    </div>
  );
}

function LevelRows({
  mode,
  horizon,
  currentPrice,
  dayLow,
}: {
  mode: DecisionMode;
  horizon: HorizonSignalPayload;
  currentPrice: number | null | undefined;
  dayLow?: DayLow | null;
}) {
  const tiers = mode === "owner" ? horizon.entry_tiers?.tiers : undefined;
  if (tiers && tiers.length > 0) {
    return (
      <div className="flex flex-col gap-1.5">
        {/* Nearest add first (highest ceiling) — tier ids are anchors (T1 MA200, T2 MOS,
            T3 stress), not an order, so listing by id read as "T2 sits above T1". */}
        {(() => {
          // Tiers above the margin-of-safety max add are "wait", not buy zones (same cap as the Owner band).
          const capped = tiers.filter((t) => t.above_max_add);
          const open = tiers.filter((t) => !t.above_max_add);
          const maxAdd = (horizon.entry_zone as { max_add?: number | null } | undefined)?.max_add ?? null;
          const above = open.filter((t) => currentPrice && t.high > currentPrice);
          const below = open.filter((t) => !(currentPrice && t.high > currentPrice)).sort((a, b) => b.high - a.high);
          const rowCls =
            "grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface2/70 border border-td-line";
          return (
            <>
              {above.length > 0 && (
                <div className={rowCls}>
                  <span className="text-[11px] font-mono font-bold uppercase tracking-wide text-td-muted">
                    {above.map((t) => t.id).join("·")}
                  </span>
                  <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">
                    at spot {fmt(currentPrice)}
                    <span className="ml-1.5 text-[11px] font-td-sans font-medium text-td-muted normal-case">
                      price is already under {above.map((t) => TIER_ANCHOR[t.id] ?? t.id).join(", ")}
                    </span>
                  </span>
                  <span className="text-[11px] font-mono text-td-muted tabular-nums">now</span>
                </div>
              )}
              {capped.length > 0 && (
                <div className={rowCls}>
                  <span className="text-[11px] font-mono font-bold uppercase tracking-wide text-td-muted">
                    {capped.map((t) => t.id).join("·")}
                  </span>
                  <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">
                    {maxAdd != null ? `max add ${fmt(maxAdd)}` : "above max add"}
                    <span className="ml-1.5 text-[11px] font-td-sans font-medium text-td-muted normal-case">
                      {capped.map((t) => TIER_ANCHOR[t.id] ?? t.id).join(", ")} sit above it — wait
                    </span>
                  </span>
                  <span className="text-[11px] font-mono text-td-muted tabular-nums">
                    {maxAdd != null ? pctFromSpot(maxAdd, currentPrice) : ""}
                  </span>
                </div>
              )}
              {below.map((t) => (
                <div key={t.id} className={rowCls}>
                  <span className="text-[11px] font-mono font-bold uppercase tracking-wide text-td-muted">{t.id}</span>
                  <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">
                    {fmt(t.low)} – {fmt(t.high)}
                    <span className="ml-1.5 text-[11px] font-td-sans font-medium text-td-muted normal-case">
                      {TIER_ANCHOR[t.id] ?? ""}
                    </span>
                  </span>
                  <span className="text-[11px] font-mono text-td-muted tabular-nums">{pctFromSpot(t.high, currentPrice)}</span>
                </div>
              ))}
            </>
          );
        })()}
        <NearbySrRows horizon={horizon} />
      </div>
    );
  }
  const ez = horizon.entry_zone;
  const ezWidthPct =
    ez?.low != null && ez?.high != null && currentPrice ? ((ez.high - ez.low) / currentPrice) * 100 : 0;
  // Every scale-in price inside the band (server-side build_entry_band_levels), nearest spot first —
  // a falling price fills the top of a buy-below band first.
  const isHit = (l: { price: number; role?: string | null }) =>
    dayLow != null && l.role !== "anchor" && l.price >= dayLow.low;
  const inBand =
    currentPrice != null && ez?.low != null && ez?.high != null && currentPrice >= ez.low && currentPrice <= ez.high * 1.005;
  // Levels filled earlier in the session stay listed (marked hit) even after price bounced above them.
  const stagedLevels = (ez?.levels ?? [])
    .filter((l) => !currentPrice || l.price <= currentPrice * 1.005 || (isHit(l) && ez?.high != null && l.price <= ez.high))
    .sort((x, y) => y.price - x.price);
  if (stagedLevels.length >= 2) {
    const entries = stagedLevels.filter((l) => l.role !== "anchor");
    const tag = (lvl: (typeof stagedLevels)[number]) => {
      if (lvl.role === "anchor") return lvl.label;
      const i = entries.indexOf(lvl);
      if (i === 0) return "1st add";
      if (i === entries.length - 1) return "Last add";
      return "Scale";
    };
    const picked = stagedLevels;
    return (
      <div className="flex flex-col gap-1.5">
        <p className="text-[12px] text-td-muted leading-relaxed -mt-0.5 mb-0.5 rounded-md border-l-2 border-td-info/60 bg-td-info/5 px-2.5 py-1.5">
          Entry band {fmt(ez?.low)} – {fmt(ez?.high)}
          {ezWidthPct > 0 ? ` (${ezWidthPct.toFixed(1)}% wide)` : ""} — scale in across these levels, not one price
          {picked.some((l) => l.touch_pct != null) &&
            ` · hit % = how often this stock reached the level within ${picked.find((l) => l.window_sessions)?.window_sessions ?? ""} trading days (${Math.round(picked.find((l) => l.touch_history_years)?.touch_history_years ?? 10)}y history)`}
        </p>
        {inBand && (
          <p className="text-[12px] leading-relaxed rounded-md border-l-2 border-td-accent/60 bg-td-accent/5 px-2.5 py-1.5 text-td-text/80">
            <span className="font-semibold text-td-accent">In band now</span> — the upper adds fill on normal
            daily swings, so high hit % is expected; it is not a prediction of a drop.
          </p>
        )}
        {picked.map((lvl) => (
          <div
            key={lvl.id}
            className={clsx(
              "grid grid-cols-[4.6rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg border",
              isHit(lvl) ? "bg-td-accent/5 border-td-accent/40" : "bg-td-surface2/70 border-td-line"
            )}
          >
            <span className={clsx("justify-self-start rounded-full px-1.5 py-0.5 text-[11px] font-mono font-bold uppercase tracking-wide truncate max-w-full", tagPill(tag(lvl)))}>
              {tag(lvl)}
            </span>
            <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">{fmt(lvl.price)}</span>
            <span className="text-[11px] font-mono text-td-muted tabular-nums text-right leading-tight">
              {pctFromSpot(lvl.price, currentPrice)}
              {isHit(lvl) ? (
                <span
                  className="block"
                  title={`Session low ${fmt(dayLow!.low)} reached this level`}
                >
                  <span className="rounded bg-td-accent/15 px-1 font-semibold text-td-accent">✓ {hitLabel(dayLow!)}</span>
                </span>
              ) : lvl.touch_pct != null && lvl.median_days != null && lvl.median_days > 0 && (
                <span
                  className="block"
                  title={`How often this stock reached this level within ${lvl.window_sessions ?? ""} trading days over the last ${Math.round(lvl.touch_history_years ?? 10)} years (median days when it did). History, not a forecast.`}
                >
                  <span className={clsx("rounded px-1", hitPill(lvl.touch_pct))}>{lvl.touch_pct}% hit</span> · ~{lvl.median_days}d
                </span>
              )}
            </span>
            <LevelStatChips lvl={lvl} hit={!!isHit(lvl)} horizon={horizon} />
          </div>
        ))}
        <StopTargetRows horizon={horizon} currentPrice={currentPrice} />
        <NearbySrRows horizon={horizon} />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface2/70 border border-td-line">
        <span className="text-[11px] font-mono font-bold uppercase tracking-wide text-td-muted">Entry</span>
        <span className="text-[13px] font-mono font-semibold text-td-text tabular-nums">
          {ez?.low != null && ez?.high != null ? `${fmt(ez.low)} – ${fmt(ez.high)}` : "—"}
        </span>
        <span className="text-[11px] font-mono text-td-muted tabular-nums">
          {pctFromSpot(ez?.low, currentPrice)}
        </span>
      </div>
      <StopTargetRows horizon={horizon} currentPrice={currentPrice} />
      <NearbySrRows horizon={horizon} />
    </div>
  );
}

function tagPill(tag: string): string {
  if (tag === "1st add") return "bg-td-accent/15 text-td-accent";
  if (tag === "Last add") return "bg-td-accent/10 text-td-accent/80";
  if (tag === "Scale") return "bg-td-info/10 text-td-info";
  return "bg-td-owner/15 text-td-owner";
}

function hitPill(pct: number): string {
  if (pct >= 50) return "bg-td-accent/15 text-td-accent";
  if (pct >= 25) return "bg-td-warn/15 text-td-warn";
  return "bg-td-surface text-td-muted";
}

export function TickerDecisionHero({
  ticker,
  companyName,
  sector,
  currentPrice,
  dailyMovePct,
  dayLow,
  summary,
  mode,
  actionStatus,
  gates,
  gatesPassed,
  gatesTotal,
  onOpenWhy,
  compact = false,
}: {
  ticker: string;
  companyName?: string | null;
  sector?: string | null;
  currentPrice: number | null | undefined;
  dailyMovePct?: number | null;
  dayLow?: DayLow | null;
  summary: InvestorDecisionSummary;
  mode: DecisionMode;
  actionStatus: RetailActionStatus;
  gates: TradingGateRow[];
  gatesPassed: number;
  gatesTotal: number;
  onOpenWhy?: () => void;
  /** Reason + levels only — the Verdict tab's VerdictPanel already shows the badge and gates. */
  compact?: boolean;
}) {
  const reason: SignalReasonPayload | null | undefined =
    summary.signal_reason_by_persona?.[mode] ?? summary.signal_reason;
  const horizonKey = primaryHorizonFromMode(mode);
  const horizon = summary.horizons[horizonKey];
  const factors = (reason?.factors ?? []).slice(0, 4);

  return (
    <div className={clsx("rounded-2xl bg-td-surface overflow-hidden", compact ? "border border-td-line" : "border-2", !compact && MODE_ACCENT[mode])}>
      {/* Ticker · verdict · price */}
      {!compact && (
      <div className="flex items-center justify-between gap-3 px-4 sm:px-5 py-3.5 border-b border-td-line">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-lg font-bold text-td-text tracking-tight">{ticker}</span>
            <span className="text-[13px] text-td-muted truncate">
              {companyName ?? ""}
              {sector ? ` · ${sector}` : ""}
            </span>
          </div>
        </div>
        <span
          className={clsx(
            "inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-sm font-mono font-bold uppercase whitespace-nowrap",
            LIGHT_BADGE[actionStatus.light],
          )}
        >
          <span className={clsx("w-1.5 h-1.5 rounded-full", LIGHT_DOT[actionStatus.light])} />
          {actionStatus.title}
        </span>
        <div className="text-right shrink-0">
          <p className="text-lg font-mono font-bold text-td-text tabular-nums">{fmt(currentPrice)}</p>
          {dailyMovePct != null && (
            <p
              className={clsx(
                "text-[13px] font-mono tabular-nums",
                dailyMovePct >= 0 ? "text-td-accent" : "text-td-crit",
              )}
            >
              {dailyMovePct >= 0 ? "+" : "−"}
              {Math.abs(dailyMovePct).toFixed(1)}% today
            </p>
          )}
        </div>
      </div>
      )}

      {/* Reason + levels */}
      <div className="grid sm:grid-cols-[1.2fr_1fr] gap-4 px-4 sm:px-5 py-4">
        <div className="min-w-0">
          {reason?.headline && (
            <p className="text-[15px] text-td-text leading-snug text-balance">{reason.headline}</p>
          )}
          {reason?.wait_plain && (
            <p className="text-[13px] text-td-text/75 mt-2 leading-relaxed rounded-md border-l-2 border-td-warn/60 bg-td-warn/5 px-2.5 py-1.5">{reason.wait_plain}</p>
          )}
          {!reason?.headline && actionStatus.subtitle && (
            <p className="text-[13.5px] text-td-text/90 leading-snug">{actionStatus.subtitle}</p>
          )}
          {factors.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {factors.map((f, i) => (
                <span
                  key={f.id ?? i}
                  className={clsx(
                    "text-[13px] font-medium px-2 py-1 rounded-md border",
                    STANCE_CHIP[f.stance ?? "neutral"],
                  )}
                >
                  {f.label}
                  {f.summary ? `: ${f.summary}` : ""}
                </span>
              ))}
            </div>
          )}
          {onOpenWhy && (
            <button
              type="button"
              onClick={onOpenWhy}
              className="inline-flex items-center gap-1 text-[13px] font-medium text-td-info hover:text-td-accent mt-3"
            >
              Full breakdown <ChevronRight className="h-3 w-3" />
            </button>
          )}
        </div>
        <div>
          <p className="text-[12px] font-mono font-semibold uppercase tracking-wider text-td-info mb-1.5">
            {horizonLabel(horizonKey)} levels
          </p>
          <ModelOddsLine ticker={ticker} horizon={horizon} horizonKey={horizonKey} />
          <LevelRows mode={mode} horizon={horizon} currentPrice={currentPrice} dayLow={dayLow} />
        </div>
      </div>

      {/* Gates */}
      {!compact && gates.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 px-4 sm:px-5 py-3 bg-td-surface2/40 border-t border-td-line">
          {gates.map((g) => (
            <div
              key={g.id}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-td-surface border border-td-line"
              title={g.detail}
            >
              <span
                className={clsx(
                  "w-4 h-4 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0",
                  g.pass ? "bg-td-accent-weak text-td-accent" : "bg-td-crit-weak text-td-crit",
                )}
              >
                {g.pass ? "✓" : "✕"}
              </span>
              <div className="min-w-0">
                <p className="text-[11px] font-semibold text-td-text truncate">{g.label}</p>
                <p className="text-[11px] text-td-muted truncate">{g.detail}</p>
              </div>
            </div>
          ))}
          <div className="col-span-2 sm:col-span-4 text-[11px] font-mono text-td-muted tabular-nums pt-0.5">
            {gatesPassed}/{gatesTotal} gates
          </div>
        </div>
      )}
    </div>
  );
}
