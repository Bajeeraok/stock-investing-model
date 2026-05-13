"use client";
import { useState, useMemo, useCallback } from "react";

/* ─── Input types ─── */
export interface HoldingRow {
  ticker: string;
  value: number | null;
  pct: number | null;
  regime: string | null;
  suggestion: string;
  action?: string | null;
  confidence?: number | null;
  score?: number | null;
  /** Optional — from portfolio report for tax / account-aware UI */
  account?: string | null;
  gain_loss?: number | null;
  purchase_date?: string | null;
}

export interface MCTRPosition {
  ticker: string;
  value_pct: number;
  risk_pct: number;
  risk_ratio: number;
}

export interface StressTest {
  name: string;
  portfolio_impact_pct: number;
  spy_drawdown_pct: number;
}

export interface SubScores {
  concentration: number;
  correlation: number;
  regime_alignment: number;
  drawdown_risk: number;
  tax_efficiency: number;
}

/* ─── Output types ─── */
export interface WhatIfRow {
  ticker: string;
  originalPct: number;
  adjustedPct: number;
  regime: string | null;
  signal: string;
  mctrPct: number;
}

export interface WhatIfResult {
  rows: WhatIfRow[];
  healthScore: number;
  subScores: SubScores;
  stressTests: StressTest[];
  effectivePositions: number;
  topSectorPct: number;
  topSectorName: string;
  isDirty: boolean;
  setAdjustedPct: (ticker: string, pct: number) => void;
  reset: () => void;
}

/* ─── Recomputation helpers (all client-side, instant) ─── */

function computeConcentrationScore(pcts: number[], sectorPcts: number[]): number {
  if (pcts.length === 0) return 50;
  const total = pcts.reduce((s, p) => s + p, 0);
  if (total <= 0) return 50;
  const normalized = pcts.map((p) => p / total);

  // HHI
  const hhi = normalized.reduce((s, p) => s + p * p, 0);
  const n = pcts.length;
  const hhiMin = 1 / n;
  const hhiScore = hhiMin < 1 ? Math.max(0, Math.min(100, ((1 - (hhi - hhiMin) / (1 - hhiMin)) * 100))) : 50;

  // Sector penalty
  const topSector = sectorPcts.length > 0 ? Math.max(...sectorPcts) : 0;
  const sectorPenalty = topSector > 40 ? Math.min(20, (topSector - 40) * 0.8) : 0;

  // Top-3 penalty
  const sorted = [...pcts].sort((a, b) => b - a);
  const top3 = sorted.slice(0, 3).reduce((s, p) => s + p, 0);
  const top3Penalty = top3 > 50 ? Math.max(0, (top3 - 50) * 0.5) : 0;

  return Math.max(0, Math.min(100, hhiScore - sectorPenalty - top3Penalty));
}

function computeCorrelationScore(
  pcts: number[],
  tickers: string[],
  corrMatrix?: Record<string, Record<string, number>>,
): number {
  if (!corrMatrix || tickers.length < 2) return 60;

  const total = pcts.reduce((s, p) => s + p, 0);
  if (total <= 0) return 60;
  const w = pcts.map((p) => p / total);

  // Weighted average absolute correlation
  let sumCorr = 0;
  let countCorr = 0;
  for (let i = 0; i < tickers.length; i++) {
    for (let j = i + 1; j < tickers.length; j++) {
      const c = corrMatrix[tickers[i]]?.[tickers[j]];
      if (c != null) {
        const weight = w[i] * w[j];
        sumCorr += Math.abs(c) * weight;
        countCorr += weight;
      }
    }
  }
  const avgCorr = countCorr > 0 ? sumCorr / countCorr : 0.5;

  const n = tickers.length;
  const effPositions = n * (1 - avgCorr) + avgCorr;
  const effRatio = n > 0 ? effPositions / n : 0.5;
  return Math.max(0, Math.min(100, effRatio * 100));
}

