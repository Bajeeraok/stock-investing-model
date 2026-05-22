"use client";

/**
 * Pre-market multi-asset signal aggregator (6 categories, 15 sources).
 * Data: /api/pre-market or DashboardData.pre_market_full.
 */

import { useState, useEffect, useCallback } from "react";
import { RefreshCw, TrendingUp, TrendingDown, Minus, AlertTriangle, Globe, Activity, ChevronDown, ChevronRight } from "lucide-react";
import { clsx } from "clsx";
import { MarketCatalystBoardPanel, type MarketCatalystBoard } from "./MarketCatalystBoard";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export interface PreMarketSignal {
  name: string;
  category: string;
  score: number;
  weight: number;
  raw_value: string;
  direction: string;
  confidence: number;
  note?: string;
}

export interface PreMarketData {
  timestamp: string;
  composite_score: number;
  bias: string;
  confidence: number;
  signals: PreMarketSignal[];
  top_bullish: string[];
  top_bearish: string[];
  key_risks: string[];
  sector_plays: Record<string, string[]>;
  minutes_to_open: number;
  message?: string;
  rotation_risk_premarket?: "High" | "Medium" | "Low";
  stale?: boolean;
  stale_message?: string;
  market_catalysts?: MarketCatalystBoard | null;
}

const CATEGORY_LABELS: Record<string, string> = {
  futures: "Equity Futures",
  international: "Intl Markets",
  volatility: "Volatility",
  rates: "Rates & Credit",
  currency: "Currencies",
  commodity: "Commodities",
  crypto: "Crypto",
  megacap: "Mega-Cap Pre-Mkt",
};

const BIAS_CONFIG: Record<string, { color: string; bg: string; border: string }> = {
  "STRONG BULL": { color: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/30" },
  "BULL": { color: "text-emerald-400", bg: "bg-emerald-500/8", border: "border-emerald-500/25" },
  "SLIGHT BULL": { color: "text-emerald-500", bg: "bg-emerald-500/5", border: "border-emerald-500/20" },
  "NEUTRAL": { color: "text-slate-400", bg: "bg-slate-800/40", border: "border-slate-600" },
  "SLIGHT BEAR": { color: "text-amber-400", bg: "bg-amber-500/5", border: "border-amber-500/20" },
  "BEAR": { color: "text-red-400", bg: "bg-red-500/8", border: "border-red-500/25" },
  "STRONG BEAR": { color: "text-red-300", bg: "bg-red-500/10", border: "border-red-500/30" },
};

function ScoreBar({ score, size = "md" }: { score: number; size?: "sm" | "md" }) {
  const color = score > 0.15 ? "bg-emerald-500" : score < -0.15 ? "bg-red-500" : "bg-slate-500";
  const h = size === "sm" ? "h-1" : "h-1.5";
  return (
    <div className={clsx("w-full rounded-full bg-slate-700/50 relative overflow-hidden", h)}>
      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-slate-600 z-10" />
      <div
        className={clsx("absolute top-0 bottom-0 rounded-full transition-all duration-500", color)}
        style={score >= 0 ? { left: "50%", width: `${Math.abs(score) * 50}%` } : { right: "50%", width: `${Math.abs(score) * 50}%` }}
      />
    </div>
  );
}

function DirectionIcon({ direction, size = 14 }: { direction: string; size?: number }) {
  if (direction === "Bullish") return <TrendingUp className="text-emerald-400 shrink-0" style={{ width: size, height: size }} />;
  if (direction === "Bearish") return <TrendingDown className="text-red-400 shrink-0" style={{ width: size, height: size }} />;
  return <Minus className="text-slate-500 shrink-0" style={{ width: size, height: size }} />;
}

function SignalRow({ signal }: { signal: PreMarketSignal }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border-b border-slate-700/40 last:border-0">
      <button
        type="button"
        className="w-full flex items-center gap-2 sm:gap-3 px-3 py-2 hover:bg-slate-800/40 transition-colors text-left"
        onClick={() => signal.note && setExpanded((v) => !v)}
      >
        <DirectionIcon direction={signal.direction} />
        <span className="text-sm text-slate-300 font-medium min-w-0 flex-1 truncate">{signal.name}</span>
        <span className={clsx("text-xs font-mono shrink-0", signal.direction === "Bullish" ? "text-emerald-400" : signal.direction === "Bearish" ? "text-red-400" : "text-slate-500")}>
          {signal.raw_value}
        </span>
        <div className="w-16 shrink-0 hidden sm:block">
          <ScoreBar score={signal.score} size="sm" />
        </div>
        <span className="text-xs text-slate-600 font-mono w-8 text-right shrink-0 hidden sm:block">
          {(signal.confidence * 100).toFixed(0)}%
        </span>
        {signal.note && (expanded ? <ChevronDown className="h-3 w-3 text-slate-600 shrink-0" /> : <ChevronRight className="h-3 w-3 text-slate-600 shrink-0" />)}
      </button>
      {expanded && signal.note && <div className="px-8 pb-2 text-xs text-slate-500 italic">{signal.note}</div>}
    </div>
  );
}

