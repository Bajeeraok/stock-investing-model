"use client";
import React from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

interface CalibrationBucket {
  label: string;
  predicted_avg: number;
  actual_win_rate: number;
  count: number;
  avg_return_pct: number;
}

interface CalibrationData {
  buckets: CalibrationBucket[];
  total_observations: number;
  is_well_calibrated: boolean;
  calibration_error: number | null;
  monotonic: boolean;
  note: string;
}

interface PaperTradingSummary {
  completed_n?: number;
  win_rate_pct?: number | null;
  avg_return_pct?: number | null;
  avg_win_pct?: number | null;
  avg_loss_pct?: number | null;
  avg_excess_vs_spy_pct?: number | null;
  buy_signals_summary?: {
    completed_n?: number;
    win_rate_pct?: number | null;
  } | null;
}

interface ForwardSummary {
  [signal: string]: {
    avg_return_20d_pct?: number;
    n_observations?: number;
    hit_rate_pct?: number;
  };
}

interface ModelHealth {
  forward_hold_add_hit_rate_20d?: number | null;
  forward_observations_20d?: number | null;
  validation_direction_accuracy_pct?: number | null;
  calibration_ok?: boolean | null;
  calibration_score?: number | null;
  walk_forward_ok?: boolean | null;
}

interface EquityPoint {
  date: string;
  ticker?: string;
  equity_index?: number;
  cumulative_return_pct?: number;
  trade_n?: number;
}

interface AuditOutcomeSummary {
  resolved_n?: number;
  events_total?: number;
  win_rate_pct?: number | null;
  pending_n?: number;
}

