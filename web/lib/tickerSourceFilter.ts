/** Filter tickers by portfolio vs watchlist membership. */

export type TickerSourceFilter = "all" | "portfolio" | "watchlist" | "watchlist_only";

export const TICKER_SOURCE_STORAGE_KEY = "thrive-ticker-source-filter";

export const TICKER_SOURCE_FILTERS: { id: TickerSourceFilter; label: string; hint: string }[] = [
  { id: "all", label: "All", hint: "Watchlist + portfolio holdings" },
  { id: "portfolio", label: "Owning", hint: "Names you hold in the linked portfolio" },
  { id: "watchlist", label: "Watchlist", hint: "All watchlist tickers (held or not)" },
  { id: "watchlist_only", label: "Watching", hint: "On watchlist but not in portfolio" },
];

export function loadTickerSourceFilter(): TickerSourceFilter {
  try {
    const raw = typeof window !== "undefined" ? localStorage.getItem(TICKER_SOURCE_STORAGE_KEY) : null;
    if (raw === "all" || raw === "portfolio" || raw === "watchlist" || raw === "watchlist_only") {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return "all";
}

export function saveTickerSourceFilter(id: TickerSourceFilter): void {
  try {
    localStorage.setItem(TICKER_SOURCE_STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}

export function toTickerSet(tickers: string[] | undefined | null): Set<string> {
  return new Set((tickers ?? []).map((t) => String(t).toUpperCase()).filter(Boolean));
}

export type PositionStatus = "owned" | "watching" | "universe";

export function positionStatusForTicker(
  ticker: string,
  portfolioSet: Set<string>,
  watchlistSet: Set<string>,
): PositionStatus {
  const u = String(ticker).toUpperCase();
  if (portfolioSet.has(u)) return "owned";
  if (watchlistSet.has(u)) return "watching";
  return "universe";
}

export function filterTickersBySource(
  tickers: string[],
  source: TickerSourceFilter,
  portfolioSet: Set<string>,
  watchlistSet: Set<string>,
): string[] {
  if (source === "all") return tickers;
  return tickers.filter((t) => {
    const u = String(t).toUpperCase();
    const inP = portfolioSet.has(u);
    const inW = watchlistSet.has(u);
    if (source === "portfolio") return inP;
    if (source === "watchlist") return inW;
    if (source === "watchlist_only") return inW && !inP;
    return true;
  });
}

export function countBySource(
  tickers: string[],
  portfolioSet: Set<string>,
  watchlistSet: Set<string>,
): Record<TickerSourceFilter, number> {
  const all = tickers.length;
  const portfolio = filterTickersBySource(tickers, "portfolio", portfolioSet, watchlistSet).length;
  const watchlist = filterTickersBySource(tickers, "watchlist", portfolioSet, watchlistSet).length;
  const watchlist_only = filterTickersBySource(tickers, "watchlist_only", portfolioSet, watchlistSet).length;
  return { all, portfolio, watchlist, watchlist_only };
}
