"use client";

/**
 * Levels tab — chart-first entry band overlay.
 * Paints ST/MT/LT entry zones as shaded horizontal bands plus spot, stop,
 * and target lines — TradingView position-tool style. Price axis is shared
 * so zones read against each other; no OHLCV needed.
 */
import React from "react";
import clsx from "clsx";

type Band = { label: string; low?: number | null; high?: number | null; kind: "entry" | "tier" | "stop" | "target" | "fv" };
type Props = {
  currentPrice?: number | null;
  bands: Band[];
  className?: string;
};

const KIND_STYLE: Record<Band["kind"], { fill: string; stroke: string; text: string }> = {
  entry: { fill: "rgba(16,185,129,0.18)", stroke: "#10B981", text: "text-emerald-300" },
  tier: { fill: "rgba(52,211,153,0.10)", stroke: "#34D399", text: "text-emerald-400/80" },
  stop: { fill: "rgba(244,63,94,0.15)", stroke: "#F43F5E", text: "text-rose-300" },
  target: { fill: "rgba(34,211,238,0.12)", stroke: "#22D3EE", text: "text-cyan-300" },
  fv: { fill: "rgba(168,85,247,0.10)", stroke: "#A855F7", text: "text-purple-300" },
};

export function EntryBandsChart({ currentPrice, bands, className }: Props) {
  const vals: number[] = [];
  for (const b of bands) {
    if (b.low != null && b.low > 0) vals.push(b.low);
    if (b.high != null && b.high > 0) vals.push(b.high);
  }
  if (currentPrice != null && currentPrice > 0) vals.push(currentPrice);
  if (vals.length === 0) return null;

  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.12 || hi * 0.05;
  lo -= pad; hi += pad;
  const range = hi - lo;
  const y = (p: number) => 100 - ((p - lo) / range) * 100; // svg % (0 = top)

  return (
    <div className={clsx("rounded-xl border border-td-line bg-td-surface/60 p-3", className)}>
      <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-td-muted mb-2">
        Entry levels vs spot
      </p>
      <div className="relative w-full" style={{ aspectRatio: "3 / 2" }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
          {bands.map((b, i) => {
            const s = KIND_STYLE[b.kind];
            if (b.low != null && b.high != null && b.high > b.low) {
              return (
                <rect key={i} x={8} width={80} y={y(b.high)} height={y(b.low) - y(b.high)}
                  fill={s.fill} stroke={s.stroke} strokeWidth={0.25} rx={0.4} />
              );
            }
            const p = b.low ?? b.high;
            if (p == null) return null;
            return <line key={i} x1={8} x2={88} y1={y(p)} y2={y(p)} stroke={s.stroke}
              strokeWidth={0.4} strokeDasharray={b.kind === "stop" ? "1.5 1" : "2.5 1.5"} />;
          })}
          {currentPrice != null && currentPrice > 0 && (
            <line x1={4} x2={96} y1={y(currentPrice)} y2={y(currentPrice)}
              stroke="#F59E0B" strokeWidth={0.7} />
          )}
        </svg>
        {/* Labels — HTML overlay for crisp text */}
        {bands.map((b, i) => {
          const s = KIND_STYLE[b.kind];
          const pTop = b.high != null ? y(b.high) : y(b.low ?? 0);
          return (
            <span key={i}
              className={clsx("absolute right-1 text-[10px] font-mono leading-none", s.text)}
              style={{ top: `${pTop}%`, transform: "translateY(-110%)" }}>
              {b.label} {b.low != null && b.high != null ? `$${b.low.toFixed(0)}–$${b.high.toFixed(0)}` : `$${(b.low ?? b.high)!.toFixed(0)}`}
            </span>
          );
        })}
        {currentPrice != null && currentPrice > 0 && (
          <span className="absolute left-1 text-[10px] font-mono font-bold leading-none text-amber-300"
            style={{ top: `${y(currentPrice)}%`, transform: "translateY(-110%)" }}>
            SPOT ${currentPrice.toFixed(2)}
          </span>
        )}
      </div>
    </div>
  );
}

/** Build bands[] from a horizons payload (short/medium/long entry zones + stops/targets + FV). */
export function bandsFromHorizons(horizons: any, currentPrice?: number | null): Band[] {
  const out: Band[] = [];
  const H = horizons || {};
  const push = (label: string, ez: any, kind: Band["kind"]) => {
    const lo = ez?.low ?? ez?.[0], hi = ez?.high ?? ez?.[1];
    if (lo != null || hi != null) out.push({ label, low: lo, high: hi ?? lo, kind });
  };
  push("ST zone", H.short?.entry_zone, "entry");
  push("MT zone", H.medium?.entry_zone, "entry");
  const lt = H.long || {};
  push("T1 MA200", lt.entry_zone, "tier");
  for (const t of lt.entry_tiers?.tiers || []) {
    push(t.id || "tier", { low: t.low, high: t.high }, t.id === "T2" ? "entry" : "tier");
  }
  for (const [k, h] of [["ST stop", H.short], ["MT stop", H.medium]] as const) {
    if (h?.stop_loss) out.push({ label: k, low: h.stop_loss, high: null, kind: "stop" });
  }
  for (const [k, h] of [["ST tgt", H.short], ["MT tgt", H.medium], ["LT tgt", H.long]] as const) {
    if (h?.target) out.push({ label: k, low: h.target, high: null, kind: "target" });
  }
  const fv = H.long?.fair_value ?? H.fair_value;
  if (fv) out.push({ label: "FV", low: fv, high: null, kind: "fv" });
  return out;
}