function CategoryGroup({ category, signals }: { category: string; signals: PreMarketSignal[] }) {
  const [open, setOpen] = useState(true);
  const avgScore = signals.reduce((s, x) => s + x.score, 0) / signals.length;
  return (
    <div className="rounded-lg border border-slate-700/50 overflow-hidden">
      <button type="button" className="w-full flex items-center gap-2 px-3 py-2 bg-slate-800/50 hover:bg-slate-800/70 transition-colors text-left" onClick={() => setOpen((v) => !v)}>
        <DirectionIcon direction={avgScore > 0.1 ? "Bullish" : avgScore < -0.1 ? "Bearish" : "Neutral"} size={12} />
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex-1">{category}</span>
        <span className="text-xs text-slate-600">{signals.length} signal{signals.length !== 1 ? "s" : ""}</span>
        {open ? <ChevronDown className="h-3 w-3 text-slate-600" /> : <ChevronRight className="h-3 w-3 text-slate-600" />}
      </button>
      {open && <div className="bg-slate-900/20">{signals.map((s) => <SignalRow key={s.name} signal={s} />)}</div>}
    </div>
  );
}

function CompositeGauge({ score, bias, confidence }: { score: number; bias: string; confidence: number }) {
  const cfg = BIAS_CONFIG[bias] ?? BIAS_CONFIG["NEUTRAL"];
  const pct = ((score + 1) / 2) * 100;
  return (
    <div className={clsx("rounded-xl border p-4 sm:p-5", cfg.bg, cfg.border)}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium text-slate-500 uppercase tracking-widest mb-1">Pre-Market Bias</p>
          <p className={clsx("text-2xl sm:text-3xl font-bold tracking-tight", cfg.color)}>{bias}</p>
          <p className="text-xs text-slate-500 mt-1">Confidence: {(confidence * 100).toFixed(0)}%</p>
        </div>
        <div className="text-right shrink-0">
          <p className={clsx("text-3xl font-mono font-bold", cfg.color)}>{score >= 0 ? "+" : ""}{score.toFixed(2)}</p>
          <p className="text-xs text-slate-600 mt-0.5">composite score</p>
        </div>
      </div>
      <div className="mt-4 space-y-1">
        <div className="flex justify-between text-xs text-slate-600"><span>Bear</span><span>Neutral</span><span>Bull</span></div>
        <div className="relative h-2 rounded-full bg-slate-700/60 overflow-hidden">
          <div className="absolute inset-y-0 left-0 w-1/2 bg-gradient-to-r from-red-900/40 to-transparent rounded-l-full" />
          <div className="absolute inset-y-0 right-0 w-1/2 bg-gradient-to-l from-emerald-900/40 to-transparent rounded-r-full" />
          <div className="absolute left-1/2 inset-y-0 w-px bg-slate-500 z-10" />
          <div
            className={clsx("absolute inset-y-0 rounded-full transition-all duration-700", score >= 0 ? "bg-emerald-500" : "bg-red-500")}
            style={score >= 0 ? { left: "50%", width: `${Math.abs(score) * 50}%` } : { right: "50%", width: `${Math.abs(score) * 50}%` }}
          />
          <div className="absolute top-0 bottom-0 w-0.5 bg-white z-20 transition-all duration-700 rounded-full" style={{ left: `${pct}%` }} />
        </div>
      </div>
    </div>
  );
}

