"use client";

/**
 * Alerts — promoted out of the Today feed into its own full-screen destination (bell icon).
 * Scanner alerts are the existing AlertsPanel (action-required vs watch-soon, dismiss +
 * per-viewer snooze); "Your price alerts" are the ones set from a ticker's Verdict tab.
 *
 * Kept mounted while closed (hidden) so the bell badge count stays live.
 */

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowLeft, BellRing, Trash2 } from "lucide-react";
import { clsx } from "clsx";
import { AlertsPanel } from "./AlertsPanel";
import { useLivePriceContext } from "@/lib/LivePriceContext";
import {
  alertCrossed,
  listPriceAlerts,
  markPriceAlertTriggered,
  removePriceAlert,
  subscribePriceAlerts,
  type PriceAlert,
} from "@/lib/priceAlerts";

function usePriceAlerts(): PriceAlert[] {
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  useEffect(() => {
    const sync = () => setAlerts(listPriceAlerts());
    sync();
    return subscribePriceAlerts(sync);
  }, []);
  return alerts;
}

/** Checks active price alerts against the dashboard's live-price poll; notifies once per alert. */
export function PriceAlertWatcher() {
  const { prices } = useLivePriceContext();
  const alerts = usePriceAlerts();
  useEffect(() => {
    for (const a of alerts) {
      if (a.triggeredAt) continue;
      const p = prices[a.ticker];
      if (p == null || !alertCrossed(a, p)) continue;
      markPriceAlertTriggered(a.id, p);
      const body = `${a.ticker} is at $${p.toFixed(2)} (your alert: ${a.direction === "below" ? "≤" : "≥"} $${a.price.toFixed(2)})`;
      try {
        if (typeof Notification !== "undefined" && Notification.permission === "granted") {
          new Notification("Thrive Alpha price alert", { body, tag: a.id });
        }
      } catch {
        /* notifications unavailable */
      }
    }
  }, [prices, alerts]);
  return null;
}

/** Price alerts that need the live-price poll to include their tickers. */
export function priceAlertTickers(): string[] {
  return listPriceAlerts()
    .filter((a) => !a.triggeredAt)
    .map((a) => a.ticker);
}

export function AlertsScreen({
  open,
  onClose,
  onTickerClick,
  dashboardRefreshedAt,
  onCounts,
}: {
  open: boolean;
  onClose: () => void;
  onTickerClick: (ticker: string) => void;
  dashboardRefreshedAt?: string | null;
  onCounts?: (total: number, actionRequired: number) => void;
}) {
  const priceAlerts = usePriceAlerts();
  const { prices } = useLivePriceContext();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (typeof window === "undefined") return null;

  return createPortal(
    <div
      className={clsx("fixed inset-0 z-[90] bg-td-bg overflow-y-auto overscroll-contain", !open && "hidden")}
      role="dialog"
      aria-modal="true"
      aria-label="Alerts"
    >
      <header className="sticky top-0 z-10 border-b border-td-line bg-td-surface/95 backdrop-blur">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center gap-3">
          <button
            type="button"
            onClick={onClose}
            className="p-2 -ml-2 rounded-lg text-td-muted hover:text-td-text hover:bg-td-surface2"
            aria-label="Back"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <h2 className="text-base font-semibold text-td-text">Alerts</h2>
          <span className="text-[11px] text-td-muted">confirm gates before acting</span>
        </div>
      </header>
      <div className="max-w-3xl mx-auto px-4 py-4 space-y-5 pb-[calc(2rem+env(safe-area-inset-bottom))]">
        {priceAlerts.length > 0 && (
          <section className="rounded-2xl border border-td-line bg-td-surface px-4 py-3">
            <h3 className="flex items-center gap-2 text-[11.5px] font-semibold uppercase tracking-wider text-td-muted mb-2">
              <BellRing className="h-4 w-4" /> Your price alerts · {priceAlerts.length}
            </h3>
            <ul className="divide-y divide-td-line">
              {priceAlerts.map((a) => {
                const live = prices[a.ticker];
                return (
                  <li key={a.id} className="flex items-center justify-between gap-3 py-2">
                    <button type="button" onClick={() => onTickerClick(a.ticker)} className="text-left min-w-0">
                      <span className="font-mono text-[13px] font-bold text-td-text">{a.ticker}</span>{" "}
                      <span className="text-[12px] text-td-muted">
                        {a.direction === "below" ? "at or below" : "at or above"} ${a.price.toFixed(2)}
                      </span>
                      <span className="block text-[11px] text-td-muted">
                        {a.triggeredAt
                          ? `Triggered ${new Date(a.triggeredAt).toLocaleString()} at $${a.triggeredPrice?.toFixed(2) ?? "—"}`
                          : live != null
                            ? `Now $${live.toFixed(2)} · ${(((a.price - live) / live) * 100).toFixed(1)}% away`
                            : "Watching — checks every minute while the app is open"}
                      </span>
                    </button>
                    <div className="flex items-center gap-2 shrink-0">
                      {a.triggeredAt && (
                        <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded-full bg-td-accent-weak text-td-accent">HIT</span>
                      )}
                      <button
                        type="button"
                        onClick={() => removePriceAlert(a.id)}
                        className="p-1.5 rounded-md text-td-muted hover:text-td-crit hover:bg-td-surface2"
                        aria-label={`Remove ${a.ticker} alert`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        )}
        <section className="rounded-2xl border border-td-line bg-slate-900 p-4">
          <AlertsPanel
            onTickerClick={(t) => {
              onTickerClick(t);
            }}
            dashboardRefreshedAt={dashboardRefreshedAt}
            onLoaded={onCounts}
          />
        </section>
      </div>
    </div>,
    document.body,
  );
}
