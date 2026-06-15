"use client";

import { clsx } from "clsx";
import type { DecisionMode } from "@/lib/decisionMode";
import type { FairValueVsExternal } from "./InvestorDecisionSummary";
import { StreetVsModelBar } from "./StreetVsModelBar";
import { AnalystRatingBar } from "./AnalystRatingBar";
import type { ValuationDeckPayload } from "./valuationDeckTypes";
import type { HorizonSignalPayload } from "./InvestorDecisionSummary";

function fmtUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

const BADGE_STYLE: Record<string, string> = {
  ok: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
  review: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  caution: "border-red-500/40 bg-red-500/10 text-red-200",
};

function GapBadge({ badge }: { badge?: string | null }) {
  if (!badge) return null;
  const label = badge === "ok" ? "OK vs street" : badge === "review" ? "Review gap" : "Caution";
  return (
    <span
      className={clsx(
        "text-[10px] px-1.5 py-0.5 rounded border font-medium uppercase tracking-wide",
        BADGE_STYLE[badge] ?? BADGE_STYLE.review,
      )}
    >
      {label}
    </span>
  );
}

function StreetColumn({ deck }: { deck: ValuationDeckPayload }) {
  const s = deck.street;
  if (!s) return <p className="text-xs text-slate-500">No street data (ETF or thin coverage).</p>;

  return (
    <div className="space-y-2">
      {(s.low_usd != null || s.high_usd != null) && (
        <p className="text-sm text-slate-200 tabular-nums">
          PT range {fmtUsd(s.low_usd)} – {fmtUsd(s.high_usd)}
        </p>
      )}
      {s.primary_usd != null && (
        <p className="text-xs text-slate-400">
          Primary ({s.primary_label || "Street"}):{" "}
          <span className="text-violet-200 font-medium tabular-nums">{fmtUsd(s.primary_usd)}</span>
          {s.yahoo_mean_usd != null && s.primary_usd !== s.yahoo_mean_usd && (
            <span className="text-slate-500"> · Yahoo {fmtUsd(s.yahoo_mean_usd)}</span>
          )}
        </p>
      )}
      {s.ratings && <AnalystRatingBar ratings={s.ratings} />}
      {s.eps_fwd != null && (
        <p className="text-xs text-slate-400">
          Fwd EPS consensus ~{s.eps_fwd.toFixed(2)}
          {s.eps_dispersion != null && s.eps_dispersion > 0.2
            ? ` · high dispersion (${(s.eps_dispersion * 100).toFixed(0)}%)`
            : ""}
        </p>
      )}
    </div>
  );
}

function ModelColumn({ deck }: { deck: ValuationDeckPayload }) {
  const m = deck.model;
  if (!m) return null;
  const pct = m.pct_vs_street_primary;

  return (
    <div className="space-y-2">
      <p className="text-sm text-emerald-200 font-semibold tabular-nums">Model FV {fmtUsd(m.fair_value_usd)}</p>
      {pct != null && (
        <p className="text-xs text-slate-400">
          {pct >= 0 ? "+" : ""}
          {pct.toFixed(1)}% vs street primary
        </p>
      )}
      <GapBadge badge={m.gap_badge} />
      {m.relative_valuation_line && (
        <p className="text-[11px] text-slate-400 leading-snug">{m.relative_valuation_line}</p>
      )}
      {m.method_used && <p className="text-xs text-slate-400">Method: {m.method_used}</p>}
      {m.methodology_summary && (
        <p className="text-sm text-slate-300 leading-relaxed">{m.methodology_summary}</p>
      )}
    </div>
  );
}

function HouseColumn({
  deck,
  currentPrice,
}: {
  deck: ValuationDeckPayload;
  currentPrice: number;
}) {
  const h = deck.house;
  if (!h?.tiers_summary?.length) {
    return <p className="text-xs text-slate-500">No long-term tiers on this name.</p>;
  }

  const fullMos = h.min_price_to_buy;
  const active = h.active_tier_id;

  return (
    <div className="space-y-2">
      {h.assessment_label && <p className="text-sm text-slate-200">{h.assessment_label}</p>}
      {fullMos != null && fullMos > 0 && (
        <p className="text-xs text-emerald-200/90">
          Full size ≤ <span className="font-semibold tabular-nums">{fmtUsd(fullMos)}</span>
          {h.above_full_mos_ceiling ? " (price above full MOS ceiling)" : " (25% MOS to model FV)"}
        </p>
      )}
      <ul className="space-y-1 text-[11px] text-slate-400">
        {h.tiers_summary.map((t) => (
          <li
            key={t.id}
            className={clsx(
              active === t.id && "text-emerald-200 font-medium",
            )}
          >
            {t.id}: {t.label || t.id}{" "}
            {t.low != null && t.high != null ? (
              <span className="tabular-nums">
                {fmtUsd(t.low)}–{fmtUsd(t.high)}
              </span>
            ) : null}
            {t.allocation_pct != null ? ` · ~${t.allocation_pct}%` : ""}
            {active === t.id ? " · active" : ""}
          </li>
        ))}
      </ul>
      {currentPrice > 0 && fullMos != null && currentPrice > fullMos && (
        <p className="text-[10px] text-amber-200/90">Now {fmtUsd(currentPrice)} — starter tiers only, not full book.</p>
      )}
    </div>
  );
}

