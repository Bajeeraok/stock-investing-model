"use client";

import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { clsx } from "clsx";
import { Search, RefreshCw, ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";
import { apiUrl } from "@/lib/apiBase";

// ─── Types ────────────────────────────────────────────────────────────────────

type EntryMode = "full_go" | "starter_only" | "hard_lock" | string;
type SortDir = "asc" | "desc";

interface UniverseRow {
  ticker: string;
  close: number | null;
  change_pct: number | null;
  score: number | null;
  regime: string;
  rsi: number | null;
  signal: string;
  entry_mode: EntryMode | null;
  gates_passed: number;
  gates_total: number;
  confidence: number | null;
  sector: string;
  market_cap_bucket: string;
}

interface UniversePayload {
  rows: UniverseRow[];
  as_of: string | null;
  total: number;
  message?: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ENTRY_MODE_ORDER: Record<string, number> = { full_go: 0, starter_only: 1, hard_lock: 2 };

function entryModeLabel(mode: EntryMode | null): { label: string; cls: string } {
  switch (mode) {
    case "full_go":
      return { label: "Full Go", cls: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" };
    case "starter_only":
      return { label: "Starter", cls: "text-amber-400 bg-amber-500/10 border-amber-500/30" };
    case "hard_lock":
      return { label: "Locked", cls: "text-slate-400 bg-slate-700/40 border-slate-600/30" };
    default:
      return { label: mode ?? "—", cls: "text-slate-500 bg-slate-800 border-slate-700" };
  }
}

function regimeColor(regime: string): string {
  if (regime === "UP" || regime === "BULL") return "text-emerald-400";
  if (regime === "DOWN" || regime === "BEAR") return "text-red-400";
  return "text-slate-400";
}

function signalColor(sig: string): string {
  if (sig.includes("BUY") || sig.includes("ADD")) return "text-emerald-400";
  if (sig.includes("SELL") || sig.includes("TRIM")) return "text-red-400";
  return "text-slate-400";
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-slate-500";
  if (score >= 65) return "text-emerald-400";
  if (score >= 50) return "text-amber-400";
  if (score >= 35) return "text-orange-400";
  return "text-red-400";
}

function fmtPct(v: number | null): string {
  if (v === null || v === undefined) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function fmtNum(v: number | null, decimals = 1): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(decimals);
}

// ─── Column definitions ───────────────────────────────────────────────────────

type ColKey = "ticker" | "close" | "change_pct" | "score" | "regime" | "rsi" | "signal" | "entry_mode" | "gates" | "confidence";

const COLS: { key: ColKey; label: string; title?: string; align: string }[] = [
  { key: "ticker", label: "Ticker", align: "text-left" },
  { key: "close", label: "Close", align: "text-right" },
  { key: "change_pct", label: "Chg%", align: "text-right" },
  { key: "score", label: "Score", align: "text-right", title: "Composite 0-100 signal score" },
  { key: "regime", label: "Regime", align: "text-center" },
  { key: "rsi", label: "RSI", align: "text-right" },
  { key: "signal", label: "Signal", align: "text-center" },
  { key: "entry_mode", label: "Entry Mode", align: "text-center" },
  { key: "gates", label: "Gates", align: "text-center", title: "Primary gates passed / total" },
  { key: "confidence", label: "Conf%", align: "text-right", title: "Model confidence %" },
];

// ─── Component ────────────────────────────────────────────────────────────────

interface Props {
  onTickerClick?: (ticker: string) => void;
}

export function SignalUniversePanel({ onTickerClick }: Props) {
  const [data, setData] = useState<UniversePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [entryModeFilter, setEntryModeFilter] = useState<"all" | EntryMode>("all");
  const [minGates, setMinGates] = useState<number | null>(null);
  const [minConf, setMinConf] = useState<number | null>(null);
  const [regimeFilter, setRegimeFilter] = useState<string>("all");

  // Sort
  const [sortKey, setSortKey] = useState<ColKey>("entry_mode");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  // Search suggestions
  const [showSuggestions, setShowSuggestions] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (isRetry = false) => {
    if (!isRetry) setLoading(true);
    setError(null);
    try {
      const url = apiUrl("/api/dashboard/eod-universe");
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: UniversePayload = await res.json();
      setData(json);
      // Auto-retry after 30s if the backend is still refreshing (no rows yet)
      if (json.rows.length === 0 && json.message?.includes("progress")) {
        if (retryRef.current) clearTimeout(retryRef.current);
        retryRef.current = setTimeout(() => load(true), 30_000);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      if (!isRetry) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => { if (retryRef.current) clearTimeout(retryRef.current); };
  }, [load]);

  const allRegimes = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.rows.map(r => r.regime).filter(Boolean))).sort();
  }, [data]);

  const suggestions = useMemo(() => {
    if (!data || search.length < 1) return [];
    const q = search.toUpperCase();
    return data.rows
      .map(r => r.ticker)
      .filter(t => t.startsWith(q) && t !== q)
      .slice(0, 6);
  }, [data, search]);

  const filtered = useMemo(() => {
    if (!data) return [];
    let rows = data.rows;

    if (search) {
      const q = search.toUpperCase();
      rows = rows.filter(r => r.ticker.includes(q) || r.sector?.toUpperCase().includes(q));
    }
    if (entryModeFilter !== "all") {
      rows = rows.filter(r => r.entry_mode === entryModeFilter);
    }
    if (minGates !== null) {
      rows = rows.filter(r => r.gates_passed >= minGates);
    }
    if (minConf !== null) {
      rows = rows.filter(r => (r.confidence ?? 0) >= minConf);
    }
    if (regimeFilter !== "all") {
      rows = rows.filter(r => r.regime === regimeFilter);
    }

    return [...rows].sort((a, b) => {
      let av: number | string = 0, bv: number | string = 0;
      switch (sortKey) {
        case "ticker": av = a.ticker; bv = b.ticker; break;
        case "close": av = a.close ?? -Infinity; bv = b.close ?? -Infinity; break;
        case "change_pct": av = a.change_pct ?? -Infinity; bv = b.change_pct ?? -Infinity; break;
        case "score": av = a.score ?? -Infinity; bv = b.score ?? -Infinity; break;
        case "regime": av = a.regime; bv = b.regime; break;
        case "rsi": av = a.rsi ?? -Infinity; bv = b.rsi ?? -Infinity; break;
        case "signal": av = a.signal; bv = b.signal; break;
        case "entry_mode":
          av = ENTRY_MODE_ORDER[a.entry_mode ?? ""] ?? 9;
          bv = ENTRY_MODE_ORDER[b.entry_mode ?? ""] ?? 9;
          break;
        case "gates": av = a.gates_passed; bv = b.gates_passed; break;
        case "confidence": av = a.confidence ?? -Infinity; bv = b.confidence ?? -Infinity; break;
      }
      if (av === bv) return 0;
      const cmp = av < bv ? -1 : 1;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [data, search, entryModeFilter, minGates, minConf, regimeFilter, sortKey, sortDir]);

  function toggleSort(key: ColKey) {
    if (sortKey === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir(key === "ticker" || key === "signal" || key === "regime" || key === "entry_mode" ? "asc" : "desc");
    }
  }

  function SortIcon({ col }: { col: ColKey }) {
    if (sortKey !== col) return <ChevronsUpDown className="h-3 w-3 opacity-30" />;
    return sortDir === "asc"
      ? <ChevronUp className="h-3 w-3 text-emerald-400" />
      : <ChevronDown className="h-3 w-3 text-emerald-400" />;
  }

  // Gate filter chips: 0+, 1+, 2+, 3+, 4
  const gateChips = [null, 1, 2, 3, 4];
  const confChips = [null, 30, 50, 70];

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">
            Signal Universe
            {data && <span className="ml-2 text-xs text-slate-500 font-normal">{data.total} tickers</span>}
            {filtered.length !== (data?.total ?? 0) && (
              <span className="ml-1 text-xs text-slate-500 font-normal">· {filtered.length} shown</span>
            )}
          </h3>
          {data?.as_of && (
            <p className="text-[10px] text-slate-500 font-mono mt-0.5">EOD snapshot: {data.as_of}</p>
          )}
        </div>
        <button
          onClick={() => void load()}
          disabled={loading}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-slate-800 border border-slate-700 text-xs text-slate-400 hover:text-slate-200 hover:border-slate-500 transition disabled:opacity-50"
        >
          <RefreshCw className={clsx("h-3 w-3", loading && "animate-spin")} />
          {loading ? "Loading…" : "Reload"}
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 items-center">
        {/* Ticker search with autocomplete */}
        <div className="relative">
          <Search className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
          <input
            ref={searchRef}
            value={search}
            onChange={e => { setSearch(e.target.value); setShowSuggestions(true); }}
            onFocus={() => setShowSuggestions(true)}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 120)}
            placeholder="Ticker / sector…"
            className="pl-7 pr-3 py-1.5 w-36 sm:w-44 text-xs bg-slate-800 border border-slate-700 rounded-md text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-emerald-500/60"
          />
          {showSuggestions && suggestions.length > 0 && (
            <div className="absolute top-full mt-1 left-0 z-30 bg-slate-800 border border-slate-700 rounded-md shadow-xl w-36 sm:w-44 py-1">
              {suggestions.map(t => (
                <button
                  key={t}
                  onMouseDown={() => { setSearch(t); setShowSuggestions(false); }}
                  className="w-full text-left px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700 font-mono"
                >
                  {t}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Entry mode filter */}
        <div className="flex items-center gap-1">
          {(["all", "full_go", "starter_only", "hard_lock"] as const).map(m => {
            const { label, cls } = m === "all"
              ? { label: "All", cls: "text-slate-400 bg-slate-800 border-slate-700" }
              : entryModeLabel(m);
            return (
              <button
                key={m}
                onClick={() => setEntryModeFilter(m)}
                className={clsx(
                  "px-2 py-1 rounded text-[10px] font-medium border transition",
                  entryModeFilter === m ? cls + " ring-1 ring-current" : "text-slate-500 bg-slate-800/50 border-slate-700/50 hover:border-slate-600"
                )}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Gates filter */}
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-slate-500">Gates≥</span>
          {gateChips.map(v => (
            <button
              key={v ?? "all"}
              onClick={() => setMinGates(v)}
              className={clsx(
                "px-1.5 py-0.5 rounded text-[10px] border transition",
                minGates === v
                  ? "text-slate-200 bg-slate-600 border-slate-500"
                  : "text-slate-500 bg-slate-800/50 border-slate-700/50 hover:border-slate-600"
              )}
            >
              {v === null ? "—" : v}
            </button>
          ))}
        </div>

        {/* Confidence filter */}
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-slate-500">Conf≥</span>
          {confChips.map(v => (
            <button
              key={v ?? "all"}
              onClick={() => setMinConf(v)}
              className={clsx(
                "px-1.5 py-0.5 rounded text-[10px] border transition",
                minConf === v
                  ? "text-slate-200 bg-slate-600 border-slate-500"
                  : "text-slate-500 bg-slate-800/50 border-slate-700/50 hover:border-slate-600"
              )}
            >
              {v === null ? "—" : `${v}%`}
            </button>
          ))}
        </div>

        {/* Regime filter */}
        {allRegimes.length > 0 && (
          <select
            value={regimeFilter}
            onChange={e => setRegimeFilter(e.target.value)}
            className="text-[10px] px-2 py-1.5 bg-slate-800 border border-slate-700 rounded-md text-slate-400 focus:outline-none focus:border-emerald-500/60"
          >
            <option value="all">All regimes</option>
            {allRegimes.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      {/* Table */}
      {!error && (
        <div className="overflow-x-auto rounded-lg border border-slate-700/60">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-800/80 border-b border-slate-700/60">
                {COLS.map(col => (
                  <th
                    key={col.key}
                    className={clsx(
                      "px-2 py-2 font-medium text-slate-400 cursor-pointer select-none hover:text-slate-200 whitespace-nowrap",
                      col.align
                    )}
                    title={col.title}
                    onClick={() => toggleSort(col.key)}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.label}
                      <SortIcon col={col.key} />
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && filtered.length === 0 ? (
                <tr>
                  <td colSpan={COLS.length} className="px-3 py-6 text-center text-slate-500">
                    Loading universe…
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={COLS.length} className="px-3 py-6 text-center text-slate-500">
                    No tickers match the current filters.
                  </td>
                </tr>
              ) : (
                filtered.map((row, i) => {
                  const { label: emLabel, cls: emCls } = entryModeLabel(row.entry_mode);
                  const changePos = (row.change_pct ?? 0) >= 0;
                  return (
                    <tr
                      key={row.ticker}
                      className={clsx(
                        "border-b border-slate-800 transition-colors",
                        i % 2 === 0 ? "bg-slate-900/30" : "bg-transparent",
                        onTickerClick ? "hover:bg-slate-800/60 cursor-pointer" : "hover:bg-slate-800/40"
                      )}
                      onClick={() => onTickerClick?.(row.ticker)}
                    >
                      {/* Ticker */}
                      <td className="px-2 py-1.5 text-left">
                        <span className="font-mono font-semibold text-slate-200">{row.ticker}</span>
                        {row.sector && (
                          <span className="block text-[9px] text-slate-600 leading-none mt-0.5 truncate max-w-[80px]">
                            {row.sector}
                          </span>
                        )}
                      </td>
                      {/* Close */}
                      <td className="px-2 py-1.5 text-right font-mono text-slate-300">
                        {row.close != null ? `$${row.close.toFixed(2)}` : "—"}
                      </td>
                      {/* Change % */}
                      <td className={clsx("px-2 py-1.5 text-right font-mono", changePos ? "text-emerald-400" : "text-red-400")}>
                        {fmtPct(row.change_pct)}
                      </td>
                      {/* Score */}
                      <td className={clsx("px-2 py-1.5 text-right font-mono font-semibold", scoreColor(row.score))}>
                        {fmtNum(row.score, 0)}
                      </td>
                      {/* Regime */}
                      <td className={clsx("px-2 py-1.5 text-center font-mono text-[10px]", regimeColor(row.regime))}>
                        {row.regime}
                      </td>
                      {/* RSI */}
                      <td className={clsx(
                        "px-2 py-1.5 text-right font-mono",
                        row.rsi != null && row.rsi >= 70 ? "text-red-400"
                          : row.rsi != null && row.rsi <= 30 ? "text-emerald-400"
                            : "text-slate-400"
                      )}>
                        {fmtNum(row.rsi, 0)}
                      </td>
                      {/* Signal */}
                      <td className={clsx("px-2 py-1.5 text-center text-[10px]", signalColor(row.signal))}>
                        {row.signal}
                      </td>
                      {/* Entry mode */}
                      <td className="px-2 py-1.5 text-center">
                        <span className={clsx("px-1.5 py-0.5 rounded text-[9px] font-medium border", emCls)}>
                          {emLabel}
                        </span>
                      </td>
                      {/* Gates */}
                      <td className="px-2 py-1.5 text-center">
                        <span className={clsx(
                          "font-mono text-[10px]",
                          row.gates_passed === row.gates_total ? "text-emerald-400"
                            : row.gates_passed >= 2 ? "text-amber-400"
                              : "text-slate-500"
                        )}>
                          {row.gates_passed}/{row.gates_total}
                        </span>
                      </td>
                      {/* Confidence */}
                      <td className={clsx(
                        "px-2 py-1.5 text-right font-mono",
                        row.confidence != null && row.confidence >= 70 ? "text-emerald-400"
                          : row.confidence != null && row.confidence >= 50 ? "text-amber-400"
                            : "text-slate-500"
                      )}>
                        {row.confidence != null ? `${fmtNum(row.confidence, 0)}%` : "—"}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      {data?.rows?.length === 0 && data?.message && (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-sm text-slate-400">{data.message}</p>
          <button
            type="button"
            onClick={() => load()}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-600/30"
          >
            <RefreshCw className="h-3 w-3" />
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
