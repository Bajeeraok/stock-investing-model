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
import {
  alertMatchesSideFilter,
  alertSideFromAlert,
  loadAlertSideFilter,
  saveAlertSideFilter,
  type AlertSideFilter,
} from "@/lib/alertSideFilter";
import { formatSnapshotAge, formatSnapshotEt } from "@/lib/dashboardCache";

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

const ENTRY_MODE_LABEL: Record<string, { text: string; cls: string; title: string }> = {
  full_go: { text: "Full GO", cls: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30", title: "All primary gates pass — staged add allowed" },
  starter_only: { text: "Starter only", cls: "bg-amber-500/10 text-amber-200 border-amber-500/30", title: "Valuation passes, technicals blocked — small starter at most" },
  hard_lock: { text: "Locked", cls: "bg-slate-700/40 text-slate-300 border-slate-600/50", title: "Gates blocked — no new adds; holders keep default HOLD" },
};

function ModeChips({ signals }: { signals?: Record<string, unknown> }) {
  if (!signals) return null;
  const em = typeof signals.entryMode === "string" ? ENTRY_MODE_LABEL[signals.entryMode] : undefined;
  const held = signals.held === true;
  const protect = typeof signals.protectActive === "boolean" ? (signals.protectActive as boolean) : null;
  return (
    <>
      {held && (
        <span className="text-[10px] px-2 py-0.5 rounded border shrink-0 bg-sky-500/10 text-sky-300 border-sky-500/30" title="You hold this position">
          Held
        </span>
      )}
      {em && (
        <span className={clsx("text-[10px] px-2 py-0.5 rounded border shrink-0", em.cls)} title={em.title}>
          {em.text}
        </span>
      )}
      {protect === true && (
        <span
          className="text-[10px] px-2 py-0.5 rounded border shrink-0 bg-violet-500/10 text-violet-300 border-violet-500/30"
          title="Optional protect mode is on (stock below 200-day average or SPY risk-off): ~half position if you use it"
        >
          Protect on
        </span>
      )}
    </>
  );
}

const ALERT_RULES: { type: string; when: string; who: string; mode: string }[] = [
  { type: "In entry band", when: "Price enters a plan band (ST/MT/LT). Re-alerts after 4h if still inside.", who: "Holdings + watchlist", mode: "Full GO → staged add OK. Starter only → small size, watchlist needs ≥2% below band top. Locked → suppressed." },
  { type: "Stop hit / near stop", when: "Once, when price crosses below a short- or medium-term plan stop, or into the 2% just above it. Not repeated while price stays below.", who: "Holdings only", mode: "Plan traders trim/exit per plan. Long-term holders: no stop alerts; default HOLD, and the protect-mode alert covers long-term risk." },
  { type: "Target hit / near target", when: "Short/medium plans only: once when price first crosses up to the top of the band (or within 5% of it). No repeats while it stays there; no long-term target alerts.", who: "Holdings only", mode: "Plan traders: optional take-profit per plan. Long-term holders: HOLD — not a sell signal." },
  { type: "Protect mode on / off", when: "Stock crosses its 200-day average (±1% band) or SPY turns risk-off / back on. Fires only on change.", who: "Holdings + watchlist", mode: "Optional insurance: ~50% position when on, full when off. Default action stays HOLD." },
  { type: "Earnings soon", when: "Earnings within the alert window.", who: "Holdings; watchlist only if Full GO", mode: "No new positions before the report; holders may trim speculative size." },
  { type: "Almost ready", when: "Moves to 3/4 gates + short-term verdict supports add.", who: "Watchlist", mode: "Not full GO — watch the last blocking gate." },
  { type: "Model cross", when: "ML probability crosses the add threshold.", who: "Holdings; watchlist only if Full GO", mode: "Split entry: starter now, optional band limit for a cheaper fill." },
  { type: "RSI oversold", when: "RSI-14 crosses below 35 or drops 3+ points deeper.", who: "Holdings; watchlist only if Full GO", mode: "Informational — oversold dips were not an edge in our 10-year test." },
  { type: "Tactical velocity", when: "Volume/Bollinger breakout with ≥2 gates.", who: "Watchlist", mode: "Short-term track only — not an accumulate GO." },
];

function AlertRulesExplainer() {
  return (
    <details className="rounded-lg border border-slate-700/60 bg-slate-950/30 px-3 py-2 text-xs text-slate-400">
      <summary className="cursor-pointer text-slate-300 font-medium">How alerts are checked (rules &amp; modes)</summary>
      <p className="mt-2 text-[11px] text-slate-500">
        Checked on every dashboard refresh (~15 min in market hours). No alert means &quot;sell because the score is low&quot; —
        a chosen stock&apos;s default is HOLD. Chips on each alert show Held, entry mode (Full GO / Starter only / Locked) and Protect on.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left border-collapse">
          <thead>
            <tr className="text-slate-500 border-b border-slate-700">
              <th className="py-1 pr-3 font-medium">Alert</th>
              <th className="py-1 pr-3 font-medium">Fires when</th>
              <th className="py-1 pr-3 font-medium">For</th>
              <th className="py-1 font-medium">Mode / what to do</th>
            </tr>
          </thead>
          <tbody>
            {ALERT_RULES.map((r) => (
              <tr key={r.type} className="border-b border-slate-800 align-top">
                <td className="py-1 pr-3 text-slate-300 whitespace-nowrap">{r.type}</td>
                <td className="py-1 pr-3">{r.when}</td>
                <td className="py-1 pr-3 whitespace-nowrap">{r.who}</td>
                <td className="py-1">{r.mode}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function prLabel(p: number): string {
  return p === 1 ? "CRITICAL" : p === 2 ? "HIGH" : p === 3 ? "MEDIUM" : "LOW";
}

function isActionRequired(p: number): boolean {
  return p === 1 || p === 2;
}

function readEntryZoneSignals(signals: Record<string, unknown> | undefined): {
  gatesPassed: number | null;
  gatesTotal: number;
  gateCleared: boolean;
  zoneOnly: boolean;
  bandLabel: string;
} {
  const s = signals ?? {};
  const band = String(s.band ?? "").toLowerCase();
  const bandLabel =
    band === "long" ? "Long-term" : band === "medium" ? "Medium-term" : band === "short" ? "Short-term" : "Entry";
  const gpRaw = s.gatesPassed ?? s.gates_passed;
  const gtRaw = s.gatesTotal ?? s.gates_total ?? 4;
  let gatesPassed: number | null = null;
  if (typeof gpRaw === "number") gatesPassed = gpRaw;
  else if (typeof gpRaw === "string" && gpRaw.trim()) gatesPassed = parseInt(gpRaw, 10);
  const gatesTotal = typeof gtRaw === "number" ? gtRaw : 4;
  const gateCleared =
    s.gateCleared === true ||
    s.gate_cleared === true ||
    String(s.goNoGo ?? s.go_no_go ?? "").toLowerCase() === "go" ||
    (gatesPassed !== null && gatesPassed >= gatesTotal);
  const zoneOnly = s.zoneOnly === true || s.zone_only === true || !gateCleared;
  return { gatesPassed, gatesTotal, gateCleared, zoneOnly, bandLabel };
}

function entryZonePrimaryCopy(a: ScanAlert): string {
  const sig = readEntryZoneSignals(a.signals);
  const lo = a.signals?.entryLow ?? a.signals?.entry_low;
  const hi = a.signals?.entryHigh ?? a.signals?.entry_high;
  const price = a.signals?.price;
  if (
    sig.zoneOnly &&
    typeof lo === "number" &&
    typeof hi === "number"
  ) {
    const gateTxt =
      sig.gatesPassed != null ? `${sig.gatesPassed}/${sig.gatesTotal} gates` : "4/4 gates";
    return `Zone only: price is in ${sig.bandLabel.toLowerCase()} band $${Number(lo).toFixed(2)}–$${Number(hi).toFixed(2)}${
      typeof price === "number" ? ` (spot $${Number(price).toFixed(2)})` : ""
    }. Open ticker detail — ${gateTxt} must clear before adding.`;
  }
  if (a.actionable?.trim()) return a.actionable.trim();
  return a.body;
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

function groupAlertsByTicker(alerts: ScanAlert[]): { key: string; ticker: string | null; alerts: ScanAlert[] }[] {
  const map = new Map<string, ScanAlert[]>();
  for (const a of alerts) {
    const key = (a.ticker || "__macro__").toUpperCase();
    const bucket = map.get(key) ?? [];
    bucket.push(a);
    map.set(key, bucket);
  }
  const groups = Array.from(map.entries()).map(([key, list]) => ({
    key,
    ticker: key === "__MACRO__" ? null : key,
    alerts: sortAlerts(list),
  }));
  return groups.sort((a, b) => {
    const pa = Math.min(...a.alerts.map((x) => x.priority));
    const pb = Math.min(...b.alerts.map((x) => x.priority));
    if (pa !== pb) return pa - pb;
    return (a.ticker || "ZZZ").localeCompare(b.ticker || "ZZZ");
  });
}

function TickerAlertAccordion({
  group,
  onTickerClick,
  onDismiss,
}: {
  group: { key: string; ticker: string | null; alerts: ScanAlert[] };
  onTickerClick?: (ticker: string) => void;
  onDismiss: (id: string) => void;
}) {
  const [open, setOpen] = useState(group.alerts.some((a) => isActionRequired(a.priority)));
  const topPriority = Math.min(...group.alerts.map((a) => a.priority));

  if (group.alerts.length === 1) {
    return <AlertCard alert={group.alerts[0]} onTickerClick={onTickerClick} onDismiss={onDismiss} />;
  }

  return (
    <div className="rounded-lg border border-slate-700/60 bg-slate-950/20 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-slate-800/50 touch-manipulation"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-slate-500 shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-slate-500 shrink-0" />
        )}
        {group.ticker ? (
          <span className="font-mono text-emerald-400 text-sm font-semibold">{group.ticker}</span>
        ) : (
          <span className="font-mono text-slate-200 text-sm font-semibold">MACRO</span>
        )}
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 tabular-nums">
          {group.alerts.length} alerts
        </span>
        <span className="text-[10px] font-bold uppercase text-amber-300/90 ml-auto">{prLabel(topPriority)}</span>
      </button>
      {open && (
        <div className="p-2 pt-0 space-y-2 border-t border-slate-700/40">
          {group.alerts.map((a) => (
            <AlertCard key={a.id} alert={a} onTickerClick={onTickerClick} onDismiss={onDismiss} />
          ))}
        </div>
      )}
    </div>
  );
}

const SNOOZE_KEY = "thrive-alert-snooze";
const SNOOZE_EVENT = "thrive-alert-snooze-changed";
const SNOOZE_HOURS = 24;

function readSnoozes(): Record<string, number> {
  if (typeof window === "undefined") return {};
  try {
    const raw = JSON.parse(localStorage.getItem(SNOOZE_KEY) || "{}") as Record<string, number>;
    const now = Date.now();
    return Object.fromEntries(Object.entries(raw).filter(([, until]) => until > now));
  } catch {
    return {};
  }
}

/** Per-viewer snooze (24h) — dismiss is server-side and permanent; snooze just hides it here. */
function snoozeAlert(id: string): void {
  const next = { ...readSnoozes(), [id]: Date.now() + SNOOZE_HOURS * 3600_000 };
  try {
    localStorage.setItem(SNOOZE_KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event(SNOOZE_EVENT));
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
    String(a.headline || "").toLowerCase().includes("buy zone") ||
    String(a.headline || "").toLowerCase().includes(" band ");
  const almostReady = a.type === "SETUP_ALMOST_READY";
  const zoneSig = buyZone ? readEntryZoneSignals(a.signals) : null;
  const zoneOnly = Boolean(zoneSig?.zoneOnly);
  const gatesClear = Boolean(zoneSig?.gateCleared);
  const side = alertSideFromAlert(a);

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
            {side === "buy" ? (
              <span className="text-[10px] px-2 py-0.5 rounded border shrink-0 bg-emerald-500/10 text-emerald-300 border-emerald-500/30 font-semibold uppercase tracking-wide">
                Buy
              </span>
            ) : side === "sell" ? (
              <span className="text-[10px] px-2 py-0.5 rounded border shrink-0 bg-red-500/10 text-red-300 border-red-500/30 font-semibold uppercase tracking-wide">
                Sell
              </span>
            ) : null}
            {zoneOnly && buyZone ? (
              <span className="text-[10px] px-2 py-0.5 rounded border shrink-0 bg-amber-500/15 text-amber-200 border-amber-500/35 font-semibold uppercase tracking-wide">
                Zone only
              </span>
            ) : gatesClear && buyZone ? (
              <span className="text-[10px] px-2 py-0.5 rounded border shrink-0 bg-emerald-500/15 text-emerald-200 border-emerald-500/35 font-semibold uppercase tracking-wide">
                Gates OK
              </span>
            ) : null}
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
            <ModeChips signals={a.signals} />
            <span className="text-[10px] text-slate-500 shrink-0">{`Risk: ${a.risk_level}`}</span>
            {a.timestamp ? (
              <span
                className="text-[10px] text-slate-500 shrink-0 tabular-nums"
                title={formatSnapshotEt(a.timestamp)}
              >
                Generated{" "}
                {formatSnapshotAge(a.timestamp) || formatSnapshotEt(a.timestamp)}
              </span>
            ) : null}
          </div>
          <p className="text-xs text-slate-300 mt-1 leading-relaxed">{entryZonePrimaryCopy(a)}</p>
          {buyZone && zoneOnly && (
            <p className="text-[11px] text-amber-200/90 mt-1.5 leading-snug rounded-md border border-amber-500/25 bg-amber-950/30 px-2 py-1.5">
              <span className="font-semibold">Not a buy signal yet.</span> Band = where you&apos;d add if gates pass.
              {zoneSig?.gatesPassed != null
                ? ` Currently ${zoneSig.gatesPassed}/${zoneSig.gatesTotal} primary gates — open ticker detail for the blocker.`
                : " Open ticker detail and confirm 4/4 primary gates before sizing."}
            </p>
          )}
          {buyZone && gatesClear && (
            <p className="text-[11px] text-emerald-200/90 mt-1.5 leading-snug">
              Gates clear — staged add allowed. Still use stop/target and tranche sizing.
            </p>
          )}
          {almostReady && (
            <p className="text-[11px] text-amber-300/85 mt-1 leading-snug">
              Almost ready (3/4 gates + ST buy) — not full GO yet. Watch the last blocker; paper track still needs 4/4.
            </p>
          )}
          {a.one_liner && (
            <p
              className={clsx(
                "text-[11px] mt-1 leading-snug tabular-nums",
                zoneOnly && buyZone ? "text-slate-500" : "text-slate-400",
              )}
            >
              {a.one_liner}
            </p>
          )}
          {a.actionable && a.body && (
            <p className="text-[11px] text-slate-500 mt-1 leading-snug" title="Context">
              {a.body}
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <button
            type="button"
            onClick={() => onDismiss(a.id)}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white touch-manipulation"
            title="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => snoozeAlert(a.id)}
            className="px-2 py-1 rounded-md text-[10.5px] font-semibold text-slate-400 hover:text-slate-100 hover:bg-slate-800 touch-manipulation"
            title={`Hide for ${SNOOZE_HOURS}h (this browser only)`}
          >
            Snooze
          </button>
        </div>
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
          {groupAlertsByTicker(alerts).map((g) => (
            <TickerAlertAccordion
              key={g.key}
              group={g}
              onTickerClick={onTickerClick}
              onDismiss={onDismiss}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function AlertsPanel({
  onTickerClick,
  onLoaded,
  dashboardRefreshedAt,
}: {
  onTickerClick?: (ticker: string) => void;
  /** Total alerts + action-required (HIGH/CRITICAL) count for Overview badge. */
  onLoaded?: (total: number, actionRequired: number) => void;
  /** When dashboard Refresh completes — bands/gates update; reload alert list. */
  dashboardRefreshedAt?: string | null;
}) {
  const [alerts, setAlerts] = useState<ScanAlert[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAt, setLastAt] = useState<Date | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("action");
  const [trackPrefs, setTrackPrefs] = useState<AlertTrackPrefs>(() => loadAlertTrackPrefs());
  const [sideFilter, setSideFilter] = useState<AlertSideFilter>(() => loadAlertSideFilter());
  const onLoadedRef = useRef(onLoaded);
  onLoadedRef.current = onLoaded;

  const base = useCallback((path: string) => (API_BASE ? `${API_BASE}${path}` : path), []);

  const fetchAlerts = useCallback(async (opts?: { silent?: boolean }) => {
    setError(null);
    if (!opts?.silent) setLoading(true);
    try {
      const res = await fetch(base("/api/scanner/alerts?limit=80"));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as ScanAlert[];
      const list = sortAlerts(Array.isArray(json) ? json : []);
      setAlerts(list);
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
    if (!dashboardRefreshedAt) return;
    fetchAlerts({ silent: true });
  }, [dashboardRefreshedAt, fetchAlerts]);

  /** Match backend scanner cadence (15–30m) — 1m poll only re-reads the same JSONL cache. */
  useEffect(() => {
    const minutes = isScannerHours() ? 15 : 0;
    if (!minutes) return;
    const id = setInterval(() => fetchAlerts({ silent: true }), minutes * 60 * 1000);
    return () => clearInterval(id);
  }, [fetchAlerts]);

  const dismiss = useCallback(
    async (id: string) => {
      try {
        await fetch(base(`/api/scanner/alerts/${id}/dismiss`), { method: "POST" });
      } catch {
        // ignore
      } finally {
        setAlerts((prev) => prev.filter((x) => x.id !== id));
      }
    },
    [base],
  );

  const [snoozed, setSnoozed] = useState<Record<string, number>>({});
  useEffect(() => {
    const sync = () => setSnoozed(readSnoozes());
    sync();
    window.addEventListener(SNOOZE_EVENT, sync);
    return () => window.removeEventListener(SNOOZE_EVENT, sync);
  }, []);

  const visibleAlerts = useMemo(
    () =>
      alerts.filter(
        (a) =>
          !snoozed[a.id] && alertMatchesTrackPrefs(a, trackPrefs) && alertMatchesSideFilter(a, sideFilter),
      ),
    [alerts, trackPrefs, sideFilter, snoozed],
  );

  const applySideFilter = useCallback((filter: AlertSideFilter) => {
    setSideFilter(filter);
    saveAlertSideFilter(filter);
  }, []);

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
    if (!hrs) {
      return "Outside 8:00–16:00 ET scan window. Band/gate context updates on Dashboard Refresh; alert list reloads then.";
    }
    return (
      "Event inbox for your book plus the 100-name audit cohort — entry/stop/target, earnings, zone vs gates. " +
      "Re-evaluates on Dashboard Refresh (~15m); reloads every 15m and after each Refresh."
    );
  }, []);

  const actionCount = grouped.actionRequired.length;
  const watchCount = grouped.medium.length + grouped.low.length;
  const buyCount = useMemo(
    () => alerts.filter((a) => alertMatchesTrackPrefs(a, trackPrefs) && alertSideFromAlert(a) === "buy").length,
    [alerts, trackPrefs],
  );
  const sellCount = useMemo(
    () => alerts.filter((a) => alertMatchesTrackPrefs(a, trackPrefs) && alertSideFromAlert(a) === "sell").length,
    [alerts, trackPrefs],
  );

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
            <span className="text-xs text-slate-600 tabular-nums">
              ({visibleAlerts.length} shown
              {alerts.length > visibleAlerts.length
                ? ` · ${alerts.length - visibleAlerts.length} hidden by filters`
                : ""}
              )
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => fetchAlerts()}
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

      <AlertRulesExplainer />

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

      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-[10px] uppercase tracking-wide text-slate-500 shrink-0">Side</span>
        {(
          [
            ["all", "All", null] as const,
            ["buy", "Buy / Add", buyCount] as const,
            ["sell", "Sell / Trim", sellCount] as const,
          ] as const
        ).map(([id, label, count]) => (
          <button
            key={id}
            type="button"
            onClick={() => applySideFilter(id)}
            className={clsx(
              "px-2.5 py-1 rounded border text-[11px] font-medium touch-manipulation",
              sideFilter === id
                ? id === "buy"
                  ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-200"
                  : id === "sell"
                    ? "border-red-500/40 bg-red-500/15 text-red-200"
                    : "border-slate-500/50 bg-slate-700/40 text-slate-200"
                : "border-slate-600 text-slate-500 hover:border-slate-500",
            )}
            title={
              id === "buy"
                ? "Entry zones, almost ready, breakouts, ML support"
                : id === "sell"
                  ? "Stops, targets, trim, risk-off"
                  : "All alert sides"
            }
          >
            {label}
            {count != null && count > 0 ? ` (${count})` : ""}
          </button>
        ))}
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
            ? "No alerts match the selected filters — adjust Tracks or Side above."
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

      <footer className="pt-2 border-t border-slate-700/50 space-y-1">
        {lastAt && (
          <p className="text-[11px] text-slate-600">
            Last refreshed:{" "}
            {lastAt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" })}
          </p>
        )}
        <p className="text-[11px] text-slate-500">{headerNote}</p>
      </footer>
    </div>
  );
}
