"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { clsx } from "clsx";
import { apiUrl } from "@/lib/apiBase";

// ── Types ────────────────────────────────────────────────────────────────────

type PeriodKey = "1d" | "5d" | "1mo";

interface Bar {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

interface IntradayData {
  ticker: string;
  period: string;
  interval: string;
  bars: Bar[];
  last_price: number | null;
  as_of: string | null;
  delayed_note?: string;
  error?: string;
}

interface Props {
  ticker: string;
  /** Optional reference lines from the Levels tab (MA200, T1 low, etc.) */
  levelLines?: Array<{ label: string; value: number; color?: string }>;
  className?: string;
  /**
   * Called after every successful 1D fetch with the latest bar's close and
   * change-from-open-pct. Use in parent to keep header price current at 1-min cadence.
   */
  onLivePrice?: (price: number, changePct: number) => void;
}

// ── Constants ────────────────────────────────────────────────────────────────

const PERIODS: Array<{ key: PeriodKey; label: string; interval: string; desc: string }> = [
  { key: "1d",  label: "1D",  interval: "1m",  desc: "Today · 1-min bars" },
  { key: "5d",  label: "5D",  interval: "15m", desc: "5 days · 15-min bars" },
  { key: "1mo", label: "1M",  interval: "1h",  desc: "30 days · 1-hour bars" },
];

/** Refresh cadence per period */
const REFRESH_MS: Record<PeriodKey, number> = {
  "1d":  1 * 60 * 1000,   // 1-min bars → refresh every 1 min
  "5d":  15 * 60 * 1000,  // 15-min bars → refresh every 15 min
  "1mo": 15 * 60 * 1000,  // 1-hour bars → refresh every 15 min
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatTime(iso: string, period: PeriodKey): string {
  try {
    const d = new Date(iso);
    if (period === "1d") {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    }
    if (period === "5d") {
      return d.toLocaleDateString([], { month: "short", day: "numeric" }) +
        " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    }
    // 1mo
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return iso.slice(11, 16) || iso;
  }
}

function tickFormatter(iso: string, period: PeriodKey): string {
  try {
    const d = new Date(iso);
    if (period === "1d") {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    }
    if (period === "5d") {
      // Show date label only
      return d.toLocaleDateString([], { month: "short", day: "numeric" });
    }
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

/** Reduce bar density for XAxis ticks so labels don't overlap */
function buildTickValues(bars: Bar[], period: PeriodKey): string[] {
  if (!bars.length) return [];
  const target = period === "1d" ? 8 : period === "5d" ? 6 : 8;
  const step = Math.max(1, Math.floor(bars.length / target));
  return bars.filter((_, i) => i % step === 0).map((b) => b.t);
}

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  try {
    const diffMs = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    return `${Math.floor(mins / 60)}h ago`;
  } catch {
    return "";
  }
}

// ── Custom Tooltip ────────────────────────────────────────────────────────────

function CustomTooltip({
  active,
  payload,
  period,
}: {
  active?: boolean;
  payload?: Array<{ payload: Bar }>;
  period: PeriodKey;
}) {
  if (!active || !payload?.length) return null;
  const bar = payload[0].payload;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-slate-400 mb-1">{formatTime(bar.t, period)}</p>
      <p className="text-white font-mono font-semibold">${bar.c.toFixed(2)}</p>
      <div className="mt-1 space-y-0.5 text-slate-400">
        <p>H <span className="text-emerald-400">${bar.h.toFixed(2)}</span>  L <span className="text-rose-400">${bar.l.toFixed(2)}</span></p>
        {bar.v > 0 && (
          <p>Vol {bar.v >= 1_000_000 ? `${(bar.v / 1_000_000).toFixed(1)}M` : bar.v >= 1_000 ? `${(bar.v / 1_000).toFixed(0)}K` : bar.v}</p>
        )}
      </div>
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function IntradayChart({ ticker, levelLines = [], className, onLivePrice }: Props) {
  const [period, setPeriod] = useState<PeriodKey>("5d");
  const [data, setData] = useState<IntradayData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onLivePriceRef = useRef(onLivePrice);
  onLivePriceRef.current = onLivePrice;

  const fetchData = useCallback(
    async (p: PeriodKey, signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const url = apiUrl(`/api/ticker/${encodeURIComponent(ticker)}/intraday?period=${p}`);
        const res = await fetch(url, { signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: IntradayData = await res.json();
        if (json.error && !json.bars?.length) {
          setError(json.error);
        } else {
          setData(json);
          setFetchedAt(new Date());
          // Emit live price on 1D fetches so parent can update header price
          if (p === "1d" && json.bars?.length) {
            const bars = json.bars;
            const last = bars[bars.length - 1].c;
            const first = bars[0].c;
            const pct = first > 0 ? ((last - first) / first) * 100 : 0;
            onLivePriceRef.current?.(last, pct);
          }
        }
      } catch (e: unknown) {
        if ((e as Error)?.name !== "AbortError") {
          setError((e as Error)?.message ?? "Failed to load chart data");
        }
      } finally {
        setLoading(false);
      }
    },
    [ticker],
  );

  // Fetch on mount + period change, then auto-refresh at cadence for that period
  useEffect(() => {
    const ac = new AbortController();
    fetchData(period, ac.signal);

    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => fetchData(period), REFRESH_MS[period]);

    return () => {
      ac.abort();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [period, fetchData]);

  // ── Derived chart data ──────────────────────────────────────────────────────
  const bars = data?.bars ?? [];
  const tickValues = buildTickValues(bars, period);

  // Price range for Y-axis domain with 2% padding
  const prices = bars.map((b) => b.c);
  const minP = prices.length ? Math.min(...prices) : 0;
  const maxP = prices.length ? Math.max(...prices) : 0;
  const pad = (maxP - minP) * 0.15 || maxP * 0.01;
  const yMin = Math.max(0, minP - pad);
  const yMax = maxP + pad;

  // Color: green if last >= first close, red otherwise
  const firstClose = bars[0]?.c ?? 0;
  const lastClose = bars[bars.length - 1]?.c ?? 0;
  const isUp = lastClose >= firstClose;
  const lineColor = isUp ? "#34d399" : "#f87171";
  const fillColor = isUp ? "#34d39920" : "#f8717120";

  // Change from first bar
  const changeAbs = bars.length >= 2 ? lastClose - firstClose : 0;
  const changePct = firstClose > 0 ? (changeAbs / firstClose) * 100 : 0;

  const periodInfo = PERIODS.find((p) => p.key === period)!;

  return (
    <div className={clsx("rounded-xl border border-slate-800 bg-slate-900/60 p-3", className)}>
      {/* ── Header ── */}
      <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-semibold text-slate-300 uppercase tracking-wide">{ticker}</span>
          {lastClose > 0 && (
            <>
              <span className="text-sm font-mono font-bold text-white">${lastClose.toFixed(2)}</span>
              <span
                className={clsx(
                  "text-xs font-mono px-1.5 py-0.5 rounded",
                  isUp ? "text-emerald-400 bg-emerald-400/10" : "text-rose-400 bg-rose-400/10",
                )}
              >
                {isUp ? "+" : ""}{changeAbs.toFixed(2)} ({isUp ? "+" : ""}{changePct.toFixed(2)}%)
              </span>
            </>
          )}
          {loading && (
            <span className="text-[10px] text-slate-500 animate-pulse">loading…</span>
          )}
        </div>

        {/* Period toggle */}
        <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-0.5">
          {PERIODS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setPeriod(key)}
              title={PERIODS.find((p) => p.key === key)?.desc}
              className={clsx(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-colors",
                period === key
                  ? "bg-slate-700 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Chart ── */}
      {error ? (
        <div className="h-40 flex items-center justify-center text-xs text-slate-500">
          {error}
        </div>
      ) : bars.length === 0 && !loading ? (
        <div className="h-40 flex items-center justify-center text-xs text-slate-500">
          No data for {ticker}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={bars} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id={`ig-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={lineColor} stopOpacity={0.3} />
                <stop offset="95%" stopColor={lineColor} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis
              dataKey="t"
              ticks={tickValues}
              tickFormatter={(v) => tickFormatter(v, period)}
              tick={{ fontSize: 9, fill: "#64748b" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={[yMin, yMax]}
              tick={{ fontSize: 9, fill: "#64748b" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `$${v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)}`}
              width={52}
            />
            <Tooltip
              content={<CustomTooltip period={period} />}
              cursor={{ stroke: "#475569", strokeWidth: 1 }}
            />
            {/* Level reference lines (MA200, tiers, etc.) */}
            {levelLines.map((ll) =>
              ll.value > yMin && ll.value < yMax ? (
                <ReferenceLine
                  key={ll.label}
                  y={ll.value}
                  stroke={ll.color ?? "#64748b"}
                  strokeDasharray="4 3"
                  strokeWidth={1}
                  label={{
                    value: ll.label,
                    position: "insideTopRight",
                    fontSize: 8,
                    fill: ll.color ?? "#64748b",
                  }}
                />
              ) : null,
            )}
            <Area
              type="monotone"
              dataKey="c"
              stroke={lineColor}
              strokeWidth={1.5}
              fill={`url(#ig-${ticker})`}
              dot={false}
              activeDot={{ r: 3, fill: lineColor, strokeWidth: 0 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}

      {/* ── Footer: last updated + delay note ── */}
      <div className="flex items-center justify-between gap-2 mt-2">
        <span className="text-[10px] text-slate-600">
          {periodInfo.desc}
          {fetchedAt && ` · updated ${timeAgo(fetchedAt.toISOString())}`}
        </span>
        <span className="text-[10px] text-slate-600 italic">
          Delayed ~15 min · not for execution
        </span>
      </div>
    </div>
  );
}
