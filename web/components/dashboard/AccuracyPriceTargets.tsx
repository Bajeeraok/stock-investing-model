"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Target, HelpCircle, RefreshCw, AlertCircle, ChevronDown, ChevronRight } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

/** Catches render errors in accuracy section so the rest of the app does not crash */
class AccuracyErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; retryKey: number }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, retryKey: 0 };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-6 text-center">
          <p className="text-amber-200 font-medium mb-2">Could not load Price target accuracy</p>
          <p className="text-slate-400 text-sm mb-3">A display error occurred. Try refreshing the dashboard or the accuracy section.</p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, retryKey: this.state.retryKey + 1 })}
            className="px-4 py-2 rounded-lg bg-slate-600 hover:bg-slate-500 text-slate-200 text-sm"
          >
            Try again
          </button>
        </div>
      );
    }
    return <React.Fragment key={this.state.retryKey}>{this.props.children}</React.Fragment>;
  }
}

export interface AccuracyPerTicker {
  ticker: string;
  close: number;
  st_target_high?: number | null;
  st_stop_low?: number | null;
  support_level?: number | null;
  suggested_buy_price?: number | null;
  mt_target_high?: number | null;
  mt_stop_low?: number | null;
  st_target_high_pct_err?: number | null;
  st_target_high_abs_pct?: number | null;
  support_level_abs_pct?: number | null;
}

export interface AccuracySummaryLevel {
  label: string;
  count: number;
  mape: number | null;
  within_1pct: number;
  within_2pct: number;
  within_5pct: number;
}

export interface AccuracyInterpretation {
  thresholds: {
    st_target_err_acceptable_pct: number;
    support_err_acceptable_pct: number;
    st_target_mape_tweak_above: number;
    support_mape_tweak_above: number;
  };
  notes: string[];
}

export interface AmberTweakTicker {
  ticker: string;
  st_target_err_pct: number;
}

export interface AccuracyReport {
  ok: boolean;
  message: string | null;
  per_ticker: AccuracyPerTicker[];
  summary: Record<string, AccuracySummaryLevel>;
  recommendations: string[];
  amber_tickers?: AmberTweakTicker[];
  tweak_tickers?: AmberTweakTicker[];
  as_of: string | null;
  interpretation?: AccuracyInterpretation;
}

function formatAsOf(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      timeZone: "America/New_York",
      dateStyle: "short",
      timeStyle: "short",
    }) + " ET";
  } catch {
    return iso;
  }
}

