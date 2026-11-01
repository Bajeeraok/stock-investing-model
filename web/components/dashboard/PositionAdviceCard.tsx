"use client";

import React from "react";
import { Scale } from "lucide-react";

export interface PositionAdvicePayload {
  portfolio_value: number;
  risk_profile: string;
  cap_pct: number;
  risk_per_trade_pct: number;
  entry_mode?: string | null;
  held: boolean;
  shares: number;
  value: number;
  weight_pct: number;
  accounts: { account: string; shares: number; value: number }[];
  buy: {
    allowed: boolean;
    shares: number;
    dollars: number;
    new_weight_pct: number;
    room_to_cap_dollars: number;
    stop_used?: number | null;
    tranches: { tranche: number; shares: number; dollars: number }[];
    note: string;
  };
  sell: {
    default?: string | null;
    options: { reason: string; label: string; shares: number | null; dollars: number | null; note: string }[];
    note: string;
  };
  scope?: string;
}

const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;

/** Buy-side and sell-side sizing from the user's real holdings (all accounts summed). */
export function PositionAdviceCard({ data }: { data?: PositionAdvicePayload | null }) {
  if (!data) return null;
  const { buy, sell } = data;
  return (
    <div className="rounded-lg border border-td-line/60 bg-td-line/10 px-3 py-2 space-y-2">
      <div className="flex items-center gap-2">
        <Scale className="h-4 w-4 shrink-0 text-td-muted" aria-hidden />
        <p className="text-xs font-semibold uppercase tracking-wide text-td-text">Your position sizing</p>
        <span className="ml-auto text-[11px] text-td-muted">
          {data.risk_profile} · cap {data.cap_pct}% · book {usd(data.portfolio_value)}
        </span>
      </div>
      <p className="text-[12px] text-td-text/90 tabular-nums">
        {data.held ? (
          <>
            You hold <span className="font-mono">{data.shares.toLocaleString()}</span> shares ({usd(data.value)},{" "}
            <span className="font-mono">{data.weight_pct.toFixed(1)}%</span> of your book)
            {data.accounts.length > 1 && ` across ${data.accounts.map((a) => a.account).join(", ")}`}.
          </>
        ) : (
          "Not held."
        )}
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="rounded-md border border-td-line/50 px-2.5 py-1.5">
          <p className="text-[11px] font-semibold text-td-text">Buy side</p>
          {buy.allowed ? (
            <p className="text-[12px] text-td-text tabular-nums">
              Up to <span className="font-mono">{buy.shares}</span> shares ({usd(buy.dollars)}) → {buy.new_weight_pct.toFixed(1)}% of book
            </p>
          ) : (
            <p className="text-[12px] text-td-text">No add now</p>
          )}
          {buy.tranches.length > 1 && (
            <p className="text-[11px] text-td-muted tabular-nums">
              {buy.tranches.map((t) => `T${t.tranche}: ${t.shares} sh`).join(" · ")}
            </p>
          )}
          <p className="text-[11px] text-td-muted leading-snug">{buy.note}</p>
        </div>
        <div className="rounded-md border border-td-line/50 px-2.5 py-1.5">
          <p className="text-[11px] font-semibold text-td-text">Sell side</p>
          {sell.default && <p className="text-[12px] text-td-text">Default: {sell.default}</p>}
          {sell.options.map((o) => (
            <div key={o.reason} className="text-[12px] text-td-text tabular-nums">
              <span className="text-td-warn">{o.label}</span>
              {o.shares != null && (
                <>
                  {" "}— optional trim <span className="font-mono">{o.shares}</span> sh ({usd(o.dollars ?? 0)})
                </>
              )}
              <p className="text-[11px] text-td-muted leading-snug">{o.note}</p>
            </div>
          ))}
          <p className="text-[11px] text-td-muted leading-snug">{sell.note}</p>
        </div>
      </div>
      <p className="text-[10px] text-td-muted leading-snug">
        Cap = max % of your book in one stock. Adds also limited so a stop-out loses ≤{data.risk_per_trade_pct}% of the book
        {buy.stop_used ? ` (stop $${buy.stop_used.toFixed(2)})` : ""}. Change risk profile in Portfolio.
      </p>
    </div>
  );
}
