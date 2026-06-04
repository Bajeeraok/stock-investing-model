"use client";

import type { BacktestResult } from "@/app/page";

function fmt(v: number | null | undefined, suffix = "%"): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v}${suffix}`;
}

function CohortTable({
  title,
  data,
}: {
  title: string;
  data?: Record<string, { n?: number; mean_fwd_pct?: number | null; hit_rate_pct?: number | null }>;
}) {
  if (!data) return null;
  const rows = Object.entries(data);
  if (!rows.length) return null;
  return (
    <div className="rounded-lg border border-slate-700/60 bg-slate-900/40 p-3">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">{title}</p>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500 text-left">
            <th className="py-1 pr-2 font-medium">Cohort</th>
            <th className="py-1 pr-2 font-medium">N</th>
            <th className="py-1 pr-2 font-medium">Avg fwd</th>
            <th className="py-1 font-medium">Hit</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, row]) => (
            <tr key={name} className="border-t border-slate-800/80 text-slate-300">
              <td className="py-1 pr-2 font-mono text-[10px]">{name.replace(/_/g, " ")}</td>
              <td className="py-1 pr-2 tabular-nums">{row.n ?? "—"}</td>
              <td className="py-1 pr-2 tabular-nums text-emerald-300/90">
                {row.mean_fwd_pct != null ? fmt(row.mean_fwd_pct) : "—"}
              </td>
              <td className="py-1 tabular-nums">{row.hit_rate_pct != null ? `${row.hit_rate_pct}%` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BacktestTierPanels({ result }: { result: BacktestResult }) {
  const tier = result.tier_enhancements;
  const kpis = result.primary_kpis;
  if (!tier && !kpis) return null;
  if (tier?.error) {
    return (
      <p className="px-4 py-2 text-xs text-amber-400/90 border-t border-slate-700/60">
        Tier enhancements unavailable: {tier.error}
      </p>
    );
  }

  const gate = tier?.gate_backtest;
  const rule = tier?.rule_strategy;
  const exit = tier?.exit_backtest;
  const byRegime = tier?.by_regime;
  const thresh = tier?.per_ticker_threshold;

  return (
    <div className="px-4 py-3 border-t border-slate-700/60 space-y-3 bg-slate-950/30">
      {kpis && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-wider text-emerald-400/80 font-semibold mb-1">
            Primary KPIs (tier 3)
          </p>
          <p className="text-sm font-medium text-emerald-100">{kpis.headline}</p>
          <p className="text-xs text-slate-400 mt-1 leading-snug">
            Confidence: <span className="text-slate-200">{kpis.confidence_band}</span>
            {kpis.recommended_horizon_months != null && (
              <> · Prefer <span className="text-slate-200">{kpis.recommended_horizon_months}m</span> horizon</>
            )}
          </p>
          {kpis.calibration_note && (
            <p className="text-[11px] text-slate-500 mt-1 leading-snug">{kpis.calibration_note}</p>
          )}
        </div>
      )}

      {rule?.non_overlapping && (
        <div className="rounded-lg border border-sky-500/25 bg-sky-950/15 px-3 py-2.5 text-xs text-slate-300 space-y-1">
          <p className="text-[10px] uppercase tracking-wider text-sky-400 font-semibold">
            Rule strategy (tier 1) — non-overlapping
          </p>
          <p className="text-slate-400 leading-snug">{rule.entry_rule}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 tabular-nums">
            <span>Trades: {rule.non_overlapping.n ?? 0}</span>
            <span>Avg: {fmt(rule.non_overlapping.avg_return_pct)}</span>
            <span>Hit: {rule.non_overlapping.hit_rate_pct != null ? `${rule.non_overlapping.hit_rate_pct}%` : "—"}</span>
            <span>Strategy CAGR: {fmt(rule.non_overlapping.strategy_cagr_pct)}</span>
            <span>B&amp;H CAGR: {fmt(rule.non_overlapping.buy_hold_cagr_pct)}</span>
            <span className="text-sky-300">
              Alpha: {fmt(rule.non_overlapping.alpha_vs_buy_hold_cagr_pct)}
            </span>
          </div>
        </div>
      )}

      {gate?.by_horizon_trading_days?.["63"] && (
        <CohortTable title="Gate cohorts @ 63d (tier 1 — question B)" data={gate.by_horizon_trading_days["63"]} />
      )}

      {exit && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-950/10 px-3 py-2 text-xs text-slate-300 space-y-1">
          <p className="text-[10px] uppercase tracking-wider text-amber-400/90 font-semibold">
            Exit / trim validation (tier 1) — score ≤ {exit.sell_max}
          </p>
          <p>
            3m avg when low score: {fmt(exit.sell_avg_fwd_3m_pct)} · unconditional:{" "}
            {fmt(exit.unconditional_avg_fwd_3m_pct)} · hit:{" "}
            {exit.sell_precision_3m_pct != null ? `${exit.sell_precision_3m_pct}%` : "—"}
          </p>
          {exit.notes?.[0] && <p className="text-slate-500 leading-snug">{exit.notes[0]}</p>}
        </div>
      )}

      {byRegime && Object.keys(byRegime).length > 0 && (
        <div className="rounded-lg border border-slate-700/60 bg-slate-900/40 px-3 py-2 text-xs">
          <p className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold mb-2">
            By market regime @ 6m (tier 2)
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {Object.entries(byRegime).map(([reg, block]) => (
              <div key={reg} className="text-slate-300">
                <span className="font-medium capitalize text-slate-200">{reg}</span>
                {" · dip "}
                {fmt(block.dip_bucket_6m?.avg_return_pct)}
                {" · mom "}
                {fmt(block.momentum_bucket_6m?.avg_return_pct)}
                {block.mr_spread_6m_edge_pct != null && (
                  <span className="text-emerald-400/90"> · spread {fmt(block.mr_spread_6m_edge_pct)}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {thresh && (
        <div className="text-xs text-slate-400 leading-snug">
          <span className="text-slate-300 font-medium">Threshold hint (tier 2):</span> buy_min={thresh.suggested_buy_min}{" "}
          · sell_max={thresh.suggested_sell_max}
          {thresh.notes?.[0] && <> — {thresh.notes[0]}</>}
        </div>
      )}

      {tier?.forward_tracking?.note && (
        <p className="text-[11px] text-slate-500 leading-snug border-t border-slate-800 pt-2">
          <span className="text-slate-400">Live (tier 3 / Q-C):</span> {tier.forward_tracking.note}
        </p>
      )}

      {tier?.regime_gate_proxy_note && (
        <p className="text-[10px] text-slate-600 leading-snug">{tier.regime_gate_proxy_note}</p>
      )}
    </div>
  );
}
