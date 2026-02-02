"use client";

import { useEffect, useState } from "react";
import { X, TrendingUp, FileText, Calendar, BarChart3, HelpCircle } from "lucide-react";
import { clsx } from "clsx";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

export interface TickerDetail {
  ticker: string;
  thesis: string;
  exit_condition: string;
  short_suggestion?: string;
  medium_suggestion?: string;
  long_suggestion?: string;
  short_reason?: string;
  medium_reason?: string;
  long_reason?: string;
  price_reasoning?: { buy?: string; sell?: string; support?: string };
  ma20?: number | null;
  ma50?: number | null;
  ma200?: number | null;
  earnings: { date: string; days_until: number } | null;
  sector: string | null;
  industry: string | null;
  sector_etf: string;
  sector_etf_name: string;
  peers: string[];
  current_price: number | null;
  returns: Record<string, number>;
  benchmark_spy: Record<string, number>;
  benchmark_industry: Record<string, number>;
  peer_returns: { ticker: string; returns: Record<string, number> }[];
  volume_ratio?: number | null;
  volume_unusual?: boolean;
  drawdown_52w?: number | null;
  dividend_yield?: number | null;
  high_52w?: number | null;
  low_52w?: number | null;
  beta?: number | null;
  st_band?: { low: number; high: number } | null;
  mt_band?: { low: number; high: number } | null;
  lt_band?: { low: number; high: number } | null;
  lt_band_low_confidence?: boolean;
}