function computeRegimeAlignmentScore(
  pcts: number[],
  regimes: (string | null)[],
  signals: string[],
): number {
  const total = pcts.reduce((s, p) => s + p, 0);
  if (total <= 0) return 50;

  let constructiveWt = 0;
  let neutralWt = 0;
  for (let i = 0; i < pcts.length; i++) {
    const w = pcts[i] / total;
    const regime = (regimes[i] || "").toUpperCase();
    const signal = (signals[i] || "").toUpperCase();
    if (regime === "UP" || signal.includes("ADD") || signal === "BUY" || signal === "STRONG BUY") {
      constructiveWt += w;
    } else if (regime === "NEUTRAL" || signal === "HOLD") {
      neutralWt += w;
    }
  }
  return Math.max(0, Math.min(100, (constructiveWt + neutralWt * 0.5) * 100));
}

function computeDrawdownScore(stressTests: StressTest[]): number {
  if (stressTests.length === 0) return 75;
  const worst = Math.min(...stressTests.map((s) => s.portfolio_impact_pct));
  const absWorst = Math.abs(worst);
  return Math.max(20, Math.min(90, 90 - absWorst * 1.2));
}

function recomputeMCTR(
  originalMctr: MCTRPosition[],
  adjustedPcts: Record<string, number>,
): MCTRPosition[] {
  // Approximate: scale risk_pct proportionally to weight change, then renormalize
  const rows = originalMctr.map((p) => {
    const origW = p.value_pct;
    const newW = adjustedPcts[p.ticker] ?? origW;
    const ratio = origW > 0 ? newW / origW : 1;
    // MCTR scales roughly with w^2 contribution, approximate linearly for small changes
    return { ...p, value_pct: newW, raw_risk: p.risk_pct * ratio };
  });
  const totalRisk = rows.reduce((s, r) => s + r.raw_risk, 0);
  return rows
    .map((r) => ({
      ticker: r.ticker,
      value_pct: Math.round(r.value_pct * 10) / 10,
      risk_pct: totalRisk > 0 ? Math.round((r.raw_risk / totalRisk) * 1000) / 10 : 0,
      risk_ratio: r.value_pct > 0 && totalRisk > 0
        ? Math.round(((r.raw_risk / totalRisk * 100) / r.value_pct) * 100) / 100
        : 0,
    }))
    .sort((a, b) => b.risk_pct - a.risk_pct);
}

function recomputeStress(
  originalStress: StressTest[],
  originalPcts: Record<string, number>,
  adjustedPcts: Record<string, number>,
): StressTest[] {
  // Scale portfolio impact proportionally to total weight shift
  const origTotal = Object.values(originalPcts).reduce((s, v) => s + v, 0);
  const adjTotal = Object.values(adjustedPcts).reduce((s, v) => s + v, 0);
  if (origTotal <= 0 || adjTotal <= 0) return originalStress;

  // Weighted shift factor (heavier positions = more impact change)
  return originalStress.map((s) => {
    // Simple: stress impact scales with portfolio composition
    // More tech = worse in dot-com, better in COVID, etc.
    const scaleFactor = adjTotal / origTotal;
    return {
      ...s,
      portfolio_impact_pct: Math.round(s.portfolio_impact_pct * scaleFactor * 10) / 10,
    };
  });
}

