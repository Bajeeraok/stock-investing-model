/** Buy vs sell / trim classification for scanner alerts. */

export type AlertSide = "buy" | "sell" | "watch";

export type AlertSideFilter = "all" | "buy" | "sell";

const STORAGE_KEY = "thrive_alert_side_filter_v1";

const BUY_TYPES = new Set([
  "ENTRY_ZONE_ENTERED",
  "SETUP_ALMOST_READY",
  "ML_PROB_CROSSED",
  "RSI_OVERSOLD",
  "MACRO_RISK_ON",
  "MOMENTUM_BREAKOUT",
  "SUPPORT_BOUNCE",
  "TACTICAL_VELOCITY",
  "PROTECT_MODE_OFF",
]);

const SELL_TYPES = new Set([
  "STOP_HIT",
  "STOP_APPROACHING",
  "TARGET_HIT",
  "TARGET_APPROACHING",
  "KELLY_REDUCTION",
  "MACRO_RISK_OFF",
  "REGIME_CHANGE",
  "PROTECT_MODE_ON",
]);

export function loadAlertSideFilter(): AlertSideFilter {
  if (typeof window === "undefined") return "all";
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "buy" || raw === "sell" || raw === "all") return raw;
  } catch {
    /* ignore */
  }
  return "all";
}

export function saveAlertSideFilter(filter: AlertSideFilter): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, filter);
  } catch {
    /* ignore */
  }
}

export function alertSideFromAlert(alert: {
  type?: string;
  headline?: string;
  signals?: Record<string, unknown>;
}): AlertSide {
  const sigSide = String(alert.signals?.side ?? alert.signals?.alert_side ?? "").toLowerCase();
  if (sigSide === "buy" || sigSide === "add") return "buy";
  if (sigSide === "sell" || sigSide === "trim" || sigSide === "exit") return "sell";

  const t = String(alert.type || "")
    .toUpperCase()
    .replace(/\s+/g, "_");
  if (BUY_TYPES.has(t)) return "buy";
  if (SELL_TYPES.has(t)) return "sell";

  const hl = String(alert.headline || "").toLowerCase();
  if (/stop hit|stop approaching|trim|target hit|take profit|reduce size|risk.?off/.test(hl)) {
    return "sell";
  }
  if (/buy zone|entry zone|almost ready|oversold|breakout|velocity|risk.?on/.test(hl)) {
    return "buy";
  }

  return "watch";
}

export function alertMatchesSideFilter(
  alert: { type?: string; headline?: string; signals?: Record<string, unknown> },
  filter: AlertSideFilter,
): boolean {
  if (filter === "all") return true;
  const side = alertSideFromAlert(alert);
  if (filter === "buy") return side === "buy";
  if (filter === "sell") return side === "sell";
  return true;
}

export function sideFilterLabel(filter: AlertSideFilter): string {
  if (filter === "buy") return "Buy / Add";
  if (filter === "sell") return "Sell / Trim";
  return "All signals";
}
