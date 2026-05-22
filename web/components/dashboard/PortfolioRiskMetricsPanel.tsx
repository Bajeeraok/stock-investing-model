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

const BAND_TONE: Record<string, string> = {
  low: "text-sky-300",
  "moderate-low": "text-emerald-300",
  neutral: "text-slate-200",
  "moderate-high": "text-amber-300",
  high: "text-rose-300",
};

const BAND_RING: Record<string, string> = {
  low: "stroke-sky-400",
  "moderate-low": "stroke-emerald-400",
  neutral: "stroke-slate-300",
  "moderate-high": "stroke-amber-400",
  high: "stroke-rose-400",
};

function BetaGauge({ beta, benchmark = "SPY" }: { beta: number; benchmark?: string }) {
  const maxScale = 2.0;
  const pct = Math.min(100, Math.max(0, (beta / maxScale) * 100));
  const marketPct = (1.0 / maxScale) * 100;
  const tone =
    beta < 0.85 ? "moderate-low" : beta <= 1.15 ? "neutral" : beta <= 1.45 ? "moderate-high" : "high";

  return (
    <div className="space-y-2">
      <div className="relative h-3 rounded-full bg-slate-700/60 overflow-hidden">
        <div
          className={`absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-emerald-500/40 via-amber-500/50 to-rose-500/60`}
          style={{ width: `${pct}%` }}
        />
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-slate-400/90"
          style={{ left: `${marketPct}%` }}
          title={`${benchmark} ≈ 1.0×`}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white shadow ring-2 ring-slate-900"
          style={{ left: `calc(${pct}% - 6px)` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-slate-500 tabular-nums">
        <span>0×</span>
        <span>{benchmark} 1.0×</span>
        <span>2.0×</span>
      </div>
      <p className={`text-xs font-medium ${BAND_TONE[tone] ?? "text-slate-300"}`}>
        {beta.toFixed(2)}× vs {benchmark}
      </p>
    </div>
  );
}

function RiskMeter({ label, valuePct, sublabel }: { label: string; valuePct: number; sublabel?: string }) {
  const magnitude = Math.min(100, Math.abs(valuePct) * 4);
  const isLoss = valuePct < 0;
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-800/40 px-4 py-3">
      <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`text-2xl font-bold tabular-nums mt-1 ${isLoss ? "text-rose-300" : "text-slate-200"}`}>
        {valuePct}%
      </p>
      <div className="mt-2 h-2 rounded-full bg-slate-700/50 overflow-hidden">
        <div
          className={`h-full rounded-full ${isLoss ? "bg-rose-500/70" : "bg-slate-500/60"}`}
          style={{ width: `${magnitude}%` }}
        />
      </div>
      {sublabel && <p className="text-[11px] text-slate-500 mt-1.5">{sublabel}</p>}
    </div>
  );
}

function BetaHero({ beta }: { beta: NonNullable<PortfolioRiskMetrics["beta"]> }) {
  if (beta.portfolio_beta == null) return null;
  const pb = beta.portfolio_beta;
  const tone = beta.band_tone ?? "neutral";

  return (
    <div className="rounded-xl border border-emerald-500/25 bg-gradient-to-br from-slate-800/80 to-slate-900/60 p-4 sm:p-5">
      <div className="flex flex-col lg:flex-row gap-5 lg:items-center">
        <div className="flex items-center gap-4 shrink-0">
          <div className="relative w-24 h-24">
            <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
              <circle cx="18" cy="18" r="15.5" fill="none" className="stroke-slate-700/80" strokeWidth="3" />
              <circle
                cx="18"
                cy="18"
                r="15.5"
                fill="none"
                className={BAND_RING[tone] ?? "stroke-emerald-400"}
                strokeWidth="3"
                strokeDasharray={`${Math.min(100, (pb / 2) * 100)} 100`}
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-xl font-bold text-slate-100 tabular-nums">{pb.toFixed(1)}×</span>
              <span className="text-[9px] uppercase text-slate-500 tracking-wide">beta</span>
            </div>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-100 leading-snug">
              {beta.headline ?? `Your portfolio moves ${pb.toFixed(1)}× the market.`}
            </p>
            {beta.band && (
              <span className="inline-flex mt-2 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-slate-700/60 text-slate-300">
                {beta.band}
              </span>
            )}
            {beta.coverage_pct != null && beta.coverage_pct < 100 && (
              <p className="text-[11px] text-amber-400/90 mt-2">
                Beta known for {beta.coverage_pct.toFixed(0)}% of portfolio weight
              </p>
            )}
          </div>
        </div>
        <div className="flex-1 min-w-0">
          <BetaGauge beta={pb} benchmark={beta.benchmark ?? "SPY"} />
        </div>
      </div>
    </div>
  );
}

