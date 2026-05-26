"use client";

import { useEffect, useState, useCallback } from "react";
import { Activity, Globe, RefreshCw } from "lucide-react";
import { clsx } from "clsx";
import { MarketCatalystBoardPanel, type MarketCatalystBoard } from "./MarketCatalystBoard";
import { PreMarketStrip, type PreMarketData } from "./PreMarketPanel";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

type OutlookRow = {
  ticker: string;
  bias?: string;
  pct_green?: number | null;
  typical_range_pct?: number | null;
};

type TypicalRow = {
  ticker: string;
  typical_pct_1d: number;
  high_vol_pct?: number | null;
};

/** `/api/market-state` enriches base pre-market payload with mover catalyst lines. */
type MarketStatePremarket = PreMarketData & {
  tech_movers_detail?: Array<{ ticker: string; pct: number; why?: string }>;
};

export interface MarketStatePayload {
  as_of_et?: string;
  macro_regime?: string | null;
  global_market_regime?: string | null;
  retail_market_decisions?: import("./RetailMarketDecisionsPanel").RetailMarketDecisions | null;
  premarket?: MarketStatePremarket | null;
  market_catalysts?: MarketCatalystBoard | null;
  next_day_outlook?: OutlookRow[];
  next_day_summary?: string | null;
  typical_move?: TypicalRow[];
  polling?: {
    premarket_poll_ms?: number;
    intraday_poll_ms?: number;
    is_premarket_et?: boolean;
    is_rth_et?: boolean;
  };
  disclaimer?: string;
}

function pollIntervalMs(polling: MarketStatePayload["polling"]): number {
  if (polling?.is_rth_et && polling.intraday_poll_ms) return polling.intraday_poll_ms;
  if (polling?.is_premarket_et && polling.premarket_poll_ms) return polling.premarket_poll_ms;
  return 30 * 60 * 1000;
}

export function MarketStatePanel() {
  const [state, setState] = useState<MarketStatePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchState = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const url = API_BASE ? `${API_BASE}/api/market-state` : "/api/market-state";
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setState(await res.json());
      setError(null);
    } catch (e) {
      if (!silent) setError(e instanceof Error ? e.message : "Failed to load market state");
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchState(false);
  }, [fetchState]);

  useEffect(() => {
    const ms = pollIntervalMs(state?.polling);
    const id = setInterval(() => fetchState(true), ms);
    return () => clearInterval(id);
  }, [state?.polling, fetchState]);

  if (loading && !state) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-800/30 p-6 text-center text-slate-400 text-sm">
        Loading market state…
      </div>
    );
  }

  if (error && !state) {
    return (
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-amber-200 text-sm">
        Market state unavailable: {error}
      </div>
    );
  }

  if (!state) return null;

  const premarket = state.premarket;
  const catalysts = state.market_catalysts;
  const intraday = catalysts?.intraday;
  const unified = state.retail_market_decisions?.market_context;
  const techMoversDetail = premarket?.tech_movers_detail;

  return (
    <div className="rounded-xl border border-violet-500/25 bg-violet-950/15 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-violet-500/20 bg-slate-900/40">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <Globe className="h-4 w-4 text-violet-400 shrink-0" />
          <span className="text-sm font-semibold text-slate-200">Market state</span>
          {unified?.coexistence_note ? (
            <span className="text-[11px] text-slate-500 leading-snug max-w-xl">{unified.coexistence_note}</span>
          ) : (
            (state.macro_regime || state.global_market_regime) && (
              <span className="text-xs text-slate-500">
                {state.macro_regime && <>Macro overlay: {state.macro_regime}</>}
                {state.global_market_regime && (
                  <> · SPY regime (LT): <span className="text-emerald-400/90">{state.global_market_regime.replace(/_/g, " ")}</span></>
                )}
              </span>
            )
          )}
        </div>
        <button
          type="button"
          onClick={() => fetchState(false)}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
        >
          <RefreshCw className={clsx("h-3 w-3", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      <div className="p-4 space-y-4">
        {premarket && <PreMarketStrip data={premarket} />}

        {Array.isArray(techMoversDetail) && techMoversDetail.length > 0 && (
          <div className="rounded-lg border border-slate-700/60 bg-slate-900/30 p-3">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Pre-market movers (why)</p>
            <ul className="space-y-1 text-xs">
              {techMoversDetail.slice(0, 6).map((m) => (
                  <li key={m.ticker} className="text-slate-300">
                    <span className={m.pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                      {m.ticker} {m.pct >= 0 ? "+" : ""}
                      {m.pct}%
                    </span>
                    {m.why && <span className="text-slate-500"> — {m.why}</span>}
                  </li>
                ))}
            </ul>
          </div>
        )}

        {intraday && (
          <div className="rounded-lg border border-slate-700/60 bg-slate-900/40 px-3 py-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
            <span className="text-slate-500 flex items-center gap-1">
              <Activity className="h-3 w-3" /> Intraday SPY
            </span>
            <span className="text-slate-300">
              Since open:{" "}
              <span className={clsx("font-mono", (intraday.since_open_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                {(intraday.since_open_pct ?? 0) >= 0 ? "+" : ""}
                {intraday.since_open_pct}%
              </span>
            </span>
            {intraday.since_release && (
              <span className="text-slate-400">
                Since {intraday.since_release.event_type} ({intraday.since_release.release_time_et}):{" "}
                <span className="font-mono text-violet-300">
                  {(intraday.since_release.pct_since_release ?? 0) >= 0 ? "+" : ""}
                  {intraday.since_release.pct_since_release}%
                </span>
              </span>
            )}
            <span className="text-slate-600">as of {intraday.as_of_et} ET</span>
          </div>
        )}

        {catalysts && <MarketCatalystBoardPanel board={catalysts} compact />}

        {(state.next_day_outlook?.length ?? 0) > 0 && (
          <div className="rounded-lg border border-slate-700/60 bg-slate-900/30 p-3">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Next-day outlook</p>
            {state.next_day_summary && (
              <p className="text-sm text-slate-300 mb-2">{state.next_day_summary}</p>
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {state.next_day_outlook!.map((o) => (
                <span key={o.ticker}>
                  <span className="text-slate-300">{o.ticker}</span>{" "}
                  {(o as { edge_strength?: string }).edge_strength === "none" ? (
                    <span className="text-slate-500">No edge</span>
                  ) : (
                    <span
                      className={
                        o.bias === "Bullish" ? "text-emerald-400" : o.bias === "Bearish" ? "text-red-400" : "text-slate-400"
                      }
                    >
                      {o.bias}
                    </span>
                  )}
                  {o.pct_green != null && (o as { edge_strength?: string }).edge_strength !== "none" && (
                    <span className="text-slate-500 text-xs"> ({o.pct_green}% green)</span>
                  )}
                </span>
              ))}
            </div>
          </div>
        )}

        {(state.typical_move?.length ?? 0) > 0 && (
          <div className="rounded-lg border border-slate-700/60 bg-slate-900/30 p-3">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Typical 1-day range</p>
            <div className="space-y-1 text-sm text-slate-300">
              {state.typical_move!.map((m) => (
                <div key={m.ticker}>
                  {m.ticker}: ±{m.typical_pct_1d}%
                  {(m as { range_note?: string }).range_note && (
                    <span className="block text-xs text-amber-300/80">{(m as { range_note?: string }).range_note}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {state.disclaimer && <p className="text-[10px] text-slate-600">{state.disclaimer}</p>}
      </div>
    </div>
  );
}
