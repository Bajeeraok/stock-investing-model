"use client";

/**
 * Portfolio tab header cards (redesign): total value + concentration verdict, "Needs
 * attention" (over-limit positions and trim candidates), and a Risk management summary
 * (VaR/CVaR + SPY shock) that opens the full risk report. All numbers come from the
 * existing portfolio_report / portfolio_risk_metrics / portfolio_stress payloads.
 */

import { clsx } from "clsx";
import { ChevronRight } from "lucide-react";
import type { PortfolioHolding, PortfolioReport, PortfolioRiskMetrics } from "@/app/page";

function usd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n < 0 ? "−" : "";
  return `${sign}$${Math.abs(Math.round(n)).toLocaleString()}`;
}

export function PortfolioValueCard({ report, limitPct }: { report: PortfolioReport | null | undefined; limitPct: number }) {
  if (!report) return null;
  const largest = report.largest_position;
  const concentrated = (report.concentration_alert?.length ?? 0) > 0;
  return (
    <section className="rounded-2xl border border-td-line bg-td-surface px-4 sm:px-5 py-4">
      <p className="text-[11.5px] text-td-muted">Total value · {report.per_holding?.length ?? 0} holdings</p>
      <div className="mt-1 flex items-center justify-between gap-3">
        <span className="font-mono text-3xl font-bold text-td-text tabular-nums">{usd(report.total_value)}</span>
        <span
          className={clsx(
            "font-mono text-[11px] font-bold px-2.5 py-1 rounded-full",
            concentrated ? "bg-td-crit-weak text-td-crit" : "bg-td-accent-weak text-td-accent",
          )}
        >
          {concentrated ? "CONCENTRATED" : "DIVERSIFIED"}
        </span>
      </div>
      <p className="mt-1.5 text-[12.5px] text-td-muted">
        {largest ? `${largest.ticker} is ${largest.pct.toFixed(1)}% of the book.` : ""}
        {report.top3_pct != null ? ` Top 3 holdings are ${report.top3_pct.toFixed(1)}%.` : ""}
        {` Limit per position: ${limitPct}%.`}
      </p>
    </section>
  );
}

export function NeedsAttentionList({
  report,
  trimCandidates,
  limitPct,
  onTickerClick,
}: {
  report: PortfolioReport | null | undefined;
  trimCandidates: PortfolioHolding[];
  limitPct: number;
  onTickerClick?: (ticker: string) => void;
}) {
  const byTicker = new Map((report?.per_holding ?? []).map((h) => [h.ticker, h]));
  const items: { ticker: string; kind: string; detail: string; tone: "warn" | "crit" }[] = [];
  for (const t of report?.concentration_alert ?? []) {
    const h = byTicker.get(t);
    items.push({
      ticker: t,
      kind: "Concentration",
      detail: `${h?.pct != null ? h.pct.toFixed(1) : "?"}% of book, above your ${limitPct}% limit`,
      tone: "warn",
    });
  }
  for (const h of trimCandidates) {
    if (items.some((i) => i.ticker === h.ticker)) continue;
    items.push({
      ticker: h.ticker,
      kind: h.trim_recommendation || h.action || "Trim candidate",
      detail: h.trim_detail || h.action_today || h.suggestion || (h.score != null ? `Score ${Math.round(h.score)}` : ""),
      tone: "crit",
    });
  }
  if (!items.length) return null;
  return (
    <section aria-label="Needs attention" className="space-y-2">
      <h3 className="text-[11.5px] font-semibold uppercase tracking-wider text-td-muted">Needs attention · {items.length}</h3>
      {items.slice(0, 6).map((i) => (
        <button
          key={`${i.kind}-${i.ticker}`}
          type="button"
          onClick={() => onTickerClick?.(i.ticker)}
          className={clsx(
            "w-full text-left rounded-xl border px-4 py-2.5 flex items-center justify-between gap-3 hover:brightness-110",
            i.tone === "warn" ? "bg-td-warn-weak/60 border-td-warn/30" : "bg-td-crit-weak/50 border-td-crit/25",
          )}
        >
          <span className="min-w-0">
            <span className="block font-mono text-[13px] font-bold text-td-text">{i.ticker}</span>
            <span className={clsx("block text-[11.5px] font-semibold", i.tone === "warn" ? "text-td-warn" : "text-td-crit")}>{i.kind}</span>
            <span className="block text-[11.5px] text-td-muted truncate">{i.detail}</span>
          </span>
          <ChevronRight className="h-4 w-4 text-td-muted shrink-0" />
        </button>
      ))}
    </section>
  );
}

