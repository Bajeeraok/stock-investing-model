"use client";

import { AlertTriangle, Info } from "lucide-react";

export function GuidelinesBanner({ guidelines }: { guidelines: { text: string; type: "caution" | "info" | "risk" }[] }) {
  if (!guidelines || guidelines.length === 0) return null;
  return (
    <div className="space-y-2">
      {guidelines.map((g, i) => (
        <div
          key={i}
          className={`flex items-start gap-2 px-4 py-2 rounded-lg border ${
            g.type === "risk"
              ? "border-red-500/30 bg-red-500/5"
              : g.type === "caution"
              ? "border-amber-500/30 bg-amber-500/5"
              : "border-slate-600 bg-slate-800/50"
          }`}
        >
          {g.type === "risk" ? (
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
          ) : (
            <Info className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          )}
          <p className="text-sm text-slate-200">{g.text}</p>
        </div>
      ))}
    </div>
  );
}
