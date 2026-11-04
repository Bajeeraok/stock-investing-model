"use client";

import React, { useState } from "react";
import { clsx } from "clsx";
import { CheckCircle2, Circle, Lock } from "lucide-react";

export interface ReportCard {
  model_version: string;
  public: boolean;
  trading_days_scored: number;
  calls_scored: number;
  calls_changing_exposure: number;
  edge_vs_hold_20d: { mean: number | null; ci95: [number, number] | null; n: number };
  model_vs_spy_20d: { mean: number | null; ci95: [number, number] | null; n: number };
  directional_hit_rate: { calls: number; hit_pct: number | null; ci95: [number, number] | null };
  months: { month: string; days: number; edge_pct: number }[];
  publish_checks: { label: string; ok: boolean; detail: string }[];
  ready_to_publish: boolean;
  calls: {
    date: string;
    ticker: string;
    signal: string | null;
    entry_mode?: string | null;
    price_at_call: number | null;
    next_close: number | null;
    return_1d_pct: number | null;
    return_20d_pct: number | null;
    spy_20d_pct: number | null;
    right_20d: boolean | null;
  }[];
  weekly_draft: string | null;
  method: string;
}

const pct = (n: number | null | undefined, d = 2) => (n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(d)}%`);
const px = (n: number | null | undefined) => (n == null ? "—" : `$${n.toFixed(2)}`);
const tone = (n: number | null | undefined) => (n == null ? "text-slate-500" : n >= 0 ? "text-emerald-400" : "text-red-400");
const ci = (c: [number, number] | null) => (c ? ` (95% range ${c[0]}% to ${c[1]}%)` : "");

/** Private report card: what the model said vs what happened, plus the publish checklist. */
export function ReportCardPanel({ data }: { data?: ReportCard | null }) {
  const [showDraft, setShowDraft] = useState(false);
  if (!data) return <p className="text-[13px] text-slate-500">Report card appears after the next forward-tracking refresh.</p>;
  const met = data.publish_checks.filter((c) => c.ok).length;
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded border border-slate-600 px-2 py-0.5 text-[13px] text-slate-300">
          <Lock className="h-3 w-3" /> {data.public ? "Public" : "Private — not published"}
        </span>
        <span className="text-[13px] text-slate-400">Model {data.model_version}</span>
        <span className={clsx("text-[13px] font-semibold", data.ready_to_publish ? "text-emerald-400" : "text-amber-300")}>
          Publish checklist {met}/{data.publish_checks.length}
        </span>
      </div>
      <div className="grid gap-2 sm:grid-cols-3 text-[13px] tabular-nums">
        <div className="rounded border border-slate-700 px-2 py-1.5">
          <p className="text-slate-500">20-day edge vs holding (after costs)</p>
          <p className={clsx("text-base font-semibold", tone(data.edge_vs_hold_20d.mean))}>{pct(data.edge_vs_hold_20d.mean, 3)}</p>
          <p className="text-slate-500">{data.edge_vs_hold_20d.n} days{ci(data.edge_vs_hold_20d.ci95)}</p>
        </div>
        <div className="rounded border border-slate-700 px-2 py-1.5">
          <p className="text-slate-500">20-day model vs SPY</p>
          <p className={clsx("text-base font-semibold", tone(data.model_vs_spy_20d.mean))}>{pct(data.model_vs_spy_20d.mean)}</p>
          <p className="text-slate-500">{data.model_vs_spy_20d.n} days{ci(data.model_vs_spy_20d.ci95)}</p>
        </div>
        <div className="rounded border border-slate-700 px-2 py-1.5">
          <p className="text-slate-500">Add/trim calls right at 20 days</p>
          <p className="text-base font-semibold text-slate-200">
            {data.directional_hit_rate.hit_pct != null ? `${data.directional_hit_rate.hit_pct}%` : "—"}
          </p>
          <p className="text-slate-500">n={data.directional_hit_rate.calls}{ci(data.directional_hit_rate.ci95)}</p>
        </div>
      </div>
      <div className="rounded border border-slate-700 px-3 py-2">
        <p className="text-[13px] text-slate-400 mb-1">Before publishing</p>
        <ul className="space-y-1">
          {data.publish_checks.map((c) => (
            <li key={c.label} className="flex items-start gap-2 text-[13px]">
              {c.ok ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 mt-0.5" /> : <Circle className="h-3.5 w-3.5 text-slate-500 mt-0.5" />}
              <span className="text-slate-200">{c.label}</span>
              <span className="ml-auto text-slate-500 tabular-nums">{c.detail}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="overflow-x-auto">
        <p className="text-[13px] text-slate-400 mb-1">What we said vs what happened (latest calls)</p>
        <table className="w-full text-[13px] min-w-[640px] tabular-nums">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-700">
              <th className="py-1 pr-2 font-medium">Date</th>
              <th className="py-1 pr-2 font-medium">Ticker</th>
              <th className="py-1 pr-2 font-medium">Call</th>
              <th className="py-1 pr-2 font-medium">Close that day</th>
              <th className="py-1 pr-2 font-medium">Next day close</th>
              <th className="py-1 pr-2 font-medium">1 day</th>
              <th className="py-1 pr-2 font-medium">20 days</th>
              <th className="py-1 pr-2 font-medium">SPY 20d</th>
              <th className="py-1 font-medium">Right?</th>
            </tr>
          </thead>
          <tbody>
            {data.calls.slice(0, 30).map((c) => (
              <tr key={`${c.date}-${c.ticker}`} className="border-b border-slate-800 text-slate-300">
                <td className="py-1 pr-2 font-mono">{c.date}</td>
                <td className="py-1 pr-2">{c.ticker}</td>
                <td className="py-1 pr-2">{c.signal ?? "—"}</td>
                <td className="py-1 pr-2">{px(c.price_at_call)}</td>
                <td className="py-1 pr-2">{c.next_close == null ? "pending" : px(c.next_close)}</td>
                <td className={clsx("py-1 pr-2", tone(c.return_1d_pct))}>{pct(c.return_1d_pct)}</td>
                <td className={clsx("py-1 pr-2", tone(c.return_20d_pct))}>{c.return_20d_pct == null ? "pending" : pct(c.return_20d_pct)}</td>
                <td className="py-1 pr-2">{pct(c.spy_20d_pct)}</td>
                <td className="py-1">
                  {c.right_20d == null ? <span className="text-slate-600">—</span> : c.right_20d ? <span className="text-emerald-400">✓</span> : <span className="text-red-400">✗</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.weekly_draft && (
        <div>
          <button type="button" onClick={() => setShowDraft((s) => !s)} className="text-[13px] text-sky-400 hover:underline">
            {showDraft ? "Hide" : "Show"} weekly post draft
          </button>
          {showDraft && (
            <pre className="mt-1 whitespace-pre-wrap rounded border border-slate-700 bg-slate-900/60 p-2 text-[13px] text-slate-300">{data.weekly_draft}</pre>
          )}
        </div>
      )}
      <p className="text-[13px] text-slate-500">{data.method} HOLD calls count as holding, so they add zero edge.</p>
    </div>
  );
}
