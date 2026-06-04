"use client";

import { useCallback, useEffect, useState } from "react";
import { BookOpen, Search } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export interface JournalEntry {
  ticker: string;
  action: string;
  note: string;
  at: string;
}

/** Phase D3 — searchable decision log (extends one-line journal). */
export function DecisionJournalPanel({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [ticker, setTicker] = useState("");
  const [expanded, setExpanded] = useState(defaultOpen);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (q.trim()) params.set("q", q.trim());
      if (ticker.trim()) params.set("ticker", ticker.trim().toUpperCase());
      const url = API_BASE
        ? `${API_BASE}/api/behavior/journal?${params}`
        : `/api/behavior/journal?${params}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setEntries(Array.isArray(j.entries) ? j.entries : []);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [q, ticker]);

  useEffect(() => {
    if (!expanded) return;
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [expanded, load]);

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/30 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left hover:bg-slate-800/50"
      >
        <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          <BookOpen className="h-4 w-4" />
          Decision log
        </span>
        <span className="text-[10px] text-slate-600">{expanded ? "Hide" : "Show"}</span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-slate-700/60">
          <div className="flex flex-wrap gap-2 pt-2">
            <div className="relative flex-1 min-w-[140px]">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
              <input
                type="search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search notes…"
                className="w-full pl-7 pr-2 py-1.5 text-xs rounded-md bg-slate-900 border border-slate-600 text-slate-200 placeholder-slate-600"
              />
            </div>
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="Ticker"
              className="w-20 py-1.5 px-2 text-xs font-mono rounded-md bg-slate-900 border border-slate-600 text-slate-200 uppercase"
            />
          </div>

          {loading && <p className="text-xs text-slate-500">Loading…</p>}
          {!loading && entries.length === 0 && (
            <p className="text-xs text-slate-500">No journal entries yet. Log a note when you add or trim.</p>
          )}
          <ul className="space-y-1.5 max-h-48 overflow-y-auto">
            {entries.map((e, i) => (
              <li
                key={`${e.at}-${e.ticker}-${i}`}
                className="text-xs rounded-md border border-slate-700/50 bg-slate-900/40 px-2 py-1.5"
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono font-semibold text-slate-200">{e.ticker}</span>
                  <span
                    className={
                      e.action === "trim"
                        ? "text-amber-400"
                        : e.action === "add"
                          ? "text-emerald-400"
                          : "text-slate-400"
                    }
                  >
                    {e.action}
                  </span>
                  <span className="text-slate-600 ml-auto font-mono text-[10px]">
                    {e.at ? e.at.slice(0, 10) : ""}
                  </span>
                </div>
                <p className="text-slate-400 mt-0.5 leading-snug">{e.note}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
