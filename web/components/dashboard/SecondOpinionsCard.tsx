"use client";

import React from "react";
import { clsx } from "clsx";
import { Users } from "lucide-react";
import type { RetailActionStatus } from "./TickerDetailModal";

type Bias = "bullish" | "neutral" | "bearish";

export interface SecondOpinion {
  key: string;
  source: string;
  timeframe?: string;
  horizon?: string;
  available: boolean;
  label?: string | null;
  bias?: Bias | null;
  score?: number;
  total?: number;
  bullish_pct?: number;
  ma?: { buy: number; neutral: number; sell: number };
  osc?: { buy: number; neutral: number; sell: number };
}

export interface SecondOpinionsPayload {
  opinions?: SecondOpinion[];
  finnhub_configured?: boolean;
  note?: string;
}

function ourBias(s?: RetailActionStatus | null): Bias | null {
  if (!s) return null;
  if (/TRIM|REDUCE|SELL|AVOID|EXIT/i.test(s.title)) return "bearish";
  if (s.light === "green") return "bullish";
  return "neutral";
}

const biasClass: Record<Bias, string> = {
  bullish: "text-td-accent",
  neutral: "text-td-muted",
  bearish: "text-td-crit",
};

/** Outside-style ratings shown next to our call. Informational only — never changes our action. */
export function SecondOpinionsCard({
  data,
  actionStatus,
}: {
  data?: SecondOpinionsPayload | null;
  actionStatus?: RetailActionStatus | null;
}) {
  const ops = data?.opinions ?? [];
  if (!ops.some((o) => o.available)) return null;
  const ours = ourBias(actionStatus);
  // A missing API key is setup detail, not something a reader can act on.
  const rows = ops.filter((o) => o.available || !(o.key === "finnhub" && !data?.finnhub_configured));
  const hasTally = rows.some((o) => o.available && o.ma && o.osc);
  return (
    <div className="rounded-lg border border-td-line/60 bg-td-line/10 px-3 py-2">
      <div className="flex items-center gap-2">
        <Users className="h-4 w-4 shrink-0 text-td-muted" aria-hidden />
        <p className="text-[13px] font-semibold uppercase tracking-wide text-td-text">Second opinions</p>
        {actionStatus && <span className="ml-auto text-[13px] text-td-muted">Ours: {actionStatus.title}</span>}
      </div>
      <table className="mt-1 w-full text-sm tabular-nums">
        <tbody>
          {rows.map((o) => {
            const detail = !o.available
              ? "Unavailable"
              : o.ma && o.osc
                ? (
                    <>
                      <span className="block whitespace-nowrap">MAs {o.ma.buy}↑ {o.ma.sell}↓</span>
                      <span className="block whitespace-nowrap">
                        Osc {o.osc.buy}↑ {o.osc.neutral}– {o.osc.sell}↓
                      </span>
                    </>
                  )
                : o.total
                  ? `${o.total} analysts · ${o.bullish_pct ?? "—"}% buy`
                  : "";
            const agrees = o.available && o.bias && ours ? o.bias === ours : null;
            return (
              <tr key={o.key} className="border-t border-td-line/40">
                <td className="py-1 pr-2 text-td-text/90">
                  {o.source}
                  <span className="block text-[11px] text-td-muted">{o.horizon}</span>
                </td>
                <td className={clsx("py-1 pr-2 font-semibold whitespace-nowrap", o.bias ? biasClass[o.bias] : "text-td-muted")}>
                  {o.available ? o.label : "—"}
                </td>
                <td className="py-1 pr-2 text-[13px] text-td-muted">{detail}</td>
                <td className="py-1 text-right text-[13px] whitespace-nowrap">
                  {agrees == null ? "" : agrees ? (
                    <span className="text-td-accent">agrees</span>
                  ) : (
                    <span className="text-td-warn">differs</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {hasTally && (
        <p className="text-[13px] text-td-muted mt-1 leading-relaxed">
          <span className="text-td-text/80">MAs</span> = moving averages (price above the average votes buy ↑,
          below votes sell ↓). <span className="text-td-text/80">Osc</span> = oscillators such as RSI, MACD and
          Stochastic: ↑ buy · – neutral · ↓ sell. The rating is the balance of these votes.
        </p>
      )}
      {data?.note && <p className="text-[13px] text-td-muted mt-1 leading-relaxed">{data.note}</p>}
    </div>
  );
}
