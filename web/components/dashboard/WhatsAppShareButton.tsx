"use client";

import { useState } from "react";
import { Check, Share2 } from "lucide-react";
import { apiUrl } from "@/lib/apiBase";
import { formatWhatsAppTeaser, type PulseTrack } from "@/lib/whatsappTeaser";
import type { InvestorDecisionSummary } from "./InvestorDecisionSummary";
import type { DayRangePayload } from "./tickerDetail/DayRangeCard";

interface Props {
  ticker: string;
  summary: InvestorDecisionSummary;
  currentPrice: number;
  dayRange?: DayRangePayload | null;
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}

/** Copies a short monospace teaser (signal, swing/long-term levels, today's range, SPY/QQQ record) for WhatsApp. */
export function WhatsAppShareButton({ ticker, summary, currentPrice, dayRange }: Props) {
  const [copied, setCopied] = useState(false);

  const handle = async () => {
    let track: PulseTrack | null = null;
    try {
      const r = await fetch(apiUrl("/api/market-pulse"), { cache: "no-store" });
      if (r.ok) track = (await r.json())?.scorecard?.summary ?? null;
    } catch {
      /* teaser still works without the track line */
    }
    await copy(formatWhatsAppTeaser(ticker, summary, currentPrice, dayRange, track));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      type="button"
      onClick={handle}
      className="inline-flex items-center gap-1.5 text-[13px] px-2.5 py-1.5 rounded-lg border border-slate-600 bg-slate-800/60 text-slate-300 hover:border-emerald-500/40 hover:text-emerald-300 transition-colors"
      title="Copy a short summary formatted for WhatsApp"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Share2 className="h-3.5 w-3.5" />}
      {copied ? "Copied" : "Copy for WhatsApp"}
    </button>
  );
}
