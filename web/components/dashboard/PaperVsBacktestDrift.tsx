"use client";

/** Paper realized returns vs forward-tracking 20d population baseline (smoke test). */

export type PaperVsBacktestDriftPayload = {
  status?: string;
  paper_completed_n?: number;
  paper_avg_return_pct?: number | null;
  forward_20d_baseline_pct?: number | null;
  forward_20d_n?: number | null;
  drift_vs_forward_pct?: number | null;
  paper_win_rate_pct?: number | null;
  paper_avg_excess_vs_spy_pct?: number | null;
  // Buy-side slice
  buy_signals_avg_return_pct?: number | null;
  buy_signals_n?: number | null;
  forward_buy_baseline_pct?: number | null;
  forward_buy_n?: number | null;
  buy_drift_vs_forward_pct?: number | null;
  message?: string | null;
  note?: string;
};

export function PaperVsBacktestDrift({ drift }: { drift: PaperVsBacktestDriftPayload }) {
  if (!drift || drift.status === undefined) return null;

  return (
    <div className="rounded-lg border border-slate-600/80 bg-slate-800/40 px-3 py-2.5 text-xs text-slate-400 mb-3">
      <p className="text-slate-300 font-medium mb-1">Paper vs forward baseline (20d)</p>
      {drift.message && <p className="text-slate-500 mb-1">{drift.message}</p>}
      {drift.status === "insufficient_paper" &&
        drift.forward_20d_baseline_pct != null &&
        drift.forward_20d_n != null && (
          <p className="text-slate-500 font-mono text-[11px] mb-1">
            Forward-tracking 20d mean:{" "}
            <span className="text-slate-300">{drift.forward_20d_baseline_pct.toFixed(2)}%</span>
            <span className="text-slate-600"> (n={drift.forward_20d_n})</span>
          </p>
        )}
      {drift.status !== "insufficient_paper" && drift.paper_completed_n != null && drift.paper_completed_n >= 3 && (
        <div className="space-y-0.5 font-mono text-[11px]">
          {drift.paper_avg_return_pct != null && (
            <p>
              Paper avg return:{" "}
              <span className="text-slate-200">{drift.paper_avg_return_pct.toFixed(2)}%</span>
              {drift.paper_win_rate_pct != null && (
                <span className="text-slate-500"> · win {drift.paper_win_rate_pct.toFixed(0)}%</span>
              )}
            </p>
          )}
          {drift.forward_20d_baseline_pct != null && (
            <p>
              Forward-tracking 20d mean:{" "}
              <span className="text-slate-200">{drift.forward_20d_baseline_pct.toFixed(2)}%</span>
              {drift.forward_20d_n != null && (
                <span className="text-slate-500"> (n={drift.forward_20d_n})</span>
              )}
            </p>
          )}
          {drift.drift_vs_forward_pct != null && (
            <p>
              Drift (paper − baseline):{" "}
              <span
                className={
                  drift.drift_vs_forward_pct > 1
                    ? "text-emerald-400"
                    : drift.drift_vs_forward_pct < -1
                      ? "text-amber-400"
                      : "text-slate-300"
                }
              >
                {drift.drift_vs_forward_pct >= 0 ? "+" : ""}
                {drift.drift_vs_forward_pct.toFixed(2)}%
              </span>
            </p>
          )}
          {drift.paper_avg_excess_vs_spy_pct != null && (
            <p className="text-slate-500">
              Avg excess vs SPY (paper window): {drift.paper_avg_excess_vs_spy_pct.toFixed(2)}%
            </p>
          )}
          {(drift.buy_signals_avg_return_pct != null || drift.buy_drift_vs_forward_pct != null) && (
            <div className="mt-1.5 pt-1.5 border-t border-slate-700/50 space-y-0.5">
              <p className="text-slate-500">Buy-side only (BUY / HOLD/ADD):</p>
              {drift.buy_signals_avg_return_pct != null && (
                <p>
                  Paper avg:{" "}
                  <span className="text-slate-200">{drift.buy_signals_avg_return_pct.toFixed(2)}%</span>
                  {drift.buy_signals_n != null && (
                    <span className="text-slate-500"> (n={drift.buy_signals_n})</span>
                  )}
                </p>
              )}
              {drift.forward_buy_baseline_pct != null && (
                <p>
                  Forward HOLD/ADD baseline:{" "}
                  <span className="text-slate-200">{drift.forward_buy_baseline_pct.toFixed(2)}%</span>
                  {drift.forward_buy_n != null && (
                    <span className="text-slate-500"> (n={drift.forward_buy_n})</span>
                  )}
                </p>
              )}
              {drift.buy_drift_vs_forward_pct != null && (
                <p>
                  Drift:{" "}
                  <span
                    className={
                      drift.buy_drift_vs_forward_pct > 1
                        ? "text-emerald-400"
                        : drift.buy_drift_vs_forward_pct < -1
                          ? "text-amber-400"
                          : "text-slate-300"
                    }
                  >
                    {drift.buy_drift_vs_forward_pct >= 0 ? "+" : ""}
                    {drift.buy_drift_vs_forward_pct.toFixed(2)}%
                  </span>
                </p>
              )}
            </div>
          )}
        </div>
      )}
      {drift.note && <p className="text-slate-600 mt-2 leading-snug">{drift.note}</p>}
    </div>
  );
}
