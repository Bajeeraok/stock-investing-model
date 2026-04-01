/**
 * Single source of truth for live vs backtest wording (MR buckets, composite, schema).
 * Import these in dashboard components so copy stays aligned with backend score.interpretation.
 */

/** Live signal card: raw composite; MR only flips how thresholds map when ACF says mean-reverting. */
export const LIVE_SCORE_LINE =
  "Live confidence uses the raw composite; when the tape is classified mean-reverting (ACF), buy/sell mapping can invert per score.interpretation — same interpretation rule as backtest buckets when apply_to_backtest_buckets is on.";

/** Backtest bucket table — first help bullet (paired with INTERPRETATION_BULLETS in BacktestStatus). */
export const BACKTEST_BUCKET_SCORE_HELP =
  "0–30 = weak through 70–100 = strong when buckets use raw momentum. On mean-reverting tape (ACF), buckets use 100−score so labels match dip-buy vs chase — aligns with live score.interpretation when MR is on.";

/** Schema badge explanation (short). */
export const SCHEMA_V2_NOTE =
  "Schema v2: MR-aware bucket assignment + validation rules; bucket rows show % MR vs trending (raw).";

export const INTERPRETATION_BULLETS = [
  { label: "Model (score bucket)", text: BACKTEST_BUCKET_SCORE_HELP },
  {
    label: "Sample size (N)",
    text: "Number of signals in that bucket for that horizon. Small N = less reliable; prefer buckets with N ≥ 30.",
  },
  {
    label: "Actual 1m / 3m / 6m",
    text: "Average % return over the next ~21 / 63 / 126 trading days when the model was in that bucket. For dip sizing, prefer 6m over 3m — dips often need more time to work.",
  },
  {
    label: "Avg return %",
    text: "Mean forward return. Positive = gains on average; negative = losses on average. Interpret with MoE and hit rate.",
  },
  {
    label: "Margin of error (±%)",
    text: "95% confidence interval around the avg return. Smaller MoE = more reliable estimate. MoE does NOT mean hit rate—you can have low MoE + negative return + low hit rate (confident the bucket underperforms).",
  },
  {
    label: "Hit rate",
    text: "% of forward periods with positive return (gain > 0). 60% hit = 6 of 10 periods gained. Not a confidence %—it measures how often gains occurred, not how sure we are.",
  },
  {
    label: "Momentum vs dip (two ideas)",
    text: "Trend-following check: raw high buckets should beat raw low. Dip-entry check: when MR buckets are on, compare dip column (70–100) vs momentum column (0–30) at 6m — same MR semantics as live when interpretation applies.",
  },
  {
    label: "How to read (simple)",
    text: "Use live composite + interpretation for entries. Use this table to sanity-check history — not as a single pass/fail number. One bad stretch or one great year does not define the whole process.",
  },
] as const;
