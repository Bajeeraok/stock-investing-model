"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Bell, Check, ChevronDown, ChevronRight, RefreshCw, X } from "lucide-react";
import { clsx } from "clsx";
import {
  alertMatchesTrackPrefs,
  loadAlertTrackPrefs,
  saveAlertTrackPrefs,
  type AlertTrackPrefs,
} from "@/lib/alertTrackPrefs";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

/** US market scan window: 8:00–16:00 ET weekdays (matches backend scanner). */
function isScannerHours(): boolean {
  const now = new Date();
  const opts: Intl.DateTimeFormatOptions = {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
    weekday: "short",
  };
  const parts = new Intl.DateTimeFormat("en-US", opts).formatToParts(now);
  const weekday = parts.find((p) => p.type === "weekday")?.value ?? "";
  const hour = parseInt(parts.find((p) => p.type === "hour")?.value ?? "0", 10);
  const minute = parseInt(parts.find((p) => p.type === "minute")?.value ?? "0", 10);
  if (weekday === "Sat" || weekday === "Sun") return false;
  const total = hour * 60 + minute;
  return total >= 480 && total <= 960;
}

export interface ScanAlert {
  id: string;
  type: string;
  ticker?: string | null;
  priority: number; // 1..4
  headline: string;
  body: string;
  /** Plain-language entry / exit / duration (when present, show instead of body for actionable guidance) */
  actionable?: string | null;
  /** Compact quick-prediction line from backend */
  one_liner?: string | null;
  risk_level: string;
  color?: string;
  emoji?: string;
  timestamp: string;
  dismissed?: boolean;
  signals?: Record<string, unknown>;
}

type ViewMode = "action" | "all";

function prLabel(p: number): string {
  return p === 1 ? "CRITICAL" : p === 2 ? "HIGH" : p === 3 ? "MEDIUM" : "LOW";
}

function isActionRequired(p: number): boolean {
  return p === 1 || p === 2;
}

function sortAlerts(list: ScanAlert[]): ScanAlert[] {
  return [...list].sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority;
    const ta = a.timestamp || "";
    const tb = b.timestamp || "";
    if (ta !== tb) return tb.localeCompare(ta);
    return (a.ticker || "").localeCompare(b.ticker || "");
  });
}

