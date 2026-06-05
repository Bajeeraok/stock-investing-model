"use client";

import { clsx } from "clsx";

/** SVG sparkline — no Recharts dependency for table cells. */
export function MiniPriceSparkline({
  closes,
  width = 72,
  height = 24,
  className,
}: {
  closes: number[];
  width?: number;
  height?: number;
  className?: string;
}) {
  if (!closes || closes.length < 2) return null;
  const vals = closes.filter((v) => v != null && !Number.isNaN(v));
  if (vals.length < 2) return null;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || max * 0.01 || 1;
  const up = vals[vals.length - 1] >= vals[0];
  const points = vals
    .map((v, i) => {
      const x = (i / (vals.length - 1)) * width;
      const y = height - ((v - min) / range) * (height - 2) - 1;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={clsx("shrink-0", className)}
      aria-hidden
    >
      <polyline
        fill="none"
        stroke={up ? "rgb(52,211,153)" : "rgb(248,113,113)"}
        strokeWidth="1.5"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}
