"use client";

import { clsx } from "clsx";

/**
 * Circular SVG gauge for HMM / market regime breakdown.
 * Accepts raw percentages (0-100). Renders a semi-arc split into
 * Bear / Trans / Bull segments with a needle at the bull position.
 */
export interface RegimeGaugeProps {
  bullPct: number;
  transPct: number;
  bearPct: number;
  /** Optional label overrides */
  labels?: { bull?: string; trans?: string; bear?: string };
  size?: number;
  className?: string;
}

function polarToXY(cx: number, cy: number, r: number, angleDeg: number): [number, number] {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  if (Math.abs(endDeg - startDeg) >= 360) {
    return `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx - 0.001} ${cy - r} Z`;
  }
  const [sx, sy] = polarToXY(cx, cy, r, startDeg);
  const [ex, ey] = polarToXY(cx, cy, r, endDeg);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${sx} ${sy} A ${r} ${r} 0 ${large} 1 ${ex} ${ey}`;
}

export function RegimeGauge({
  bullPct,
  transPct,
  bearPct,
  labels,
  size = 140,
  className,
}: RegimeGaugeProps) {
  const total = (bullPct + transPct + bearPct) || 100;
  const bPct = (bearPct / total) * 100;
  const tPct = (transPct / total) * 100;
  const bulPct = (bullPct / total) * 100;

  // Full 270° arc (−135° to +135°), starting at bear
  const START = -135;
  const TOTAL_DEG = 270;

  const bearEnd = START + (bPct / 100) * TOTAL_DEG;
  const transEnd = bearEnd + (tPct / 100) * TOTAL_DEG;
  const bullEnd = transEnd + (bulPct / 100) * TOTAL_DEG;

  // Needle at bull position center
  const needleAngle = transEnd + (bulPct / 100) * TOTAL_DEG * 0.5;

  const cx = size / 2;
  const cy = size * 0.58;
  const r = size * 0.36;
  const strokeW = size * 0.085;

  const [nx, ny] = polarToXY(cx, cy, r * 0.62, needleAngle);

  const dominant = bulPct >= 50 ? "bull" : bPct >= 50 ? "bear" : "trans";

  return (
    <div className={clsx("flex flex-col items-center", className)}>
      <svg width={size} height={size * 0.72} viewBox={`0 0 ${size} ${size * 0.72}`} role="img" aria-label="Regime gauge">
        {/* Background track */}
        <path
          d={arcPath(cx, cy, r, START, START + TOTAL_DEG)}
          fill="none"
          stroke="#1e293b"
          strokeWidth={strokeW}
          strokeLinecap="round"
        />
        {/* Bear segment */}
        {bPct > 0.5 && (
          <path
            d={arcPath(cx, cy, r, START, bearEnd)}
            fill="none"
            stroke="#FF6B6B"
            strokeWidth={strokeW}
            strokeLinecap={bPct < 5 ? "round" : "butt"}
            opacity={dominant === "bear" ? 1 : 0.55}
          />
        )}
        {/* Transition segment */}
        {tPct > 0.5 && (
          <path
            d={arcPath(cx, cy, r, bearEnd, transEnd)}
            fill="none"
            stroke="#F59E0B"
            strokeWidth={strokeW}
            opacity={dominant === "trans" ? 1 : 0.55}
          />
        )}
        {/* Bull segment */}
        {bulPct > 0.5 && (
          <path
            d={arcPath(cx, cy, r, transEnd, bullEnd)}
            fill="none"
            stroke="#00C896"
            strokeWidth={strokeW}
            strokeLinecap={bulPct < 5 ? "round" : "butt"}
            opacity={dominant === "bull" ? 1 : 0.55}
          />
        )}
        {/* Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={nx}
          y2={ny}
          stroke="white"
          strokeWidth={1.5}
          strokeLinecap="round"
          opacity={0.85}
        />
        <circle cx={cx} cy={cy} r={size * 0.025} fill="#64748b" />
      </svg>

      {/* Center labels */}
      <div className="-mt-3 flex flex-col items-center gap-0.5">
        <span className={clsx(
          "text-[11px] font-black uppercase tracking-wider",
          dominant === "bull" ? "text-[#00C896]" : dominant === "bear" ? "text-[#FF6B6B]" : "text-amber-400",
        )}>
          {dominant === "bull" ? (labels?.bull ?? "Bull") : dominant === "bear" ? (labels?.bear ?? "Bear") : (labels?.trans ?? "Trans")}
        </span>
      </div>

      {/* Pct row */}
      <div className="flex gap-3 mt-1.5">
        {[
          { label: labels?.bear ?? "Bear", pct: bearPct, color: "text-[#FF6B6B]" },
          { label: labels?.trans ?? "Trans", pct: transPct, color: "text-amber-400" },
          { label: labels?.bull ?? "Bull", pct: bullPct, color: "text-[#00C896]" },
        ].map(item => (
          <div key={item.label} className="flex flex-col items-center gap-0">
            <span className={clsx("text-[11px] font-mono font-bold tabular-nums", item.color)}>
              {item.pct.toFixed(0)}%
            </span>
            <span className="text-[8px] uppercase text-slate-500">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
