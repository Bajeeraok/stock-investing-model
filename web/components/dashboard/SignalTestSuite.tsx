"use client";

/**
 * SignalTestSuite.tsx
 * Live Signal Behavior Test Suite — replicates the pre-flight HTML design
 * with real backend data, add-ticker-on-the-fly, and report generation.
 *
 * Tab: "Test Suite" (7th tab in DashboardTabs)
 * Endpoint: POST /api/test-suite
 */

import { useState, useCallback, useRef } from "react";
import {
  Play, Plus, X, Download, RefreshCw, FlaskConical,
  AlertTriangle, Info, Ban, Zap, ChevronDown, ChevronRight,
  CheckCircle, Circle, Filter,
} from "lucide-react";
import { clsx } from "clsx";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface Flag { type: "error" | "warn" | "info"; message: string; }

interface WeightProfile {
  regime: number; pattern: number; ml: number; options: number;
  insider: number; fundamentals: number; news: number;
}

interface ClassificationResult {
  ticker: string;
  asset_type: string;
  name: string;
  sector: string;
  is_scoreable: boolean;
  weight_profile: WeightProfile;
  weight_label: string;
  flags: Flag[];
  flag_count: number;
}

interface CoherenceResult {
  level: "HIGH" | "MODERATE" | "LOW" | "INCOHERENT";
  std_dev: number | null;
  mean: number | null;
  spread: number | null;
  active_layer_count: number;
  tradeable: boolean;
  is_contrarian: boolean;
  message: string;
}

interface TransitionBonus {
  bonus_active: boolean;
  upgrade: string | null;
  rationale: string | null;
  days_to_confirm: number | null;
}

interface RSIDirection {
  signal: string;
  label: string;
  rsi_current: number;
  delta: number;
  pattern_bonus: number;
  is_oversold: boolean;
  is_overbought: boolean;
}

interface BreakdownLayer {
  score: number | null;
  weight: number;
  label: string;
  available: boolean;
}

interface ConfidenceResult {
  ticker: string;
  confidence: number | null;
  action: string;
  n_layers_active: number;
  breakdown: Record<string, BreakdownLayer>;
  hmm?: {
    dominant_state?: string;
    dominant_state_validated?: string;
    ma_conflict?: {
      reason?: string;
      last_close?: number;
      ma50?: number;
      ma200?: number;
    } | null;
  } | null;
  pre_flight?: {
    coherence: CoherenceResult | null;
    transition_bonus: TransitionBonus | null;
    rsi_direction: RSIDirection | null;
    flags: Flag[];
    current_mode: string | null;
    current_action: string | null;
    position_size: string | null;
  };
  error?: string;
}

