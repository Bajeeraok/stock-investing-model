"use client";

/**
 * App-wide live price store.
 *
 * LivePricesProvider wraps any subtree and polls /api/live-prices every 60 s
 * for the tickers it is told to watch. Components call useLivePrice(ticker) to
 * get the latest delayed quote (yfinance, ~15-min delay) or null if not yet fetched.
 *
 * Usage:
 *   // In Dashboard (or any parent):
 *   <LivePricesProvider tickers={allTickersInView}>
 *     <SignalsTable .../>
 *     <PortfolioHoldings .../>
 *   </LivePricesProvider>
 *
 *   // In a child component:
 *   const liveClose = useLivePrice("AAPL");   // number | null
 *   const displayPrice = liveClose ?? row.close;
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { apiUrl } from "./apiBase";

// ── Types ─────────────────────────────────────────────────────────────────────

type PriceMap = Record<string, number>; // TICKER → price

interface LivePriceCtx {
  prices: PriceMap;
  lastFetchedAt: Date | null;
  source: string | null;
}

// ── Context ───────────────────────────────────────────────────────────────────

const LivePriceContext = createContext<LivePriceCtx>({
  prices: {},
  lastFetchedAt: null,
  source: null,
});

// ── Hook ──────────────────────────────────────────────────────────────────────

/** Returns the latest live price for a ticker, or null if not yet received. */
export function useLivePrice(ticker: string): number | null {
  const { prices } = useContext(LivePriceContext);
  return prices[ticker?.toUpperCase()] ?? null;
}

/** Returns the full context — useful for debugging or bulk access. */
export function useLivePriceContext(): LivePriceCtx {
  return useContext(LivePriceContext);
}

// ── Provider ──────────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 60_000; // 1 minute
const MAX_TICKERS = 150;

export function LivePricesProvider({
  tickers,
  children,
  intervalMs = POLL_INTERVAL_MS,
}: {
  tickers: string[];
  children: React.ReactNode;
  intervalMs?: number;
}) {
  const [ctx, setCtx] = useState<LivePriceCtx>({
    prices: {},
    lastFetchedAt: null,
    source: null,
  });

  // Stable sorted key so the effect only re-runs when the ticker list actually changes
  const tickerKey = Array.from(
    new Set(tickers.map((t) => t.toUpperCase()).filter(Boolean)),
  )
    .sort()
    .slice(0, MAX_TICKERS)
    .join(",");

  const fetchPrices = useCallback(
    async (key: string, signal?: AbortSignal) => {
      if (!key) return;
      try {
        const url = apiUrl(`/api/live-prices?tickers=${encodeURIComponent(key)}`);
        const res = await fetch(url, { signal, cache: "no-store" });
        if (!res.ok) return;
        const json = await res.json();
        if (json?.prices && typeof json.prices === "object") {
          setCtx({
            prices: json.prices as PriceMap,
            lastFetchedAt: new Date(),
            source: json.source ?? null,
          });
        }
      } catch {
        // Network errors are silent — stale prices stay in state
      }
    },
    [],
  );

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!tickerKey) return;
    const ac = new AbortController();

    // Fetch immediately, then on interval
    fetchPrices(tickerKey, ac.signal);

    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => fetchPrices(tickerKey), intervalMs);

    return () => {
      ac.abort();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [tickerKey, intervalMs, fetchPrices]);

  return (
    <LivePriceContext.Provider value={ctx}>
      {children}
    </LivePriceContext.Provider>
  );
}