export function RiskManagementCard({
  totalValue,
  metrics,
  stress,
  onOpenFull,
}: {
  totalValue: number | null | undefined;
  metrics: PortfolioRiskMetrics | null | undefined;
  stress: { scenarios: { name: string; shock_pct: number; loss_dollars: number }[] } | null | undefined;
  onOpenFull?: () => void;
}) {
  const vc = metrics?.var_cvar;
  const tv = totalValue ?? 0;
  const varUsd = vc?.var_95_10day_pct != null && tv > 0 ? -Math.abs((vc.var_95_10day_pct / 100) * tv) : null;
  const cvarUsd = vc?.cvar_95_10day_pct != null && tv > 0 ? -Math.abs((vc.cvar_95_10day_pct / 100) * tv) : null;
  const scen = stress?.scenarios ?? [];
  const shock =
    scen.find((s) => Math.round(Math.abs(s.shock_pct)) === 20) ?? scen.slice().sort((a, b) => Math.abs(b.shock_pct) - Math.abs(a.shock_pct))[0];
  if (varUsd == null && !shock) return null;
  return (
    <section className="rounded-2xl border border-td-owner/40 bg-td-surface px-4 sm:px-5 py-4">
      <div className="flex items-baseline justify-between gap-2 mb-2.5">
        <h3 className="text-[11.5px] font-semibold uppercase tracking-wider text-td-owner">Risk management</h3>
        {vc?.horizon_days && <span className="text-[10.5px] text-td-muted">{vc.horizon_days}-day horizon</span>}
      </div>
      <div className="grid grid-cols-2 gap-2.5">
        <div className="rounded-xl border border-td-line bg-td-surface2/50 px-3 py-2.5">
          <p className="text-[11px] text-td-muted">95% VaR / CVaR</p>
          <p className="mt-0.5 font-mono text-[15px] font-bold text-td-text tabular-nums">
            {usd(varUsd)} / {usd(cvarUsd)}
          </p>
        </div>
        <div className="rounded-xl border border-td-line bg-td-surface2/50 px-3 py-2.5">
          <p className="text-[11px] text-td-muted">{shock ? `${shock.shock_pct > 0 ? "+" : ""}${shock.shock_pct}% SPY shock` : "SPY shock"}</p>
          <p className="mt-0.5 font-mono text-[15px] font-bold text-td-crit tabular-nums">{shock ? usd(-Math.abs(shock.loss_dollars)) : "—"}</p>
        </div>
      </div>
      {vc?.interpretation && <p className="mt-2 text-[11.5px] text-td-muted leading-snug">{vc.interpretation}</p>}
      {onOpenFull && (
        <button type="button" onClick={onOpenFull} className="mt-2 inline-flex items-center gap-1 text-[11.5px] font-semibold text-td-accent">
          Full risk report <ChevronRight className="h-3.5 w-3.5" />
        </button>
      )}
    </section>
  );
}

/** Book-level regime mix as one thin Up / Neutral / Down strip (TradingView-style), not a pie to hunt for. */
export function PortfolioRegimeStrip({ counts }: { counts: { UP: number; NEUTRAL: number; DOWN: number } | null | undefined }) {
  if (!counts) return null;
  const total = (counts.UP ?? 0) + (counts.NEUTRAL ?? 0) + (counts.DOWN ?? 0);
  if (!total) return null;
  const segs = [
    { k: "Up", n: counts.UP ?? 0, cls: "bg-td-accent", txt: "text-td-accent" },
    { k: "Neutral", n: counts.NEUTRAL ?? 0, cls: "bg-td-warn", txt: "text-td-warn" },
    { k: "Down", n: counts.DOWN ?? 0, cls: "bg-td-crit", txt: "text-td-crit" },
  ];
  return (
    <section className="rounded-2xl border border-td-line bg-td-surface px-4 sm:px-5 py-3.5">
      <h3 className="text-[11.5px] font-semibold uppercase tracking-wider text-td-muted mb-2">Regime mix · {total} holdings</h3>
      <div className="flex h-2 rounded-full overflow-hidden gap-px bg-td-surface2">
        {segs.map((s) => (s.n > 0 ? <div key={s.k} className={s.cls} style={{ flex: s.n }} title={`${s.k}: ${s.n}`} /> : null))}
      </div>
      <div className="mt-2 flex gap-4 text-[11.5px]">
        {segs.map((s) => (
          <span key={s.k} className={s.txt}>
            {s.k} <span className="font-mono font-semibold">{s.n}</span>
          </span>
        ))}
      </div>
    </section>
  );
}