interface Props {
  calibration?: CalibrationData | null;
  paperTrading?: PaperTradingSummary | null;
  forwardSummary?: ForwardSummary | null;
  summaryByLens?: import("@/lib/forwardTrackingLens").SummaryByLens | null;
  activeLens?: import("@/lib/tradingLens").TradingLens;
  modelHealth?: ModelHealth | null;
  /** Completed paper trades — cumulative equity index (starts 100) from dashboard API */
  equityCurve?: EquityPoint[] | null;
  /** 100-ticker cohort audit outcomes (Phase 2+) */
  auditOutcomeSummary?: AuditOutcomeSummary | null;
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-0.5">{label}</p>
      <p className={`text-lg font-semibold ${color || "text-slate-100"}`}>{value}</p>
      {sub && <p className="text-[10px] text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}

function CalibrationChart({ buckets }: { buckets: CalibrationBucket[] }) {
  if (!buckets.length) return null;
  const maxRate = Math.max(...buckets.map((b) => Math.max(b.predicted_avg, b.actual_win_rate)), 100);

  return (
    <div className="mt-3">
      <p className="text-[11px] text-slate-400 mb-2 font-medium">Reliability Diagram</p>
      <div className="space-y-1.5">
        {buckets.map((b) => (
          <div key={b.label} className="flex items-center gap-2 text-[10px]">
            <span className="w-14 text-slate-400 text-right shrink-0">{b.label}</span>
            <div className="flex-1 flex flex-col gap-0.5">
              <div className="flex items-center gap-1">
                <div
                  className="h-2.5 rounded-sm bg-slate-600/80"
                  style={{ width: `${(b.predicted_avg / maxRate) * 100}%` }}
                  title={`Predicted: ${b.predicted_avg}%`}
                />
                <span className="text-slate-500">{b.predicted_avg}%</span>
              </div>
              <div className="flex items-center gap-1">
                <div
                  className={`h-2.5 rounded-sm ${
                    b.actual_win_rate >= b.predicted_avg - 10
                      ? "bg-emerald-500/70"
                      : "bg-red-500/70"
                  }`}
                  style={{ width: `${(b.actual_win_rate / maxRate) * 100}%` }}
                  title={`Actual: ${b.actual_win_rate}%`}
                />
                <span className="text-slate-400">{b.actual_win_rate}%</span>
              </div>
            </div>
            <span className="w-8 text-slate-500 text-right shrink-0">n={b.count}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-4 mt-2 text-[9px] text-slate-500">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-2 rounded-sm bg-slate-600/80" /> Predicted
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-2 rounded-sm bg-emerald-500/70" /> Actual win rate
        </span>
      </div>
    </div>
  );
}

export default function TrackRecordPanel({
  calibration,
  paperTrading,
  forwardSummary,
  summaryByLens,
  activeLens = "scout",
  modelHealth,
  equityCurve,
  auditOutcomeSummary,
}: Props) {
  const hasCalibration = calibration && calibration.buckets && calibration.buckets.length > 0;
  const hasPaper = paperTrading && paperTrading.completed_n != null && paperTrading.completed_n > 0;
  const hasForward = forwardSummary && Object.keys(forwardSummary).length > 0;
  const hasEquity = equityCurve && equityCurve.length >= 2;
  const hasAudit = (auditOutcomeSummary?.resolved_n ?? 0) > 0;

  const winRate = paperTrading?.win_rate_pct;
  const avgReturn = paperTrading?.avg_return_pct;
  const dirAccuracy = modelHealth?.validation_direction_accuracy_pct;
  const fwdHitRate = modelHealth?.forward_hold_add_hit_rate_20d;
  const auditWin = auditOutcomeSummary?.win_rate_pct;

  if (!hasCalibration && !hasPaper && !hasForward && !hasEquity && !dirAccuracy && !fwdHitRate && !hasAudit) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-4 text-center">
        <p className="text-sm text-slate-400">
          No track record data yet. Run the model daily and log paper trades to build history.
        </p>
        <p className="text-xs text-slate-500 mt-1">
          Forward tracking, paper trades, and EOD snapshots all contribute to the reliability diagram.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Key metrics strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {winRate != null && (
          <StatCard
            label="Paper trade win rate"
            value={`${winRate.toFixed(1)}%`}
            sub={`${paperTrading!.completed_n} trades`}
            color={winRate >= 55 ? "text-emerald-400" : winRate >= 45 ? "text-yellow-400" : "text-red-400"}
          />
        )}
        {avgReturn != null && (
          <StatCard
            label="Avg return per trade"
            value={`${avgReturn >= 0 ? "+" : ""}${avgReturn.toFixed(2)}%`}
            color={avgReturn >= 0 ? "text-emerald-400" : "text-red-400"}
          />
        )}
        {dirAccuracy != null && (
          <StatCard
            label="Direction accuracy"
            value={`${dirAccuracy.toFixed(1)}%`}
            sub="Model validation"
            color={dirAccuracy >= 55 ? "text-emerald-400" : dirAccuracy >= 50 ? "text-yellow-400" : "text-red-400"}
          />
        )}
        {fwdHitRate != null && (
          <StatCard
            label="HOLD/ADD 20d hit rate"
            value={`${fwdHitRate.toFixed(1)}%`}
            sub={`${modelHealth?.forward_observations_20d ?? 0} obs`}
            color={fwdHitRate >= 55 ? "text-emerald-400" : "text-yellow-400"}
          />
        )}
        {auditWin != null && (
          <StatCard
            label="Cohort audit win rate"
            value={`${auditWin.toFixed(1)}%`}
            sub={`${auditOutcomeSummary!.resolved_n}/${auditOutcomeSummary!.events_total} resolved`}
            color={auditWin >= 55 ? "text-emerald-400" : auditWin >= 45 ? "text-yellow-400" : "text-red-400"}
          />
        )}
      </div>

      {summaryByLens && Object.keys(summaryByLens).length > 0 && (
        <div className="rounded-lg border border-violet-500/20 bg-violet-950/10 px-3 py-2">
          <p className="text-[11px] text-violet-300/90 font-medium mb-1.5">Calibration by lens (forward EOD pairs)</p>
          <div className="grid gap-1.5 sm:grid-cols-3 text-[10px]">
            {(["scout", "swing", "owner"] as const).map((lens) => {
              const row = summaryByLens[lens];
              const active = lens === activeLens;
              return (
                <div
                  key={lens}
                  className={`rounded px-2 py-1.5 border ${
                    active ? "border-violet-400/40 bg-violet-500/10" : "border-slate-700/50 bg-slate-900/30"
                  }`}
                >
                  <span className="uppercase tracking-wide text-slate-400">{lens}</span>
                  <p className="text-slate-200 mt-0.5">{row?.label || "Insufficient EOD history"}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Cumulative paper-trade equity (compounded by completed trade returns) */}
      {hasEquity && (
        <div>
          <p className="text-[11px] text-slate-400 mb-1 font-medium">Paper trade equity curve</p>
          <p className="text-[10px] text-slate-500 mb-2">
            Index starts at 100; each completed trade updates by (1 + return%). Chronological by exit date.
          </p>
          <div className="h-[200px] w-full min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={equityCurve!} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 9, fill: "#94a3b8" }}
                  tickFormatter={(v) => (typeof v === "string" && v.length >= 10 ? v.slice(5) : String(v))}
                  interval="preserveStartEnd"
                />
                <YAxis
                  dataKey="equity_index"
                  tick={{ fontSize: 9, fill: "#94a3b8" }}
                  domain={["auto", "auto"]}
                  width={42}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #475569", fontSize: 11 }}
                  formatter={(value: number) => [value?.toFixed?.(2) ?? value, "Equity index"]}
                  labelFormatter={(label) => `Exit ${label}`}
                />
                <Line type="monotone" dataKey="equity_index" stroke="#34d399" strokeWidth={2} dot={false} name="Equity" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Signal breakdown from forward tracking */}
      {hasForward && (
        <div>
          <p className="text-[11px] text-slate-400 mb-1.5 font-medium">Signal performance (20-day forward)</p>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px] text-left border-collapse">
              <thead>
                <tr className="text-slate-500 border-b border-slate-700">
                  <th className="py-1.5 pr-3 font-medium">Signal</th>
                  <th className="py-1.5 pr-3 font-medium text-right">Avg return</th>
                  <th className="py-1.5 pr-3 font-medium text-right">Hit rate</th>
                  <th className="py-1.5 font-medium text-right">Count</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(forwardSummary!).map(([signal, data]) => (
                  <tr key={signal} className="border-b border-slate-700/50">
                    <td className="py-1.5 pr-3 text-slate-300 font-medium">{signal}</td>
                    <td className={`py-1.5 pr-3 text-right ${(data.avg_return_20d_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {(data.avg_return_20d_pct ?? 0) >= 0 ? "+" : ""}{(data.avg_return_20d_pct ?? 0).toFixed(2)}%
                    </td>
                    <td className="py-1.5 pr-3 text-right text-slate-300">{(data.hit_rate_pct ?? 0).toFixed(1)}%</td>
                    <td className="py-1.5 text-right text-slate-500">{data.n_observations ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Paper trading breakdown */}
      {hasPaper && (
        <div>
          <p className="text-[11px] text-slate-400 mb-1.5 font-medium">Paper trade breakdown</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <StatCard label="Avg win" value={paperTrading!.avg_win_pct != null ? `+${paperTrading!.avg_win_pct.toFixed(2)}%` : "---"} color="text-emerald-400" />
            <StatCard label="Avg loss" value={paperTrading!.avg_loss_pct != null ? `${paperTrading!.avg_loss_pct.toFixed(2)}%` : "---"} color="text-red-400" />
            <StatCard label="Excess vs SPY" value={paperTrading!.avg_excess_vs_spy_pct != null ? `${paperTrading!.avg_excess_vs_spy_pct >= 0 ? "+" : ""}${paperTrading!.avg_excess_vs_spy_pct.toFixed(2)}%` : "---"} />
            {paperTrading!.buy_signals_summary?.completed_n != null && (
              <StatCard label="BUY signal win rate" value={paperTrading!.buy_signals_summary.win_rate_pct != null ? `${paperTrading!.buy_signals_summary.win_rate_pct.toFixed(1)}%` : "---"} sub={`${paperTrading!.buy_signals_summary.completed_n} trades`} />
            )}
          </div>
        </div>
      )}

      {/* Confidence calibration */}
      {hasCalibration && (
        <div>
          <div className="flex items-center gap-2 mb-1">
            <p className="text-[11px] text-slate-400 font-medium">Confidence calibration</p>
            {calibration!.is_well_calibrated ? (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/30">CALIBRATED</span>
            ) : (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400 ring-1 ring-amber-500/30">NEEDS REVIEW</span>
            )}
          </div>
          {calibration!.note && (
            <p className="text-[10px] text-slate-500 mb-1">{calibration!.note}</p>
          )}
          {calibration!.calibration_error != null && (
            <p className="text-[10px] text-slate-500">
              Mean calibration error: {calibration!.calibration_error}pp
              {calibration!.monotonic ? " · Monotonic ✓" : " · Non-monotonic ✗"}
              {` · ${calibration!.total_observations} observations`}
            </p>
          )}
          <CalibrationChart buckets={calibration!.buckets} />
        </div>
      )}
    </div>
  );
}
