"use client";

/** HMM / regime bull % with remainder as transitional (when bear/trans not split in API). */
export function RegimeBar({ bullPct }: { bullPct: number | null | undefined }) {
  const bull = Math.max(0, Math.min(100, bullPct ?? 0));
  const transitional = Math.max(0, 100 - bull);

  return (
    <div className="space-y-1.5">
      <div className="flex h-2 rounded-full overflow-hidden bg-slate-800">
        {bull > 0.5 && (
          <div className="bg-teal-400 transition-all" style={{ width: `${bull}%` }} title={`Bull ${bull.toFixed(0)}%`} />
        )}
        {transitional > 0.5 && (
          <div
            className="bg-amber-400/90 transition-all"
            style={{ width: `${transitional}%` }}
            title={`Non-bull ${transitional.toFixed(0)}%`}
          />
        )}
      </div>
      <div className="flex justify-between text-[10px] font-mono tabular-nums">
        <span className="text-teal-400">Bull {bull.toFixed(0)}%</span>
        <span className="text-amber-400/90">Trans / other {transitional.toFixed(0)}%</span>
      </div>
    </div>
  );
}
