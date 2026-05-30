export type AlertTrackFilter = "accumulate" | "tactical";

const STORAGE_KEY = "thrive_alert_tracks_v1";

export type AlertTrackPrefs = {
  accumulate: boolean;
  tactical: boolean;
};

const DEFAULT_PREFS: AlertTrackPrefs = {
  accumulate: true,
  tactical: true,
};

export function loadAlertTrackPrefs(): AlertTrackPrefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<AlertTrackPrefs>;
    return {
      accumulate: parsed.accumulate !== false,
      tactical: parsed.tactical !== false,
    };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function saveAlertTrackPrefs(prefs: AlertTrackPrefs): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}

const ACCUMULATE_ALERT_TYPES = new Set([
  "ENTRY_ZONE_ENTERED",
  "STOP_HIT",
  "STOP_APPROACHING",
  "TARGET_HIT",
  "TARGET_APPROACHING",
  "ML_PROB_CROSSED",
  "SETUP_ALMOST_READY",
]);

const TACTICAL_ALERT_TYPES = new Set([
  "EARNINGS_SOON",
  "MOMENTUM_BREAKOUT",
  "SUPPORT_BOUNCE",
  "ER_LOTTO",
  "ER_IV_CRUSH",
  "COVERED_CALL",
  "CREDIT_SPREAD",
  "OPTIONS_FLOW_SPIKE",
  "TACTICAL_VELOCITY",
]);

const MACRO_ALERT_TYPES = new Set([
  "MACRO_RISK_OFF",
  "MACRO_RISK_ON",
  "REGIME_CHANGE",
  "KELLY_REDUCTION",
]);

export function alertTrackFromSignals(
  signals?: Record<string, unknown>,
  alertType?: string,
): AlertTrackFilter | "macro" {
  const track = signals?.track;
  if (track === "tactical" || track === "accumulate" || track === "macro") {
    return track;
  }
  const t = String(alertType || "")
    .toUpperCase()
    .replace(/\s+/g, "_");
  if (MACRO_ALERT_TYPES.has(t)) return "macro";
  if (TACTICAL_ALERT_TYPES.has(t)) return "tactical";
  if (ACCUMULATE_ALERT_TYPES.has(t)) return "accumulate";
  return "accumulate";
}

export function alertMatchesTrackPrefs(
  alert: { type?: string; signals?: Record<string, unknown> },
  prefs: AlertTrackPrefs,
): boolean {
  const track = alertTrackFromSignals(alert.signals, alert.type);
  if (track === "macro") return true;
  if (track === "tactical") return prefs.tactical;
  return prefs.accumulate;
}
