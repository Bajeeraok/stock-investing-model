/**
 * App-wide trading lens (Phase A) — Scout / Swing / Owner.
 * Per-ticker mode in decisionMode.ts still applies inside the ticker modal.
 */
import type { DecisionMode } from "./decisionMode";
import type { SignalsPresetId } from "./signalPresets";

export type TradingLens = DecisionMode;

export const TRADING_LENS_STORAGE_KEY = "thrive-trading-lens";

export function getTradingLens(): TradingLens {
  if (typeof window === "undefined") return "scout";
  try {
    const raw = localStorage.getItem(TRADING_LENS_STORAGE_KEY);
    if (raw === "scout" || raw === "swing" || raw === "owner") return raw;
  } catch {
    /* ignore */
  }
  return "scout";
}

export function setTradingLens(lens: TradingLens): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(TRADING_LENS_STORAGE_KEY, lens);
  } catch {
    /* ignore */
  }
}

export function tradingLensLabel(lens: TradingLens): string {
  if (lens === "scout") return "Scout";
  if (lens === "swing") return "Swing";
  return "Owner";
}

export function tradingLensHint(lens: TradingLens): string {
  if (lens === "scout") return "Tactical — session tape, short bands, breakouts first.";
  if (lens === "swing") return "Swing — earnings, medium-term adds and trims.";
  return "Owner — book risk, long-term tiers, thesis discipline.";
}

export function primaryHorizonKey(lens: TradingLens): "short" | "medium" | "long" {
  if (lens === "owner") return "long";
  if (lens === "swing") return "medium";
  return "short";
}

/**
 * Default Signals tab preset when lens changes — the morning-login promise is "opportunities
 * for my time horizon," so this must resolve to a buy-side filter for every lens. Scout keeps
 * its own short-term-specific filter (UP regime + RSI reset); Swing/Owner previously defaulted
 * to "earnings_week"/"trim_candidates" — a caution list and a sell list, not opportunities.
 */
export function defaultPresetForLens(lens: TradingLens): SignalsPresetId {
  if (lens === "scout") return "pullback_buys";
  return "opportunities";
}

/** Order ST/MT/LT cards on Overview for visual emphasis. */
export function matrixHorizonOrder(lens: TradingLens): ("short_term" | "medium_term" | "long_term")[] {
  if (lens === "scout") return ["short_term", "medium_term", "long_term"];
  if (lens === "swing") return ["medium_term", "short_term", "long_term"];
  return ["long_term", "medium_term", "short_term"];
}
