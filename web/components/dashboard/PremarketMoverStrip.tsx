"use client";

import { clsx } from "clsx";
import { Activity } from "lucide-react";
import type { PreMarketData } from "./PreMarketPanel";

function parseDriverLine(line: string): { label: string; value: string } {
  const colon = line.indexOf(":");
  if (colon < 0) return { label: line.trim(), value: "" };
  return { label: line.slice(0, colon).trim(), value: line.slice(colon + 1).trim() };
}

function pctTone(value: string): "up" | "down" | "flat" {
  const n = parseFloat(value.replace(/[^0-9.-]/g, ""));
  if (Number.isNaN(n)) return "flat";
  if (n > 0.05) return "up";
  if (n < -0.05) return "down";
  return "flat";
}

interface SimplePreMarket {
  es_pct?: number | null;
  nq_pct?: number | null;
  tech_avg_pct?: number | null;
  message?: string | null;
}

export function PremarketMoverStrip({
  full,
  simple,
  onTickerClick,
}: {
  full?: PreMarketData | null;
  simple?: SimplePreMarket | null;
  onTickerClick?: (ticker: string) => void;
}) {
  const chips: { key: string; label: string; value: string; tone: "up" | "down" | "flat"; ticker?: string }[] = [];

  if (full) {
    for (const line of [...(full.top_bullish ?? []).slice(0, 3), ...(full.top_bearish ?? []).slice(0, 3)]) {
      const { label, value } = parseDriverLine(line);
      const ticker = /^[A-Z]{1,5}$/.test(label.split(" ")[0]) ? label.split(" ")[0] : undefined;
      chips.push({
        key: line,
        label,
        value,
        tone: pctTone(value),
        ticker,
      });
    }
    if (full.tech_movers_detail?.length) {
      for (const m of full.tech_movers_detail.slice(0, 6)) {
        if (chips.some((c) => c.label.startsWith(m.ticker))) continue;
        chips.push({
          key: `detail-${m.ticker}`,
          label: m.ticker,
          value: `${m.pct >= 0 ? "+" : ""}${m.pct}%`,
          tone: m.pct >= 0 ? "up" : "down",
          ticker: m.ticker,
        });
      }
    }
  } else if (simple) {
    if (simple.es_pct != null) {
      chips.push({
        key: "es",
        label: "ES",
        value: `${simple.es_pct >= 0 ? "+" : ""}${simple.es_pct.toFixed(2)}%`,
        tone: simple.es_pct >= 0 ? "up" : "down",
      });
    }
    if (simple.nq_pct != null) {
      chips.push({
        key: "nq",
        label: "NQ",
        value: `${simple.nq_pct >= 0 ? "+" : ""}${simple.nq_pct.toFixed(2)}%`,
        tone: simple.nq_pct >= 0 ? "up" : "down",
      });
    }
    if (simple.tech_avg_pct != null) {
      chips.push({
        key: "tech",
        label: "Tech basket",
        value: `${simple.tech_avg_pct >= 0 ? "+" : ""}${simple.tech_avg_pct.toFixed(2)}%`,
        tone: simple.tech_avg_pct >= 0 ? "up" : "down",
      });
    }
  }

  const bias = full?.bias;
  const hasTape = chips.length > 0 || Boolean(bias || simple?.message);
  if (!hasTape) return null;
  const minutes = full?.minutes_to_open;

  return (
    <div className="rounded-lg border border-violet-500/25 bg-violet-950/15 px-3 py-2 space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <Activity className="h-3.5 w-3.5 text-violet-400 shrink-0" />
        <span className="text-slate-300 font-medium">Pre-market</span>
        {bias && (
          <span
            className={clsx(
              "font-semibold",
              bias.includes("BULL") && "text-emerald-300",
              bias.includes("BEAR") && "text-red-300",
              bias === "NEUTRAL" && "text-slate-300"
            )}
          >
            {bias}
          </span>
        )}
        {full && (
          <span className="text-slate-400 font-mono tabular-nums">
            {full.composite_score >= 0 ? "+" : ""}
            {full.composite_score.toFixed(2)}
          </span>
        )}
        {minutes != null && minutes > 0 && <span className="text-slate-400">{minutes}m to open</span>}
        {full?.rotation_risk_premarket && full.rotation_risk_premarket !== "Low" && (
          <span className="text-amber-300">Rotation {full.rotation_risk_premarket}</span>
        )}
      </div>
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.slice(0, 8).map((c) => {
            const chipCls = clsx(
              "text-[11px] font-mono px-2 py-0.5 rounded border",
              c.tone === "up" && "border-emerald-500/35 text-emerald-200 bg-emerald-500/10",
              c.tone === "down" && "border-red-500/35 text-red-200 bg-red-500/10",
              c.tone === "flat" && "border-slate-600/60 text-slate-200 bg-slate-800/50"
            );
            const inner = (
              <>
                <span className="font-semibold">{c.label}</span>
                {c.value && <span className="opacity-90 ml-1">{c.value}</span>}
              </>
            );
            if (c.ticker && onTickerClick) {
              return (
                <button key={c.key} type="button" onClick={() => onTickerClick(c.ticker!)} className={chipCls}>
                  {inner}
                </button>
              );
            }
            return (
              <span key={c.key} className={chipCls}>
                {inner}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
