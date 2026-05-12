"use client";
import React, { useState } from "react";
import {
  RotateCcw,
  Sliders,
} from "lucide-react";
import { usePortfolioWhatIf, type HoldingRow, type MCTRPosition, type StressTest, type SubScores } from "./usePortfolioWhatIf";

/* ─── Types ─── */
interface HealthData {
  score: number;
  sub_scores: SubScores;
  biggest_drag?: string | null;
  improvement_note?: string | null;
}
interface MCTRData {
  positions: MCTRPosition[];
  portfolio_vol_annual_pct?: number;
  note?: string | null;
}
interface EarningsItem {
  ticker: string;
  earnings_date?: string;
  days_until: number;
  portfolio_pct: number;
}
interface EarningsCalendar {
  items: EarningsItem[];
  total_at_risk_pct: number;
  count: number;
  note?: string | null;
}
interface PriorityAction {
  ticker: string;
  action: string;
  reason: string;
  tags?: string[];
  urgency?: string;
  dollars?: number;
}
interface PriorityActions {
  this_week: PriorityAction[];
  this_month: PriorityAction[];
}
interface PortfolioRiskMetrics {
  var_cvar?: {
    var_95_10day_pct?: number;
  } | null;
  correlation_matrix?: Record<string, Record<string, number>>;
}

export interface PortfolioDoctorV2Data {
  health?: HealthData;
  mctr?: MCTRData;
  stress_tests?: StressTest[];
  earnings_calendar?: EarningsCalendar;
  priority_actions?: PriorityActions;
  portfolio_beta?: number | null;
}

interface Props {
  data: PortfolioDoctorV2Data | null | undefined;
  portfolioRiskMetrics?: PortfolioRiskMetrics;
  portfolioBeta?: number | null;
  totalValue?: number;
  holdingCount?: number;
  sectorExposure?: { sector: string; pct: number }[];
  holdings?: HoldingRow[];
  onTickerClick?: (t: string) => void;
}

/* ─── Sub-score label map ─── */
const SUB_LABELS: Record<string, string> = {
  concentration: "Concentration",
  correlation: "Correlation",
  regime_alignment: "Regime alignment",
  drawdown_risk: "Drawdown risk",
  tax_efficiency: "Tax efficiency",
};
const SUB_COLORS: Record<string, string> = {
  concentration: "bg-amber-500",
  correlation: "bg-orange-500",
  regime_alignment: "bg-emerald-500",
  drawdown_risk: "bg-sky-500",
  tax_efficiency: "bg-indigo-500",
};

function mctrBarColor(riskPct: number): string {
  if (riskPct >= 25) return "bg-rose-500";
  if (riskPct >= 15) return "bg-amber-500";
  return "bg-emerald-500";
}

/* ─── Health ring SVG ─── */
function HealthRing({ score, size = 96 }: { score: number; size?: number }) {
  const r = (size - 20) / 2;
  const circ = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score));
  const offset = circ * (1 - pct / 100);
  const color =
    pct >= 75 ? "text-emerald-500" : pct >= 50 ? "text-amber-500" : "text-rose-500";

  return (
    <div className="relative flex items-center justify-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor"
          strokeWidth="6" className="text-slate-700/40" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor"
          strokeWidth="6" strokeDasharray={circ} strokeDashoffset={offset}
          strokeLinecap="round" className={color} />
      </svg>
      <span className="absolute text-2xl font-bold text-slate-100">{score}</span>
    </div>
  );
}

