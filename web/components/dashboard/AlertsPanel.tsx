"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Bell, Check, RefreshCw, X } from "lucide-react";
import { clsx } from "clsx";

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

export function AlertsPanel({
  onTickerClick,
  onLoaded,
}: {
  onTickerClick?: (ticker: string) => void;
  /** Called after first fetch with alert count (for conditional Overview section). */
  onLoaded?: (count: number) => void;
}) {
  const [alerts, setAlerts] = useState<ScanAlert[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAt, setLastAt] = useState<Date | null>(null);

  const base = useCallback((path: string) => (API_BASE ? `${API_BASE}${path}` : path), []);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(base("/api/scanner/alerts?limit=80"));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as ScanAlert[];
      const list = Array.isArray(json) ? json : [];
      setAlerts(list);
      onLoaded?.(list.length);
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

  // Poll only during scanner hours to reduce API usage
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
        setAlerts((a) => a.filter((x) => x.id !== id));
      }
    },
    [base]
  );

  const headerNote = useMemo(() => {
    const hrs = isScannerHours();
    if (!hrs) return "Scanner idle outside 8:00–16:00 ET weekdays (manual refresh works).";
    return "Auto-refreshing during scan hours (1m).";
  }, []);

  const prLabel = (p: number) => (p === 1 ? "CRITICAL" : p === 2 ? "HIGH" : p === 3 ? "MEDIUM" : "LOW");

  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Bell className="h-4 w-4 text-emerald-400 shrink-0" />
            <h3 className="text-sm font-semibold text-slate-200">Alerts</h3>
            <span className="text-xs text-slate-500">({alerts.length})</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1">{headerNote}</p>
        </div>
        <button
          type="button"
          onClick={fetchAlerts}
          className={clsx(
            "flex items-center gap-2 px-3 py-2 rounded-lg border text-xs",
            "border-slate-600 text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          )}
          disabled={loading}
          title="Refresh alerts"
        >
          <RefreshCw className={clsx("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          <AlertTriangle className="h-4 w-4 text-red-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs text-red-300">Failed to load alerts: {error}</p>
          </div>
        </div>
      )}

      {alerts.length === 0 && !error && (
        <div className="text-sm text-slate-500 flex items-center gap-2">
          <Check className="h-4 w-4 text-emerald-400" />
          No actionable alerts right now.
        </div>
      )}

      <div className="space-y-2">
        {alerts.map((a) => (
          <div
            key={a.id}
            className="rounded-lg border border-slate-700/60 bg-slate-950/30 px-3 py-2.5"
          >
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
                  <span className="text-sm text-slate-200 font-semibold truncate">{a.headline}</span>
                  <span className={clsx(
                    "text-[10px] px-2 py-0.5 rounded border",
                    a.priority === 1 ? "bg-red-500/15 text-red-300 border-red-500/30" :
                    a.priority === 2 ? "bg-amber-500/15 text-amber-300 border-amber-500/30" :
                    "bg-slate-700/20 text-slate-300 border-slate-600/30"
                  )}>
                    {`Priority: ${prLabel(a.priority)}`}
                  </span>
                  <span className="text-[10px] text-slate-500">{`Risk: ${a.risk_level}`}</span>
                </div>
                <p className="text-xs text-slate-400 mt-1 leading-snug">
                  {a.actionable ?? a.body}
                </p>
                {a.one_liner && (
                  <p className="text-[11px] text-emerald-300/90 mt-1 leading-snug">
                    {a.one_liner}
                  </p>
                )}
                {a.actionable && a.body && (
                  <p className="text-[11px] text-slate-500 mt-1 leading-snug" title="Context">
                    {a.body}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(a.id)}
                className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
                title="Dismiss"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {lastAt && (
        <p className="text-[11px] text-slate-600">
          Last refreshed: {lastAt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" })}
        </p>
      )}
    </div>
  );
}

