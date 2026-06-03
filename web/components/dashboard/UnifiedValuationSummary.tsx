"use client";

import { Target } from "lucide-react";
import { clsx } from "clsx";
import { AnalystRatingBar } from "./AnalystRatingBar";
import { ValuationDeck } from "./ValuationDeck";
import type { AnalystTargets } from "./PriceTargetsPanel";
import type { ValuationDeckPayload } from "./valuationDeckTypes";
import type { FairValueVsExternal } from "./InvestorDecisionSummary";
import type { DecisionMode } from "@/lib/decisionMode";

function fmt(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function returnColor(r: number | null | undefined): string {
  if (r == null) return "text-slate-400";
  if (r >= 8) return "text-emerald-400";
  if (r >= 0) return "text-amber-400";
  return "text-red-400";
}

/** Merged Wall Street PT row + buy/hold/sell distribution + optional full valuation deck. */
export function UnifiedValuationSummary({
  deck,
  analystTargets,
  currentPrice,
  fairValue,
  external,
  decisionMode = "owner",
  showFullDeck = true,
}: {
  deck?: ValuationDeckPayload | null;
  analystTargets?: AnalystTargets | null;
  currentPrice: number;
  fairValue: number;
  external?: FairValueVsExternal | null;
  decisionMode?: DecisionMode;
  showFullDeck?: boolean;
}) {
  const street = deck?.street;
  const at = analystTargets;
  const ratings = street?.ratings;

  const high =
    street?.high_usd ?? at?.high ?? null;
  const median =
    street?.median_usd ?? street?.primary_usd ?? at?.median ?? null;
  const low =
    street?.low_usd ?? at?.low ?? null;
  const highRet =
    street?.high_return_pct ?? at?.high_return ?? null;
  const medRet =
    street?.median_return_pct ?? at?.median_return ?? null;
  const lowRet =
    street?.low_return_pct ?? at?.low_return ?? null;
  const analystCount =
    street?.analyst_count ?? at?.analyst_count ?? ratings?.total ?? null;

  const hasPt = median != null || high != null || low != null;
  const hasRatings = ratings != null && (ratings.total ?? 0) > 0;

  if (!hasPt && !hasRatings && !deck) return null;

  return (
    <div className="space-y-3">
      {(hasPt || hasRatings) && (
        <div className="bg-purple-500/5 border border-purple-500/20 rounded-xl px-3.5 py-3 space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <Target size={11} className="text-purple-400 shrink-0" />
            <span className="text-[10px] font-semibold text-purple-300 uppercase tracking-widest">
              Valuation summary — Wall Street
              {analystCount ? ` · ${analystCount} analysts` : ""}
            </span>
            <span className="text-[10px] text-slate-500 font-normal normal-case tracking-normal">
              (FMP · anchors Bull/Base scenarios)
            </span>
          </div>

          {hasPt && (
            <div className="flex items-center gap-5 flex-wrap">
              {high != null && (
                <div className="text-center">
                  <p className="text-[10px] text-slate-500">Analyst High</p>
                  <p className={clsx("text-sm font-mono font-bold", returnColor(highRet ?? 0))}>{fmt(high)}</p>
                  <p className={clsx("text-[10px]", returnColor(highRet ?? 0))}>{fmtPct(highRet)}</p>
                </div>
              )}
              {median != null && (
                <div className="text-center">
                  <p className="text-[10px] text-slate-500">Consensus</p>
                  <p className={clsx("text-sm font-mono font-bold", returnColor(medRet ?? 0))}>{fmt(median)}</p>
                  <p className={clsx("text-[10px]", returnColor(medRet ?? 0))}>{fmtPct(medRet)}</p>
                </div>
              )}
              {low != null && (
                <div className="text-center">
                  <p className="text-[10px] text-slate-500">Analyst Low</p>
                  <p className={clsx("text-sm font-mono font-bold", returnColor(lowRet ?? 0))}>{fmt(low)}</p>
                  <p className={clsx("text-[10px]", returnColor(lowRet ?? 0))}>{fmtPct(lowRet)}</p>
                </div>
              )}
              <div className="text-center">
                <p className="text-[10px] text-slate-500">Current</p>
                <p className="text-sm font-mono font-bold text-white">{fmt(currentPrice)}</p>
              </div>
            </div>
          )}

          {hasRatings && <AnalystRatingBar ratings={ratings!} />}

          {at?.note && !hasRatings && (
            <p className="text-[10px] text-slate-600 leading-snug">{at.note}</p>
          )}
        </div>
      )}

      {showFullDeck && deck && fairValue > 0 && (
        <ValuationDeck
          deck={deck}
          currentPrice={currentPrice}
          modelFairValue={fairValue}
          external={external}
          mode={decisionMode}
          variant="full"
        />
      )}
    </div>
  );
}
