"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, SlidersHorizontal } from "lucide-react";
import { clsx } from "clsx";
import type { FairValueMetadata, FairValueVsExternal } from "./InvestorDecisionSummary";

function fmtUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function streetSourceLabel(src: string | null | undefined): string {
  if (!src) return "—";
  const map: Record<string, string> = {
    fmp_median: "FMP consensus median",
    fmp_range_midpoint: "FMP range midpoint",
    yahoo_12m_mean: "Yahoo 12m mean",
    fmp_consensus: "FMP consensus",
  };
  return map[src] ?? src.replace(/_/g, " ");
}

function Row({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5">
      <span className="text-td-muted shrink-0">{label}</span>
      <span className={clsx("text-right text-td-text", mono && "font-mono text-[11px]")}>{value}</span>
    </div>
  );
}

/** Collapsible FV inputs — forward EPS, implied P/E, street anchor, routing (Owner / Why → Valuation). */
export function FairValueDebugPanel({
  currentPrice,
  displayFairValue,
  ttmPeUsed,
  forwardPeUsed,
  metadata,
  external,
  defaultOpen = false,
}: {
  currentPrice: number;
  displayFairValue: number;
  ttmPeUsed?: number | null;
  forwardPeUsed?: number | null;
  metadata?: FairValueMetadata | null;
  external?: FairValueVsExternal | null;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  const meta = metadata ?? {};
  const fwdEps = meta.forward_eps ?? null;
  const impliedFwdPe =
    fwdEps != null && fwdEps > 0 && currentPrice > 0
      ? currentPrice / fwdEps
      : forwardPeUsed ?? null;

  const streetUsd =
    meta.street_anchor_usd ??
    meta.fv_street_anchor_usd ??
    external?.fmp_consensus_median_usd ??
    external?.yahoo_12m_mean_usd ??
    null;

  const streetSrc =
    meta.street_anchor_source ??
    meta.fv_street_anchor_source ??
    external?.street_primary_source ??
    null;

  const modelFv = meta.model_fair_value_usd ?? (meta.fv_suppressed ? null : displayFairValue);
  const gapVsStreet =
    modelFv != null && streetUsd != null && streetUsd > 0
      ? ((modelFv - streetUsd) / streetUsd) * 100
      : external?.pct_model_vs_fmp_median ?? external?.pct_model_vs_yahoo_mean ?? null;

  const hasContent =
    ttmPeUsed != null ||
    forwardPeUsed != null ||
    impliedFwdPe != null ||
    streetUsd != null ||
    meta.method_used ||
    meta.fv_suppressed;

  if (!hasContent) return null;

  return (
    <div className="rounded-xl border border-td-line/60 bg-td-surface/50 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3.5 py-2.5 text-left hover:bg-td-surface2/40 transition-colors"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-td-muted shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-td-muted shrink-0" />
        )}
        <SlidersHorizontal className="h-3.5 w-3.5 text-td-muted shrink-0" />
        <span className="text-xs font-semibold uppercase tracking-wide text-td-text">
          FV inputs (debug)
        </span>
        {meta.fv_suppressed && (
          <span className="text-[10px] px-1.5 py-0.5 rounded border border-td-warn/40 text-td-warn/90 bg-td-warn/10">
            Model suppressed
          </span>
        )}
      </button>

      {open && (
        <div className="px-3.5 pb-3 pt-0.5 space-y-2 border-t border-td-line/40">
          {meta.fv_suppressed && meta.fv_suppressed_reason && (
            <p className="text-[11px] text-td-warn/80 leading-snug">{meta.fv_suppressed_reason}</p>
          )}

          <div className="text-xs space-y-0.5">
            <Row label="Spot" value={fmtUsd(currentPrice)} />
            <Row
              label="Display FV"
              value={
                meta.fv_suppressed
                  ? `${fmtUsd(displayFairValue)} (street anchor)`
                  : fmtUsd(displayFairValue)
              }
            />
            {modelFv != null && (
              <Row label="Model FV (raw)" value={fmtUsd(modelFv)} />
            )}
            <Row label="Street anchor" value={fmtUsd(streetUsd)} />
            <Row label="Street source" value={streetSourceLabel(streetSrc)} mono={false} />
            {gapVsStreet != null && (
              <Row
                label="Model vs street"
                value={fmtPct(gapVsStreet)}
              />
            )}
          </div>

          <div className="border-t border-td-line/40 pt-2 text-xs space-y-0.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-td-text mb-1">EPS / multiples</p>
            <Row label="TTM EPS" value={meta.ttm_eps != null ? fmtNum(meta.ttm_eps, 4) : "—"} />
            <Row label="Forward EPS (NTM)" value={meta.forward_eps != null ? fmtNum(meta.forward_eps, 4) : "—"} />
            <Row label="TTM P/E" value={fmtNum(ttmPeUsed ?? null, 1)} />
            <Row label="Forward P/E (feed)" value={fmtNum(forwardPeUsed ?? null, 1)} />
            <Row label="Implied fwd P/E" value={fmtNum(impliedFwdPe, 1)} />
            {meta.sector_pe_used != null && (
              <Row label="Sector TTM P/E (ref)" value={fmtNum(meta.sector_pe_used, 1)} />
            )}
            {meta.sector_forward_pe_used != null && (
              <Row label="Sector fwd P/E (ref)" value={fmtNum(meta.sector_forward_pe_used, 1)} />
            )}
          </div>

          {(meta.growth_used_pct != null || meta.method_used) && (
            <div className="border-t border-td-line/40 pt-2 text-xs space-y-0.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-td-text mb-1">Method</p>
              {meta.fv_route_method_label && (
                <Row label="Route" value={meta.fv_route_method_label} mono={false} />
              )}
              {meta.method_used && (
                <Row label="Estimator" value={meta.method_used} mono={false} />
              )}
              {meta.growth_used_pct != null && (
                <Row
                  label="Growth used (PEG)"
                  value={
                    meta.growth_was_capped && meta.growth_raw_pct != null
                      ? `${fmtNum(meta.growth_used_pct, 0)}% (raw ${fmtNum(meta.growth_raw_pct, 0)}%)`
                      : `${fmtNum(meta.growth_used_pct, 0)}%`
                  }
                  mono={false}
                />
              )}
              {meta.gap_badge_type && (
                <Row label="Gap badge" value={meta.gap_badge_type} mono={false} />
              )}
              {meta.divergence_pct != null && (
                <Row label="NTM/TTM EPS divergence" value={`${fmtNum(meta.divergence_pct, 1)}%`} />
              )}
            </div>
          )}

          {external?.yahoo_12m_mean_usd != null && external?.fmp_consensus_median_usd != null && (
            <div className="border-t border-td-line/40 pt-2 text-xs text-td-muted leading-relaxed">
              Yahoo ${external.yahoo_12m_mean_usd.toFixed(2)} · FMP median $
              {external.fmp_consensus_median_usd.toFixed(2)}
              {external.fmp_median_is_range_midpoint ? " (range midpoint)" : ""}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