export function TickerDetailModal({
  ticker,
  onClose,
}: {
  ticker: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<TickerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    const url = API_BASE ? `${API_BASE}/api/ticker/${ticker}` : `/api/ticker/${ticker}`;
    fetch(url)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setDetail)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [ticker]);

  const periods = ["1m", "3m", "6m", "1y"];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        className="bg-slate-900 border border-slate-700 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-slate-900 border-b border-slate-700 px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <TrendingUp className="h-6 w-6 text-emerald-500" />
            {ticker}
            {detail?.sector && (
              <span className="text-sm font-normal text-slate-400">· {detail.sector}</span>
            )}
          </h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {loading && (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-10 w-10 border-2 border-emerald-500 border-t-transparent" />
            </div>
          )}
          {error && (
            <p className="text-red-400 py-4">Failed to load: {error}</p>
          )}
          {detail && !loading && (
            <>
              {/* Quick reference – bullet summary for retail investors */}
              <section className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-4 mb-4">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-emerald-400 mb-3">
                  <HelpCircle className="h-4 w-4" />
                  Quick reference – What each metric means
                </h3>
                <ul className="space-y-2 text-sm text-slate-300 list-disc list-inside">
                  <li><span className="font-medium text-slate-200">Price vs MAs:</span> Price &gt; MA50 &gt; MA200 = uptrend. Price &lt; MA50 &lt; MA200 = downtrend.</li>
                  <li><span className="font-medium text-slate-200">MA20:</span> Short-term trend. Price above = bullish; break below = watch for weakness.</li>
                  <li><span className="font-medium text-slate-200">MA50:</span> Medium-term trend. Often used for add-on pullbacks.</li>
                  <li><span className="font-medium text-slate-200">MA200:</span> Long-term trend. Price above = broader uptrend intact.</li>
                  <li><span className="font-medium text-emerald-400">Buy:</span> Suggested add level (e.g. pullback to MA50). Only shown when no sell signal.</li>
                  <li><span className="font-medium text-red-400">Sell:</span> Actionable trim/exit when overbought (RSI high) or score weak.</li>
                  <li><span className="font-medium text-amber-400">Support:</span> MA20 when price is above it. Break below = caution, not a sell trigger.</li>
                  <li><span className="font-medium text-slate-200">Position size:</span> Normal size when macro is calm; reduce size when guidelines show elevated risk (real yields, VIX, crowded positioning).</li>
                  <li><span className="font-medium text-slate-200">Short (~1 mo):</span> MA20 vs MA50 + RSI. Quick momentum view.</li>
                  <li><span className="font-medium text-slate-200">Medium (~3–6 mo):</span> Composite score. Main signal for adds/trims.</li>
                  <li><span className="font-medium text-slate-200">Long (1–2 yr):</span> Price vs MA200. Big-picture trend.</li>
                  <li><span className="font-medium text-slate-200">Vol vs 20d avg:</span> Today&apos;s volume ÷ 20-day average. ≥2× = unusual; interpret with price direction.</li>
                  <li><span className="font-medium text-slate-200">Drawdown 52w:</span> % below 52-week high. Larger negative = farther from peak.</li>
                  <li><span className="font-medium text-slate-200">52w range:</span> Low–high. Near high = extended; near low = value or weakness.</li>
                  <li><span className="font-medium text-slate-200">Dividend yield:</span> Annual yield. Income component of total return.</li>
                  <li><span className="font-medium text-slate-200">Beta:</span> Volatility vs SPY. β &gt; 1 = more volatile; β &lt; 1 = less.</li>
                  <li><span className="font-medium text-slate-200">vs Market:</span> Your ticker return minus SPY. Positive = outperformance.</li>
                </ul>
              </section>

              {/* Moving averages – compare against reasoning */}
              {(detail.ma20 != null || detail.ma50 != null || detail.ma200 != null) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-3">
                    <BarChart3 className="h-4 w-4 text-emerald-500" />
                    Moving averages
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                    {detail.current_price != null && (
                      <div className="bg-slate-800 rounded-lg p-2">
                        <p className="text-slate-500 text-xs font-medium">Price</p>
                        <p className="text-slate-100 font-mono font-semibold">${detail.current_price.toFixed(2)}</p>
                      </div>
                    )}
                    {detail.ma20 != null && (
                      <div className="bg-slate-800 rounded-lg p-2">
                        <p className="text-slate-500 text-xs font-medium">MA20</p>
                        <p className="text-slate-200 font-mono font-semibold">${detail.ma20.toFixed(2)}</p>
                      </div>
                    )}
                    {detail.ma50 != null && (
                      <div className="bg-slate-800 rounded-lg p-2">
                        <p className="text-slate-500 text-xs font-medium">MA50</p>
                        <p className="text-slate-200 font-mono font-semibold">${detail.ma50.toFixed(2)}</p>
                      </div>
                    )}
                    {detail.ma200 != null && (
                      <div className="bg-slate-800 rounded-lg p-2">
                        <p className="text-slate-500 text-xs font-medium">MA200</p>
                        <p className="text-slate-200 font-mono font-semibold">${detail.ma200.toFixed(2)}</p>
                      </div>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-2">
                    Compare against reasons: price &gt; MA50 &gt; MA200 = uptrend; price &lt; MA50 &lt; MA200 = downtrend.
                  </p>
                </section>
              )}

              {/* Target bands – ST/MT/LT price ranges */}
              {(detail.st_band || detail.mt_band || detail.lt_band) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200 mb-3">
                    <TrendingUp className="h-4 w-4 text-emerald-500" />
                    Target price bands (context, not promises)
                  </h3>
                  <div className="space-y-3 text-sm">
                    {detail.st_band && (
                      <div>
                        <p className="font-medium text-slate-300">Short-term (days–weeks)</p>
                        <p className="text-slate-400">
                          Stop: ${detail.st_band.low.toFixed(2)} – Target: ${detail.st_band.high.toFixed(2)}
                        </p>
                        <p className="text-xs text-slate-500 mt-0.5">ATR-based; MA20/swing context</p>
                      </div>
                    )}
                    {detail.mt_band && (
                      <div>
                        <p className="font-medium text-slate-300">Medium-term (months)</p>
                        <p className="text-slate-400">
                          Low: ${detail.mt_band.low.toFixed(2)} – High: ${detail.mt_band.high.toFixed(2)}
                        </p>
                        <p className="text-xs text-slate-500 mt-0.5">Regime + 6m volatility band</p>
                      </div>
                    )}
                    {detail.lt_band && (
                      <div>
                        <p className="font-medium text-slate-300">Long-term (1–3+ yr)</p>
                        <p className="text-slate-400">
                          Low: ${detail.lt_band.low.toFixed(2)} – High: ${detail.lt_band.high.toFixed(2)}
                          {detail.lt_band_low_confidence && (
                            <span className="ml-2 text-amber-400 text-xs">(low confidence – high analyst dispersion)</span>
                          )}
                        </p>
                        <p className="text-xs text-slate-500 mt-0.5">Fair value (EPS × P/E) blended with analyst consensus</p>
                      </div>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 mt-3 border-t border-slate-700/50 pt-3">
                    Use ST band for trades up to ~1 month, MT band for 3–6 months; LT is 1–3+ years.
                  </p>
                </section>
              )}

              {/* Buy / Sell / Support – reasoning (helps learn and understand) */}
              {detail.price_reasoning && (detail.price_reasoning.buy || detail.price_reasoning.sell || detail.price_reasoning.support) && (
                <section className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-emerald-400 mb-3">
                    <TrendingUp className="h-4 w-4" />
                    Buy / Sell / Support – What it means
                  </h3>
                  <div className="space-y-2 text-sm">
                    {detail.price_reasoning.buy && (
                      <p className="text-slate-300">
                        <span className="text-emerald-400 font-medium">Buy:</span> {detail.price_reasoning.buy}
                      </p>
                    )}
                    {detail.price_reasoning.sell && (
                      <p className="text-slate-300">
                        <span className="text-red-400 font-medium">Sell:</span> {detail.price_reasoning.sell}
                      </p>
                    )}
                    {detail.price_reasoning.support && (
                      <p className="text-slate-300">
                        <span className="text-amber-400 font-medium">Support:</span> {detail.price_reasoning.support}
                      </p>
                    )}
                  </div>
                </section>
              )}

              {/* Signal & reasoning */}
              {(detail.short_suggestion || detail.medium_suggestion || detail.long_suggestion) && (
                <section>
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-3">
                    <TrendingUp className="h-4 w-4" />
                    Hold / Buy / Sell – Reasoning
                  </h3>
                  <div className="space-y-3">
                    {detail.short_suggestion && (
                      <div className="bg-slate-800/50 rounded-lg p-3">
                        <span className={clsx(
                          "font-medium",
                          detail.short_suggestion.includes("ADD") && "text-emerald-400",
                          detail.short_suggestion.includes("TRIM") && "text-red-400",
                          detail.short_suggestion === "HOLD" && "text-slate-300"
                        )}>
                          Short (~1 mo): {detail.short_suggestion}
                        </span>
                        {detail.short_reason && (
                          <p className="text-sm text-slate-400 mt-1">{detail.short_reason}</p>
                        )}
                      </div>
                    )}
                    {detail.medium_suggestion && (
                      <div className="bg-slate-800/50 rounded-lg p-3">
                        <span className={clsx(
                          "font-medium",
                          detail.medium_suggestion.includes("ADD") && "text-emerald-400",
                          detail.medium_suggestion.includes("TRIM") && "text-red-400",
                          detail.medium_suggestion === "HOLD" && "text-slate-300"
                        )}>
                          Medium (~3–6 mo): {detail.medium_suggestion}
                        </span>
                        {detail.medium_reason && (
                          <p className="text-sm text-slate-400 mt-1">{detail.medium_reason}</p>
                        )}
                      </div>
                    )}
                    {detail.long_suggestion && (
                      <div className="bg-slate-800/50 rounded-lg p-3">
                        <span className={clsx(
                          "font-medium",
                          detail.long_suggestion.includes("ADD") && "text-emerald-400",
                          detail.long_suggestion.includes("TRIM") && "text-red-400",
                          detail.long_suggestion === "HOLD" && "text-slate-300"
                        )}>
                          Long (1–2 yr): {detail.long_suggestion}
                        </span>
                        {detail.long_reason && (
                          <p className="text-sm text-slate-400 mt-1">{detail.long_reason}</p>
                        )}
                      </div>
                    )}
                  </div>
                </section>
              )}

              {/* Thesis */}
              {(detail.thesis || detail.exit_condition) && (
                <section>
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-2">
                    <FileText className="h-4 w-4" />
                    Thesis
                  </h3>
                  <div className="bg-slate-800/50 rounded-lg p-4 text-sm text-slate-300 space-y-2">
                    {detail.thesis && <p>{detail.thesis}</p>}
                    {detail.exit_condition && (
                      <p className="text-amber-400/90">
                        <span className="text-slate-400">Exit when:</span> {detail.exit_condition}
                      </p>
                    )}
                    {!detail.thesis && !detail.exit_condition && (
                      <p className="text-slate-500 italic">No thesis. Add in data/theses.yaml or via add_thesis.py</p>
                    )}
                  </div>
                </section>
              )}

              {/* Earnings */}
              {detail.earnings && (
                <section>
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-2">
                    <Calendar className="h-4 w-4" />
                    Earnings
                  </h3>
                  <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-2 text-sm text-amber-200">
                    {detail.earnings.date}
                    {detail.earnings.days_until != null && (
                      <span className="text-amber-400/80 ml-2">
                        ({detail.earnings.days_until > 0 ? `in ${detail.earnings.days_until} days` : "recent"})
                      </span>
                    )}
                  </div>
                </section>
              )}

              {/* Benchmark comparison */}
              <section>
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-3">
                  <BarChart3 className="h-4 w-4" />
                  Performance vs Benchmarks
                </h3>
                <div className="rounded-lg border border-slate-700 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-800/80 text-left text-slate-400">
                        <th className="px-4 py-2 font-medium">Period</th>
                        <th className="px-4 py-2 font-medium text-emerald-400">{detail.ticker}</th>
                        <th className="px-4 py-2 font-medium">SPY (Market)</th>
                        <th className="px-4 py-2 font-medium">{detail.sector_etf_name}</th>
                        <th className="px-4 py-2 font-medium text-slate-500">vs Market</th>
                      </tr>
                    </thead>
                    <tbody>
                      {periods.map((p) => {
                        const r = detail.returns[p];
                        const spy = detail.benchmark_spy[p];
                        const ind = detail.benchmark_industry[p];
                        const vsSpy = r != null && spy != null ? r - spy : null;
                        return (
                          <tr key={p} className="border-t border-slate-700/50">
                            <td className="px-4 py-2 text-slate-400">{p}</td>
                            <td className="px-4 py-2">
                              <span className={r != null ? (r >= 0 ? "text-emerald-400" : "text-red-400") : "text-slate-500"}>
                                {r != null ? `${r >= 0 ? "+" : ""}${r}%` : "-"}
                              </span>
                            </td>
                            <td className="px-4 py-2">
                              <span className={spy != null ? (spy >= 0 ? "text-emerald-400" : "text-red-400") : "text-slate-500"}>
                                {spy != null ? `${spy >= 0 ? "+" : ""}${spy}%` : "-"}
                              </span>
                            </td>
                            <td className="px-4 py-2">
                              <span className={ind != null ? (ind >= 0 ? "text-emerald-400" : "text-red-400") : "text-slate-500"}>
                                {ind != null ? `${ind >= 0 ? "+" : ""}${ind}%` : "-"}
                              </span>
                            </td>
                            <td className="px-4 py-2">
                              {vsSpy != null ? (
                                <span className={vsSpy >= 0 ? "text-emerald-400" : "text-red-400"}>
                                  {vsSpy >= 0 ? "+" : ""}{vsSpy.toFixed(1)}%
                                </span>
                              ) : (
                                "-"
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>

              {/* Peer comparison */}
              {(detail.peer_returns?.length ?? 0) > 0 && (
                <section>
                  <h3 className="text-sm font-semibold text-slate-300 mb-2">Top Peers ({detail.industry || detail.sector || "same sector"})</h3>
                  <div className="rounded-lg border border-slate-700 overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-slate-800/80 text-left text-slate-400">
                          <th className="px-4 py-2 font-medium">Ticker</th>
                          {periods.map((p) => (
                            <th key={p} className="px-4 py-2 font-medium">{p}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-t border-slate-700/50 bg-emerald-500/5">
                          <td className="px-4 py-2 font-mono font-medium text-emerald-400">{detail.ticker}</td>
                          {periods.map((p) => (
                            <td key={p} className="px-4 py-2">
                              <span className={detail.returns[p] != null ? (detail.returns[p]! >= 0 ? "text-emerald-400" : "text-red-400") : "text-slate-500"}>
                                {detail.returns[p] != null ? `${detail.returns[p]! >= 0 ? "+" : ""}${detail.returns[p]}%` : "-"}
                              </span>
                            </td>
                          ))}
                        </tr>
                        {detail.peer_returns.map((pr) => (
                          <tr key={pr.ticker} className="border-t border-slate-700/50">
                            <td className="px-4 py-2 font-mono text-slate-300">{pr.ticker}</td>
                            {periods.map((p) => (
                              <td key={p} className="px-4 py-2">
                                {pr.returns[p] != null ? (
                                  <span className={pr.returns[p]! >= 0 ? "text-emerald-400" : "text-red-400"}>
                                    {pr.returns[p]! >= 0 ? "+" : ""}{pr.returns[p]}%
                                  </span>
                                ) : (
                                  <span className="text-slate-500">-</span>
                                )}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-xs text-slate-500 mt-2">
                    Compare vs industry ETF ({detail.sector_etf}) and peers to gauge relative strength.
                  </p>
                </section>
              )}

              {/* Volume & drawdown with interpretation */}
              {(detail.volume_ratio != null || detail.drawdown_52w != null) && (
                <section className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                  <h3 className="flex items-center gap-2 text-base font-semibold text-slate-200 mb-3">
                    <HelpCircle className="h-4 w-4" />
                    Understanding today&apos;s metrics
                  </h3>
                  <div className="space-y-4 text-sm">
                    {detail.volume_ratio != null && (
                      <div className={detail.volume_unusual ? "bg-amber-500/10 border border-amber-500/30 rounded-lg p-4" : ""}>
                        <p className="font-medium text-slate-200">
                          Vol vs 20d avg: <span className={detail.volume_unusual ? "text-amber-400 font-bold" : "text-slate-300"}>{detail.volume_ratio}x</span>
                          {detail.volume_unusual && " (unusual)"}
                        </p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">
                          Today&apos;s volume is {detail.volume_ratio}× the 20-day average. {detail.volume_unusual ? "Orange = unusual (≥2×). High volume often signals news, institutional activity, or a potential breakout—interpret with price direction (up = buying interest, down = selling pressure)." : "Normal range. Volume &lt; 2× avg is typical."}
                        </p>
                        {detail.volume_unusual && (
                          <p className="text-amber-200 mt-2 text-sm font-medium leading-relaxed">
                            Recommended: Check if price moved up (buying interest) or down (selling pressure). If up on high volume, consider it confirmation; if down, watch for follow-through before adding. Look for news or catalysts before sizing in.
                          </p>
                        )}
                      </div>
                    )}
                    {detail.drawdown_52w != null && (
                      <div>
                        <p className="font-medium text-slate-200">
                          Drawdown (52w): <span className={detail.drawdown_52w < -10 ? "text-red-400" : "text-slate-300"}>{detail.drawdown_52w}%</span>
                        </p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">
                          Price is {detail.drawdown_52w >= 0 ? "at or above" : `${Math.abs(detail.drawdown_52w)}% below`} the 52-week high. Larger drawdowns = more distance from peak; can signal consolidation or weakness.
                        </p>
                      </div>
                    )}
                    {(detail.high_52w != null || detail.low_52w != null) && (
                      <div>
                        <p className="font-medium text-slate-200">
                          52w range: {detail.low_52w != null && `$${detail.low_52w}`} – {detail.high_52w != null && `$${detail.high_52w}`}
                        </p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">
                          Where price sits in the yearly range. Near high = extended; near low = potential value or weakness.
                        </p>
                      </div>
                    )}
                    {detail.dividend_yield != null && detail.dividend_yield > 0 && (
                      <div>
                        <p className="font-medium text-slate-200">Dividend yield: {detail.dividend_yield}%</p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">Annual yield. ETFs like GLD don&apos;t pay dividends.</p>
                      </div>
                    )}
                    {detail.beta != null && (
                      <div>
                        <p className="font-medium text-slate-200">Beta vs SPY: {detail.beta}</p>
                        <p className="text-slate-300 mt-2 text-sm leading-relaxed">β &gt; 1 = more volatile than market; β &lt; 1 = less. Gold (GLD) often has low/negative beta.</p>
                      </div>
                    )}
                  </div>
                </section>
              )}

              {detail.current_price != null && (
                <p className="text-sm text-slate-500">Current price: ${detail.current_price.toFixed(2)}</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
