"use client";

import { clsx } from "clsx";
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
    at_band_only?: boolean;
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
    <div className="rounded-lg border border-td-info/25 bg-td-info/5 px-3 py-2 space-y-2">
      <div className="flex items-center gap-2">
        <Scale className="h-4 w-4 shrink-0 text-td-info" aria-hidden />
        <p className="text-[13px] font-semibold uppercase tracking-wide text-td-text">Your position sizing</p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {[data.risk_profile, `cap ${data.cap_pct}%`, `book ${usd(data.portfolio_value)}`].map((t) => (
          <span key={t} className="rounded-full bg-td-surface2 border border-td-line px-2 py-0.5 text-[12px] text-td-text/85 capitalize tabular-nums">
            {t}
          </span>
        ))}
      </div>
      <p className="text-sm text-td-text/90 tabular-nums">
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
        <div className={clsx("rounded-md border px-2.5 py-1.5", buy.at_band_only ? "border-td-warn/35 bg-td-warn/5" : buy.allowed ? "border-td-accent/35 bg-td-accent/5" : "border-td-crit/30 bg-td-crit/5")}>
          <div className="flex items-center justify-between gap-2">
            <p className="text-[13px] font-semibold text-td-text">Buy side</p>
            <span className={clsx("rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide", buy.at_band_only ? "bg-td-warn/15 text-td-warn" : buy.allowed ? "bg-td-accent/15 text-td-accent" : "bg-td-crit/15 text-td-crit")}>
              {buy.at_band_only ? "At band only" : buy.allowed ? "Can add" : "Locked"}
            </span>
          </div>
          {buy.allowed ? (
            <p className="text-sm text-td-text tabular-nums">
              {buy.at_band_only ? "In the band, up to " : "Up to "}<span className="font-mono">{buy.shares}</span> shares ({usd(buy.dollars)}) → {buy.new_weight_pct.toFixed(1)}% of book
            </p>
          ) : (
            <p className="text-sm text-td-text">No add now</p>
          )}
          {buy.tranches.length > 1 && (
            <p className="text-[13px] text-td-muted tabular-nums">
              {buy.tranches.map((t) => `T${t.tranche}: ${t.shares} sh`).join(" · ")}
            </p>
          )}
          <p className="text-[13px] text-td-muted leading-relaxed">{buy.note}</p>
        </div>
        <div className={clsx("rounded-md border px-2.5 py-1.5", sell.options.length ? "border-td-warn/35 bg-td-warn/5" : "border-td-line/60 bg-td-surface2/40")}>
          <div className="flex items-center justify-between gap-2">
            <p className="text-[13px] font-semibold text-td-text">Sell side</p>
            <span className={clsx("rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide", sell.options.length ? "bg-td-warn/15 text-td-warn" : "bg-td-surface2 text-td-muted")}>
              {sell.options.length ? "Options" : data.held ? "Hold" : "Not held"}
            </span>
          </div>
          {sell.default && <p className="text-sm text-td-text">Default: {sell.default}</p>}
          {sell.options.map((o) => (
            <div key={o.reason} className="text-sm text-td-text tabular-nums">
              <span className="text-td-warn">{o.label}</span>
              {o.shares != null && (
                <>
                  {" "}— optional trim <span className="font-mono">{o.shares}</span> sh ({usd(o.dollars ?? 0)})
                </>
              )}
              <p className="text-[13px] text-td-muted leading-relaxed">{o.note}</p>
            </div>
          ))}
          <p className="text-[13px] text-td-muted leading-relaxed">{sell.note}</p>
        </div>
      </div>
      <p className="text-[11px] text-td-muted leading-relaxed">
        Cap = max % of your book in one stock. Adds also limited so a stop-out loses ≤{data.risk_per_trade_pct}% of the book
        {buy.stop_used ? ` (stop $${buy.stop_used.toFixed(2)})` : ""}. Change risk profile in Portfolio.
      </p>
    </div>
  );
}
