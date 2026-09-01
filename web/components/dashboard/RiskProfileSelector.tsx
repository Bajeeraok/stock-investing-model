"use client";

import { useState } from "react";
import { clsx } from "clsx";
import { apiUrl } from "@/lib/apiBase";

export type RiskProfile = "conservative" | "moderate" | "aggressive";

const PROFILES: { id: RiskProfile; label: string; hint: string }[] = [
  { id: "conservative", label: "Conservative", hint: "Max 15% per position — tighter trim / add thresholds" },
  { id: "moderate", label: "Moderate", hint: "Max 20% per position — balanced trim / add thresholds" },
  { id: "aggressive", label: "Aggressive", hint: "Max 25% per position — looser trim / add thresholds" },
];

/**
 * Drives allocation_recommendations() (trim/add + max position %) and the Tier1
 * Kelly position-sizing engine together — one persisted, server-side setting (no
 * per-user accounts yet, so this is one site-wide value, not per-browser).
 */
export function RiskProfileSelector({
  value,
  onChanged,
}: {
  value?: RiskProfile | null;
  onChanged?: () => void;
}) {
  const [pending, setPending] = useState<RiskProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const current = pending ?? value ?? "moderate";

  const setProfile = async (profile: RiskProfile) => {
    if (profile === current) return;
    setError(null);
    setPending(profile);
    try {
      const res = await fetch(apiUrl("/api/portfolio/risk-profile"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile }),
      });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.detail || "Could not update risk profile");
      }
      onChanged?.();
    } catch (e) {
      setPending(null);
      setError(e instanceof Error ? e.message : "Could not update risk profile");
    }
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Risk profile</span>
        <div className="flex rounded-lg border border-slate-700 overflow-hidden">
          {PROFILES.map((p) => (
            <button
              key={p.id}
              type="button"
              title={p.hint}
              onClick={() => setProfile(p.id)}
              className={clsx(
                "px-3 py-1.5 text-xs font-medium transition-colors touch-manipulation",
                current === p.id
                  ? "bg-emerald-600/80 text-white"
                  : "bg-slate-800/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800",
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
        <span className="text-[11px] text-slate-500">
          {PROFILES.find((p) => p.id === current)?.hint}
        </span>
      </div>
      {error && <p className="text-[11px] text-red-400">{error}</p>}
    </div>
  );
}
