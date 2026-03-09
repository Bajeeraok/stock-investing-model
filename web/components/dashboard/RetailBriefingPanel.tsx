"use client";

import { Target, Thermometer, AlertTriangle, TrendingUp, Calendar, Shield, PieChart, Info } from "lucide-react";
import type { DashboardData } from "@/app/page";
import { clsx } from "clsx";

interface Props {
  data: Pick<DashboardData, "retail_briefing"> | null;
  onTickerClick?: (ticker: string) => void;
}

const ACTION_STYLE: Record<string, { bg: string; text: string }> = {
  BUY: { bg: "bg-emerald-500/20", text: "text-emerald-300" },
  WAIT: { bg: "bg-blue-500/20", text: "text-blue-300" },
  TRIM: { bg: "bg-amber-500/20", text: "text-amber-300" },
  HOLD: { bg: "bg-slate-500/20", text: "text-slate-300" },
};

export function RetailBriefingPanel({ data, onTickerClick }: Props) {
  const rb = data?.retail_briefing;
  if (!rb) return null;

  const db = rb.daily_briefing;
  const summary = db?.summary_sentence;
  const regimeSentence = rb.regime_plain_english ?? db?.regime_plain_english;
  const suggested = db?.suggested_actions ?? [];
  const heat = rb.portfolio_heat_pct ?? 0;
  const concentration = rb.concentration;
  const taxApproaching = rb.tax_approaching_ltcg ?? db?.tax_approaching_ltcg ?? [];
  const winLoss = rb.win_loss_recap;
  const overtrading = rb.overtrading_nudge;
  const sectorGap = rb.sector_gap;
  const drawdownGuard = rb.drawdown_guard;

  return (
    <div className="rounded-xl border border-slate-700/80 bg-slate-900/50 backdrop-blur-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-700/60 bg-slate-800/40 flex items-center gap-2">
        <Target className="h-5 w-5 text-emerald-400 shrink-0" />
        <h2 className="text-base font-semibold text-slate-100">Today&apos;s briefing</h2>
      </div>
      <div className="p-4 space-y-4">
        {summary && (
          <p className="text-sm text-slate-200 leading-relaxed">
            {summary}
          </p>
        )}
        {regimeSentence && (
          <div className="flex items-start gap-2 rounded-lg border border-slate-600/60 bg-slate-800/30 px-3 py-2">
            <Info className="h-4 w-4 text-slate-400 shrink-0 mt-0.5" />
            <p className="text-sm text-slate-300">{regimeSentence}</p>
          </div>
        )}

        {/* Metrics row */}
        <div className="flex flex-wrap gap-3">
          {heat > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/50 border border-slate-600/50">
              <Thermometer className={clsx("h-4 w-4", heat > 15 ? "text-amber-400" : "text-slate-400")} />
              <span className="text-sm font-medium text-slate-200">Portfolio heat: {heat}%</span>
            </div>
          )}
          {concentration?.concentration_pct != null && concentration.concentration_pct > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/50 border border-slate-600/50">
              <PieChart className="h-4 w-4 text-slate-400" />
              <span className="text-sm text-slate-300">Top 3: {concentration.concentration_pct}%</span>
            </div>
          )}
          {winLoss != null && (winLoss.wins != null || winLoss.losses != null) && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/50 border border-slate-600/50">
              <TrendingUp className="h-4 w-4 text-slate-400" />
              <span className="text-sm text-slate-300">
                Paper: {winLoss.wins ?? 0}W / {winLoss.losses ?? 0}L
                {winLoss.win_rate_pct != null && ` · ${winLoss.win_rate_pct}% win rate`}
                {winLoss.net_pnl_pct != null && ` · ${winLoss.net_pnl_pct >= 0 ? "+" : ""}${winLoss.net_pnl_pct}% net`}
              </span>
            </div>
          )}
        </div>

        {/* Suggested actions */}
        {suggested.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Do one thing</h3>
            <ul className="space-y-1.5">
              {suggested.slice(0, 5).map((a, i) => (
                <li key={`${a.ticker}-${i}`} className="flex items-center gap-2 flex-wrap">
                  <button
                    type="button"
                    onClick={() => onTickerClick?.(a.ticker)}
                    className="font-medium text-emerald-300 hover:text-emerald-200 hover:underline"
                  >
                    {a.ticker}
                  </button>
                  <span className={clsx("text-xs font-semibold px-2 py-0.5 rounded", ACTION_STYLE[a.action]?.bg, ACTION_STYLE[a.action]?.text)}>
                    {a.action}
                  </span>
                  <span className="text-slate-400 text-sm">{a.reason}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Nudges */}
        <div className="space-y-2">
          {drawdownGuard && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
              <Shield className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-sm text-amber-200">{drawdownGuard}</p>
            </div>
          )}
          {overtrading && (
            <div className="flex items-start gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2">
              <AlertTriangle className="h-4 w-4 text-blue-400 shrink-0 mt-0.5" />
              <p className="text-sm text-blue-200">{overtrading}</p>
            </div>
          )}
          {sectorGap && (
            <div className="flex items-start gap-2 rounded-lg border border-slate-600 bg-slate-800/40 px-3 py-2">
              <PieChart className="h-4 w-4 text-slate-400 shrink-0 mt-0.5" />
              <p className="text-sm text-slate-300">{sectorGap}</p>
            </div>
          )}
          {concentration?.message && (
            <div className="flex items-start gap-2 rounded-lg border border-slate-600 bg-slate-800/40 px-3 py-2">
              <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-sm text-slate-300">{concentration.message}</p>
            </div>
          )}
          {taxApproaching.length > 0 && (
            <div className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2">
              <Calendar className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
              <div className="text-sm text-emerald-200">
                <span className="font-medium">Approaching 1-year (LTCG):</span>{" "}
                {taxApproaching.map((t) => `${t.ticker} (${t.days_to_ltcg}d)`).join(", ")}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