export function PortfolioRiskMetricsPanel({ metrics }: { metrics: PortfolioRiskMetrics | null | undefined }) {
  if (!metrics || typeof metrics !== "object") {
    return (
      <p className="text-sm text-slate-500">
        No portfolio risk metrics yet. Add holdings with price history to see beta, correlation, and VaR.
      </p>
    );
  }

  const err = metrics.correlation_error;
  const vc = metrics.var_cvar;
  const vcErr = vc && typeof vc === "object" && "error" in vc ? (vc as { error?: string }).error : undefined;
  const sizes = metrics.correlation_adjusted_sizes;
  const pairs = topCorrelationPairs(metrics.correlation_matrix);
  const beta = metrics.beta;

  const varPct =
    vc && typeof vc === "object" && "var_95_10day_pct" in vc
      ? (vc as { var_95_10day_pct?: number }).var_95_10day_pct
      : undefined;
  const cvarPct =
    vc && typeof vc === "object" && "cvar_95_10day_pct" in vc
      ? (vc as { cvar_95_10day_pct?: number }).cvar_95_10day_pct
      : undefined;

  const hasAny =
    beta?.portfolio_beta != null ||
    pairs.length > 0 ||
    (vc && !vcErr && typeof vc === "object" && "var_95_10day_pct" in vc) ||
    (sizes && Object.keys(sizes).length > 0);

  if (!hasAny && !err && !beta?.error) {
    return (
      <p className="text-sm text-slate-500">
        Portfolio risk metrics are empty. Check that holdings have overlapping return history.
      </p>
    );
  }

  const topHoldings = (beta?.holdings ?? []).filter((h) => h.beta != null).slice(0, 8);
  const sectors = beta?.sectors ?? [];

  return (
    <div className="space-y-5 text-sm">
      {metrics.note && (
        <p className="text-xs text-slate-500 border border-slate-700/60 rounded-lg px-3 py-2 bg-slate-800/40">{metrics.note}</p>
      )}

      {beta?.portfolio_beta != null && <BetaHero beta={beta} />}
      {beta?.error && !beta.portfolio_beta && (
        <p className="text-xs text-amber-400/90">Beta: {beta.error}</p>
      )}

      {(varPct != null || cvarPct != null) && (
        <div>
          <p className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">Tail risk (10-day, historical)</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {varPct != null && (
              <RiskMeter label="95% VaR" valuePct={varPct} sublabel="Illustrative equal-weight book; negative = loss tail." />
            )}
            {cvarPct != null && (
              <RiskMeter label="95% CVaR" valuePct={cvarPct ?? 0} sublabel="Average loss beyond the VaR cutoff." />
            )}
          </div>
        </div>
      )}

      {sectors.length > 0 && sectors.some((s) => s.beta != null) && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-4">
          <p className="text-xs font-medium text-slate-400 mb-3">Sector beta vs {beta?.benchmark ?? "SPY"}</p>
          <div className="space-y-2.5">
            {sectors
              .filter((s) => s.beta != null)
              .slice(0, 6)
              .map((s) => (
                <div key={s.sector} className="flex items-center gap-3">
                  <span className="w-28 sm:w-36 text-xs text-slate-400 truncate" title={s.sector}>
                    {s.sector}
                  </span>
                  <div className="flex-1 h-2 rounded-full bg-slate-700/50 overflow-hidden relative">
                    <div
                      className={`h-full rounded-full ${
                        (s.beta ?? 1) > 1.2 ? "bg-amber-500/70" : (s.beta ?? 1) < 0.85 ? "bg-sky-500/60" : "bg-emerald-500/60"
                      }`}
                      style={{ width: `${Math.min(100, ((s.beta ?? 0) / 2) * 100)}%` }}
                    />
                    <div className="absolute top-0 bottom-0 w-px bg-slate-400/50" style={{ left: "50%" }} />
                  </div>
                  <span className="w-14 text-right text-xs font-mono tabular-nums text-slate-200">
                    {(s.beta ?? 0).toFixed(2)}×
                  </span>
                  <span className="w-12 text-right text-[10px] text-slate-500 tabular-nums">{s.weight_pct}%</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {topHoldings.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-4">
          <p className="text-xs font-medium text-slate-400 mb-3">Largest beta contributors</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {topHoldings.map((h) => (
              <div
                key={h.ticker}
                className="flex items-center justify-between gap-2 rounded-lg border border-slate-700/40 bg-slate-900/50 px-3 py-2"
              >
                <div className="min-w-0">
                  <span className="font-mono text-sm text-emerald-400/90">{h.ticker}</span>
                  <span className="text-[10px] text-slate-500 ml-2">{h.weight_pct}%</span>
                </div>
                <span
                  className={`text-sm font-semibold tabular-nums ${
                    (h.beta ?? 1) > 1.3 ? "text-amber-300" : (h.beta ?? 1) < 0.8 ? "text-sky-300" : "text-slate-200"
                  }`}
                >
                  {h.beta?.toFixed(2)}×
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {err && <p className="text-xs text-amber-400/90">Correlation: {err}</p>}
      {vcErr && <p className="text-xs text-amber-400/90">VaR/CVaR: {vcErr}</p>}

      {pairs.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-4">
          <p className="text-xs font-medium text-slate-400 mb-2">Largest pairwise correlations</p>
          <ul className="space-y-1.5">
            {pairs.map(({ a, b, rho }) => (
              <li key={`${a}-${b}`} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-slate-300 shrink-0">
                  {a} ↔ {b}
                </span>
                <div className="flex-1 h-1.5 rounded-full bg-slate-700/50 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${rho >= 0 ? "bg-emerald-500/60" : "bg-rose-500/60"}`}
                    style={{ width: `${Math.abs(rho) * 100}%` }}
                  />
                </div>
                <span className={`w-10 text-right tabular-nums ${rho >= 0 ? "text-emerald-400/90" : "text-rose-400/90"}`}>
                  {rho.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {sizes && Object.keys(sizes).length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-400 mb-2">Correlation-adjusted size weights (illustrative)</p>
          <p className="text-[11px] text-slate-500 mb-2">
            Base Kelly fractions scaled down when names move together.
          </p>
          <div className="max-h-40 overflow-y-auto rounded-lg border border-slate-700/50">
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
