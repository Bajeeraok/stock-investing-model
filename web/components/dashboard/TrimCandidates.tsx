"use client";

import type { PortfolioHolding } from "@/app/page";
import { clsx } from "clsx";
import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { retailStatusClasses } from "@/lib/retailStatusStyles";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

const TRIM_GATE_LABEL: Record<string, string> = {
  extension: "Ext",
  tape: "Tape",
  ml_momentum: "ML",
  plan: "Plan",
};

function TrimGatePills({ holding }: { holding: PortfolioHolding }) {
  const gates = holding.trim_gates ?? [];
  if (!gates.length && holding.trim_gates_passed == null) return null;

  const passed = holding.trim_gates_passed ?? gates.filter((g) => g.pass).length;
  const total = holding.trim_gates_total ?? (gates.length || 4);
  const cleared = holding.trim_gate_cleared ?? (passed >= 2);

  return (
    <div className="flex flex-wrap items-center gap-1 mt-1">
      <span
        className={clsx(
          "text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border",
          cleared ? "border-emerald-500/40 text-emerald-300 bg-emerald-950/30" : "border-amber-500/40 text-amber-300 bg-amber-950/20"
        )}
        title={`Trim gates ${passed}/${total} · ${cleared ? "cleared for trim list" : "score trigger but gates pending"}`}
      >
        Trim {passed}/{total}
      </span>
      {gates.map((g) => (
        <span
          key={g.id}
          title={`${g.label}: ${g.detail}`}
          className={clsx(
            "inline-flex items-center gap-0.5 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border tabular-nums",
            retailStatusClasses(g.pass ? "cleared" : "blocked")
          )}
        >
          <span aria-hidden>{g.pass ? "✓" : "✕"}</span>
          {TRIM_GATE_LABEL[g.id] ?? g.label.slice(0, 4)}
        </span>
      ))}
    </div>
  );
}

export function TrimCandidates({
  items,
  onTickerClick,
}: {
  items: PortfolioHolding[];
  onTickerClick?: (ticker: string) => void;
}) {
  const sorted = [...items].sort((a, b) => (a.score ?? 0) - (b.score ?? 0));
  const [logged, setLogged] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const logTrim = async (ticker: string) => {
    const n = note.trim() || "Trim candidate — logged from dashboard";
    try {
      const url = API_BASE ? `${API_BASE}/api/behavior/trim-cooldown` : "/api/behavior/trim-cooldown";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, note: n }),
      });
      const json = await res.json();
      if (json.ok) {
        setLogged((prev) => ({ ...prev, [ticker]: json.until || "logged" }));
        setPending(null);
        setNote("");
      }
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
      <p className="text-xs text-slate-400 mb-3">
        Trim list requires score trigger plus ≥2/4 trim gates (extension, tape, ML/momentum, plan).
        Log a trim to start a re-add cooldown (default 14 days).
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {sorted.map((h) => (
          <div
            key={h.ticker}
            className="flex flex-col gap-2 p-3 rounded-lg bg-slate-900/80 border border-amber-500/20"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
                {onTickerClick ? (
                  <button
                    type="button"
                    onClick={() => onTickerClick(h.ticker)}
                    className="font-mono font-medium text-emerald-400 hover:underline cursor-pointer text-left"
                  >
                    {h.ticker}
                  </button>
                ) : (
                  <span className="font-mono font-medium">{h.ticker}</span>
                )}
              </div>
              <div className="text-right text-sm">
                <p className="text-amber-400">score {h.score?.toFixed(1)}</p>
                <p className="text-slate-400">{h.regime} • {h.suggestion}</p>
              </div>
            </div>
            {h.trim_detail && (
              <p className="text-[11px] text-slate-400 leading-snug">{h.trim_detail}</p>
            )}
            <TrimGatePills holding={h} />
            {logged[h.ticker] ? (
              <p className="text-xs text-emerald-400/90">Cooldown until {logged[h.ticker]}</p>
            ) : pending === h.ticker ? (
              <div className="space-y-1.5">
                <input
                  type="text"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Why trim? (optional)"
                  className="w-full px-2 py-1 rounded bg-slate-950 border border-slate-600 text-xs text-slate-200"
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => void logTrim(h.ticker)}
                    className="text-xs px-2 py-1 rounded bg-amber-600/80 hover:bg-amber-500 text-white"
                  >
                    Confirm
                  </button>
                  <button
                    type="button"
                    onClick={() => { setPending(null); setNote(""); }}
                    className="text-xs px-2 py-1 rounded border border-slate-600 text-slate-400"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setPending(h.ticker)}
                className="text-xs text-left text-amber-300/90 hover:text-amber-200 underline-offset-2 hover:underline"
              >
                Log trim + cooldown
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
