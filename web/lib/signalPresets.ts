/** Shared signal list presets (Signals tab + Roadmaps tab). */

import type { TradingLens } from "./tradingLens";
import { defaultPresetForLens } from "./tradingLens";

export type SignalsPresetId = "all" | "pullback_buys" | "trim_candidates" | "earnings_week";

export const SIGNALS_PRESET_STORAGE_KEY = "thrive-signals-preset";

export const SIGNAL_PRESETS: { id: SignalsPresetId; label: string; hint: string; lens?: TradingLens }[] = [
  { id: "all", label: "All signals", hint: "No action/regime filter" },
  {
    id: "pullback_buys",
    label: "Tactical setups",
    hint: "UP regime · RSI < 50 · score ≥ 55 — Scout-friendly",
    lens: "scout",
  },
  {
    id: "trim_candidates",
    label: "Core trim",
    hint: "Score < 40 or REDUCE/AVOID — Owner / steward",
    lens: "owner",
  },
  {
    id: "earnings_week",
    label: "Earnings week",
    hint: "Report within 7 days or caution window — Swing",
    lens: "swing",
  },
];

/** Presets ordered with lens-default first. */
export function presetsForLens(lens: TradingLens): typeof SIGNAL_PRESETS {
  const def = defaultPresetForLens(lens);
  const rest = SIGNAL_PRESETS.filter((p) => p.id !== def);
  const primary = SIGNAL_PRESETS.find((p) => p.id === def);
  return primary ? [primary, ...rest] : SIGNAL_PRESETS;
}

export function loadSignalsPreset(): SignalsPresetId {
  try {
    const raw = typeof window !== "undefined" ? localStorage.getItem(SIGNALS_PRESET_STORAGE_KEY) : null;
    if (raw === "all" || raw === "pullback_buys" || raw === "trim_candidates" || raw === "earnings_week") {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return "all";
}

export function saveSignalsPreset(id: SignalsPresetId): void {
  try {
    localStorage.setItem(SIGNALS_PRESET_STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}

/** Minimal signal shape for preset matching. */
export interface SignalPresetRow {
  ticker?: string;
  regime?: string | null;
  rsi?: number | null;
  confluence_score?: number | null;
  composite_buy?: number | null;
  signal?: string | null;
  earnings_caution?: boolean | null;
  earnings_days_until?: number | null;
}

export function matchesSignalPreset(signal: SignalPresetRow, preset: SignalsPresetId): boolean {
  if (preset === "all") return true;
  const score = signal.confluence_score ?? signal.composite_buy ?? 0;
  const sig = (signal.signal ?? "").toUpperCase();
  if (preset === "pullback_buys") {
    return signal.regime === "UP" && (signal.rsi ?? 100) < 50 && score >= 55;
  }
  if (preset === "trim_candidates") {
    return score < 40 || sig === "REDUCE" || sig === "AVOID" || sig === "SELL";
  }
  if (preset === "earnings_week") {
    return Boolean(signal.earnings_caution) || (signal.earnings_days_until != null && signal.earnings_days_until <= 7);
  }
  return true;
}

export function filterTickersByPreset(
  tickers: string[],
  preset: SignalsPresetId,
  signalByTicker: Map<string, SignalPresetRow>,
): string[] {
  if (preset === "all") return tickers;
  return tickers.filter((t) => {
    const row = signalByTicker.get(String(t).toUpperCase());
    return row ? matchesSignalPreset(row, preset) : false;
  });
}