/* ─── Main hook ─── */
export function usePortfolioWhatIf(
  holdings: HoldingRow[],
  originalMctr: MCTRPosition[],
  originalStress: StressTest[],
  originalSubScores: SubScores | undefined,
  sectorExposure: { sector: string; pct: number }[],
  corrMatrix?: Record<string, Record<string, number>>,
): WhatIfResult {
  const validHoldings = useMemo(
    () => holdings.filter((h) => h.pct != null && h.pct > 0).sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0)),
    [holdings],
  );

  // Consolidate duplicate tickers (multi-account portfolios)
  const originalPcts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const h of validHoldings) {
      m[h.ticker] = (m[h.ticker] ?? 0) + (h.pct ?? 0);
    }
    return m;
  }, [validHoldings]);

  // Unique tickers for correlation/factor computations
  const uniqueTickers = useMemo(() => {
    const seen: Record<string, boolean> = {};
    return validHoldings.filter((h) => {
      if (seen[h.ticker]) return false;
      seen[h.ticker] = true;
      return true;
    }).map((h) => h.ticker);
  }, [validHoldings]);

  const [adjustments, setAdjustments] = useState<Record<string, number>>({});

  const setAdjustedPct = useCallback((ticker: string, pct: number) => {
    setAdjustments((prev) => ({ ...prev, [ticker]: Math.max(0, Math.min(100, pct)) }));
  }, []);

  const reset = useCallback(() => setAdjustments({}), []);

  const isDirty = Object.keys(adjustments).length > 0;

  const adjustedPcts = useMemo(() => {
    const m = { ...originalPcts };
    for (const [t, p] of Object.entries(adjustments)) {
      m[t] = p;
    }
    return m;
  }, [originalPcts, adjustments]);

  // Recompute everything
  const result = useMemo(() => {
    // Use consolidated pcts for portfolio-level scoring
    const consolidatedPcts = uniqueTickers.map((t) => adjustedPcts[t] ?? 0);
    const sectorPcts = sectorExposure.map((s) => s.pct);

    // For regime alignment, pick best regime/signal per consolidated ticker
    const consolidatedRegimes = uniqueTickers.map((t) => {
      const h = validHoldings.find((hh) => hh.ticker === t);
      return h?.regime ?? null;
    });
    const consolidatedSignals = uniqueTickers.map((t) => {
      const h = validHoldings.find((hh) => hh.ticker === t);
      return h?.action || h?.suggestion || "";
    });

    // Sub-scores (use consolidated data)
    const concentration = computeConcentrationScore(consolidatedPcts, sectorPcts);
    const correlation = computeCorrelationScore(consolidatedPcts, uniqueTickers, corrMatrix);
    const regime_alignment = computeRegimeAlignmentScore(consolidatedPcts, consolidatedRegimes, consolidatedSignals);
    const drawdown_risk = originalSubScores?.drawdown_risk ?? 75;
    const tax_efficiency = originalSubScores?.tax_efficiency ?? 80;

    const subScores: SubScores = {
      concentration: Math.round(concentration),
      correlation: Math.round(correlation),
      regime_alignment: Math.round(regime_alignment),
      drawdown_risk: Math.round(drawdown_risk),
      tax_efficiency: Math.round(tax_efficiency),
    };

    // Weighted health score (same weights as backend)
    const weights = { concentration: 0.25, correlation: 0.20, regime_alignment: 0.25, drawdown_risk: 0.15, tax_efficiency: 0.15 };
    const totalW = Object.values(weights).reduce((s, w) => s + w, 0);
    const healthScore = Math.round(
      Object.entries(weights).reduce((s, [k, w]) => s + subScores[k as keyof SubScores] * w, 0) / totalW,
    );

    // MCTR
    const mctrRows = recomputeMCTR(originalMctr, adjustedPcts);

    // Stress
    const stress = isDirty
      ? recomputeStress(originalStress, originalPcts, adjustedPcts)
      : originalStress;

    // Effective positions (risk-based HHI)
    const totalRisk = mctrRows.reduce((s, p) => s + p.risk_pct, 0);
    const riskHhi = totalRisk > 0
      ? mctrRows.reduce((s, p) => s + (p.risk_pct / totalRisk) ** 2, 0)
      : 1;
    const effectivePositions = riskHhi > 0 ? Math.round((1 / riskHhi) * 10) / 10 : uniqueTickers.length;

    // Top sector (recalculate from adjusted weights would need per-holding sector — approximate)
    const topSectorName = sectorExposure[0]?.sector ?? "";
    const topSectorPct = sectorExposure[0]?.pct ?? 0;

    // Build deduplicated rows (one per ticker, consolidated from multi-account)
    const seenTickers: Record<string, boolean> = {};
    const rows: WhatIfRow[] = [];
    for (const h of validHoldings) {
      if (seenTickers[h.ticker]) continue;
      seenTickers[h.ticker] = true;
      const mctrEntry = mctrRows.find((m) => m.ticker === h.ticker);
      rows.push({
        ticker: h.ticker,
        originalPct: originalPcts[h.ticker] ?? 0,
        adjustedPct: adjustedPcts[h.ticker] ?? 0,
        regime: h.regime,
        signal: h.action || h.suggestion || "",
        mctrPct: mctrEntry?.risk_pct ?? 0,
      });
    }

    return {
      rows,
      healthScore,
      subScores,
      stressTests: stress,
      effectivePositions,
      topSectorPct,
      topSectorName,
      isDirty,
      setAdjustedPct,
      reset,
    };
  }, [validHoldings, uniqueTickers, adjustedPcts, originalMctr, originalStress, originalSubScores, sectorExposure, corrMatrix, isDirty, originalPcts, setAdjustedPct, reset]);

  return result;
}
