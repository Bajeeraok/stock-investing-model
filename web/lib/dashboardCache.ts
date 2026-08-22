/** Client-side stale-while-revalidate cache for instant dashboard paint. */
import type { DashboardData } from "@/app/page";

export const DASHBOARD_CACHE_KEY = "thrive-dashboard-v2";

/** Drop localStorage shells older than this so overnight tabs don't keep Aug‑20 forever. */
const CACHE_MAX_AGE_MS = 6 * 60 * 60 * 1000;

function _freshnessMs(data: DashboardData): number | null {
  const iso =
    data?.data_freshness?.signals_updated_at ||
    data?.data_freshness?.quotes_updated_at ||
    data?.data_freshness?.snapshot_updated_at ||
    null;
  if (!iso || typeof iso !== "string") return null;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : null;
}

export function loadCachedDashboard(): DashboardData | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(DASHBOARD_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DashboardData;
    if (!parsed || typeof parsed !== "object") return null;
    const ts = _freshnessMs(parsed);
    if (ts != null && Date.now() - ts > CACHE_MAX_AGE_MS) {
      localStorage.removeItem(DASHBOARD_CACHE_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function saveCachedDashboard(data: DashboardData): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(DASHBOARD_CACHE_KEY, JSON.stringify(data));
  } catch {
    // quota or private mode
  }
}

export function mergeDashboardData(
  base: DashboardData,
  patch: Partial<DashboardData>
): DashboardData {
  const merged: DashboardData = { ...base, ...patch };
  // Prefer the patch's freshness wholesale when present — never keep an older
  // signals_updated_at / eod_snapshot_latest_date from localStorage.
  if (patch.data_freshness && typeof patch.data_freshness === "object") {
    merged.data_freshness = { ...(base.data_freshness ?? {}), ...patch.data_freshness };
  }
  if (patch.eod_snapshot_latest_date != null) {
    merged.eod_snapshot_latest_date = patch.eod_snapshot_latest_date;
  }
  if (Array.isArray(patch.eod_snapshots)) {
    merged.eod_snapshots = patch.eod_snapshots;
  }
  // Explicitly clear transient refresh flags when server says data is fresh.
  if (patch.stale === false) {
    merged.stale = false;
    merged.refresh_coalesced = false;
    merged.warming = false;
    if (patch.refresh_status === "idle" || patch.refresh_status === "done" || !patch.refresh_status) {
      merged.refresh_status = patch.refresh_status ?? "idle";
    }
    if (merged.data_freshness && typeof merged.data_freshness === "object") {
      merged.data_freshness = { ...merged.data_freshness, serving_stale: false };
    }
  }
  return merged;
}

/** Parse ISO snapshot timestamp for staleness display. */
export function parseSnapshotDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatSnapshotAge(iso: string | null | undefined, nowMs = Date.now()): string {
  const d = parseSnapshotDate(iso);
  if (!d) return "";
  const sec = Math.floor((nowMs - d.getTime()) / 1000);
  if (sec < 0) return "just now";
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} min ago`;
  const h = Math.floor(min / 60);
  if (h < 48) return `${h}h ago`;
  const days = Math.floor(h / 24);
  return `${days}d ago`;
}

export function formatSnapshotEt(iso: string | null | undefined): string {
  const d = parseSnapshotDate(iso);
  if (!d) return iso ?? "—";
  return (
    d.toLocaleString("en-US", {
      timeZone: "America/New_York",
      dateStyle: "short",
      timeStyle: "short",
    }) + " ET"
  );
}

export function snapshotAgeTone(iso: string | null | undefined, nowMs = Date.now()): "fresh" | "aging" | "stale" {
  const d = parseSnapshotDate(iso);
  if (!d) return "stale";
  const min = (nowMs - d.getTime()) / 60000;
  if (min <= 30) return "fresh";
  if (min <= 180) return "aging";
  return "stale";
}
