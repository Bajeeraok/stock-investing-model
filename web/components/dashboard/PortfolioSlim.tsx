"use client";

/**
 * Slim Portfolio tab: one row per ticker for the selected account (account rows merged in "All"),
 * an action list that covers every holding, a compact holdings table and a one-card risk summary.
 * Trim follows docs/signals/SIGNAL_RULES.md: only with a concrete risk; AVOID alone = hold, don't add.
 */

import { useMemo, useState } from "react";
import { clsx } from "clsx";
import type { PortfolioHolding, PortfolioReport, Signal } from "@/app/page";

type ActionKind = "trim" | "over" | "add" | "noadd" | "hold";

export interface MergedHolding {
  ticker: string;
  value: number;
  pct: number;
  gainLoss: number | null;
  gainLossPct: number | null;
  accounts: { account: string; value: number }[];
  base: PortfolioHolding;
  action: ActionKind;
  overLimit: boolean;
  reason: string;
  stop: number | null;
  earningsDays: number | null;
}

const ACTION_META: Record<ActionKind, { label: string; tone: string; chip: string }> = {
  trim: { label: "Trim", tone: "text-td-crit", chip: "bg-td-crit-weak text-td-crit" },
  over: { label: "Over limit", tone: "text-td-warn", chip: "bg-td-warn-weak text-td-warn" },
  add: { label: "Add zone", tone: "text-td-accent", chip: "bg-td-accent-weak text-td-accent" },
  noadd: { label: "Hold · don't add", tone: "text-td-warn", chip: "bg-td-surface2 text-td-warn" },
  hold: { label: "Hold", tone: "text-td-muted", chip: "bg-td-surface2 text-td-muted" },
};
const ORDER: ActionKind[] = ["trim", "over", "add", "noadd", "hold"];

const REASON_TEXT: Record<string, string> = {
  extended: "overextended",
  plan_reduce: "plan says reduce",
  stop_broken: "below swing stop",
};

function usd(n: number | null | undefined, digits = 0): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n < 0 ? "−" : "";
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

function earningsDaysFrom(h: PortfolioHolding, s?: Signal): number | null {
  if (s?.earnings_days_until != null) return s.earnings_days_until;
  const m = /earnings in (\d+) day/i.exec(h.earnings_note ?? "");
  return m ? Number(m[1]) : null;
}

export function mergeHoldings(
  rows: PortfolioHolding[],
  signalsByTicker: Map<string, Signal>,
  limitPct: number,
): MergedHolding[] {
  const total = rows.reduce((a, h) => a + (h.value ?? 0), 0);
  const groups = new Map<string, PortfolioHolding[]>();
  for (const h of rows) {
    if (!h.ticker) continue;
    const g = groups.get(h.ticker) ?? [];
    g.push(h);
    groups.set(h.ticker, g);
  }
  const out: MergedHolding[] = [];
  for (const [ticker, g] of Array.from(groups.entries())) {
    const base = g[0];
    const value = g.reduce((a, h) => a + (h.value ?? 0), 0);
    const hasGl = g.some((h) => h.gain_loss != null);
    const gainLoss = hasGl ? g.reduce((a, h) => a + (h.gain_loss ?? 0), 0) : null;
    const cost = gainLoss != null ? value - gainLoss : null;
    const pct = total > 0 ? (100 * value) / total : 0;
    const sig = signalsByTicker.get(ticker);
    const trim = g.some((h) => h.is_trim_candidate === true);
    const overLimit = pct > limitPct;
    const act = (base.action ?? "").toUpperCase();
    const weak =
      g.some((h) => h.trim_recommendation === "hold_no_add") || act === "AVOID" || act === "REDUCE";
    let action: ActionKind = "hold";
    let reason = "";
    if (trim) {
      action = "trim";
      const reasons = (g.find((h) => h.is_trim_candidate)?.trim_risk_reasons ?? []).map((r) => REASON_TEXT[r] ?? r);
      reason = reasons.join(" · ") || "risk check failed";
    } else if (overLimit) {
      action = "over";
    } else if (sig?.entry_mode === "full_go" && !weak) {
      action = "add";
      reason = "all entry gates cleared";
    } else if (weak) {
      action = "noadd";
      reason = act === "AVOID" ? "weak score / trend — not a sell" : "weak setup";
    }
    if (overLimit) {
      const t = `${pct.toFixed(1)}% vs ${limitPct}% limit`;
      reason = reason ? `${reason} · ${t}` : t;
    }
    out.push({
      ticker,
      value,
      pct,
      gainLoss,
      gainLossPct: gainLoss != null && cost && cost > 0 ? (100 * gainLoss) / cost : null,
      accounts: g.map((h) => ({ account: h.account ?? "—", value: h.value ?? 0 })),
      base,
      action,
      overLimit,
      reason,
      stop: sig?.swing_stop ?? null,
      earningsDays: earningsDaysFrom(base, sig),
    });
  }
  return out.sort((a, b) => b.value - a.value);
}

