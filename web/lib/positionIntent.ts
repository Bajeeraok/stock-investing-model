export type PositionIntent = "trade" | "invest";

const STORAGE_KEY = "thrive-position-intent";

function readMap(): Record<string, PositionIntent> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, PositionIntent>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeMap(map: Record<string, PositionIntent>): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* ignore */
  }
}

export function getPositionIntent(ticker: string): PositionIntent | null {
  const t = (ticker || "").toUpperCase();
  return readMap()[t] ?? null;
}

export function setPositionIntent(ticker: string, intent: PositionIntent | null): void {
  const t = (ticker || "").toUpperCase();
  const map = readMap();
  if (intent == null) {
    delete map[t];
  } else {
    map[t] = intent;
  }
  writeMap(map);
}

export function intentGateHint(intent: PositionIntent | null): string {
  if (intent === "trade") {
    return "Trade intent — short-term gates and ST band matter most for sizing.";
  }
  if (intent === "invest") {
    return "Invest intent — long-term fair value, tiers, and structural stop dominate.";
  }
  return "Set trade vs invest intent to tune which gates we emphasize.";
}

export function intentLabel(intent: PositionIntent): string {
  return intent === "trade" ? "Trade" : "Invest";
}