export function PreMarketStrip({ data }: { data: PreMarketData }) {
  const cfg = BIAS_CONFIG[data.bias] ?? BIAS_CONFIG["NEUTRAL"];
  return (
    <div className={clsx("rounded-lg border px-3 py-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm", cfg.bg, cfg.border)}>
      <div className="flex items-center gap-2">
        <Activity className="h-3.5 w-3.5 text-slate-500 shrink-0" />
        <span className="text-slate-400 font-medium">Pre-Market</span>
        <span className={clsx("font-semibold", cfg.color)}>{data.bias}</span>
        <span className="text-slate-600 font-mono text-xs">{data.composite_score >= 0 ? "+" : ""}{data.composite_score.toFixed(2)}</span>
      </div>
      {data.minutes_to_open > 0 && <span className="text-slate-600 text-xs">{data.minutes_to_open}m to open</span>}
      {data.top_bullish.slice(0, 1).map((b, i) => <span key={i} className="text-emerald-500 text-xs hidden sm:inline">↑ {b.split(":")[0]}</span>)}
      {data.top_bearish.slice(0, 1).map((b, i) => <span key={i} className="text-red-500 text-xs hidden sm:inline">↓ {b.split(":")[0]}</span>)}
      {data.rotation_risk_premarket && data.rotation_risk_premarket !== "Low" && (
        <span className={clsx("text-xs flex items-center gap-1", data.rotation_risk_premarket === "High" ? "text-amber-400" : "text-slate-400")}>
          <AlertTriangle className="h-3 w-3" /> Rotation risk: {data.rotation_risk_premarket}
        </span>
      )}
    </div>
  );
}

interface PreMarketPanelProps {
  data?: PreMarketData | null;
  apiEndpoint?: string;
}

