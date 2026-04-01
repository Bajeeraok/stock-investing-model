"use client";

import type { PortfolioRiskMetrics } from "@/app/page";

function topCorrelationPairs(
  matrix: Record<string, Record<string, number>> | undefined,
  limit = 6,
): { a: string; b: string; rho: number }[] {
  if (!matrix || typeof matrix !== "object") return [];
  const pairs: { a: string; b: string; rho: number }[] = [];
  const rows = Object.keys(matrix);
  for (const a of rows) {
    const row = matrix[a];
    if (!row || typeof row !== "object") continue;
    for (const b of Object.keys(row)) {
      if (a >= b) continue;
      const rho = row[b];
      if (typeof rho === "number" && !Number.isNaN(rho)) {
        pairs.push({ a, b, rho });
      }
    }
  }
  pairs.sort((x, y) => Math.abs(y.rho) - Math.abs(x.rho));
  return pairs.slice(0, limit);
}

export function PortfolioRiskMetricsPanel({ metrics }: { metrics: PortfolioRiskMetrics | null | undefined }) {
  if (!metrics || typeof metrics !== "object") {
    return (
      <p className="text-sm text-slate-500">
        No portfolio risk metrics yet. Add at least two holdings with price history to see correlation, VaR, and sizing hints.
      </p>
    );
  }

  const err = metrics.correlation_error;
  const vc = metrics.var_cvar;
  const vcErr = vc && typeof vc === "object" && "error" in vc ? (vc as { error?: string }).error : undefined;
  const sizes = metrics.correlation_adjusted_sizes;
  const pairs = topCorrelationPairs(metrics.correlation_matrix);
  const hasAny =
    pairs.length > 0 ||
    (vc && !vcErr && typeof vc === "object" && "var_95_10day_pct" in vc) ||
    (sizes && Object.keys(sizes).length > 0);

  if (!hasAny && !err) {
    return (
      <p className="text-sm text-slate-500">
        Portfolio risk metrics are empty. Check that holdings have overlapping return history.
      </p>
    );
  }

  const varPct =
    vc && typeof vc === "object" && "var_95_10day_pct" in vc
      ? (vc as { var_95_10day_pct?: number }).var_95_10day_pct
      : undefined;
  const cvarPct =
    vc && typeof vc === "object" && "cvar_95_10day_pct" in vc
      ? (vc as { cvar_95_10day_pct?: number }).cvar_95_10day_pct
      : undefined;

  return (
    <div className="space-y-4 text-sm">
      {metrics.note && (
        <p className="text-xs text-slate-500 border border-slate-700/60 rounded-lg px-3 py-2 bg-slate-800/40">{metrics.note}</p>
      )}
      {err && (
        <p className="text-xs text-amber-400/90">Correlation: {err}</p>
      )}
      {vcErr && (
        <p className="text-xs text-amber-400/90">VaR/CVaR: {vcErr}</p>
      )}
      {(varPct != null || cvarPct != null) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="rounded-lg border border-slate-700/60 bg-slate-800/30 px-3 py-2">
            <p className="text-[10px] uppercase tracking-wide text-slate-500">95% VaR (10d, hist.)</p>
            <p className="text-lg font-semibold text-slate-200 tabular-nums">{varPct != null ? `${varPct}%` : "—"}</p>
            <p className="text-[11px] text-slate-500 mt-1">Equal-weight illustrative; negative = loss tail.</p>
          </div>
          <div className="rounded-lg border border-slate-700/60 bg-slate-800/30 px-3 py-2">
            <p className="text-[10px] uppercase tracking-wide text-slate-500">95% CVaR (10d)</p>
            <p className="text-lg font-semibold text-slate-200 tabular-nums">{cvarPct != null ? `${cvarPct}%` : "—"}</p>
            <p className="text-[11px] text-slate-500 mt-1">Expected shortfall in the tail.</p>
          </div>
        </div>
      )}
      {pairs.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-400 mb-2">Largest pairwise correlations</p>
          <ul className="space-y-1">
            {pairs.map(({ a, b, rho }) => (
              <li
                key={`${a}-${b}`}
                className="flex justify-between gap-2 text-slate-300 font-mono text-xs border-b border-slate-700/40 pb-1 last:border-0"
              >
                <span>
                  {a} <span className="text-slate-600">↔</span> {b}
                </span>
                <span className={rho >= 0 ? "text-emerald-400/90" : "text-rose-400/90"}>{rho.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {sizes && Object.keys(sizes).length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-400 mb-2">Correlation-adjusted size weights (illustrative)</p>
          <p className="text-[11px] text-slate-500 mb-2">
            Base Kelly fractions are scaled down when names move together; combine with your own risk budget.
          </p>
          <div className="max-h-40 overflow-y-auto rounded border border-slate-700/50">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-700/60">
                  <th className="px-2 py-1.5 font-medium">Ticker</th>
                  <th className="px-2 py-1.5 font-medium text-right">Weight</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(sizes)
                  .sort((x, y) => y[1] - x[1])
                  .map(([t, w]) => (
                    <tr key={t} className="border-b border-slate-800/80 last:border-0">
                      <td className="px-2 py-1.5 font-mono text-slate-300">{t}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-slate-200">{(w * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
