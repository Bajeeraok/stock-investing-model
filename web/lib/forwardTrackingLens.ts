import type { TradingLens } from "./tradingLens";

export type LensHorizonRow = {
  horizon_days?: number;
  win_rate_pct?: number;
  avg_return_pct?: number;
  n_observations?: number;
  st_target_hit_rate_pct?: number;
};

export type LensForwardSummary = {
  primary_horizon_days?: number;
  primary?: LensHorizonRow | null;
  horizons?: LensHorizonRow[];
  add_20d?: {
    hit_rate_pct?: number;
    n_observations?: number;
    avg_return_pct?: number;
  } | null;
  label?: string | null;
};

export type SummaryByLens = Partial<Record<TradingLens, LensForwardSummary>>;

export function lensForwardLine(
  lens: TradingLens,
  summaryByLens: SummaryByLens | null | undefined,
): string | null {
  const row = summaryByLens?.[lens];
  if (row?.label) return row.label;
  const p = row?.primary;
  if (p?.win_rate_pct != null && p.n_observations) {
    const h = row?.primary_horizon_days ?? "?";
    return `${h}d win ${p.win_rate_pct.toFixed(0)}% (n=${p.n_observations})`;
  }
  return null;
}