function AlertCard({
  alert: a,
  onTickerClick,
  onDismiss,
}: {
  alert: ScanAlert;
  onTickerClick?: (ticker: string) => void;
  onDismiss: (id: string) => void;
}) {
  const buyZone =
    a.type === "ENTRY_ZONE_ENTERED" ||
    String(a.headline || "").toLowerCase().includes("buy zone");
  const almostReady = a.type === "SETUP_ALMOST_READY";

  return (
    <div className="rounded-lg border border-slate-700/60 bg-slate-950/30 px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm">{a.emoji || "🔔"}</span>
            {a.ticker ? (
              <button
                type="button"
                onClick={() => a.ticker && onTickerClick?.(a.ticker)}
                className="font-mono text-emerald-400 hover:underline text-sm"
              >
                {a.ticker}
              </button>
            ) : (
              <span className="font-mono text-slate-200 text-sm">MACRO</span>
            )}
            <span className="text-sm text-slate-200 font-semibold">{a.headline}</span>
            <span
              className={clsx(
                "text-[10px] px-2 py-0.5 rounded border shrink-0",
                a.priority === 1
                  ? "bg-red-500/15 text-red-300 border-red-500/30"
                  : a.priority === 2
                    ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                    : a.priority === 3
                      ? "bg-slate-600/20 text-slate-300 border-slate-600/40"
                      : "bg-slate-800/40 text-slate-500 border-slate-700/50",
              )}
            >
              {prLabel(a.priority)}
            </span>
            <span className="text-[10px] text-slate-500 shrink-0">{`Risk: ${a.risk_level}`}</span>
          </div>
          <p className="text-xs text-slate-400 mt-1 leading-snug">{a.actionable ?? a.body}</p>
          {buyZone && (
            <p className="text-[11px] text-violet-300/80 mt-1 leading-snug">
              Price in zone — open ticker detail and confirm GO/NO-GO gates before adding.
            </p>
          )}
          {almostReady && (
            <p className="text-[11px] text-amber-300/85 mt-1 leading-snug">
              Almost ready (3/4 gates + ST buy) — not full GO yet. Watch the last blocker; paper track still needs 4/4.
            </p>
          )}
          {a.one_liner && (
            <p className="text-[11px] text-emerald-300/90 mt-1 leading-snug">{a.one_liner}</p>
          )}
          {a.actionable && a.body && (
            <p className="text-[11px] text-slate-500 mt-1 leading-snug" title="Context">
              {a.body}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => onDismiss(a.id)}
          className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white shrink-0 touch-manipulation"
          title="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

function AlertGroup({
  title,
  subtitle,
  alerts,
  defaultOpen,
  onTickerClick,
  onDismiss,
}: {
  title: string;
  subtitle?: string;
  alerts: ScanAlert[];
  defaultOpen: boolean;
  onTickerClick?: (ticker: string) => void;
  onDismiss: (id: string) => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (!alerts.length) return null;

  return (
    <div className="rounded-lg border border-slate-700/50 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2.5 bg-slate-800/60 hover:bg-slate-800 text-left touch-manipulation"
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {open ? (
              <ChevronDown className="h-4 w-4 text-slate-500 shrink-0" />
            ) : (
              <ChevronRight className="h-4 w-4 text-slate-500 shrink-0" />
            )}
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-300">{title}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 tabular-nums">
              {alerts.length}
            </span>
          </div>
          {subtitle && <p className="text-[11px] text-slate-500 mt-0.5 ml-6">{subtitle}</p>}
        </div>
      </button>
      {open && (
        <div className="p-2 pt-0 space-y-2 border-t border-slate-700/40">
          {alerts.map((a) => (
            <AlertCard key={a.id} alert={a} onTickerClick={onTickerClick} onDismiss={onDismiss} />
          ))}
        </div>
      )}
    </div>
  );
}

export function AlertsPanel({
  onTickerClick,
  onLoaded,
}: {
  onTickerClick?: (ticker: string) => void;
  /** Total alerts + action-required (HIGH/CRITICAL) count for Overview badge. */
  onLoaded?: (total: number, actionRequired: number) => void;
}) {
  const [alerts, setAlerts] = useState<ScanAlert[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAt, setLastAt] = useState<Date | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("action");
  const [trackPrefs, setTrackPrefs] = useState<AlertTrackPrefs>(() => loadAlertTrackPrefs());
  const onLoadedRef = useRef(onLoaded);
  onLoadedRef.current = onLoaded;

  const base = useCallback((path: string) => (API_BASE ? `${API_BASE}${path}` : path), []);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(base("/api/scanner/alerts?limit=80"));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as ScanAlert[];
      const list = sortAlerts(Array.isArray(json) ? json : []);
      const actionRequired = list.filter((a) => isActionRequired(a.priority)).length;
      setAlerts(list);
      onLoadedRef.current?.(list.length, actionRequired);
      setLastAt(new Date());
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [base]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  useEffect(() => {
    const minutes = isScannerHours() ? 1 : 0;
    if (!minutes) return;
    const id = setInterval(fetchAlerts, minutes * 60 * 1000);
    return () => clearInterval(id);
  }, [fetchAlerts]);

  const dismiss = useCallback(
    async (id: string) => {
      try {
        await fetch(base(`/api/scanner/alerts/${id}/dismiss`), { method: "POST" });
      } catch {
        // ignore
      } finally {
        setAlerts((prev) => {
          const next = prev.filter((x) => x.id !== id);
          const actionRequired = next.filter((a) => isActionRequired(a.priority)).length;
          onLoadedRef.current?.(next.length, actionRequired);
          return next;
        });
      }
    },
    [base],
  );

  const visibleAlerts = useMemo(
    () => alerts.filter((a) => alertMatchesTrackPrefs(a, trackPrefs)),
    [alerts, trackPrefs],
  );

  const updateTrackPref = useCallback((key: keyof AlertTrackPrefs, value: boolean) => {
    setTrackPrefs((prev) => {
      const next = { ...prev, [key]: value };
      saveAlertTrackPrefs(next);
      return next;
    });
  }, []);

  useEffect(() => {
    const actionRequired = visibleAlerts.filter((a) => isActionRequired(a.priority)).length;
    onLoadedRef.current?.(visibleAlerts.length, actionRequired);
  }, [visibleAlerts]);

  const grouped = useMemo(() => {
    const critical = sortAlerts(visibleAlerts.filter((a) => a.priority === 1));
    const high = sortAlerts(visibleAlerts.filter((a) => a.priority === 2));
    const medium = sortAlerts(visibleAlerts.filter((a) => a.priority === 3));
    const low = sortAlerts(visibleAlerts.filter((a) => a.priority >= 4));
    const actionRequired = sortAlerts([...critical, ...high]);
    return { critical, high, medium, low, actionRequired };
  }, [visibleAlerts]);

  const headerNote = useMemo(() => {
    const hrs = isScannerHours();
    if (!hrs) return "Scanner idle outside 8:00–16:00 ET weekdays (manual refresh works).";
    return "Auto-refreshing during scan hours (1m).";
  }, []);

  const actionCount = grouped.actionRequired.length;
  const watchCount = grouped.medium.length + grouped.low.length;

  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Bell className="h-4 w-4 text-emerald-400 shrink-0" />
            <h3 className="text-sm font-semibold text-slate-200">Alerts</h3>
            {actionCount > 0 ? (
              <span className="text-xs text-amber-300 font-medium tabular-nums">{actionCount} action</span>
            ) : null}
            {watchCount > 0 && (
              <span className="text-xs text-slate-500 tabular-nums">{watchCount} watch soon</span>
            )}
            <span className="text-xs text-slate-600 tabular-nums">({visibleAlerts.length} shown)</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1">{headerNote}</p>
        </div>
        <button
          type="button"
          onClick={fetchAlerts}
          className={clsx(
            "flex items-center gap-2 px-3 py-2 rounded-lg border text-xs shrink-0 touch-manipulation",
            "border-slate-600 text-slate-300 hover:bg-slate-800 disabled:opacity-50",
          )}
          disabled={loading}
          title="Refresh alerts"
        >
          <RefreshCw className={clsx("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-[10px] uppercase tracking-wide text-slate-500 shrink-0">Tracks</span>
        <button
          type="button"
          onClick={() => updateTrackPref("accumulate", !trackPrefs.accumulate)}
          className={clsx(
            "px-2.5 py-1 rounded border text-[11px] font-medium touch-manipulation",
            trackPrefs.accumulate
              ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-200"
              : "border-slate-600 text-slate-500 hover:border-slate-500",
          )}
          title="Swing / accumulate: buy zone, almost ready, stops, targets"
        >
          Accumulate
        </button>
        <button
          type="button"
          onClick={() => updateTrackPref("tactical", !trackPrefs.tactical)}
          className={clsx(
            "px-2.5 py-1 rounded border text-[11px] font-medium touch-manipulation",
            trackPrefs.tactical
              ? "border-violet-500/40 bg-violet-500/15 text-violet-200"
              : "border-slate-600 text-slate-500 hover:border-slate-500",
          )}
          title="Quick in/out: earnings, breakouts, velocity (when enabled)"
        >
          Tactical
        </button>
      </div>

      <div className="flex rounded border border-slate-600 overflow-hidden w-fit max-w-full">
        <button
          type="button"
          onClick={() => setViewMode("action")}
          className={clsx(
            "px-3 py-1.5 text-xs font-medium touch-manipulation",
            viewMode === "action" ? "bg-emerald-600/70 text-white" : "bg-slate-900 text-slate-400 hover:bg-slate-800",
          )}
        >
          Action required
        </button>
        <button
          type="button"
          onClick={() => setViewMode("all")}
          className={clsx(
            "px-3 py-1.5 text-xs font-medium touch-manipulation",
            viewMode === "all" ? "bg-emerald-600/70 text-white" : "bg-slate-900 text-slate-400 hover:bg-slate-800",
          )}
        >
          Show all
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          <AlertTriangle className="h-4 w-4 text-red-400 mt-0.5 shrink-0" />
          <p className="text-xs text-red-300">Failed to load alerts: {error}</p>
        </div>
      )}

      {visibleAlerts.length === 0 && !error && (
        <div className="text-sm text-slate-500 flex items-center gap-2">
          <Check className="h-4 w-4 text-emerald-400" />
          {alerts.length > 0
            ? "No alerts match the selected tracks — toggle Accumulate or Tactical above."
            : "No actionable alerts right now."}
        </div>
      )}

      {viewMode === "action" && visibleAlerts.length > 0 && (
        <div className="space-y-2">
          {grouped.actionRequired.length === 0 ? (
            <p className="text-sm text-slate-500">
              No HIGH or CRITICAL alerts — expand &quot;Show all&quot; for watch-soon items (stops approaching, etc.).
            </p>
          ) : (
            <>
              {grouped.critical.length > 0 && (
                <AlertGroup
                  title="Critical"
                  subtitle="Immediate attention"
                  alerts={grouped.critical}
                  defaultOpen
                  onTickerClick={onTickerClick}
                  onDismiss={dismiss}
                />
              )}
              {grouped.high.length > 0 && (
                <AlertGroup
                  title="High"
                  subtitle="Buy zone, stop hit, or model cross — confirm gates before acting"
                  alerts={grouped.high}
                  defaultOpen
                  onTickerClick={onTickerClick}
                  onDismiss={dismiss}
                />
              )}
            </>
          )}
          {watchCount > 0 && (
            <button
              type="button"
              onClick={() => setViewMode("all")}
              className="text-xs text-violet-300 hover:text-violet-200 underline-offset-2 hover:underline"
            >
              Show {watchCount} watch-soon alert{watchCount === 1 ? "" : "s"} (medium / low)
            </button>
          )}
        </div>
      )}

      {viewMode === "all" && visibleAlerts.length > 0 && (
        <div className="space-y-2">
          <AlertGroup
            title="Action required"
            subtitle="Critical + high priority"
            alerts={grouped.actionRequired}
            defaultOpen
            onTickerClick={onTickerClick}
            onDismiss={dismiss}
          />
          <AlertGroup
            title="Watch soon"
            subtitle="Almost ready (3/4 gates), stop approaching, earnings, near target"
            alerts={grouped.medium}
            defaultOpen={false}
            onTickerClick={onTickerClick}
            onDismiss={dismiss}
          />
          <AlertGroup
            title="Low priority"
            subtitle="Informational — safe to skip unless you are drilling in"
            alerts={grouped.low}
            defaultOpen={false}
            onTickerClick={onTickerClick}
            onDismiss={dismiss}
          />
        </div>
      )}

      {lastAt && (
        <p className="text-[11px] text-slate-600">
          Last refreshed:{" "}
          {lastAt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" })}
        </p>
      )}
    </div>
  );
}
