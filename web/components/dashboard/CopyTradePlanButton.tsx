"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";
import type { DecisionMode } from "@/lib/decisionMode";
import { formatTradePlanForClipboard } from "@/lib/copyTradePlan";
import type { InvestorDecisionSummary } from "./InvestorDecisionSummary";

interface Props {
  ticker: string;
  summary: InvestorDecisionSummary;
  currentPrice: number;
  mode: DecisionMode;
  riskPct?: number;
  stopPct?: number;
}

/** Phase D4 — copy trade plan for manual broker entry. */
export function CopyTradePlanButton({ ticker, summary, currentPrice, mode, riskPct, stopPct }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const text = formatTradePlanForClipboard(ticker, summary, currentPrice, mode, riskPct, stopPct);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* fallback */
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-slate-600 bg-slate-800/60 text-slate-300 hover:border-emerald-500/40 hover:text-emerald-300 transition-colors"
      title="Copy action, entry, stop, and target for manual broker entry"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? "Copied" : "Copy trade plan"}
    </button>
  );
}
