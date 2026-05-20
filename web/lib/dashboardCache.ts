/** Client-side stale-while-revalidate cache for instant dashboard paint. */
import type { DashboardData } from "@/app/page";

export const DASHBOARD_CACHE_KEY = "thrive-dashboard-v1";

export function loadCachedDashboard(): DashboardData | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(DASHBOARD_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DashboardData;
    if (!parsed || typeof parsed !== "object") return null;
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
  return { ...base, ...patch };
}
