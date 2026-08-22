"use client";

/**
 * Insider & Institutional Flow Tracker — SEC EDGAR Form 4 (free data).
 * Flags insider buys/sells at watched tickers with links to EDGAR.
 */

import { TrendingUp, TrendingDown, ExternalLink } from "lucide-react";

export interface InsiderBuy {
  ticker: string;
  filing_date: string;
  shares: number;
  edgar_url: string;
}

export interface InsiderSell {
  ticker: string;
  filing_date: string;
  shares: number;
  edgar_url: string;
}

export interface InsiderFlowData {
  insider_buys: InsiderBuy[];
  insider_sells: InsiderSell[];
  ticker_activities?: { ticker: string; filing_date: string; edgar_url: string; buys_shares: number; sells_shares: number }[];
  message?: string | null;
  as_of_date?: string | null;
  fetched_at?: string | null;
}

interface InsiderFlowTrackerProps {
  data: InsiderFlowData | null | undefined;
}

function formatShares(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function InsiderFlowTracker({ data }: InsiderFlowTrackerProps) {
  if (!data) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4 text-sm text-slate-500">
        No insider flow data. Data is from SEC EDGAR Form 4 (free); updated once daily after the close.
      </div>
    );
  }

  const buys = data.insider_buys ?? [];
  const sells = data.insider_sells ?? [];
  const message = data.message;
  const asOf = data.as_of_date || (data.fetched_at ? String(data.fetched_at).slice(0, 10) : null);

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4 space-y-4">
      <p className="text-xs text-slate-500">
        Form 4 filings (insider buys/sells) from SEC EDGAR. Multiple insiders buying in the same quarter is a strong medium/long-term signal. Updated once daily after the close
        {asOf ? <> · as of <span className="font-mono text-slate-400">{asOf}</span></> : null}.
      </p>
      {message && (
        <p className="text-xs text-amber-400">{message}</p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Insider buys — highlight */}
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="h-4 w-4 text-emerald-400 shrink-0" />
            <span className="text-xs font-semibold text-emerald-500 uppercase tracking-wider">
              Recent insider buys ({buys.length})
            </span>
          </div>
          {buys.length === 0 ? (
            <p className="text-xs text-slate-500">No insider buys in the last 90 days for watched tickers.</p>
          ) : (
            <ul className="space-y-1.5">
              {buys.slice(0, 15).map((b, i) => (
                <li key={`${b.ticker}-${b.filing_date}-${i}`} className="flex items-center justify-between gap-2 text-sm">
                  <span className="font-medium text-slate-200">{b.ticker}</span>
                  <span className="text-slate-400 text-xs">{b.filing_date}</span>
                  <span className="text-emerald-400 font-mono text-xs">{formatShares(b.shares)}</span>
                  {b.edgar_url ? (
                    <a
                      href={b.edgar_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-slate-500 hover:text-slate-300 shrink-0"
                      aria-label="View on SEC EDGAR"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Insider sells */}
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
          <div className="flex items-center gap-2 mb-2">
            <TrendingDown className="h-4 w-4 text-red-400 shrink-0" />
            <span className="text-xs font-semibold text-red-500 uppercase tracking-wider">
              Recent insider sells ({sells.length})
            </span>
          </div>
          {sells.length === 0 ? (
            <p className="text-xs text-slate-500">No insider sells in the last 90 days for watched tickers.</p>
          ) : (
            <ul className="space-y-1.5">
              {sells.slice(0, 15).map((s, i) => (
                <li key={`${s.ticker}-${s.filing_date}-${i}`} className="flex items-center justify-between gap-2 text-sm">
                  <span className="font-medium text-slate-200">{s.ticker}</span>
                  <span className="text-slate-400 text-xs">{s.filing_date}</span>
                  <span className="text-red-400 font-mono text-xs">{formatShares(s.shares)}</span>
                  {s.edgar_url ? (
                    <a
                      href={s.edgar_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-slate-500 hover:text-slate-300 shrink-0"
                      aria-label="View on SEC EDGAR"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
