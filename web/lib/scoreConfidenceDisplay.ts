/**
 * Composite score (chart rules) vs 7-layer model confidence — keep separate in UI.
 */

export const SCORE_BULL = 65;
export const SCORE_BEAR = 35;
export const CONF_ADD = 70;
export const CONF_TRIM = 40;
export const MISMATCH_SCORE_HIGH = 65;
export const MISMATCH_CONF_LOW = 55;
export const MISMATCH_SCORE_LOW = 35;
export const MISMATCH_CONF_HIGH = 55;

export function scoreTileClass(score: number | null | undefined): string {
  if (score == null) return "bg-slate-700/80 border-slate-600 text-slate-300";
  if (score >= SCORE_BULL) return "bg-emerald-600/35 border-emerald-500/45 text-emerald-100";
  if (score <= SCORE_BEAR) return "bg-red-600/30 border-red-500/40 text-red-100";
  return "bg-slate-600/40 border-slate-500/40 text-slate-200";
}

export function confidenceRingClass(confidence: number | null | undefined): string {
  if (confidence == null) return "ring-1 ring-slate-600/50 ring-dashed";
  if (confidence >= CONF_ADD) return "ring-2 ring-emerald-400/70";
  if (confidence >= CONF_TRIM) return "ring-2 ring-amber-400/55";
  return "ring-2 ring-dashed ring-slate-500/60";
}

export function confidenceTextClass(confidence: number | null | undefined): string {
  if (confidence == null) return "text-slate-500";
  if (confidence >= CONF_ADD) return "text-emerald-400";
  if (confidence > CONF_TRIM) return "text-slate-300";
  return "text-red-400";
}

export function isScoreConfidenceMismatch(
  score: number | null | undefined,
  confidence: number | null | undefined,
): boolean {
  if (score == null || confidence == null) return false;
  return (
    (score >= MISMATCH_SCORE_HIGH && confidence < MISMATCH_CONF_LOW) ||
    (score <= MISMATCH_SCORE_LOW && confidence >= MISMATCH_CONF_HIGH)
  );
}

export function mismatchHint(
  score: number | null | undefined,
  confidence: number | null | undefined,
): string | null {
  if (!isScoreConfidenceMismatch(score, confidence) || score == null || confidence == null) {
    return null;
  }
  if (score >= MISMATCH_SCORE_HIGH && confidence < MISMATCH_CONF_LOW) {
    return "Strong chart score, lower model confidence — size carefully.";
  }
  if (score <= MISMATCH_SCORE_LOW && confidence >= MISMATCH_CONF_HIGH) {
    return "Weak chart score; model confidence still moderate — review trim vs add context.";
  }
  return null;
}

export function countScoreConfidenceMismatches(
  items: Array<{ score?: number | null; confidence?: number | null }>,
): number {
  return items.filter((h) => isScoreConfidenceMismatch(h.score, h.confidence)).length;
}

export function avgConfidence(
  items: Array<{ confidence?: number | null }>,
): number | null {
  const vals = items.map((h) => h.confidence).filter((c): c is number => c != null && !Number.isNaN(c));
  if (!vals.length) return null;
  return Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10;
}

export function fmtScore(score: number | null | undefined): string {
  return score != null ? String(Math.round(score)) : "—";
}

export function fmtConfidence(confidence: number | null | undefined): string {
  return confidence != null ? `${Math.round(confidence)}%` : "—";
}
