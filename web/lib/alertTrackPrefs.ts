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

export function alertTrackFromSignals(signals?: Record<string, unknown>): AlertTrackFilter | "macro" {
  const track = signals?.track;
  if (track === "tactical" || track === "accumulate" || track === "macro") {
    return track;
  }
  return "accumulate";
}

export function alertMatchesTrackPrefs(
  alert: { type?: string; signals?: Record<string, unknown> },
  prefs: AlertTrackPrefs,
): boolean {
  const track = alertTrackFromSignals(alert.signals);
  if (track === "macro") return true;
  if (track === "tactical") return prefs.tactical;
  return prefs.accumulate;
}