function TickerButton({ t, onClick }: { t: string; onClick?: (t: string) => void }) {
  return (
    <button type="button" onClick={() => onClick?.(t)} className="font-mono text-[13px] font-bold text-td-text hover:underline">
      {t}
    </button>
  );
}

export function PortfolioHeader({ report, holdings, limitPct }: { report: PortfolioReport | null | undefined; holdings: MergedHolding[]; limitPct: number }) {
  if (!report) return null;
  const over = holdings.filter((h) => h.overLimit).length;
  const top3 = holdings.slice(0, 3).reduce((a, h) => a + h.pct, 0);
  return (
    <section className="rounded-2xl border border-td-line bg-td-surface px-4 py-3.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-2xl font-bold text-td-text tabular-nums">{usd(report.total_value)}</span>
        <span className="text-[12px] text-td-muted">{holdings.length} tickers</span>
      </div>
      <p className="mt-1 text-[12px] text-td-muted">
        Top 3 = {top3.toFixed(1)}% · {over ? <span className="text-td-warn">{over} over the {limitPct}% limit</span> : `none over the ${limitPct}% limit`}
      </p>
    </section>
  );
}

export function PortfolioActions({ holdings, onTickerClick, showAccounts }: { holdings: MergedHolding[]; onTickerClick?: (t: string) => void; showAccounts: boolean }) {
  const [showHold, setShowHold] = useState(false);
  const byKind = useMemo(() => {
    const m = new Map<ActionKind, MergedHolding[]>();
    for (const h of holdings) m.set(h.action, [...(m.get(h.action) ?? []), h]);
    return m;
  }, [holdings]);
  return (
    <section aria-label="Actions" className="rounded-2xl border border-td-line bg-td-surface px-4 py-3.5 space-y-3">
      <h3 className="text-[11.5px] font-semibold uppercase tracking-wider text-td-muted">Actions · {holdings.length} tickers</h3>
      {ORDER.map((k) => {
        const items = byKind.get(k) ?? [];
        if (!items.length) return null;
        const meta = ACTION_META[k];
        if (k === "hold") {
          return (
            <div key={k}>
              <button type="button" onClick={() => setShowHold((v) => !v)} className={clsx("text-[12px] font-semibold", meta.tone)}>
                {meta.label} · {items.length} {showHold ? "▾" : "▸"}
              </button>
              <div className={clsx("mt-1.5 flex flex-wrap gap-1.5", !showHold && "hidden")}>
                {items.map((h) => (
                  <button key={h.ticker} type="button" onClick={() => onTickerClick?.(h.ticker)} className="rounded-md bg-td-surface2 px-2 py-0.5 font-mono text-[12px] text-td-text hover:brightness-125">
                    {h.ticker}
                  </button>
                ))}
              </div>
            </div>
          );
        }
        return (
          <div key={k}>
            <p className={clsx("text-[12px] font-semibold", meta.tone)}>{meta.label} · {items.length}</p>
            <ul className="mt-1 divide-y divide-td-line/60">
              {items.map((h) => (
                <li key={h.ticker} className="flex items-center justify-between gap-3 py-1.5">
                  <span className="min-w-0">
                    <TickerButton t={h.ticker} onClick={onTickerClick} />
                    <span className="ml-2 text-[12px] text-td-muted">{h.reason}</span>
                    {showAccounts && h.accounts.length > 1 && (
                      <span className="block text-[11px] text-td-muted truncate">
                        {h.accounts.map((a) => `${a.account} ${usd(a.value)}`).join(" · ")}
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 font-mono text-[12px] text-td-muted tabular-nums">{h.pct.toFixed(1)}%</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}

export function PortfolioRiskSummary({ report, holdings }: { report: PortfolioReport | null | undefined; holdings: MergedHolding[] }) {
  const total = report?.total_value ?? 0;
  if (!total) return null;
  const earnings = holdings.filter((h) => h.earningsDays != null && h.earningsDays <= 14).sort((a, b) => (a.earningsDays ?? 0) - (b.earningsDays ?? 0));
  const top = holdings.slice(0, 3);
  return (
    <section className="rounded-2xl border border-td-line bg-td-surface px-4 py-3.5">
      <h3 className="text-[11.5px] font-semibold uppercase tracking-wider text-td-muted mb-2">Risk</h3>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-[12.5px]">
        <dt className="text-td-muted">Market −20%</dt>
        <dd className="font-mono text-td-crit tabular-nums">{usd(-0.2 * total)} <span className="text-td-muted font-sans">(if every holding falls with SPY)</span></dd>
        <dt className="text-td-muted">Largest</dt>
        <dd className="font-mono text-td-text">{top.map((h) => `${h.ticker} ${h.pct.toFixed(1)}%`).join(" · ")}</dd>
        <dt className="text-td-muted">Earnings ≤14d</dt>
        <dd className="font-mono text-td-text">{earnings.length ? earnings.map((h) => `${h.ticker} ${h.earningsDays}d`).join(" · ") : <span className="text-td-muted font-sans">none</span>}</dd>
      </dl>
    </section>
  );
}

export function PortfolioHoldingsSlim({ holdings, onTickerClick, showAccounts }: { holdings: MergedHolding[]; onTickerClick?: (t: string) => void; showAccounts: boolean }) {
  return (
    <div className="rounded-xl border border-td-line overflow-x-auto">
      <table className="w-full text-[12.5px] tabular-nums">
        <thead className="text-left text-td-muted">
          <tr className="border-b border-td-line">
            <th className="px-3 py-2 font-medium">Ticker</th>
            <th className="px-3 py-2 font-medium text-right">Value</th>
            <th className="px-3 py-2 font-medium text-right">Gain</th>
            <th className="px-3 py-2 font-medium">Signal</th>
            <th className="px-3 py-2 font-medium text-right" title="Swing stop from the ticker page">Stop</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const meta = ACTION_META[h.action];
            return (
              <tr key={h.ticker} className="border-t border-td-line/50">
                <td className="px-3 py-2">
                  <TickerButton t={h.ticker} onClick={onTickerClick} />
                  {showAccounts && h.accounts.length > 1 && <span className="ml-1 text-[11px] text-td-muted">×{h.accounts.length}</span>}
                </td>
                <td className="px-3 py-2 text-right font-mono">
                  {usd(h.value)}
                  <span className="block text-[11px] text-td-muted">{h.pct.toFixed(1)}%</span>
                </td>
                <td className={clsx("px-3 py-2 text-right font-mono", (h.gainLossPct ?? 0) >= 0 ? "text-td-accent" : "text-td-crit")}>
                  {h.gainLossPct != null ? `${h.gainLossPct >= 0 ? "+" : ""}${h.gainLossPct.toFixed(1)}%` : "—"}
                </td>
                <td className="px-3 py-2">
                  <span className={clsx("rounded px-1.5 py-0.5 text-[11.5px] font-semibold whitespace-nowrap", meta.chip)}>{meta.label}</span>
                </td>
                <td className="px-3 py-2 text-right font-mono text-td-muted">{usd(h.stop, 2)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
