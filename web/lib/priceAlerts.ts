/**
 * Per-viewer price alerts ("Alert me at $X" on the ticker Verdict tab).
 *
 * Stored in localStorage — there is no server-side price-alert store yet. Alerts are
 * checked against the dashboard's live-price poll (LivePricesProvider, ~60s) by
 * PriceAlertWatcher, so they only fire while the app is open. Direction is fixed at
 * creation time from where price sat relative to the level ("below" = fire when price
 * drops to or under it).
 */

export type PriceAlert = {
  id: string;
  ticker: string;
  price: number;
  direction: "below" | "above";
  createdAt: string;
  /** ISO timestamp once triggered; triggered alerts stay listed until removed. */
  triggeredAt?: string | null;
  triggeredPrice?: number | null;
};

const STORAGE_KEY = "thrive-price-alerts";
const CHANGE_EVENT = "thrive-price-alerts-changed";

export function listPriceAlerts(): PriceAlert[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as PriceAlert[]) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeAll(alerts: PriceAlert[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
  } catch {
    /* ignore — private mode / quota */
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function addPriceAlert(ticker: string, price: number, currentPrice: number | null | undefined): PriceAlert {
  const t = ticker.toUpperCase();
  const alert: PriceAlert = {
    id: `${t}-${price.toFixed(2)}-${Date.now()}`,
    ticker: t,
    price,
    direction: currentPrice != null && currentPrice < price ? "above" : "below",
    createdAt: new Date().toISOString(),
    triggeredAt: null,
  };
  // One active alert per ticker+level — re-adding the same level replaces it.
  const rest = listPriceAlerts().filter((a) => !(a.ticker === t && Math.abs(a.price - price) < 0.005));
  writeAll([...rest, alert]);
  return alert;
}

export function removePriceAlert(id: string): void {
  writeAll(listPriceAlerts().filter((a) => a.id !== id));
}

export function markPriceAlertTriggered(id: string, price: number): void {
  writeAll(
    listPriceAlerts().map((a) =>
      a.id === id ? { ...a, triggeredAt: new Date().toISOString(), triggeredPrice: price } : a,
    ),
  );
}

export function activeAlertForTicker(ticker: string): PriceAlert | null {
  const t = ticker.toUpperCase();
  return listPriceAlerts().find((a) => a.ticker === t && !a.triggeredAt) ?? null;
}

/** Subscribe to changes from this tab (custom event) and other tabs (storage event). */
export function subscribePriceAlerts(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) cb();
  };
  window.addEventListener(CHANGE_EVENT, cb);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, cb);
    window.removeEventListener("storage", onStorage);
  };
}

export function alertCrossed(alert: PriceAlert, price: number): boolean {
  return alert.direction === "below" ? price <= alert.price : price >= alert.price;
}
