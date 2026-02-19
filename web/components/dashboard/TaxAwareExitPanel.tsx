"use client";

/**
 * Tax-Aware Exit Optimizer — positions approaching 1-year LTCG threshold.
 * Federal + state (e.g. SC) rates; recommends hold to threshold vs trim now.
 * Add purchase_date (YYYY-MM-DD) to holdings in config or Excel to enable.
 */

import { Calendar } from "lucide-react";

export interface TaxAwareExitItem {
  ticker: string;
  days_held: number;
  days_to_ltcg: number;
  gain: number;
  tax_savings_if_hold: number;
  recommendation: string;
  account?: string;
  score?: number;
  regime?: string;
}

export interface TaxAwareExitsData {
  items: TaxAwareExitItem[];
  message?: string | null;
}

interface TaxAwareExitPanelProps {
  data: TaxAwareExitsData | null | undefined;
  onTickerClick?: (ticker: string) => void;
}

export function TaxAwareExitPanel({ data, onTickerClick }: TaxAwareExitPanelProps) {
  if (!data) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4 text-sm text-slate-500">
        No tax-aware exit data.
      </div>
    );
  }

  const items = data.items ?? [];
  const message = data.message;

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Calendar className="h-4 w-4 text-slate-400 shrink-0" />
        <span className="text-sm font-semibold text-slate-300">Tax-Aware Exit Optimizer</span>
      </div>
      <p className="text-xs text-slate-500">
        Positions approaching 1-year (long-term capital gains). Short-term = taxed as income (e.g. 32% federal + 7% SC);
        long-term = 0–20% federal + 7% SC. Holding to day 366 can save $1,700+ on a $10K gain.
      </p>
      {message && items.length === 0 && (
        <p className="text-xs text-amber-400">{message}</p>
      )}
      {items.length === 0 && !message && (
        <p className="text-xs text-slate-500">No positions approaching LTCG, or add purchase_date to holdings (config or Excel: column purchase_date YYYY-MM-DD).</p>
      )}
      {items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="text-slate-500 border-b border-slate-600">
                <th className="py-1.5 pr-2 font-medium">Ticker</th>
                <th className="py-1.5 pr-2 font-medium">Days held</th>
                <th className="py-1.5 pr-2 font-medium">Days to LTCG</th>
                <th className="py-1.5 pr-2 font-medium">Gain</th>
                <th className="py-1.5 pr-2 font-medium">Save if hold</th>
                <th className="py-1.5 pr-2 font-medium">Recommendation</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.ticker} className="border-b border-slate-700/50">
                  <td className="py-2 pr-2">
                    {onTickerClick ? (
                      <button type="button" onClick={() => onTickerClick(row.ticker)} className="font-medium text-emerald-400 hover:underline">
                        {row.ticker}
                      </button>
                    ) : (
                      <span className="font-medium text-slate-200">{row.ticker}</span>
                    )}
                  </td>
                  <td className="py-2 pr-2 text-slate-400">{row.days_held}</td>
                  <td className="py-2 pr-2 text-amber-400 font-medium">{row.days_to_ltcg}</td>
                  <td className="py-2 pr-2 text-slate-300">${row.gain.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
                  <td className="py-2 pr-2 text-emerald-400">${row.tax_savings_if_hold.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
                  <td className="py-2 pr-2 text-slate-400 text-xs max-w-[280px]">{row.recommendation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