/* ─── Tag badge ─── */
function Tag({ label, variant }: { label: string; variant?: string }) {
  const cls =
    variant === "urgent"
      ? "bg-rose-500/20 text-rose-300 border-rose-500/30"
      : variant === "tax"
        ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/30"
        : variant === "watch"
          ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
          : "bg-slate-700/60 text-slate-300 border-slate-600/40";
  return (
    <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full border ${cls}`}>
      {label}
    </span>
  );
}

function tagVariant(tag: string): string {
  const t = tag.toLowerCase();
  if (t.includes("urgent") || t.includes("regime") || t.includes("earnings")) return "urgent";
  if (t.includes("tax") || t.includes("ira")) return "tax";
  if (t.includes("watch") || t.includes("conditional")) return "watch";
  return "";
}

/* ─── Stress bar ─── */
function StressBar({ pct }: { pct: number }) {
  const absPct = Math.abs(pct);
  const w = Math.min(100, absPct * 1.5);
  const color = absPct >= 40 ? "bg-rose-500" : absPct >= 25 ? "bg-amber-500" : "bg-orange-400";
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-2.5 rounded-full bg-slate-700/40 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${w}%` }} />
      </div>
      <span className={`text-sm font-semibold tabular-nums ${absPct >= 40 ? "text-rose-400" : "text-amber-400"}`}>
        {pct > 0 ? "+" : ""}{pct}%
      </span>
    </div>
  );
}

