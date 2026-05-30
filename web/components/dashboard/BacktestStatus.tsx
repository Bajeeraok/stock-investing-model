"use client";

import { useState, useEffect, useCallback } from "react";
import { BarChart3, HelpCircle, Plus, X, Play } from "lucide-react";
import type { BacktestResult, BacktestBucketMonth } from "@/app/page";
import { INTERPRETATION_BULLETS, SCHEMA_V2_NOTE } from "@/lib/modelSemantics";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

const DEFAULT_TICKERS = ["SPY", "QQQ", "GLD"];
const YEAR_OPTIONS = [2, 5, 10] as const;
const YEAR_LABELS: Record<number, string> = { 2: "2 years", 5: "5 years", 10: "10 years" };
const BUCKET_ORDER = ["70-100", "50-70", "30-50", "0-30"];
const FORWARD_MONTHS = [1, 3, 6] as const;

function BucketTable({ buckets }: { buckets: Record<string, Record<number, BacktestBucketMonth>> }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-slate-400 border-b border-slate-700 bg-slate-800/50">
          <th className="px-3 py-2 font-medium">Model (score bucket)</th>
          <th className="px-3 py-2 font-medium">Actual 1m</th>
          <th className="px-3 py-2 font-medium">Actual 3m</th>
          <th className="px-3 py-2 font-medium">Actual 6m</th>
        </tr>
      </thead>
      <tbody>
        {BUCKET_ORDER.map((key) => {
          const months = buckets[key];
          if (!months) return null;
          return (
            <tr key={key} className="border-b border-slate-700/50 hover:bg-slate-800/30">
              <td className="px-3 py-2 font-medium text-slate-300">{key}</td>
              {FORWARD_MONTHS.map((m) => {
                const d = months[m];
                if (!d) return <td key={m} className="px-3 py-2 text-slate-500">–</td>;
                return (
                  <td key={m} className="px-3 py-2">
                    <span className={d.avg_return_pct != null && d.avg_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                      {d.avg_return_pct != null ? `${d.avg_return_pct >= 0 ? "+" : ""}${d.avg_return_pct}%` : "–"}
                    </span>
                    {d.margin_of_error_pct != null && (
                      <span className="text-slate-500 text-xs ml-1">±{d.margin_of_error_pct}%</span>
                    )}
                    <span className="text-slate-500 text-xs ml-1">({d.hit_rate != null ? `${d.hit_rate}%` : "–"} hit)</span>
                    {d.count != null && d.count > 0 && (
                      <span className="text-slate-500 text-xs block mt-0.5">N={d.count}</span>
                    )}
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ByPeriodTable({
  byPeriod,
  periodLabel,
}: {
  byPeriod: Record<string, Record<string, Record<number, BacktestBucketMonth>>>;
  periodLabel: "Year" | "Quarter";
}) {
  const periods = Object.keys(byPeriod).sort();
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-slate-400 border-b border-slate-700 bg-slate-800/50">
          <th className="px-3 py-2 font-medium">{periodLabel}</th>
          <th className="px-3 py-2 font-medium">Model (score bucket)</th>
          <th className="px-3 py-2 font-medium">Actual 1m</th>
          <th className="px-3 py-2 font-medium">Actual 3m</th>
          <th className="px-3 py-2 font-medium">Actual 6m</th>
        </tr>
      </thead>
      <tbody>
        {periods.flatMap((periodKey) =>
          BUCKET_ORDER.map((key) => {
            const bucketData = byPeriod[periodKey]?.[key];
            if (!bucketData) return null;
            const m1 = bucketData[1];
            const m3 = bucketData[3];
            const m6 = bucketData[6];
            if (!m1 && !m3 && !m6) return null;
            return (
              <tr key={`${periodKey}-${key}`} className="border-b border-slate-700/50 hover:bg-slate-800/30">
                <td className="px-3 py-2 font-medium text-slate-400">{periodKey}</td>
                <td className="px-3 py-2 font-medium text-slate-300">{key}</td>
                {FORWARD_MONTHS.map((m) => {
                  const d = bucketData[m];
                  if (!d) return <td key={m} className="px-3 py-2 text-slate-500">–</td>;
                  return (
                    <td key={m} className="px-3 py-2">
                      <span className={d.avg_return_pct != null && d.avg_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                        {d.avg_return_pct != null ? `${d.avg_return_pct >= 0 ? "+" : ""}${d.avg_return_pct}%` : "–"}
                      </span>
                      {d.margin_of_error_pct != null && (
                        <span className="text-slate-500 text-xs ml-1">±{d.margin_of_error_pct}%</span>
                      )}
                      <span className="text-slate-500 text-xs ml-1">({d.hit_rate != null ? `${d.hit_rate}%` : "–"} hit)</span>
                    </td>
                  );
                })}
              </tr>
            );
          })
        )}
      </tbody>
    </table>
  );
}

export function BacktestStatus() {
  const [tickers, setTickers] = useState<string[]>(["SPY"]);
  const [years, setYears] = useState<number>(2);
  const [addTickerInput, setAddTickerInput] = useState("");
  const [results, setResults] = useState<BacktestResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [yearsUsed, setYearsUsed] = useState(2);
  const [periodLabel, setPeriodLabel] = useState<string>("");
  const [view, setView] = useState<"overall" | "yearly" | "quarterly">("overall");
  const [lastBypassedCache, setLastBypassedCache] = useState(false);

  const fetchBacktest = useCallback(async (tickerList: string[], yearsVal: number, bypassCache = false) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ tickers: tickerList.join(","), years: String(yearsVal) });
      if (bypassCache) params.set("refresh", "true");
      const url = API_BASE ? `${API_BASE}/api/backtest?${params}` : `/api/backtest?${params}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setResults(json.backtest ?? []);
      setYearsUsed(json.backtest_years ?? yearsVal);
      setPeriodLabel(json.backtest_period ?? `${yearsVal}y`);
      setLastBypassedCache(Boolean(json.bypass_cache));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load backtest");
      setResults([]);
      setLastBypassedCache(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBacktest(tickers, years, false);
  }, []);

  const handleRun = () => fetchBacktest(tickers, years, false);
  const handleRunFresh = () => fetchBacktest(tickers, years, true);

  const toggleTicker = (t: string) => {
    setTickers((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t].sort()
    );
  };

  const addTicker = () => {
    const t = addTickerInput.trim().toUpperCase();
    if (!t || tickers.includes(t)) return;
    setTickers((prev) => [...prev, t].sort());
    setAddTickerInput("");
  };

  const removeTicker = (t: string) => {
    if (tickers.length <= 1) return;
    setTickers((prev) => prev.filter((x) => x !== t));
  };

  const availableTickers = Array.from(new Set(DEFAULT_TICKERS.concat(tickers))).sort();

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-emerald-500" />
          Backtesting status
        </h3>
        <span className="text-sm text-slate-400">
          Data: <span className="font-medium text-slate-200">{yearsUsed} year{yearsUsed !== 1 ? "s" : ""}</span>
          {periodLabel && <span className="text-slate-500 ml-1">({periodLabel})</span>}
        </span>
      </div>

      <div className="flex flex-wrap gap-4 mb-4 p-3 bg-slate-800/50 rounded-lg border border-slate-700">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Tickers</label>
          <div className="flex flex-wrap gap-2">
            {availableTickers.map((t) => (
              <label key={t} className="flex items-center gap-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={tickers.includes(t)}
                  onChange={() => toggleTicker(t)}
                  className="rounded border-slate-600 bg-slate-700 text-emerald-500 focus:ring-emerald-500"
                />
                <span className="text-sm text-slate-300 font-mono">{t}</span>
                {tickers.includes(t) && tickers.length > 1 && (
                  <button
                    type="button"
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); removeTicker(t); }}
                    className="p-0.5 rounded hover:bg-slate-600 text-slate-400"
                    aria-label={`Remove ${t}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </label>
            ))}
          </div>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Years</label>
          <select
            value={years}
            onChange={(e) => setYears(Number(e.target.value) as 2 | 5 | 10)}
            className="px-3 py-1.5 rounded-lg bg-slate-700 border border-slate-600 text-slate-200 text-sm"
          >
            {YEAR_OPTIONS.map((y) => (
              <option key={y} value={y}>{YEAR_LABELS[y]}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Add ticker</label>
          <div className="flex gap-1">
            <input
              type="text"
              value={addTickerInput}
              onChange={(e) => setAddTickerInput(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && addTicker()}
              placeholder="AAPL"
              className="px-3 py-1.5 rounded-lg bg-slate-700 border border-slate-600 text-slate-200 text-sm font-mono w-24"
            />
            <button
              type="button"
              onClick={addTicker}
              className="px-2 py-1.5 rounded-lg bg-slate-600 hover:bg-slate-500 text-slate-200"
              title="Add ticker"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-end gap-2">
          <button
            type="button"
            onClick={handleRun}
            disabled={loading || tickers.length === 0}
            className="flex items-center justify-center gap-2 px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            title="Uses Redis cache when available (24h TTL) — fast repeat runs."
          >
            <Play className={loading ? "animate-spin h-4 w-4" : "h-4 w-4"} />
            {loading ? "Running..." : "Run backtest"}
          </button>
          <button
            type="button"
            onClick={handleRunFresh}
            disabled={loading || tickers.length === 0}
            className="flex items-center justify-center gap-2 px-4 py-1.5 rounded-lg bg-slate-600 hover:bg-slate-500 text-slate-100 font-medium text-sm border border-slate-500 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Skip Redis and recompute — use after deploying code changes so results match new logic."
          >
            Re-run fresh
          </button>
        </div>
      </div>

      {lastBypassedCache && !loading && (
        <p className="text-xs text-amber-300/90 mb-2" title="Cache was skipped; results reflect current server code.">
          Last run: cache bypassed — full backtest recomputed.
        </p>
      )}

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
      <div className="mb-3 rounded-lg border border-sky-800/50 bg-sky-950/35 px-3 py-2.5 text-sm text-slate-300 leading-relaxed">
        <span className="font-medium text-sky-300">Recommended (dip entries — default):</span> Use the{" "}
        <span className="text-slate-200">live dashboard score</span> plus{" "}
        <span className="text-slate-200">interpretation</span> (mean-reverting tape = frame adds as dip-buy, not chase). This backtest helps you{" "}
        <span className="text-slate-200">sanity-check history</span>: when “Bucket rows” show mean-reverting %, high buckets ≈{" "}
        <span className="text-slate-200">dip periods</span> after the flip — compare <span className="text-slate-200">6m</span> more than 3m to see if weakness led to better outcomes. You are{" "}
        <span className="text-slate-200">not</span> trying to prove raw momentum wins; that is a different test.
      </div>
      <p className="text-sm text-slate-300 mb-2">
        <span className="font-medium text-slate-200">Model vs Actual:</span> Each row is a score bucket. The columns show the{" "}
        <span className="text-emerald-400">average actual</span> forward return (1m / 3m / 6m) when the model was in that bucket. How you read “high vs low” depends on whether buckets are raw momentum or MR-mapped — see the callout above and the spread line under each ticker.
      </p>
      {results.some((r) => r.schema_version != null) && (
        <p className="text-xs text-slate-500 mb-2 leading-snug" title={SCHEMA_V2_NOTE}>
          <span className="text-slate-400 font-medium">Backtest schema:</span> {SCHEMA_V2_NOTE} After a deploy, use{" "}
          <span className="text-slate-300">Re-run fresh</span> so Redis does not serve stale JSON.
        </p>
      )}
      <div className="flex gap-2 mb-4">
        {(["overall", "yearly", "quarterly"] as const).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
              view === v
                ? "bg-emerald-600 text-white"
                : "bg-slate-700/50 text-slate-400 hover:bg-slate-700 hover:text-slate-200"
            }`}
          >
            {v === "overall" ? "Overall" : v === "yearly" ? "By year" : "By quarter"}
          </button>
        ))}
      </div>
      {loading && results.length === 0 ? (
        <div className="flex items-center justify-center gap-3 py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-emerald-500 border-t-transparent" />
          <p className="text-slate-400">Running backtest... This may take 1–2 min per ticker.</p>
        </div>
      ) : (
      <div className="space-y-4">
        {results.map((r) => (
          <div key={r.ticker} className="border border-slate-700 rounded-lg overflow-hidden">
            {r.error ? (
              <div className="px-4 py-3 text-sm text-amber-400 bg-amber-500/5">{r.ticker}: {r.error}</div>
            ) : (
              <>
                <div className="px-4 py-2 bg-slate-800/80 border-b border-slate-700 flex flex-wrap items-center gap-2">
                  <span className="font-mono font-medium text-slate-200">{r.ticker}</span>
                  {r.schema_version != null && (
                    <span
                      className="text-[10px] uppercase tracking-wide font-sans font-normal text-emerald-400/90 px-2 py-0.5 rounded border border-emerald-700/50 bg-emerald-950/40"
                      title="API bucket-assignment schema — compare across deploys"
                    >
                      Schema v{r.schema_version}
                    </span>
                  )}
                </div>
                {r.bucket_assignment_note && (
                  <p className="px-4 py-1.5 text-xs text-slate-400 bg-slate-900/40 border-b border-slate-700/50 leading-snug">
                    {r.bucket_assignment_note}
                  </p>
                )}
                {r.bucket_assignment_stats &&
                  r.bucket_assignment_stats.n_bars_scored > 0 &&
                  r.bucket_assignment_stats.pct_mean_reverting != null &&
                  r.bucket_assignment_stats.pct_trending != null && (
                    <p
                      className="px-4 py-1.5 text-xs text-slate-500 bg-slate-900/30 border-b border-slate-700/40 leading-snug font-mono"
                      title="Per trading day in the backtest window: MR = bucket uses (100 − raw score); Trending = raw composite bucket. Add ticker to force_mean_reverting if MR% is low and buckets look inverted."
                    >
                      Bucket rows:{" "}
                      <span className="text-slate-300">{r.bucket_assignment_stats.pct_mean_reverting}%</span>{" "}
                      mean-reverting (100−score) ·{" "}
                      <span className="text-slate-300">{r.bucket_assignment_stats.pct_trending}%</span> trending
                      (raw) · N={r.bucket_assignment_stats.n_bars_scored}
                    </p>
                  )}
                {r.buckets && (() => {
                  const high = r.buckets["70-100"]?.[3]?.avg_return_pct;
                  const low = r.buckets["0-30"]?.[3]?.avg_return_pct;
                  const edge = high != null && low != null ? (high - low) : null;
                  const pctMr = r.bucket_assignment_stats?.pct_mean_reverting ?? 0;
                  const mrDominated = pctMr >= 50;
                  return edge != null ? (
                    <p className="px-4 py-2 text-sm text-slate-300 bg-slate-800/50 border-b border-slate-700/50 leading-snug">
                      {mrDominated ? (
                        <>
                          <span className="font-medium text-sky-400">MR bucket spread (3m):</span> dip-period rows (70–100
                          after flip) vs momentum-period rows (0–30) ={" "}
                          <span className={edge >= 0 ? "text-emerald-400" : "text-amber-300"}>
                            {edge >= 0 ? "+" : ""}{edge.toFixed(1)}%
                          </span>{" "}
                          (dip − momentum).{" "}
                          {edge >= 0 ? (
                            <span className="text-slate-400">Dips led 3m — MR-style edge.</span>
                          ) : (
                            <span className="text-slate-400">
                              Momentum led 3m — common for mega-cap growth; not a failed flip.
                            </span>
                          )}
                        </>
                      ) : (
                        <>
                          <span className="font-medium text-emerald-400">Model edge:</span> 70–100 bucket beats 0–30 by{" "}
                          <span className={edge >= 0 ? "text-emerald-400" : "text-red-400"}>
                            {edge >= 0 ? "+" : ""}{edge.toFixed(1)}%
                          </span>{" "}
                          per 3m (avg).
                        </>
                      )}
                    </p>
                  ) : null;
                })()}
                {r.bucket_return_ordering_notes &&
                  r.bucket_return_ordering_notes.length > 0 && (
                    <ul className="px-4 py-2 text-xs text-slate-400 bg-amber-950/25 border-b border-amber-900/35 leading-snug space-y-1 list-disc list-inside marker:text-amber-600/80">
                      {r.bucket_return_ordering_notes.map((note, i) => (
                        <li key={i}>{note}</li>
                      ))}
                    </ul>
                  )}
                {r.earnings_exclusion && r.earnings_exclusion.enabled && (
                  <p
                    className="px-4 py-1.5 text-xs text-slate-500 bg-slate-900/35 border-b border-slate-700/40 leading-snug"
                    title="Short-horizon noise reduction: bars skipped when next earnings within N calendar days (FMP). See docs/backend/BACKTEST_DATA.md."
                  >
                    <span className="text-slate-400">Earnings exclusion:</span>{" "}
                    {r.earnings_exclusion.days_before}d window ·{" "}
                    {r.earnings_exclusion.bars_skipped ?? 0} bars skipped
                    {r.earnings_exclusion.dates_loaded != null && r.earnings_exclusion.dates_loaded > 0
                      ? ` · ${r.earnings_exclusion.dates_loaded} FMP dates`
                      : ""}
                    {r.earnings_exclusion.note ? ` — ${r.earnings_exclusion.note}` : ""}
                  </p>
                )}
                {r.spy_regime_summary &&
                  r.spy_regime_summary.pct_trading_days_bull != null &&
                  r.spy_regime_summary.bars_counted != null &&
                  r.spy_regime_summary.bars_counted > 0 && (
                    <p
                      className="px-4 py-1.5 text-xs text-slate-500 bg-slate-900/25 border-b border-slate-700/35 leading-snug"
                      title={r.spy_regime_summary.note ?? ""}
                    >
                      <span className="text-slate-400">Market regime (window):</span>{" "}
                      {r.spy_regime_summary.benchmark} vs {r.spy_regime_summary.ma_days}d SMA —{" "}
                      {r.spy_regime_summary.pct_trading_days_bull}% bull ·{" "}
                      {r.spy_regime_summary.pct_trading_days_bear ?? "—"}% bear ·{" "}
                      {r.spy_regime_summary.pct_trading_days_neutral ?? "—"}% neutral ({r.spy_regime_summary.bars_counted}{" "}
                      bars)
                    </p>
                  )}
                <div className="overflow-x-auto">
                  {view === "overall" && r.buckets && Object.keys(r.buckets).length > 0 && (
                    <BucketTable buckets={r.buckets} />
                  )}
                  {view === "yearly" && r.by_year && Object.keys(r.by_year).length > 0 && (
                    <ByPeriodTable byPeriod={r.by_year} periodLabel="Year" />
                  )}
                  {view === "quarterly" && r.by_quarter && Object.keys(r.by_quarter).length > 0 && (
                    <ByPeriodTable byPeriod={r.by_quarter} periodLabel="Quarter" />
                  )}
                  {view === "yearly" && (!r.by_year || Object.keys(r.by_year).length === 0) && (
                    <p className="px-4 py-3 text-sm text-slate-500">No by-year data.</p>
                  )}
                  {view === "quarterly" && (!r.by_quarter || Object.keys(r.by_quarter).length === 0) && (
                    <p className="px-4 py-3 text-sm text-slate-500">No by-quarter data.</p>
                  )}
                </div>
                {r.validation && !r.validation.valid && r.validation.issues.length > 0 && (
                  <div className="px-4 py-2 bg-amber-500/10 border-t border-amber-500/30 text-sm">
                    <p className="font-medium text-amber-400 mb-1">Data quality</p>
                    <ul className="list-disc list-inside text-amber-200/90 space-y-0.5">
                      {r.validation.issues.slice(0, 3).map((issue, i) => (
                        <li key={i}>{issue}</li>
                      ))}
                    </ul>
                    {r.validation.data_quality_score != null && (
                      <p className="text-amber-400/80 text-xs mt-1">Score: {r.validation.data_quality_score}/100</p>
                    )}
                  </div>
                )}
                <div className="px-4 py-3 bg-slate-800/30 border-t border-slate-700 space-y-2">
                  <div className="flex items-start gap-3 text-sm text-slate-300">
                    <HelpCircle className="h-5 w-5 text-amber-500/80 flex-shrink-0 mt-0.5" />
                    <div className="space-y-2.5">
                      <p className="font-semibold text-slate-200 text-base">How to interpret – quick reference</p>
                      <ul className="space-y-2 list-disc list-inside">
                        {INTERPRETATION_BULLETS.map((b) => (
                          <li key={b.label}>
                            <span className="font-medium text-slate-200">{b.label}:</span> {b.text}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  {(r.suggested_buy_min || r.suggested_sell_max) && (
                    <div className="text-sm text-slate-300 space-y-1.5 pt-2 border-t border-slate-700/50">
                      {r.suggested_buy_min && <p><span className="text-emerald-400">Buy:</span> {r.suggested_buy_min}</p>}
                      {r.suggested_sell_max && <p><span className="text-red-400">Sell:</span> {r.suggested_sell_max}</p>}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        ))}
      </div>
      )}
    </div>
  );
}
