"use client";

import { BarChart3, ClipboardCheck, TrendingUp } from "lucide-react";

const CARDS = [
  {
    id: "A",
    title: "Historical dip edge",
    subtitle: "Backtest buckets",
    icon: BarChart3,
    color: "text-sky-400",
    border: "border-sky-800/50",
    bg: "bg-sky-950/30",
    body:
      "Did high-score (dip-mapped) buckets beat low buckets in past windows? Uses causal bar scores; optional live regime + MRO parity. Not a single pass/fail for today.",
    sectionIds: ["analysis-backtest"],
  },
  {
    id: "B",
    title: "Live gate clearance",
    subtitle: "Model audit",
    icon: ClipboardCheck,
    color: "text-amber-400",
    border: "border-amber-800/50",
    bg: "bg-amber-950/25",
    body:
      "At each EOD snapshot: did retail + ML + confidence gates pass (GO)? Frozen gate state explains why TACTICAL BUY can still be no_go. Separate from historical bucket edge.",
    sectionIds: ["analysis-model-audit"],
  },
  {
    id: "C",
    title: "Paper / live forward outcomes",
    subtitle: "Forward + paper",
    icon: TrendingUp,
    color: "text-emerald-400",
    border: "border-emerald-800/50",
    bg: "bg-emerald-950/25",
    body:
      "What happened after signals logged: 7d/21d path, partial outcomes until enough EOD snapshots, paper P&L vs SPY. Drift vs backtest is expected — different question.",
    sectionIds: ["analysis-forward", "analysis-paper", "analysis-track-record"],
  },
] as const;

export function TrackRecordFramework() {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-4 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-slate-200">Track record — three questions</h3>
        <p className="text-xs text-slate-500 mt-1 leading-relaxed">
          Do not collapse (A), (B), and (C) into one score. Each panel answers a different decision-support question.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {CARDS.map((c) => {
          const Icon = c.icon;
          return (
            <div
              key={c.id}
              className={`rounded-lg border p-3 ${c.border} ${c.bg}`}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span className={`text-xs font-bold font-mono ${c.color}`}>({c.id})</span>
                <Icon className={`h-4 w-4 ${c.color}`} />
                <span className="text-sm font-medium text-slate-200">{c.title}</span>
              </div>
              <p className={`text-[10px] uppercase tracking-wide ${c.color} opacity-80 mb-1`}>{c.subtitle}</p>
              <p className="text-xs text-slate-400 leading-relaxed">{c.body}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
