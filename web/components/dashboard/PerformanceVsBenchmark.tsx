"use client";

import { BarChart3 } from "lucide-react";

interface PeriodRow {
  period: string;
  portfolio_pct: number | null;
  spy_pct: number | null;
  qqq_pct: number | null;
  vs_spy: number | null;
  vs_qqq: number | null;
}

interface Props {
  periods: PeriodRow[];
  message?: string | null;
  as_of?: string | null;
}

function fmt(pct: number | null): string {
  if (pct == null) return "—";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function cellClass(pct: number | null): string {
  if (pct == null) return "text-slate-500";
  return pct >= 0 ? "text-emerald-400" : "text-red-400";
}

export function PerformanceVsBenchmark({ periods, message, as_of }: Props) {
  if (!periods?.length && message) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4">
        <p className="text-sm font-medium text-slate-400 mb-1">Performance vs benchmark</p>
        <p className="text-slate-500 text-sm">{message}</p>
      </div>
    );
  }

  if (!periods?.length) {
    return null;
  }

  /** Hide 1y row when portfolio return is missing — avoids "—" next to live SPY/QQQ. */
  const displayPeriods = periods.filter((p) => {
    const isLong = /^1\s*y/i.test(p.period.trim()) || p.period.toLowerCase().includes("1 year");
    if (isLong && p.portfolio_pct == null) return false;
    return true;
  });

  const hiddenLong = periods.length > displayPeriods.length;

  if (displayPeriods.length === 0) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4">
        <p className="text-sm font-medium text-slate-400 mb-1">Performance vs benchmark</p>
        <p className="text-slate-500 text-sm">
          {message ?? "Not enough portfolio history yet for period comparisons."}
          {as_of ? ` Tracking since ${new Date(as_of).toLocaleDateString()}.` : ""}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4">
      <div className="flex items-center gap-2 mb-3">
        <BarChart3 className="h-4 w-4 text-emerald-400 shrink-0" />
        <p className="text-sm font-medium text-slate-300">Performance vs benchmark</p>
        {as_of && <span className="text-xs text-slate-500 ml-auto">As of {new Date(as_of).toLocaleDateString()}</span>}
      </div>
      <p className="text-xs text-slate-500 mb-3" title="Portfolio total return vs SPY (S&P 500) and QQQ (Nasdaq 100). vs SPY = portfolio − SPY.">
        Total return over period. Positive vs SPY/QQQ = outperformed.
      </p>
      {hiddenLong && (
        <p className="text-[11px] text-slate-500 mb-2">
          1-year portfolio return hidden until enough history
          {as_of ? ` (tracking since ${new Date(as_of).toLocaleDateString()})` : ""}.
        </p>
      )}
      {/* Mobile: card per period */}
      <div className="md:hidden space-y-3">
        {displayPeriods.map((p) => (
          <div key={p.period} className="rounded-lg border border-slate-600/80 bg-slate-800/50 p-3 text-sm">
            <div className="font-medium text-slate-300 border-b border-slate-600/80 pb-2 mb-2">{p.period}</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              <span className="text-slate-500">Portfolio</span>
              <span className={cellClass(p.portfolio_pct)}>{fmt(p.portfolio_pct)}</span>
              <span className="text-slate-500">SPY</span>
              <span className={cellClass(p.spy_pct)}>{fmt(p.spy_pct)}</span>
              <span className="text-slate-500">QQQ</span>
              <span className={cellClass(p.qqq_pct)}>{fmt(p.qqq_pct)}</span>
              <span className="text-slate-500">vs SPY</span>
              <span className={cellClass(p.vs_spy)}>{fmt(p.vs_spy)}</span>
              <span className="text-slate-500">vs QQQ</span>
              <span className={cellClass(p.vs_qqq)}>{fmt(p.vs_qqq)}</span>
            </div>
          </div>
        ))}
      </div>
      {/* Desktop: table */}
      <div className="hidden md:block overflow-x-auto [-webkit-overflow-scrolling:touch]">
        <table className="w-full text-sm text-left min-w-[480px]">
          <thead>
            <tr className="text-slate-500 border-b border-slate-600">
              <th className="py-1.5 pr-3 font-medium">Period</th>
              <th className="py-1.5 pr-3 font-medium">Portfolio</th>
              <th className="py-1.5 pr-3 font-medium">SPY</th>
              <th className="py-1.5 pr-3 font-medium">QQQ</th>
              <th className="py-1.5 pr-2 font-medium">vs SPY</th>
              <th className="py-1.5 pr-2 font-medium">vs QQQ</th>
            </tr>
          </thead>
          <tbody>
            {displayPeriods.map((p) => (
              <tr key={p.period} className="border-b border-slate-700/50">
                <td className="py-2 pr-3 font-medium text-slate-300">{p.period}</td>
                <td className={`py-2 pr-3 ${cellClass(p.portfolio_pct)}`}>{fmt(p.portfolio_pct)}</td>
                <td className={`py-2 pr-3 ${cellClass(p.spy_pct)}`}>{fmt(p.spy_pct)}</td>
                <td className={`py-2 pr-3 ${cellClass(p.qqq_pct)}`}>{fmt(p.qqq_pct)}</td>
                <td className={`py-2 pr-2 ${cellClass(p.vs_spy)}`}>{fmt(p.vs_spy)}</td>
                <td className={`py-2 pr-2 ${cellClass(p.vs_qqq)}`}>{fmt(p.vs_qqq)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
