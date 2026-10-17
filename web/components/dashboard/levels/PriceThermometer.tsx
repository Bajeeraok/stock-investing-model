"use client";

import { useMemo, useState } from "react";
import { clsx } from "clsx";

export interface ThermometerLevel {
  id: string;
  label: string;
  value: number;
  /** Band extent — if present, this is a zone, not a point. */
  band?: { low: number; high: number };
  color: string;           // Tailwind text/bg color key e.g. "emerald" | "violet" | "amber" | "red"
  role?: "tier" | "anchor" | "current" | "structural";
  description?: string;
  active?: boolean;        // highlight as current zone
  target?: boolean;        // next actionable zone
  badge?: string;
}

const COLOR_MAP: Record<string, { band: string; dot: string; border: string; text: string; glow: string }> = {
  current:   { band: "bg-white/15",        dot: "bg-white shadow-[0_0_6px_rgba(255,255,255,0.8)]",  border: "border-white/40",       text: "text-td-text",        glow: "shadow-[0_0_8px_rgba(255,255,255,0.3)]" },
  emerald:   { band: "bg-td-accent/20",   dot: "bg-td-accent shadow-[0_0_6px_rgba(0,200,150,0.6)]", border: "border-td-accent/50",  text: "text-td-accent",  glow: "shadow-[0_0_8px_rgba(0,200,150,0.2)]" },
  violet:    { band: "bg-td-owner/20",    dot: "bg-td-owner shadow-[0_0_5px_rgba(139,92,246,0.5)]",  border: "border-td-owner/50",   text: "text-td-owner",   glow: "" },
  amber:     { band: "bg-td-warn/15",     dot: "bg-td-warn",       border: "border-td-warn/45",   text: "text-td-warn",    glow: "" },
  cyan:      { band: "bg-td-info/15",      dot: "bg-td-info",        border: "border-td-info/40",    text: "text-td-info",     glow: "" },
  red:       { band: "bg-td-crit/15",       dot: "bg-td-crit",         border: "border-td-crit/40",     text: "text-td-crit",      glow: "" },
  slate:     { band: "bg-td-surface2/30",     dot: "bg-td-line",       border: "border-td-line/60",   text: "text-td-muted",    glow: "" },
  orange:    { band: "bg-td-warn/15",    dot: "bg-td-warn",      border: "border-td-warn/40",  text: "text-td-warn",   glow: "" },
};

function clr(color: string, key: keyof (typeof COLOR_MAP)[string]): string {
  return (COLOR_MAP[color] ?? COLOR_MAP.slate)[key];
}

function pct(val: number, min: number, span: number): number {
  return Math.max(0, Math.min(100, ((val - min) / span) * 100));
}