/** Full 3-column valuation deck (Bloomberg-style parallel). */
export function ValuationDeck({
  deck,
  currentPrice,
  modelFairValue,
  external,
  mode = "owner",
  variant = "full",
}: {
  deck: ValuationDeckPayload | null | undefined;
  currentPrice: number;
  modelFairValue: number;
  external?: FairValueVsExternal | null;
  mode?: DecisionMode;
  variant?: "full" | "compact";
}) {
  if (!deck) return null;

  const showHouse = mode === "owner" || variant === "full";
  const showModelFull = mode !== "scout" || variant === "full";

  if (variant === "compact") {
    const s = deck.street;
    const m = deck.model;
    return (
      <div className="rounded-xl border border-violet-500/25 bg-violet-950/20 px-4 py-3 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-violet-300/90">
            Street context
          </h4>
          <GapBadge badge={m?.gap_badge} />
        </div>
        {s?.primary_usd != null && (
          <p className="text-sm text-slate-200">
            {s.primary_label || "Street"} {fmtUsd(s.primary_usd)}
            {m?.pct_vs_street_primary != null && (
              <span className="text-slate-400 text-xs ml-2">
                Model {m.pct_vs_street_primary >= 0 ? "+" : ""}
                {m.pct_vs_street_primary.toFixed(1)}%
              </span>
            )}
          </p>
        )}
        {s?.ratings && <AnalystRatingBar ratings={s.ratings} compact />}
        {showHouse && deck.house?.min_price_to_buy != null && (
          <p className="text-[11px] text-emerald-200/80">
            Full size ≤ {fmtUsd(deck.house.min_price_to_buy)} · see Owner for tiers
          </p>
        )}
        {deck.disclaimer && <p className="text-xs text-slate-500 leading-snug">{deck.disclaimer}</p>}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-sky-500/25 bg-sky-950/15 overflow-hidden">
      <div className="px-4 py-2.5 border-b border-sky-500/20 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-sky-300/90">
          Valuation deck
        </h4>
        <span className="text-xs text-slate-400">Street · Model · House</span>
      </div>
      <div
        className={clsx(
          "grid gap-4 p-4",
          showHouse ? "md:grid-cols-3" : "md:grid-cols-2",
        )}
      >
        <div>
          <p className="text-xs uppercase tracking-wide text-violet-300/90 font-semibold mb-2">
            Street (ANR / EE)
          </p>
          <StreetColumn deck={deck} />
        </div>
        {showModelFull && (
          <div>
            <p className="text-xs uppercase tracking-wide text-emerald-300/90 font-semibold mb-2">
              Model (RV / FA)
            </p>
            <ModelColumn deck={deck} />
          </div>
        )}
        {showHouse && (
          <div>
            <p className="text-xs uppercase tracking-wide text-emerald-300/90 font-semibold mb-2">
              House (what we do)
            </p>
            <HouseColumn deck={deck} currentPrice={currentPrice} />
          </div>
        )}
      </div>
      {external && modelFairValue > 0 && (
        <div className="px-4 pb-4">
          <StreetVsModelBar
            modelFairValue={modelFairValue}
            currentPrice={currentPrice}
            external={external}
          />
        </div>
      )}
      {deck.disclaimer && (
        <p className="px-4 pb-3 text-xs text-slate-500 leading-snug border-t border-slate-700/50 pt-2">
          {deck.disclaimer}
        </p>
      )}
    </div>
  );
}

export function valuationDeckFromSummary(summary: {
  valuation_deck?: ValuationDeckPayload | null;
  fair_value: number;
  fair_value_vs_external?: FairValueVsExternal | null;
  horizons?: { long?: HorizonSignalPayload };
}): ValuationDeckPayload | null {
  return summary.valuation_deck ?? null;
}