/* ─── Signal badge ─── */
function SignalBadge({ signal }: { signal: string }) {
  const s = signal.toUpperCase();
  let cls = "bg-slate-600/40 text-slate-300";
  if (s.includes("BUY") || s.includes("ADD")) cls = "bg-emerald-500/20 text-emerald-300";
  else if (s.includes("AVOID") || s.includes("REDUCE")) cls = "bg-rose-500/20 text-rose-300";
  else if (s.includes("WATCH") || s.includes("HOLD")) cls = "bg-amber-500/20 text-amber-300";
  const label = s.includes("STRONG BUY") ? "Strong Buy" : s.includes("BUY") ? "Buy" : s.includes("ADD") ? "Hold/Add" : s.includes("AVOID") ? "Avoid" : s.includes("REDUCE") ? "Reduce" : s.includes("WATCH") ? "Watch" : s.includes("HOLD") ? "Hold" : signal;
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${cls}`}>{label}</span>
  );
}

/* ─── Correlation Alert Row ─── */
function CorrelationAlerts({ matrix }: { matrix?: Record<string, Record<string, number>> }) {
  if (!matrix) return null;
  const tickers = Object.keys(matrix);
  const pairs: { t1: string; t2: string; corr: number; note: string }[] = [];
  for (let i = 0; i < tickers.length; i++) {
    for (let j = i + 1; j < tickers.length; j++) {
      const val = matrix[tickers[i]]?.[tickers[j]];
      if (val != null && val > 0.7) {
        let note = "Correlated";
        if (val > 0.9) note = "Effectively one position";
        else if (val > 0.8) note = "Limited diversification benefit";
        else note = "Moderate overlap";
        pairs.push({ t1: tickers[i], t2: tickers[j], corr: val, note });
      }
    }
  }
  if (pairs.length === 0) return null;
  pairs.sort((a, b) => b.corr - a.corr);
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-800/40 p-5">
      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Correlation Alerts</h4>
      <div className="space-y-2">
        {pairs.slice(0, 5).map((p) => {
          const color = p.corr > 0.9 ? "text-rose-400" : p.corr > 0.8 ? "text-amber-400" : "text-yellow-400";
          return (
            <div key={`${p.t1}-${p.t2}`} className="flex items-center justify-between text-sm">
              <span className="text-slate-300">{p.t1} ↔ {p.t2}</span>
              <span className="flex items-center gap-3">
                <span className={`font-semibold tabular-nums ${color}`}>{(p.corr * 100).toFixed(0)}% corr</span>
                <span className="text-slate-500 text-xs">{p.note}</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN PANEL
   ═══════════════════════════════════════════════════════════════════════════ */
export default function PortfolioDoctorPanel({
  data,
  portfolioRiskMetrics,
  portfolioBeta,
  totalValue,
  holdingCount,
  sectorExposure,
  holdings,
  onTickerClick,
}: Props) {
  if (!data) return null;
  const { health, mctr, stress_tests, earnings_calendar, priority_actions } = data;

  const [interactiveOpen, setInteractiveOpen] = useState(false);

  const whatIf = usePortfolioWhatIf(
    holdings ?? [],
    mctr?.positions ?? [],
    stress_tests ?? [],
    health?.sub_scores,
    sectorExposure ?? [],
    portfolioRiskMetrics?.correlation_matrix,
  );

  // Use what-if values when interactive and dirty, otherwise original
  const activeHealth = whatIf.isDirty
    ? { score: whatIf.healthScore, sub_scores: whatIf.subScores }
    : health;
  const activeStress = whatIf.isDirty ? whatIf.stressTests : stress_tests;
  const activeEffPositions = whatIf.isDirty ? whatIf.effectivePositions : (
    mctr?.positions
      ? (() => {
          const total = mctr.positions.reduce((s, p) => s + p.risk_pct, 0);
          if (total <= 0) return holdingCount ?? 0;
          const hhi = mctr.positions.reduce((s, p) => s + (p.risk_pct / total) ** 2, 0);
          return hhi > 0 ? Math.round(1 / hhi * 10) / 10 : holdingCount ?? 0;
        })()
      : holdingCount ?? 0
  );

  const varCvar = portfolioRiskMetrics?.var_cvar;
  const dailyVaR = varCvar?.var_95_10day_pct ? Math.abs(varCvar.var_95_10day_pct / Math.sqrt(10)) : null;
  const dailyVaRDollars = dailyVaR != null && totalValue ? Math.round((dailyVaR / 100) * totalValue) : null;
  const topSector = sectorExposure?.[0];

  return (
    <div className="space-y-6">
      {/* ── HEALTH SCORE (live-updating) ── */}
      {activeHealth && (
        <div className={`rounded-xl border ${whatIf.isDirty ? "border-emerald-500/40 bg-emerald-950/20" : "border-slate-700/60 bg-slate-800/40"} p-5 transition-colors`}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">
              Portfolio Health{whatIf.isDirty ? " — adjusted" : ""}
            </h3>
            {whatIf.isDirty && (
              <span className="text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-full font-semibold">
                LIVE PREVIEW
              </span>
            )}
          </div>
          <div className="flex flex-col sm:flex-row items-start gap-6">
            <div className="flex flex-col items-center gap-1">
              <HealthRing score={activeHealth.score} />
              <span className="text-xs text-slate-500">/100</span>
              {whatIf.isDirty && health && activeHealth.score !== health.score && (
                <span className={`text-xs font-semibold ${activeHealth.score > health.score ? "text-emerald-400" : "text-rose-400"}`}>
                  {activeHealth.score > health.score ? "+" : ""}{activeHealth.score - health.score} pts
                </span>
              )}
            </div>
            <div className="flex-1 w-full space-y-2">
              {(Object.keys(SUB_LABELS) as (keyof SubScores)[]).map((key) => {
                const val = activeHealth.sub_scores?.[key] ?? 0;
                const origVal = health?.sub_scores?.[key] ?? val;
                const changed = whatIf.isDirty && val !== origVal;
                const color = SUB_COLORS[key] || "bg-slate-500";
                return (
                  <div key={key} className="flex items-center gap-3">
                    <span className="w-32 text-xs text-slate-400">{SUB_LABELS[key]}</span>
                    <div className="flex-1 h-2 rounded-full bg-slate-700/40 overflow-hidden relative">
                      {changed && (
                        <div className="absolute h-full rounded-full bg-slate-600/50" style={{ width: `${origVal}%` }} />
                      )}
                      <div className={`h-full rounded-full ${color} relative z-10 transition-all duration-300`} style={{ width: `${val}%` }} />
                    </div>
                    <span className={`w-12 text-right text-xs font-semibold tabular-nums ${val >= 75 ? "text-emerald-400" : val >= 50 ? "text-amber-400" : "text-rose-400"}`}>
                      {val}
                      {changed && (
                        <span className={`ml-0.5 text-[9px] ${val > origVal ? "text-emerald-400" : "text-rose-400"}`}>
                          {val > origVal ? "↑" : "↓"}
                        </span>
                      )}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
          {!whatIf.isDirty && health?.biggest_drag && (
            <p className="mt-3 text-xs text-slate-400 leading-relaxed">
              <strong className="text-slate-300">Biggest drag:</strong> {health.biggest_drag}
            </p>
          )}
          {!whatIf.isDirty && health?.improvement_note && (
            <p className="mt-1 text-xs text-emerald-400/80">{health.improvement_note}</p>
          )}
        </div>
      )}

      {/* ── QUICK STATS ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {portfolioBeta != null && (
          <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3 text-center">
            <p className="text-lg font-bold text-slate-100 tabular-nums">{portfolioBeta.toFixed(2)}</p>
            <p className="text-[10px] text-slate-500 uppercase tracking-wide mt-0.5">Portfolio beta</p>
            {portfolioBeta > 1.2 && <p className="text-[10px] text-amber-400 mt-0.5">target &lt; 1.2</p>}
          </div>
        )}
        {dailyVaRDollars != null && (
          <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3 text-center">
            <p className="text-lg font-bold text-slate-100 tabular-nums">${dailyVaRDollars.toLocaleString()}</p>
            <p className="text-[10px] text-slate-500 uppercase tracking-wide mt-0.5">95% daily VaR</p>
            <p className="text-[10px] text-slate-500 mt-0.5">max expected loss/day</p>
          </div>
        )}
        <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3 text-center">
          <p className="text-lg font-bold text-slate-100 tabular-nums">{activeEffPositions.toFixed(1)}</p>
          <p className="text-[10px] text-slate-500 uppercase tracking-wide mt-0.5">Effective positions</p>
          <p className="text-[10px] text-slate-500 mt-0.5">of {holdingCount ?? "–"} holdings</p>
        </div>
        {topSector && (
          <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3 text-center">
            <p className={`text-lg font-bold tabular-nums ${topSector.pct > 40 ? "text-amber-400" : "text-slate-100"}`}>
              {topSector.pct.toFixed(1)}%
            </p>
            <p className="text-[10px] text-slate-500 uppercase tracking-wide mt-0.5">{topSector.sector}</p>
            {topSector.pct > 35 && <p className="text-[10px] text-amber-400 mt-0.5">target &lt; 35%</p>}
          </div>
        )}
      </div>

      {/* ── INTERACTIVE ALLOCATION TABLE ── */}
      {whatIf.rows.length > 0 && (
        <div className={`rounded-xl border ${interactiveOpen ? "border-emerald-500/30 bg-slate-800/60" : "border-slate-700/60 bg-slate-800/40"} p-5 transition-colors`}>
          <div className="flex items-center justify-between mb-4">
            <button
              onClick={() => setInteractiveOpen(!interactiveOpen)}
              className="flex items-center gap-2 text-xs font-bold text-slate-300 uppercase tracking-wider hover:text-emerald-400 transition-colors"
            >
              <Sliders className="w-3.5 h-3.5" />
              Adjust Allocations — See Health Update Live
            </button>
            <div className="flex items-center gap-2">
              {whatIf.isDirty && (
                <button
                  onClick={whatIf.reset}
                  className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-emerald-400 transition-colors border border-slate-600 rounded px-2 py-1"
                >
                  <RotateCcw className="w-3 h-3" />
                  Reset
                </button>
              )}
              <button
                onClick={() => setInteractiveOpen(!interactiveOpen)}
                className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
              >
                {interactiveOpen ? "Collapse" : "Expand"}
              </button>
            </div>
          </div>

          {interactiveOpen && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/40">
                    <th className="text-left text-[10px] text-slate-500 uppercase tracking-wider py-2 pr-3">Ticker</th>
                    <th className="text-left text-[10px] text-slate-500 uppercase tracking-wider py-2 pr-3 w-32">Allocation</th>
                    <th className="text-right text-[10px] text-slate-500 uppercase tracking-wider py-2 pr-3 w-16">%</th>
                    <th className="text-center text-[10px] text-slate-500 uppercase tracking-wider py-2 pr-3 w-20">Signal</th>
                    <th className="text-center text-[10px] text-slate-500 uppercase tracking-wider py-2 pr-3 w-28">Adjust %</th>
                    <th className="text-right text-[10px] text-slate-500 uppercase tracking-wider py-2 w-16">MCTR</th>
                  </tr>
                </thead>
                <tbody>
                  {whatIf.rows.slice(0, 15).map((row) => {
                    const changed = row.adjustedPct !== row.originalPct;
                    const barColor = row.signal.toUpperCase().includes("AVOID") || row.signal.toUpperCase().includes("REDUCE")
                      ? "bg-rose-500" : row.signal.toUpperCase().includes("BUY") || row.signal.toUpperCase().includes("ADD")
                        ? "bg-emerald-500" : "bg-slate-400";
                    return (
                      <tr key={row.ticker} className={`border-b border-slate-700/20 ${changed ? "bg-emerald-950/20" : ""}`}>
                        <td className="py-2 pr-3">
                          <button
                            className="text-xs font-semibold text-slate-200 hover:text-emerald-400 transition-colors"
                            onClick={() => onTickerClick?.(row.ticker)}
                          >
                            {row.ticker}
                          </button>
                        </td>
                        <td className="py-2 pr-3">
                          <div className="h-2 rounded-full bg-slate-700/40 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-200 ${barColor}`}
                              style={{ width: `${Math.min(100, row.adjustedPct * 3)}%` }}
                            />
                          </div>
                        </td>
                        <td className="py-2 pr-3 text-right">
                          <span className={`text-xs tabular-nums font-medium ${changed ? "text-emerald-300" : "text-slate-300"}`}>
                            {row.adjustedPct.toFixed(1)}%
                          </span>
                        </td>
                        <td className="py-2 pr-3 text-center">
                          <SignalBadge signal={row.signal} />
                        </td>
                        <td className="py-2 pr-3">
                          <input
                            type="range"
                            min={0}
                            max={Math.min(50, row.originalPct * 3)}
                            step={0.5}
                            value={row.adjustedPct}
                            onChange={(e) => whatIf.setAdjustedPct(row.ticker, parseFloat(e.target.value))}
                            className="w-full h-1.5 rounded-full appearance-none cursor-pointer
                              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                              [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-emerald-400 [&::-webkit-slider-thumb]:border-2
                              [&::-webkit-slider-thumb]:border-slate-800 [&::-webkit-slider-thumb]:shadow-md
                              bg-slate-600/60"
                          />
                        </td>
                        <td className="py-2 text-right">
                          <span className={`text-xs tabular-nums font-semibold ${row.mctrPct >= 20 ? "text-rose-400" : row.mctrPct >= 12 ? "text-amber-400" : "text-slate-300"}`}>
                            {row.mctrPct.toFixed(0)}%
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── PRIORITY ACTIONS ── */}
      {priority_actions && (priority_actions.this_week.length > 0 || priority_actions.this_month.length > 0) && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-800/40 p-5">
          {priority_actions.this_week.length > 0 && (
            <>
              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-3">
                This Week — {priority_actions.this_week.length} Priority Actions
              </h4>
              <ol className="space-y-4 mb-6">
                {priority_actions.this_week.map((a, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-rose-500/20 text-rose-300 text-xs font-bold flex items-center justify-center border border-rose-500/30">
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-200">
                        <button className="hover:text-emerald-400 transition-colors cursor-pointer" onClick={() => onTickerClick?.(a.ticker)}>
                          {a.action}
                        </button>
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{a.reason}</p>
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {a.tags?.map((t) => <Tag key={t} label={t} variant={tagVariant(t)} />)}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}
          {priority_actions.this_month.length > 0 && (
            <>
              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-3">
                This Month — If Conditions Met
              </h4>
              <ol className="space-y-4" start={priority_actions.this_week.length + 1}>
                {priority_actions.this_month.map((a, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-sky-500/20 text-sky-300 text-xs font-bold flex items-center justify-center border border-sky-500/30">
                      {priority_actions.this_week.length + i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-200">
                        <button className="hover:text-emerald-400 transition-colors cursor-pointer" onClick={() => onTickerClick?.(a.ticker)}>
                          {a.action}
                        </button>
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{a.reason}</p>
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {a.tags?.map((t) => <Tag key={t} label={t} variant={tagVariant(t)} />)}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      )}

      {/* ── MCTR ── */}
      {mctr && mctr.positions.length > 0 && (
        <div className="rounded-xl border border-slate-700/60 bg-slate-800/40 p-5">
          <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-1">
            Marginal Contribution to Risk (MCTR)
          </h4>
          <p className="text-[11px] text-slate-500 mb-4">
            Each position&apos;s share of total portfolio risk — not just its % of value
          </p>
          <div className="space-y-2.5">
            {mctr.positions.slice(0, 6).map((p) => (
              <div key={p.ticker} className="flex items-center gap-3">
                <button className="w-14 text-xs font-semibold text-slate-200 text-left hover:text-emerald-400 transition-colors" onClick={() => onTickerClick?.(p.ticker)}>
                  {p.ticker}
                </button>
                <div className="flex-1 h-3 rounded-full bg-slate-700/40 overflow-hidden">
                  <div className={`h-full rounded-full ${mctrBarColor(p.risk_pct)}`} style={{ width: `${Math.min(100, p.risk_pct * 2)}%` }} />
                </div>
                <span className="w-10 text-right text-xs font-semibold text-slate-300 tabular-nums">{p.risk_pct.toFixed(0)}%</span>
              </div>
            ))}
            {mctr.positions.length > 6 && (
              <div className="flex items-center gap-3">
                <span className="w-14 text-xs text-slate-400">Other {mctr.positions.length - 6}</span>
                <div className="flex-1 h-3 rounded-full bg-slate-700/40 overflow-hidden">
                  <div className="h-full rounded-full bg-slate-500" style={{ width: `${Math.min(100, mctr.positions.slice(6).reduce((s, p) => s + p.risk_pct, 0) * 2)}%` }} />
                </div>
                <span className="w-10 text-right text-xs font-semibold text-slate-400 tabular-nums">
                  {mctr.positions.slice(6).reduce((s, p) => s + p.risk_pct, 0).toFixed(0)}%
                </span>
              </div>
            )}
          </div>
          {mctr.note && <p className="mt-3 text-xs text-slate-400 italic">{mctr.note}</p>}
        </div>
      )}

      {/* ── STRESS + EARNINGS side by side ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {activeStress && activeStress.length > 0 && (
          <div className={`rounded-xl border ${whatIf.isDirty ? "border-emerald-500/20" : "border-slate-700/60"} bg-slate-800/40 p-5 transition-colors`}>
            <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-3">
              Historical Stress Test{whatIf.isDirty ? " — adjusted" : ""}
            </h4>
            <div className="space-y-3">
              {activeStress.map((s) => (
                <div key={s.name} className="flex items-center gap-3">
                  <span className="w-24 text-xs text-slate-400 flex-shrink-0">{s.name}</span>
                  <StressBar pct={s.portfolio_impact_pct} />
                </div>
              ))}
            </div>
          </div>
        )}
        {earnings_calendar && earnings_calendar.items.length > 0 && (
          <div className="rounded-xl border border-slate-700/60 bg-slate-800/40 p-5">
            <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-3">Earnings Calendar</h4>
            <p className="text-[11px] text-slate-500 mb-3">Next 30 days</p>
            <div className="space-y-2">
              {earnings_calendar.items.map((e) => (
                <div key={e.ticker} className="flex items-center justify-between text-sm">
                  <button className="font-semibold text-slate-200 hover:text-emerald-400 transition-colors" onClick={() => onTickerClick?.(e.ticker)}>
                    {e.ticker}
                  </button>
                  <span className="text-slate-400 text-xs">{e.earnings_date ? `~${e.earnings_date}` : `~${e.days_until}d`}</span>
                  <span className={`text-xs font-semibold tabular-nums ${e.portfolio_pct > 10 ? "text-amber-400" : "text-slate-300"}`}>
                    ~{e.portfolio_pct.toFixed(0)}% of port
                  </span>
                </div>
              ))}
            </div>
            {earnings_calendar.note && (
              <p className="mt-3 text-xs text-slate-400 border-t border-slate-700/40 pt-2">{earnings_calendar.note}</p>
            )}
          </div>
        )}
      </div>

      {/* ── Correlation Alerts ── */}
      <CorrelationAlerts matrix={portfolioRiskMetrics?.correlation_matrix} />
    </div>
  );
}
