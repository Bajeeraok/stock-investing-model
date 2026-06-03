/** Backend investor_summary.valuation_deck */
export interface AnalystRatingDistribution {
  strong_buy: number;
  buy: number;
  hold: number;
  sell: number;
  strong_sell: number;
  total: number;
  bullish_pct?: number;
  source: string;
}

export interface ValuationDeckPayload {
  street?: {
    primary_usd?: number | null;
    primary_label?: string | null;
    median_usd?: number | null;
    low_usd?: number | null;
    high_usd?: number | null;
    median_return_pct?: number | null;
    high_return_pct?: number | null;
    low_return_pct?: number | null;
    analyst_count?: number | null;
    yahoo_mean_usd?: number | null;
    ratings?: AnalystRatingDistribution | null;
    eps_fwd?: number | null;
    eps_dispersion?: number | null;
  };
  model?: {
    fair_value_usd?: number | null;
    pct_vs_street_primary?: number | null;
    gap_badge?: "ok" | "review" | "caution" | null;
    method_used?: string | null;
    methodology_summary?: string | null;
    relative_valuation_line?: string | null;
    ttm_pe?: number | null;
    forward_pe?: number | null;
    sector_pe_reference?: number | null;
  };
  house?: {
    active_tier_id?: string | null;
    assessment_label?: string | null;
    min_price_to_buy?: number | null;
    above_full_mos_ceiling?: boolean | null;
    margin_of_safety_pct?: number | null;
    tiers_summary?: {
      id?: string;
      label?: string;
      low?: number;
      high?: number;
      allocation_pct?: number;
    }[];
  };
  scout_street_alert?: boolean;
  disclaimer?: string;
}