export function PreMarketPanel({ data: initialData, apiEndpoint = "/api/pre-market" }: PreMarketPanelProps) {
  const [data, setData] = useState<PreMarketData | null>(initialData ?? null);
  const [loading, setLoading] = useState(false);
  // null = no error | string = fetch error | "unavailable" = 503 (expected outside pre-market)
  const [error, setError] = useState<string | "unavailable" | null>(null);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const url = API_BASE ? `${API_BASE}${apiEndpoint}` : apiEndpoint;
      const res = await fetch(url);
      if (res.status === 503) {
        // Expected outside pre-market hours when no cached file exists — not a hard error
        if (!data) setError("unavailable");
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setLastFetch(new Date());
    } catch (e) {
      // On silent background refresh, keep existing data rather than show error
      if (!silent) setError(e instanceof Error ? e.message : "Failed to fetch pre-market data");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [apiEndpoint, data]);

  // Always fetch fresh on mount — initialData may be stale SSR data from yesterday.
  // Silent=true when initialData exists so it shows while the refresh happens in background.
  useEffect(() => {
    fetchData(!!initialData);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // During pre-market: refresh every 5 min (prices moving fast)
    // Outside pre-market: refresh every 30 min (stale check + scheduler may have run)
    const getInterval = () => {
      const now = new Date();
      const h = now.getHours(), m = now.getMinutes();
      const isPreMarket = (h >= 4 && h < 9) || (h === 9 && m < 30);
      return isPreMarket ? 5 * 60 * 1000 : 30 * 60 * 1000;
    };
    let timeout: ReturnType<typeof setTimeout>;
    const schedule = () => {
      timeout = setTimeout(() => {
        fetchData(true);
        schedule();
      }, getInterval());
    };
    schedule();
    return () => clearTimeout(timeout);
  }, [fetchData]);

  const grouped = data ? Object.entries(
    data.signals.reduce<Record<string, PreMarketSignal[]>>((acc, sig) => {
      const label = CATEGORY_LABELS[sig.category] ?? sig.category;
      acc[label] = [...(acc[label] ?? []), sig];
      return acc;
    }, {})
  ) : [];
  const sortedGroups = grouped.sort(([, a], [, b]) => {
    const scoreA = Math.abs(a.reduce((s, x) => s + x.score * x.weight, 0));
    const scoreB = Math.abs(b.reduce((s, x) => s + x.score * x.weight, 0));
    return scoreB - scoreA;
  });

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/30">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
        <div className="flex items-center gap-2">
          <Globe className="h-4 w-4 text-slate-400 shrink-0" />
          <span className="text-sm font-semibold text-slate-300">Pre-Market Signal Engine</span>
          {data?.minutes_to_open != null && data.minutes_to_open > 0 && (
            <span className="text-xs text-slate-500 bg-slate-800 border border-slate-700 px-2 py-0.5 rounded-full">{data.minutes_to_open}m to open</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {lastFetch && <span className="text-xs text-slate-600 hidden sm:inline">{lastFetch.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true })} ET</span>}
          <button type="button" onClick={() => fetchData(false)} disabled={loading} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-slate-600 text-slate-400 hover:bg-slate-800 text-xs disabled:opacity-50 transition-colors">
            <RefreshCw className={clsx("h-3 w-3", loading && "animate-spin")} />
            <span>{loading ? "Fetching…" : "Refresh"}</span>
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {error === "unavailable" && (
          <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 px-4 py-6 text-center space-y-2">
            <Activity className="h-6 w-6 text-slate-600 mx-auto" />
            <p className="text-sm font-medium text-slate-400">Pre-market signals not yet available</p>
            <p className="text-xs text-slate-600">Data is generated at 4:00 AM ET on trading days.<br />Check back before market open or run the pre-market scheduler.</p>
          </div>
        )}

        {error && error !== "unavailable" && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-amber-200 text-sm flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Could not fetch pre-market data</p>
              <p className="text-amber-300/70 text-xs mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {data?.stale && (
          <div className="rounded-lg border border-slate-600/50 bg-slate-800/40 px-3 py-2 text-slate-400 text-xs flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 text-slate-500 shrink-0" />
            <span>{data.stale_message ?? "Showing cached pre-market data — refreshes at 4:00 AM ET on trading days"}</span>
          </div>
        )}

        {loading && !data && (
          <div className="space-y-3 animate-pulse">
            <div className="h-28 rounded-xl bg-slate-800/60" />
            <div className="grid grid-cols-2 gap-3">
              <div className="h-16 rounded-lg bg-slate-800/40" />
              <div className="h-16 rounded-lg bg-slate-800/40" />
            </div>
            {[1, 2, 3].map((i) => <div key={i} className="h-10 rounded-lg bg-slate-800/30" />)}
          </div>
        )}

        {data && (
          <>
            <CompositeGauge score={data.composite_score} bias={data.bias} confidence={data.confidence} />
            {data.market_catalysts && <MarketCatalystBoardPanel board={data.market_catalysts} />}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
                <p className="text-xs font-semibold text-emerald-500 uppercase tracking-wider mb-2 flex items-center gap-1.5"><TrendingUp className="h-3 w-3" /> Bullish Drivers</p>
                {data.top_bullish.length > 0 ? <ul className="space-y-1">{data.top_bullish.map((item, i) => <li key={i} className="text-xs text-slate-300 flex items-start gap-1.5"><span className="text-emerald-500 shrink-0 mt-0.5">+</span>{item}</li>)}</ul> : <p className="text-xs text-slate-600">No significant bullish signals</p>}
              </div>
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                <p className="text-xs font-semibold text-red-500 uppercase tracking-wider mb-2 flex items-center gap-1.5"><TrendingDown className="h-3 w-3" /> Bearish Drivers</p>
                {data.top_bearish.length > 0 ? <ul className="space-y-1">{data.top_bearish.map((item, i) => <li key={i} className="text-xs text-slate-300 flex items-start gap-1.5"><span className="text-red-500 shrink-0 mt-0.5">−</span>{item}</li>)}</ul> : <p className="text-xs text-slate-600">No significant bearish signals</p>}
              </div>
            </div>
            {data.key_risks.length > 0 && (
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                <p className="text-xs font-semibold text-amber-500 uppercase tracking-wider mb-2 flex items-center gap-1.5"><AlertTriangle className="h-3 w-3" /> Key Risks / Notes</p>
                <ul className="space-y-1">{data.key_risks.map((r, i) => <li key={i} className="text-xs text-slate-400">{r}</li>)}</ul>
              </div>
            )}
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Signal Breakdown ({data.signals.length} sources)</p>
                <div className="hidden sm:flex items-center gap-3 text-xs text-slate-600"><span>Raw value</span><span className="w-16 text-center">Score</span><span className="w-8 text-right">Conf</span></div>
              </div>
              <div className="space-y-2">{sortedGroups.map(([category, signals]) => <CategoryGroup key={category} category={category} signals={signals} />)}</div>
            </div>
            {Object.keys(data.sector_plays || {}).length > 0 && (
              <div className="rounded-lg border border-slate-700/50 bg-slate-800/20 p-3">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Sector Implications</p>
                <div className="flex flex-wrap gap-x-6 gap-y-2">
                  {Object.entries(data.sector_plays).map(([category, tickers]) => (
                    <div key={category}>
                      <span className={clsx("text-xs font-medium", category.toLowerCase().includes("avoid") ? "text-amber-400" : category.toLowerCase().includes("short") ? "text-red-400" : "text-emerald-400")}>{category}:</span>
                      <span className="text-xs text-slate-400 ml-1.5">{tickers.join(", ")}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <p className="text-xs text-slate-600 text-center pt-1">Educational only. Not financial advice. Signals: Equity Futures 35%, Intl 20%, VIX 10%, Rates 12%, FX 8%, Commodities 10%, Crypto+Mega-cap 5%.</p>
          </>
        )}
      </div>
    </div>
  );
}
