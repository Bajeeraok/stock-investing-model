/** How the user is thinking about this ticker — drives Today tab hero + primary horizon. */
export type DecisionMode = "scout" | "swing" | "owner";

import type { PositionIntent } from "./positionIntent";

const STORAGE_KEY = "thrive-decision-mode";

function readMap(): Record<string, DecisionMode> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, DecisionMode>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeMap(map: Record<string, DecisionMode>): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* ignore */
  }
}

export function getDecisionMode(ticker: string, intent?: PositionIntent | null): DecisionMode {
  const t = (ticker || "").toUpperCase();
  const stored = readMap()[t];
  if (stored === "scout" || stored === "swing" || stored === "owner") return stored;
  if (intent === "invest") return "owner";
  if (intent === "trade") return "scout";
  return "scout";
}

export function setDecisionMode(ticker: string, mode: DecisionMode): void {
  const t = (ticker || "").toUpperCase();
  const map = readMap();
  map[t] = mode;
  writeMap(map);
}

export function decisionModeLabel(mode: DecisionMode): string {
  if (mode === "scout") return "Scout";
  if (mode === "swing") return "Swing";
  return "Owner";
}

export function decisionModeHint(mode: DecisionMode): string {
  if (mode === "scout") return "Quick / tactical — short band, velocity, swing stop.";
  if (mode === "swing") return "Swing add — short + medium bands over weeks to months.";
  return "Long-term accumulate — tiers, thesis stop, margin of safety.";
}

export function primaryHorizonFromMode(mode: DecisionMode): "short" | "medium" | "long" {
  if (mode === "owner") return "long";
  if (mode === "swing") return "medium";
  return "short";
}

export function intentFromMode(mode: DecisionMode): PositionIntent | null {
  if (mode === "scout") return "trade";
  if (mode === "owner") return "invest";
  return null;
}

export function modeFromIntent(intent: PositionIntent | null): DecisionMode | null {
  if (intent === "trade") return "scout";
  if (intent === "invest") return "owner";
  return null;
}

export type HorizonKey = "short" | "medium" | "long";

export function horizonLabel(key: HorizonKey): string {
  if (key === "short") return "Short-term";
  if (key === "medium") return "Medium-term";
  return "Long-term";
}
