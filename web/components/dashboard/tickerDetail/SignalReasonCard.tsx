export type SignalReasonFactor = {
  id?: string;
  label: string;
  category?: string;
  stance?: "helps" | "hurts" | "neutral";
  weight_pct?: number;
  score_pct?: number | null;
  summary?: string;
};

/** signals.pattern_signals.near_bottom_score — surfaced instead of discarded. */
export type NearBottomSignal = {
  score?: number;
  mode?: "bottom_reversal" | "trend_continuation";
  signals?: string[];
};

/** signals.price_move_narrative — rule-based "why did this move" classification. */
export type MoveNarrative = {
  driver?: "stock_specific" | "broad_market" | "earnings" | "unclear";
  headline?: string;
  detail?: string | null;
  citation?: string | null;
  day_change_pct?: number | null;
  spy_day_change_pct?: number | null;
};

export type SignalReasonPayload = {
  persona?: "scout" | "swing" | "owner";
  headline?: string;
  wait_plain?: string | null;
  factors?: SignalReasonFactor[];
  supporting?: string[];
  blocking?: string[];
  top_driver?: string | null;
  top_blocker?: string | null;
  near_bottom?: NearBottomSignal | null;
  move_narrative?: MoveNarrative | null;
};

/** One signal_reason per persona — same gates, different framing/time-horizon. */
export type SignalReasonByPersona = {
  scout: SignalReasonPayload;
  swing: SignalReasonPayload;
  owner: SignalReasonPayload;
};