export function AccuracyPriceTargets() {
  const [data, setData] = useState<AccuracyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showGuide, setShowGuide] = useState(false);

  const fetchAccuracy = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/accuracy`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Failed to load");
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load accuracy report");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAccuracy();
  }, [fetchAccuracy]);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center gap-3 py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-emerald-500 border-t-transparent" />
        <span className="text-slate-400">Loading accuracy report...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 flex items-center gap-2">
        <AlertCircle className="h-5 w-5 text-red-400 shrink-0" />
        <p className="text-red-200">{error}</p>
        <button
          type="button"
          onClick={fetchAccuracy}
          className="ml-auto px-3 py-1.5 rounded-lg bg-slate-600 hover:bg-slate-500 text-slate-200 text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data?.ok) {
    const interpNoReport = data?.interpretation;
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-6 space-y-4">
        <div className="flex items-start gap-3">
          <Target className="h-6 w-6 text-amber-500 shrink-0 mt-0.5" />
          <div>
            <h3 className="font-medium text-slate-200 mb-1">Price target accuracy</h3>
            <p className="text-slate-400 text-sm mb-3">
              Compare model target levels (ST target, support, suggested buy) vs today&apos;s close. Refresh the dashboard or run the script to generate the report.
            </p>
            <p className="text-amber-200/90 text-sm font-mono bg-slate-900/80 px-3 py-2 rounded-lg">
              {data?.message ?? "Run: cd backend && python scripts/accuracy_price_targets.py"}
            </p>
            <button
              type="button"
              onClick={fetchAccuracy}
              className="mt-3 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-600 hover:bg-slate-500 text-slate-200 text-sm"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
        {interpNoReport && typeof interpNoReport === "object" && (
          <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-3 text-sm">
            <p className="font-medium text-slate-300 mb-2">How to interpret (when report is available)</p>
            {Array.isArray(interpNoReport.notes) && (
              <ul className="list-disc list-inside space-y-1 text-slate-400">
                {interpNoReport.notes.slice(0, 4).map((note: unknown, i: number) => (
                  <li key={i}>{typeof note === "string" ? note : String(note)}</li>
                ))}
              </ul>
            )}
            {interpNoReport.thresholds && typeof interpNoReport.thresholds === "object" && (
              <p className="mt-2 text-slate-500">
                Acceptable: ST target err ≤ {(interpNoReport.thresholds.st_target_err_acceptable_pct ?? 5)}%, MAPE ≤ 5–8%. Tweak if ST MAPE &gt; {(interpNoReport.thresholds.st_target_mape_tweak_above ?? 8)}%.
              </p>
            )}
          </div>
        )}
      </div>
    );
  }

  const perTicker = Array.isArray(data.per_ticker) ? data.per_ticker : [];
  const summary = data.summary && typeof data.summary === "object" ? data.summary : {};
  const recs = Array.isArray(data.recommendations) ? data.recommendations : [];
  const amberTickers = Array.isArray(data.amber_tickers) ? data.amber_tickers : [];
  const tweakTickers = Array.isArray(data.tweak_tickers) ? data.tweak_tickers : [];
  const summaryEntries = Object.entries(summary).filter(
    ([, v]) => v != null && typeof v === "object" && "label" in v
  );
  const interp = data.interpretation && typeof data.interpretation === "object" ? data.interpretation : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-400">
        <span>As of: {formatAsOf(data.as_of)}</span>
        <button
          type="button"
          onClick={fetchAccuracy}
          className="flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-700 text-slate-300"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      <p className="text-sm text-slate-400 flex items-start gap-2">
        <HelpCircle className="h-4 w-4 shrink-0 mt-0.5" />
        <span>
          Close = latest close. Levels = model outputs (st_band, support, suggested_buy). Pct error = 100 × (close − level) / close. Positive = close above level.
        </span>
      </p>

      {/* How to interpret: err% and MAPE – when acceptable vs when to tweak */}
      <div className="rounded-lg border border-slate-700 bg-slate-800/30 overflow-hidden">
        <button
          type="button"
          onClick={() => setShowGuide(!showGuide)}
          className="w-full flex items-center gap-2 px-4 py-2 text-left text-slate-200 font-medium hover:bg-slate-700/50"
        >
          {showGuide ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          How to interpret ST target err%, Support err%, and MAPE – when is error acceptable?
        </button>
        {showGuide && (
          <div className="px-4 pb-4 pt-0 space-y-3 text-sm border-t border-slate-700/50">
            {interp?.thresholds && typeof interp.thresholds === "object" && (
              <div className="rounded bg-slate-900/60 p-3">
                <p className="font-medium text-slate-300 mb-2">Thresholds (from config)</p>
                <ul className="space-y-1 text-slate-400">
                  <li><span className="text-emerald-400">ST target err%</span> ≤ {(interp.thresholds.st_target_err_acceptable_pct ?? 5)}% per ticker → acceptable (no tweak). 5–10% amber; &gt;10% consider tweak for that name.</li>
                  <li><span className="text-emerald-400">Support err%</span> ≤ {(interp.thresholds.support_err_acceptable_pct ?? 5)}% → acceptable. MA20 lags; &gt;10% common in fast moves.</li>
                  <li><span className="text-amber-400">MAPE</span> (overall): ≤ 5–8% → acceptable. ST target MAPE &gt; {(interp.thresholds.st_target_mape_tweak_above ?? 8)}% → consider adjusting ATR in target_bands.py.</li>
                </ul>
              </div>
            )}
            {Array.isArray(interp?.notes) && interp.notes.length > 0 && (
              <div>
                <p className="font-medium text-slate-300 mb-1">Notes</p>
                <ul className="list-disc list-inside space-y-1 text-slate-400">
                  {interp.notes.map((note: unknown, i: number) => (
                    <li key={i}>{typeof note === "string" ? note : String(note)}</li>
                  ))}
                </ul>
              </div>
            )}
            {!interp && (
              <p className="text-slate-500">Acceptable: ST target err ≤ 5% per ticker, MAPE ≤ 5–8%. Consider tweak: ST MAPE &gt; 8% or many tickers with err &gt; 10%.</p>
            )}
          </div>
        )}
      </div>

      {/* Amber (5–10% err) and Tweak (>10%) tickers – how to tweak model */}
      {(amberTickers.length > 0 || tweakTickers.length > 0) && (
        <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-4 space-y-3">
          <p className="font-medium text-slate-200">Tickers to review (by ST target err%)</p>
          <p className="text-sm text-slate-400">
            Add tickers with high err% to <code className="px-1 py-0.5 rounded bg-slate-700 text-amber-200">config.accuracy.st_target_atr_mult_overrides</code> with value <code className="px-1 py-0.5 rounded bg-slate-700">1.8</code> or <code className="px-1 py-0.5 rounded bg-slate-700">2.0</code> to widen their short-term band (reduces error for volatile names like CRWD, SLV).
          </p>
          <div className="flex flex-wrap gap-4">
            {amberTickers.length > 0 && (
              <div>
                <span className="text-amber-400 font-medium text-sm">Amber (5–10%):</span>
                <span className="ml-2 text-slate-300 text-sm">
                  {amberTickers.map((t) => `${t.ticker} ${typeof t.st_target_err_pct === "number" ? t.st_target_err_pct + "%" : ""}`).join(", ")}
                </span>
              </div>
            )}
            {tweakTickers.length > 0 && (
              <div>
                <span className="text-red-400 font-medium text-sm">Consider tweak (&gt;10%):</span>
                <span className="ml-2 text-slate-300 text-sm">
                  {tweakTickers.map((t) => `${t.ticker} ${typeof t.st_target_err_pct === "number" ? t.st_target_err_pct + "%" : ""}`).join(", ")}
                </span>
              </div>
            )}
          </div>
          <p className="text-xs text-slate-500">
            Example in config.yaml: <code className="text-amber-200/90">st_target_atr_mult_overrides: &#123; CRWD: 1.8, SLV: 1.8 &#125;</code>
          </p>
        </div>
      )}

      {/* Per-ticker table */}
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-400 border-b border-slate-700 bg-slate-800/50">
              <th className="px-3 py-2 font-medium">Ticker</th>
              <th className="px-3 py-2 font-medium text-right">Close</th>
              <th className="px-3 py-2 font-medium text-right">ST target</th>
              <th className="px-3 py-2 font-medium text-right">Support</th>
              <th className="px-3 py-2 font-medium text-right">Buy@</th>
              <th className="px-3 py-2 font-medium text-right">ST target err %</th>
              <th className="px-3 py-2 font-medium text-right">Support err %</th>
            </tr>
          </thead>
          <tbody>
            {perTicker.map((row, idx) => (
              <tr key={row?.ticker ?? idx} className="border-b border-slate-700/50 hover:bg-slate-800/30">
                <td className="px-3 py-2 font-mono font-medium text-slate-200">{row?.ticker ?? "—"}</td>
                <td className="px-3 py-2 text-right text-slate-300">{typeof row?.close === "number" ? row.close.toFixed(2) : "—"}</td>
                <td className="px-3 py-2 text-right text-slate-300">{typeof row?.st_target_high === "number" ? row.st_target_high.toFixed(2) : "—"}</td>
                <td className="px-3 py-2 text-right text-slate-300">{typeof row?.support_level === "number" ? row.support_level.toFixed(2) : "—"}</td>
                <td className="px-3 py-2 text-right text-slate-300">{typeof row?.suggested_buy_price === "number" ? row.suggested_buy_price.toFixed(2) : "—"}</td>
                <td className="px-3 py-2 text-right">
                  {typeof row?.st_target_high_abs_pct === "number" ? (
                    <span className={row.st_target_high_abs_pct <= 2 ? "text-emerald-400" : row.st_target_high_abs_pct <= 5 ? "text-amber-400" : "text-red-400"}>
                      {row.st_target_high_abs_pct.toFixed(1)}%
                    </span>
                  ) : "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  {typeof row?.support_level_abs_pct === "number" ? (
                    <span className={row.support_level_abs_pct <= 2 ? "text-emerald-400" : row.support_level_abs_pct <= 5 ? "text-amber-400" : "text-red-400"}>
                      {row.support_level_abs_pct.toFixed(1)}%
                    </span>
                  ) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Summary by level */}
      {summaryEntries.length > 0 && (
        <div className="rounded-lg border border-slate-700 overflow-hidden">
          <div className="px-4 py-2 bg-slate-800/80 font-medium text-slate-300 border-b border-slate-700">
            Margin of error by level (MAPE vs close)
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-700 bg-slate-800/50">
                <th className="px-3 py-2 font-medium">Level</th>
                <th className="px-3 py-2 font-medium text-right">Count</th>
                <th className="px-3 py-2 font-medium text-right">MAPE %</th>
                <th className="px-3 py-2 font-medium text-right">Within 1%</th>
                <th className="px-3 py-2 font-medium text-right">Within 2%</th>
                <th className="px-3 py-2 font-medium text-right">Within 5%</th>
              </tr>
            </thead>
            <tbody>
              {summaryEntries.map(([key, s]) => {
                const level = s as AccuracySummaryLevel;
                return (
                  <tr key={key} className="border-b border-slate-700/50 hover:bg-slate-800/30">
                    <td className="px-3 py-2 text-slate-300">{level?.label ?? "—"}</td>
                    <td className="px-3 py-2 text-right text-slate-300">{typeof level?.count === "number" ? level.count : "—"}</td>
                    <td className="px-3 py-2 text-right text-slate-300">
                      {level?.mape != null && typeof level.mape === "number" ? `${level.mape}%` : "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-300">{typeof level?.within_1pct === "number" ? level.within_1pct : "—"}</td>
                    <td className="px-3 py-2 text-right text-slate-300">{typeof level?.within_2pct === "number" ? level.within_2pct : "—"}</td>
                    <td className="px-3 py-2 text-right text-slate-300">{typeof level?.within_5pct === "number" ? level.within_5pct : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Recommendations */}
      {recs.length > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3">
          <p className="font-medium text-amber-200 mb-2">Recommendations (tweak model?)</p>
          <ul className="list-disc list-inside text-sm text-slate-300 space-y-1">
            {recs.map((r, i) => (
              <li key={i}>{typeof r === "string" ? r : String(r ?? "")}</li>
            ))}
          </ul>
        </div>
      )}
      {recs.length === 0 && data.ok && perTicker.length > 0 && (
        <p className="text-sm text-slate-500">No strong tweak recommended; error bands are in a reasonable range.</p>
      )}
    </div>
  );
}

/** Accuracy section wrapped in error boundary to avoid full-app crash */
export function AccuracyPriceTargetsWithBoundary() {
  return (
    <AccuracyErrorBoundary>
      <AccuracyPriceTargets />
    </AccuracyErrorBoundary>
  );
}
