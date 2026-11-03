"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "@/lib/apiBase";

interface Finding {
  ticker: string;
  rule: string;
  severity: "error" | "warn" | "info";
  message: string;
}
interface RuleRow {
  rule: string;
  severity: Finding["severity"];
  count: number;
  tickers: string[];
}
interface Report {
  generated_at: string;
  n_tickers: number;
  counts: Record<string, number>;
  by_rule: RuleRow[];
  findings: Finding[];
  duration_s?: number;
}

const SEV_CLASS: Record<string, string> = {
  error: "text-red-400",
  warn: "text-amber-300",
  info: "text-slate-500",
};

export function TickerAuditPanel() {
  const [report, setReport] = useState<Report | null>(null);
  const [running, setRunning] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    fetch(apiUrl("/api/audit/ticker-consistency"))
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        setReport(j?.report ?? null);
        setRunning(Boolean(j?.running));
      })
      .catch(() => undefined)
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) return <p className="text-sm text-slate-500">Loading ticker-page checks…</p>;
  if (!report) {
    return (
      <p className="text-sm text-slate-500">
        {running ? "Checker is running now — " : "No report yet — "}it runs automatically after each 8 PM ET EOD job.
      </p>
    );
  }

  return (
    <div className="space-y-2 text-sm">
      <p className="text-xs text-slate-500 leading-relaxed">
        Rule checks on every ticker page (all 3 modes): numbers that should match across sections, stops below
        price, bands at or below spot, fresh data. Run {report.generated_at.replace("T", " ").slice(0, 16)} UTC on{" "}
        {report.n_tickers} tickers.
      </p>
      <p className="text-slate-300">
        <span className="text-red-400">{report.counts.error ?? 0} errors</span> ·{" "}
        <span className="text-amber-300">{report.counts.warn ?? 0} warnings</span> ·{" "}
        <span className="text-slate-500">{report.counts.info ?? 0} notes</span>
      </p>
      {report.by_rule.length === 0 && <p className="text-emerald-400">All checks passed.</p>}
      <ul className="space-y-1">
        {report.by_rule.map((r) => (
          <li key={r.rule}>
            <button
              type="button"
              onClick={() => setOpen(open === r.rule ? null : r.rule)}
              className="w-full text-left flex flex-wrap items-baseline gap-x-2"
            >
              <span className={`font-mono text-xs ${SEV_CLASS[r.severity]}`}>{r.rule}</span>
              <span className="text-xs text-slate-400">
                {r.count}× · {r.tickers.slice(0, 8).join(", ")}
                {r.tickers.length > 8 ? ` +${r.tickers.length - 8}` : ""}
              </span>
            </button>
            {open === r.rule && (
              <ul className="mt-1 ml-3 space-y-0.5">
                {report.findings
                  .filter((f) => f.rule === r.rule)
                  .map((f, i) => (
                    <li key={i} className="text-xs text-slate-400">
                      <span className="font-mono text-slate-200">{f.ticker}</span> — {f.message}
                    </li>
                  ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