export function PriceThermometer({
  levels,
  currentPrice,
  structuralStop,
  className,
}: {
  levels: ThermometerLevel[];
  currentPrice: number;
  structuralStop?: number | null;
  className?: string;
}) {
  const [hovered, setHovered] = useState<string | null>(null);

  const allValues = useMemo(() => {
    const pts: number[] = [currentPrice];
    for (const l of levels) {
      if (l.value > 0) pts.push(l.value);
      if (l.band) { pts.push(l.band.low, l.band.high); }
    }
    if (structuralStop && structuralStop > 0) pts.push(structuralStop);
    return pts;
  }, [levels, currentPrice, structuralStop]);

  const rawMin = Math.min(...allValues);
  const rawMax = Math.max(...allValues);
  const padding = (rawMax - rawMin) * 0.07 || rawMin * 0.03 || 1;
  const min = rawMin - padding;
  const max = rawMax + padding;
  const span = max - min;

  const nowPct = pct(currentPrice, min, span);

  return (
    <div className={clsx("flex gap-4 select-none", className)}>
      {/* ── Vertical bar ─────────────────────────────── */}
      <div className="relative w-8 shrink-0 rounded-full bg-td-surface2/80 border border-td-line/50 overflow-visible" style={{ minHeight: 320 }}>
        {/* Grid lines */}
        {[25, 50, 75].map(p => (
          <div key={p} className="absolute w-full border-b border-td-line/30" style={{ bottom: `${p}%` }} />
        ))}

        {/* Tier bands */}
        {levels.filter(l => l.band && l.role === "tier").map(l => {
          const lo = pct(l.band!.low, min, span);
          const hi = pct(l.band!.high, min, span);
          const isHovered = hovered === l.id;
          const isActive = l.active;
          const isTarget = l.target;
          const dim = hovered !== null && !isHovered;
          return (
            <div
              key={l.id}
              className={clsx(
                "absolute inset-x-0 transition-all duration-200",
                clr(l.color, "band"),
                isActive && "ring-1 ring-inset ring-td-accent/40",
                dim && "opacity-20",
              )}
              style={{ bottom: `${lo}%`, height: `${Math.max(hi - lo, 1)}%` }}
              onMouseEnter={() => setHovered(l.id)}
              onMouseLeave={() => setHovered(null)}
            />
          );
        })}

        {/* Structural stop */}
        {structuralStop != null && structuralStop > 0 && (
          <div
            className="absolute inset-x-0 flex items-center"
            style={{ bottom: `${pct(structuralStop, min, span)}%` }}
          >
            <div className="w-full border-b border-dashed border-td-crit/40" />
          </div>
        )}

        {/* Anchor dots for point levels */}
        {levels.filter(l => !l.band && l.role !== "current").map(l => {
          const dim = hovered !== null && hovered !== l.id;
          return (
            <div
              key={l.id}
              className={clsx("absolute left-1/2 -translate-x-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full border-2 border-td-bg transition-all duration-150",
                clr(l.color, "dot"),
                dim && "opacity-25",
              )}
              style={{ bottom: `${pct(l.value, min, span)}%` }}
              onMouseEnter={() => setHovered(l.id)}
              onMouseLeave={() => setHovered(null)}
            />
          );
        })}

        {/* Current price marker — floating needle */}
        <div
          className="absolute inset-x-0 z-10 flex items-center transition-all duration-300"
          style={{ bottom: `${nowPct}%` }}
        >
          <div className="w-full h-px bg-white/80" />
          <div className="absolute right-0 w-0 h-0 border-l-[6px] border-l-transparent border-r-0 border-t-[4px] border-t-white/80 border-b-[4px] border-b-white/80 -translate-y-px" />
        </div>
      </div>

      {/* ── Label column ───────────────────────────────── */}
      <div className="relative flex-1" style={{ minHeight: 320 }}>
        {/* Current price label */}
        <div
          className="absolute left-0 flex items-center gap-2 -translate-y-1/2 transition-all duration-300"
          style={{ bottom: `${nowPct}%` }}
        >
          <span className="text-[11px] font-mono font-bold text-td-text tabular-nums">${currentPrice.toFixed(2)}</span>
          <span className="text-[9px] uppercase tracking-wider text-td-muted font-semibold">Now</span>
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-50" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-white/80" />
          </span>
        </div>

        {/* Per-level labels */}
        {levels.filter(l => l.role !== "current").map(l => {
          const position = l.band ? (pct(l.band.low, min, span) + pct(l.band.high, min, span)) / 2 : pct(l.value, min, span);
          const isHovered = hovered === l.id;
          const dim = hovered !== null && !isHovered;
          return (
            <div
              key={l.id}
              className={clsx(
                "absolute left-0 flex items-center gap-1.5 -translate-y-1/2 cursor-default transition-all duration-200 group",
                dim && "opacity-30",
              )}
              style={{ bottom: `${position}%` }}
              onMouseEnter={() => setHovered(l.id)}
              onMouseLeave={() => setHovered(null)}
            >
              {l.band ? (
                <span className={clsx("text-[10px] font-mono text-right tabular-nums", clr(l.color, "text"))}>
                  ${l.band.low.toFixed(0)}–${l.band.high.toFixed(0)}
                </span>
              ) : (
                <span className={clsx("text-[10px] font-mono tabular-nums", clr(l.color, "text"))}>
                  ${l.value.toFixed(2)}
                </span>
              )}
              <span className={clsx("text-[9px] text-td-muted font-medium", isHovered && "text-td-text")}>
                {l.label}
              </span>
              {l.badge && (
                <span className={clsx(
                  "text-[8px] uppercase font-black tracking-wider px-1.5 py-0.5 rounded-full border",
                  l.active
                    ? "border-td-accent/50 bg-td-accent/15 text-td-accent"
                    : l.target
                      ? "border-td-warn/40 bg-td-warn/10 text-td-warn"
                      : "border-td-line text-td-muted",
                )}>
                  {l.badge}
                </span>
              )}
            </div>
          );
        })}

        {structuralStop != null && structuralStop > 0 && (
          <div
            className="absolute left-0 flex items-center gap-1.5 -translate-y-1/2 opacity-50"
            style={{ bottom: `${pct(structuralStop, min, span)}%` }}
          >
            <span className="text-[9px] font-mono text-td-crit/70 tabular-nums">${structuralStop.toFixed(2)}</span>
            <span className="text-[8px] text-td-crit/50">Structural stop</span>
          </div>
        )}
      </div>
    </div>
  );
}