interface TickerResult {
  ticker: string;
  classification: ClassificationResult | null;
  confidence: ConfidenceResult | null;
  error: string | null;
  elapsed_ms: number;
  loading?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_TICKERS = [
  "NVDA","TSLA","PLTR","BRK-B","KO",
  "GLD","BABA","BIDU","ARKK","UVXY",
];

const ASSET_TYPE_LABELS: Record<string, string> = {
  EQUITY_US:          "US Equity",
  EQUITY_SPECULATIVE: "Speculative",
  EQUITY_DEFENSIVE:   "Defensive",
  EQUITY_ADR:         "ADR",
  ETF_EQUITY:         "ETF",
  ETF_COMMODITY:      "Commodity",
  ETF_VOLATILITY:     "Volatility",
};

const FILTER_TABS = [
  { id: "all",                label: "All"        },
  { id: "EQUITY_US",         label: "US Equity"  },
  { id: "EQUITY_SPECULATIVE", label: "Speculative"},
  { id: "EQUITY_DEFENSIVE",  label: "Defensive"  },
  { id: "EQUITY_ADR",        label: "ADR"        },
  { id: "ETF_EQUITY",        label: "ETF"        },
  { id: "ETF_COMMODITY",     label: "Commodity"  },
  { id: "ETF_VOLATILITY",    label: "Volatility" },
];

const LAYER_LABELS: Record<string, string> = {
  regime_hmm:        "Regime HMM",
  pattern_technical: "Pattern Score",
  lgbm_probability:  "ML Probability",
  options_sentiment: "Options Sentiment",
  insider_signal:    "Insider Activity",
  fundamental_score: "Fundamentals",
  nlp_sentiment:     "News Sentiment",
};

// ─────────────────────────────────────────────────────────────────────────────
// Colour helpers
// ─────────────────────────────────────────────────────────────────────────────

function scoreColor(v: number | null): string {
  if (v === null) return "text-slate-500";
  if (v >= 65) return "text-emerald-400";
  if (v >= 40) return "text-amber-400";
  return "text-red-400";
}

function scoreBg(v: number | null): string {
  if (v === null) return "bg-slate-700";
  if (v >= 65) return "bg-emerald-500";
  if (v >= 40) return "bg-amber-500";
  return "bg-red-500";
}

function coherenceColor(level: string) {
  return level === "HIGH"       ? { text: "text-emerald-300", bg: "bg-emerald-500/15", border: "border-emerald-500/40" } :
         level === "MODERATE"   ? { text: "text-amber-300",   bg: "bg-amber-500/15",   border: "border-amber-500/40"   } :
         level === "LOW"        ? { text: "text-orange-300",  bg: "bg-orange-500/15",  border: "border-orange-500/40"  } :
                                  { text: "text-red-300",     bg: "bg-red-500/15",     border: "border-red-500/40"     };
}

function assetTypeColor(type: string): string {
  return type === "ETF_COMMODITY"      ? "text-yellow-300" :
         type === "ETF_EQUITY"         ? "text-blue-300"   :
         type === "ETF_VOLATILITY"     ? "text-red-400"    :
         type === "EQUITY_ADR"         ? "text-purple-300" :
         type === "EQUITY_SPECULATIVE" ? "text-orange-300" :
         type === "EQUITY_DEFENSIVE"   ? "text-teal-300"   :
                                         "text-slate-300";
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function SummaryChip({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div className="bg-slate-900 border border-slate-700/60 rounded-xl p-4 text-center">
      <div className={clsx("font-mono text-3xl font-bold leading-none", color)}>{value}</div>
      <div className="text-[10px] text-slate-500 uppercase tracking-widest mt-1.5">{label}</div>
    </div>
  );
}

function SignalBar({ label, score, weight }: { label: string; score: number | null; weight: number }) {
  const wPct   = Math.round(weight * 100);
  const isZero = weight === 0;
  const hasData = score !== null && !isZero;
  const sPct   = hasData ? Math.round(score!) : null;

  return (
    <div className="bg-slate-800/70 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] text-slate-400 font-medium">
          {label}
          {isZero
            ? <span className="ml-1.5 text-red-400/70 text-[9px] font-bold">DISABLED</span>
            : <span className="ml-1 text-slate-600 text-[9px]">({wPct}%)</span>}
        </span>
        <span className={clsx("font-mono text-xs font-bold", hasData ? scoreColor(sPct) : "text-slate-600")}>
          {isZero ? "—" : sPct !== null ? `${sPct}%` : "N/A"}
        </span>
      </div>
      {!isZero && (
        <div className="h-1 rounded-full bg-slate-700/60 overflow-hidden">
          {hasData && sPct !== null && (
            <div className={clsx("h-full rounded-full transition-all duration-700", scoreBg(sPct))}
                 style={{ width: `${sPct}%` }} />
          )}
        </div>
      )}
    </div>
  );
}

function WeightGrid({ wp, label }: { wp: WeightProfile; label: string }) {
  const keys: (keyof WeightProfile)[] = ["regime","pattern","ml","options","insider","fundamentals","news"];
  const names = { regime:"Regime", pattern:"Pattern", ml:"ML", options:"Options", insider:"Insider", fundamentals:"Fund.", news:"News" };
  return (
    <div className="p-4 border-t border-slate-700/40">
      <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mb-2">
        Weight Profile — {label}
      </p>
      <div className="grid grid-cols-4 sm:grid-cols-7 gap-1.5">
        {keys.map(k => {
          const v = wp[k];
          const pct = Math.round(v * 100);
          const isZero = v === 0;
          return (
            <div key={k} className="bg-slate-800/60 rounded-md p-2 text-center">
              <div className="text-[9px] text-slate-500 uppercase tracking-wide">{names[k]}</div>
              <div className={clsx("font-mono text-sm font-bold mt-0.5",
                isZero     ? "text-slate-700" :
                v >= 0.25  ? "text-emerald-400" :
                v >= 0.15  ? "text-blue-400" : "text-slate-400"
              )}>
                {isZero ? "—" : `${pct}%`}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PreflightFlags({ flags }: { flags: Flag[] }) {
  if (!flags.length) return null;
  return (
    <div className="p-4 border-t border-slate-700/40 space-y-1.5">
      <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mb-2">
        Pre-flight Flags ({flags.length})
      </p>
      {flags.map((f, i) => (
        <div key={i} className={clsx("flex items-start gap-2 text-xs rounded-lg px-3 py-2 border",
          f.type === "error" ? "bg-red-500/10 border-red-500/25 text-red-300" :
          f.type === "warn"  ? "bg-amber-500/10 border-amber-500/25 text-amber-300" :
                               "bg-slate-700/20 border-slate-600/20 text-slate-400"
        )}>
          {f.type === "error" ? <Ban size={11} className="shrink-0 mt-0.5" /> :
           f.type === "warn"  ? <AlertTriangle size={11} className="shrink-0 mt-0.5" /> :
                                <Info size={11} className="shrink-0 mt-0.5" />}
          {f.message}
        </div>
      ))}
    </div>
  );
}

function TickerCard({ result, onRunAnalysis }: {
  result: TickerResult;
  onRunAnalysis: (ticker: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const cls  = result.classification;
  const conf = result.confidence;
  const pf   = conf?.pre_flight;

  if (!cls) {
    return (
      <div className="bg-slate-900 border border-red-500/30 rounded-xl p-4">
        <div className="flex items-center gap-3">
          <span className="font-mono text-base font-bold text-red-400">{result.ticker}</span>
          <span className="text-xs text-red-300/70">{result.error ?? "Classification failed"}</span>
        </div>
      </div>
    );
  }

  const isIncompat  = !cls.is_scoreable;
  const coherence   = conf?.pre_flight?.coherence ?? null;
  const bonusActive = pf?.transition_bonus?.bonus_active ?? false;
  const rsiDir      = pf?.rsi_direction ?? null;

  // Header badge
  const headerBadge = (() => {
    if (isIncompat) return { label: "INCOMPATIBLE", cls: "bg-red-500/15 text-red-400 border-red-500/40" };
    if (bonusActive) return { label: "⚡ TRANSITION BONUS", cls: "bg-amber-500/15 text-amber-400 border-amber-500/40" };
    if (coherence) {
      const cc = coherenceColor(coherence.level);
      return { label: `${coherence.level} COHERENCE`, cls: `${cc.bg} ${cc.text} ${cc.border}` };
    }
    return null;
  })();

  // Layer scores from confidence breakdown
  const layers = conf?.breakdown ?? {};
  const hasLive = Object.keys(layers).length > 0;

  return (
    <div className={clsx(
      "bg-slate-900 border rounded-xl overflow-hidden transition-all duration-200",
      isIncompat        ? "border-red-500/40"     :
      bonusActive       ? "border-amber-500/40"   :
      coherence?.level === "HIGH"    ? "border-emerald-500/30" :
      coherence?.level === "INCOHERENT" ? "border-red-500/30"  :
                           "border-slate-700/60"
    )}>
      {/* Card header */}
      <button
        className="w-full flex items-center gap-3 px-4 py-4 cursor-pointer hover:bg-slate-800/40 transition-colors text-left"
        onClick={() => setOpen(v => !v)}
      >
        {/* Symbol */}
        <span className={clsx("font-mono text-base font-bold min-w-[72px]",
          isIncompat ? "text-red-400" : assetTypeColor(cls.asset_type)
        )}>
          {result.ticker}
        </span>

        {/* Name + type */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-200 truncate">{cls.name}</p>
          <p className="text-[11px] text-slate-500 font-mono mt-0.5">
            {ASSET_TYPE_LABELS[cls.asset_type] ?? cls.asset_type} · {cls.sector}
          </p>
        </div>

        {/* Badges */}
        <div className="flex items-center gap-2 shrink-0">
          {result.loading && (
            <RefreshCw size={13} className="text-slate-500 animate-spin" />
          )}
          {result.elapsed_ms > 0 && !result.loading && (
            <span className="text-[10px] font-mono text-slate-600">{result.elapsed_ms}ms</span>
          )}
          {headerBadge && (
            <span className={clsx("text-[9px] font-mono font-bold px-2 py-1 rounded border uppercase tracking-wider", headerBadge.cls)}>
              {headerBadge.label}
            </span>
          )}
          {open ? <ChevronDown size={14} className="text-slate-500" /> : <ChevronRight size={14} className="text-slate-500" />}
        </div>
      </button>

      {/* Expanded body */}
      {open && (
        <div className="border-t border-slate-700/40">

          {/* INCOMPATIBLE */}
          {isIncompat ? (
            <div className="p-4 bg-red-500/8 space-y-2">
              <div className="flex items-center gap-2">
                <Ban size={16} className="text-red-400 shrink-0" />
                <p className="text-sm font-bold text-red-300">Standard Model: INCOMPATIBLE</p>
              </div>
              <p className="text-xs text-red-300/70 leading-relaxed">
                Volatility instruments behave inversely to equity market regimes.
                ML models trained on stock price patterns produce systematically misleading outputs.
                Use a dedicated volatility regime model.
              </p>
              <PreflightFlags flags={cls.flags} />
            </div>
          ) : (
            <>
              {/* Run Analysis button (if no live data yet) */}
              {!hasLive && !result.loading && (
                <div className="px-4 py-3 bg-slate-800/30 flex items-center justify-between gap-3">
                  <p className="text-xs text-slate-400">
                    Classification loaded · Run full analysis to see live signal scores
                  </p>
                  <button
                    onClick={e => { e.stopPropagation(); onRunAnalysis(result.ticker); }}
                    className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 px-3 py-1.5 rounded-lg transition-colors"
                  >
                    <Play size={11} />
                    Run Analysis
                  </button>
                </div>
              )}

              {result.loading && (
                <div className="px-4 py-3 flex items-center gap-2 text-xs text-slate-400">
                  <RefreshCw size={12} className="animate-spin" />
                  Loading live signal data…
                </div>
              )}

              {/* Transition bonus */}
              {bonusActive && pf?.transition_bonus && (
                <div className="px-4 py-3 bg-amber-500/8 border-b border-amber-500/20">
                  <p className="text-[10px] font-mono text-amber-400 uppercase tracking-widest mb-1">
                    ⚡ Transition Momentum Bonus Active
                  </p>
                  <p className="text-xs font-bold text-amber-300">{pf.transition_bonus.upgrade}</p>
                  <p className="text-[11px] text-amber-300/70 mt-0.5">{pf.transition_bonus.rationale}</p>
                </div>
              )}

              {/* Signal layers grid */}
              {hasLive && (
                <div className="p-4 border-b border-slate-700/40">
                  <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mb-3">Signal Layers</p>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(layers).map(([key, layer]) => (
                      <SignalBar
                        key={key}
                        label={LAYER_LABELS[key] ?? key}
                        score={layer.available && layer.score !== null ? Math.round(layer.score * 100) : null}
                        weight={layer.weight ?? 0}
                      />
                    ))}
                  </div>

                  {/* Confidence total */}
                  {conf?.confidence != null && (
                    <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-700/30">
                      <span className="text-xs text-slate-400">Overall Confidence</span>
                      <div className="flex items-center gap-2">
                        <span className={clsx("text-sm font-bold font-mono", scoreColor(Math.round(conf.confidence * 100)))}>
                          {Math.round(conf.confidence * 100)}%
                        </span>
                        <span className="text-[11px] text-slate-500">→ {conf.action}</span>
                      </div>
                    </div>
                  )}

                {/* HMM regime sanity (validated vs MA structure) */}
                {conf?.hmm && (conf.hmm.dominant_state || conf.hmm.dominant_state_validated || conf.hmm.ma_conflict) && (
                  <div className="mt-3 pt-3 border-t border-slate-700/30">
                    <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mb-2">
                      HMM Regime Sanity
                    </p>
                    <div className="text-xs text-slate-300 space-y-1">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-slate-500">HMM dominant</span>
                        <span className="font-mono">{conf.hmm.dominant_state ?? "—"}</span>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-slate-500">Validated</span>
                        <span className={clsx("font-mono", conf.hmm.ma_conflict ? "text-amber-300" : "text-slate-200")}>
                          {conf.hmm.dominant_state_validated ?? "—"}
                        </span>
                      </div>
                      {conf.hmm.ma_conflict && (
                        <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 mt-2">
                          <p className="text-[11px] text-amber-200 font-mono">
                            Conflict: {conf.hmm.ma_conflict.reason ?? "MA_STRUCTURE_OVERRIDE"}
                          </p>
                          {(conf.hmm.ma_conflict.last_close != null || conf.hmm.ma_conflict.ma50 != null || conf.hmm.ma_conflict.ma200 != null) && (
                            <p className="text-[11px] text-amber-200/70 font-mono mt-1">
                              close={conf.hmm.ma_conflict.last_close ?? "—"} · ma50={conf.hmm.ma_conflict.ma50 ?? "—"} · ma200={conf.hmm.ma_conflict.ma200 ?? "—"}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
                </div>
              )}

              {/* Coherence section */}
              {coherence && (
                <div className="px-4 py-3 border-b border-slate-700/40">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mb-1">Signal Coherence</p>
                      <p className="text-xs text-slate-300 leading-relaxed max-w-sm">{coherence.message}</p>
                    </div>
                    <div className="text-right shrink-0">
                      <span className={clsx(
                        "text-[10px] font-mono font-bold px-2.5 py-1 rounded border",
                        coherenceColor(coherence.level).text,
                        coherenceColor(coherence.level).bg,
                        coherenceColor(coherence.level).border,
                      )}>
                        {coherence.level}
                      </span>
                      {coherence.std_dev != null && (
                        <p className="text-[10px] text-slate-600 font-mono mt-1">
                          σ={coherence.std_dev} · spread={coherence.spread}pts
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* RSI direction */}
              {rsiDir && (
                <div className="px-4 py-3 border-b border-slate-700/40">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mb-1">RSI Direction Signal</p>
                      <p className="text-[11px] text-slate-400">
                        Current: {rsiDir.rsi_current.toFixed(0)} · Δ {rsiDir.delta > 0 ? "+" : ""}{rsiDir.delta}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <span className={clsx(
                        "text-[10px] font-mono font-bold px-2.5 py-1 rounded border",
                        rsiDir.is_oversold  && rsiDir.delta > 0  ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/30" :
                        rsiDir.is_oversold  && rsiDir.delta <= 0 ? "text-red-300 bg-red-500/10 border-red-500/30"           :
                        rsiDir.is_overbought && rsiDir.delta < 0 ? "text-amber-300 bg-amber-500/10 border-amber-500/30"     :
                                                                    "text-slate-400 bg-slate-700/20 border-slate-600/20"
                      )}>
                        {rsiDir.label.split(" — ")[0]}
                      </span>
                      <p className="text-[10px] text-slate-600 font-mono mt-1">
                        Pattern bonus: {rsiDir.pattern_bonus > 0 ? "+" : ""}{rsiDir.pattern_bonus}pts
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Pre-flight flags */}
              <PreflightFlags flags={cls.flags} />

              {/* Weight profile */}
              <WeightGrid wp={cls.weight_profile} label={cls.weight_label} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
function apiUrl(path: string) { return API_BASE ? `${API_BASE}${path}` : path; }

export function SignalTestSuite() {
  const [results,    setResults]    = useState<TickerResult[]>([]);
  const [filter,     setFilter]     = useState("all");
  const [addInput,   setAddInput]   = useState("");
  const [running,    setRunning]    = useState(false);
  const [runAllConf, setRunAllConf] = useState(false);
  const [lastRun,    setLastRun]    = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Computed stats
  const scoreable   = results.filter(r => r.classification?.is_scoreable).length;
  const incompat    = results.filter(r => r.classification && !r.classification.is_scoreable).length;
  const totalFlags  = results.reduce((s, r) => s + (r.classification?.flag_count ?? 0), 0);
  const bonusActive = results.filter(r =>
    r.confidence?.pre_flight?.transition_bonus?.bonus_active
  ).length;

  // Filtered results
  const filtered = filter === "all"
    ? results
    : results.filter(r => r.classification?.asset_type === filter);

  // Filter tab counts
  function countForFilter(f: string) {
    if (f === "all") return results.length;
    return results.filter(r => r.classification?.asset_type === f).length;
  }

  // Run classification-only (fast) for a list of tickers
  const runClassify = useCallback(async (tickers: string[]) => {
    setRunning(true);
    // Initialise rows with loading state
    setResults(prev => {
      const existing = new Map(prev.map(r => [r.ticker, r]));
      return tickers.map(t => existing.get(t) ?? {
        ticker: t, classification: null, confidence: null, error: null, elapsed_ms: 0, loading: true,
      });
    });

    try {
      const res  = await fetch(apiUrl("/api/test-suite"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tickers, include_confidence: false }),
      });
      const data = await res.json();
      setResults(data.results.map((r: TickerResult) => ({ ...r, loading: false })));
      setLastRun(new Date().toLocaleTimeString());
    } catch (e) {
      console.error("[TestSuite] classify error:", e);
    } finally {
      setRunning(false);
    }
  }, []);

  // Run full analysis for a single ticker
  const runSingleAnalysis = useCallback(async (ticker: string) => {
    setResults(prev => prev.map(r =>
      r.ticker === ticker ? { ...r, loading: true } : r
    ));
    try {
      const res = await fetch(apiUrl(`/api/confidence/${ticker}`));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const conf: ConfidenceResult = await res.json();
      setResults(prev => prev.map(r =>
        r.ticker === ticker ? { ...r, confidence: conf, loading: false } : r
      ));
    } catch (e) {
      setResults(prev => prev.map(r =>
        r.ticker === ticker ? { ...r, loading: false, error: String(e) } : r
      ));
    }
  }, []);

  // Run full analysis for all scoreable tickers
  const runAllAnalysis = useCallback(async () => {
    setRunAllConf(true);
    const scoreableTickers = results.filter(r => r.classification?.is_scoreable).map(r => r.ticker);
    for (const t of scoreableTickers) {
      await runSingleAnalysis(t);
    }
    setRunAllConf(false);
  }, [results, runSingleAnalysis]);

  // Add a ticker
  const addTicker = useCallback(() => {
    const t = addInput.trim().toUpperCase().replace(/[^A-Z0-9\-.]/g, "");
    if (!t || results.some(r => r.ticker === t)) { setAddInput(""); return; }
    const newList = [...results.map(r => r.ticker), t];
    setAddInput("");
    runClassify(newList);
  }, [addInput, results, runClassify]);

  // Remove a ticker
  const removeTicker = useCallback((ticker: string) => {
    const newList = results.filter(r => r.ticker !== ticker).map(r => r.ticker);
    if (newList.length === 0) { setResults([]); return; }
    runClassify(newList);
  }, [results, runClassify]);

  // Generate & download report
  const downloadReport = useCallback(() => {
    const rows = results.map(r => ({
      ticker:       r.ticker,
      asset_type:   r.classification?.asset_type ?? "N/A",
      name:         r.classification?.name ?? "",
      is_scoreable: r.classification?.is_scoreable ?? false,
      flags:        r.classification?.flag_count ?? 0,
      coherence:    r.confidence?.pre_flight?.coherence?.level ?? "N/A",
      confidence:   r.confidence?.confidence != null ? Math.round(r.confidence.confidence * 100) + "%" : "N/A",
      action:       r.confidence?.action ?? "N/A",
      transition_bonus: r.confidence?.pre_flight?.transition_bonus?.bonus_active ? "YES" : "NO",
      weight_label: r.classification?.weight_label ?? "",
      elapsed_ms:   r.elapsed_ms,
    }));
    const header = Object.keys(rows[0] ?? {}).join(",");
    const csv = [header, ...rows.map(r => Object.values(r).map(v => `"${v}"`).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `thrive-alpha-test-report-${Date.now()}.csv`;
    a.click(); URL.revokeObjectURL(url);
  }, [results]);

  // Init: load default tickers on mount (or after navigation)
  const initialised = useRef(false);
  if (!initialised.current) {
    initialised.current = true;
    setTimeout(() => runClassify(DEFAULT_TICKERS), 0);
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 pb-5 border-b border-slate-700/40">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399] animate-pulse" />
            <span className="text-[11px] font-mono text-slate-400 uppercase tracking-widest">
              Thrive Alpha · Asset Classifier v1.0
            </span>
          </div>
          <h2 className="text-2xl font-bold text-slate-100 tracking-tight">
            Signal Behavior <span className="text-emerald-400">Test Suite</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            {results.length} ticker{results.length !== 1 ? "s" : ""} · {Object.keys(ASSET_TYPE_LABELS).length} asset types ·
            Full pre-flight routing + coherence analysis
            {lastRun && <span className="ml-2 text-slate-600">· Last run {lastRun}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {results.some(r => r.confidence) && (
            <button
              onClick={downloadReport}
              className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 bg-slate-700/50 hover:bg-slate-700 border border-slate-600/50 px-3 py-2 rounded-lg transition-colors"
            >
              <Download size={13} />
              Export CSV
            </button>
          )}
          <button
            onClick={() => runClassify(results.map(r => r.ticker))}
            disabled={running}
            className="flex items-center gap-1.5 text-xs font-semibold text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 px-3 py-2 rounded-lg transition-colors disabled:opacity-50"
          >
            <RefreshCw size={13} className={running ? "animate-spin" : ""} />
            Refresh
          </button>
          {results.length > 0 && results.some(r => r.classification?.is_scoreable && !r.confidence) && (
            <button
              onClick={runAllAnalysis}
              disabled={runAllConf}
              className="flex items-center gap-1.5 text-xs font-semibold text-blue-300 bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/30 px-3 py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              <Play size={13} className={runAllConf ? "animate-pulse" : ""} />
              {runAllConf ? "Running…" : "Run All Analysis"}
            </button>
          )}
        </div>
      </div>

      {/* ── Summary chips ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <SummaryChip value={scoreable}   label="Scoreable"    color="text-emerald-400" />
        <SummaryChip value={totalFlags}  label="Flags"        color="text-amber-400" />
        <SummaryChip value={bonusActive} label="Bonus Active" color="text-purple-400" />
        <SummaryChip value={incompat}    label="Incompatible" color="text-red-400" />
      </div>

      {/* ── Add ticker bar ── */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-xs">
          <input
            ref={inputRef}
            value={addInput}
            onChange={e => setAddInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === "Enter" && addTicker()}
            placeholder="Add ticker (e.g. MSFT)"
            className="w-full bg-slate-800/60 border border-slate-700/60 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/30 font-mono"
          />
        </div>
        <button
          onClick={addTicker}
          disabled={!addInput.trim() || running}
          className="flex items-center gap-1.5 text-xs font-semibold text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 px-3 py-2 rounded-lg transition-colors disabled:opacity-40"
        >
          <Plus size={13} />
          Add
        </button>
        {results.length > 0 && (
          <div className="flex items-center gap-1 ml-2 flex-wrap">
            {results.map(r => (
              <span key={r.ticker} className="group flex items-center gap-1 bg-slate-800/60 border border-slate-700/40 rounded-md px-2 py-1 text-[11px] font-mono">
                <span className={assetTypeColor(r.classification?.asset_type ?? "")}>{r.ticker}</span>
                <button
                  onClick={() => removeTicker(r.ticker)}
                  className="text-slate-600 hover:text-red-400 transition-colors"
                >
                  <X size={9} />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Filter tabs ── */}
      {results.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {FILTER_TABS.map(tab => {
            const count = countForFilter(tab.id);
            if (count === 0 && tab.id !== "all") return null;
            return (
              <button
                key={tab.id}
                onClick={() => setFilter(tab.id)}
                className={clsx(
                  "text-[10px] font-mono uppercase tracking-wider px-3.5 py-1.5 rounded-full border transition-all",
                  filter === tab.id
                    ? "bg-emerald-500/15 border-emerald-500/50 text-emerald-300"
                    : "bg-slate-800/40 border-slate-700/40 text-slate-500 hover:border-emerald-500/40 hover:text-emerald-400"
                )}
              >
                {tab.label}
                {count > 0 && <span className="ml-1 opacity-60">({count})</span>}
              </button>
            );
          })}
          <span className="flex items-center gap-1 text-[10px] text-slate-600 ml-auto">
            <Filter size={10} />
            {filtered.length} shown
          </span>
        </div>
      )}

      {/* ── Ticker cards ── */}
      {running && results.length === 0 ? (
        <div className="flex items-center justify-center py-16 gap-3 text-slate-400">
          <FlaskConical size={20} className="animate-pulse" />
          <span className="text-sm">Running pre-flight classification…</span>
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-slate-500 text-sm">
          No tickers match the current filter · Try "All"
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(r => (
            <TickerCard
              key={r.ticker}
              result={r}
              onRunAnalysis={runSingleAnalysis}
            />
          ))}
        </div>
      )}

      {/* ── Empty state ── */}
      {!running && results.length === 0 && (
        <div className="rounded-xl border border-slate-700/40 bg-slate-900/60 p-10 text-center space-y-3">
          <FlaskConical size={28} className="mx-auto text-slate-600" />
          <p className="text-slate-400 font-medium">No tickers loaded</p>
          <button
            onClick={() => runClassify(DEFAULT_TICKERS)}
            className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 px-4 py-2 rounded-lg transition-colors"
          >
            <Play size={14} />
            Load Default Tickers
          </button>
        </div>
      )}

      {/* ── Report legend ── */}
      {results.length > 0 && (
        <div className="rounded-xl bg-slate-900/60 border border-slate-700/30 p-4">
          <p className="text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-3">
            Quick Reference — What Each Coherence Level Means
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            {[
              { level: "HIGH",       desc: "σ < 15 — Signals aligned, output reliable",         color: "text-emerald-400" },
              { level: "MODERATE",   desc: "σ 15-25 — Some disagreement, reduce size",           color: "text-amber-400"   },
              { level: "LOW",        desc: "σ 25-35 — Significant conflict, wait for confirm",   color: "text-orange-400"  },
              { level: "INCOHERENT", desc: "σ > 35 — All layers fight. No signal. Stand down.", color: "text-red-400"     },
            ].map(r => (
              <div key={r.level} className="bg-slate-800/40 rounded-lg p-2.5 space-y-1">
                <span className={clsx("font-mono font-bold text-[10px]", r.color)}>{r.level}</span>
                <p className="text-slate-500 leading-tight">{r.desc}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
