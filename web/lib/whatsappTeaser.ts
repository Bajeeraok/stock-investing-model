import type { InvestorDecisionSummary } from "@/components/dashboard/InvestorDecisionSummary";
import type { DayRangePayload } from "@/components/dashboard/tickerDetail/DayRangeCard";

/** SPY/QQQ said-vs-happened summary (from /api/market-pulse scorecard.summary). */
export type PulseTrack = Record<string, { days: number; direction_hit_pct: number | null; direction_calls: number; range_coverage_pct: number | null }>;

const n1 = (v?: number | null) => (v != null && v > 0 ? v.toFixed(v >= 1000 ? 0 : 1) : "—");
const n2 = (v?: number | null) => (v != null && v > 0 ? v.toFixed(2) : "—");
const band = (z?: { low?: number | null; high?: number | null } | null) => (z?.low && z?.high ? `${n1(z.low)}-${n1(z.high)}` : "—");
const row = (label: string, a: string, b: string) => `${label.padEnd(5)} ${a.padStart(11)}  ${b.padStart(11)}`;

/** Monospace block for WhatsApp: wrap in ``` so columns line up on phones. */
export function formatWhatsAppTeaser(
  ticker: string,
  summary: InvestorDecisionSummary,
  price: number,
  dayRange?: DayRangePayload | null,
  track?: PulseTrack | null,
): string {
  const t = ticker.toUpperCase();
  const h = summary.horizons as unknown as Record<string, { entry_zone?: { low?: number; high?: number } | null; stop_loss?: number | null; target?: number | null; verdict?: string }>;
  const sw = h.medium ?? {};
  const lt = h.long ?? {};
  const date = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const oa = summary.one_answer;
  const L: string[] = ["```", `${t}  $${n2(price)}  ${date}`, (oa?.verdict || summary.overall_verdict || "").toString()];
  L.push("", row("", "SWING", "LONG-TERM"));
  L.push(row("Band", band(sw.entry_zone), band(lt.entry_zone)));
  L.push(row("Stop", n1(sw.stop_loss), n1(lt.stop_loss)));
  L.push(row("Goal", n1(sw.target), n1(lt.target)));
  if (dayRange) {
    const live = dayRange.phase === "intraday";
    L.push("", `${live ? "Today" : "Next session"} close range (80%):`, `  ${n2(dayRange.close_low)}-${n2(dayRange.close_high)}`);
    if (live && dayRange.p_close_green != null) L.push(`Green-close odds ${Math.round(dayRange.p_close_green * 100)}%`);
    const top = dayRange.levels.find((l) => l.label === "Swing band top") ?? dayRange.levels[0];
    if (top) L.push(`${top.label} ${n2(top.price)}:`, `  ${top.touched ? "traded there today" : `${Math.round(top.p_reach * 100)}% chance ${live ? "today" : "next session"}`}`);
  }
  const tr = track?.["10:30"] ?? track?.pre_open;
  if (tr && tr.days > 0 && tr.direction_hit_pct != null) {
    L.push("", `SPY/QQQ day calls, last ${tr.days} days:`, `  direction ${Math.round(tr.direction_hit_pct)}% · in range ${tr.range_coverage_pct != null ? Math.round(tr.range_coverage_pct) : "—"}%`);
  }
  L.push("", "Educational, not advice.", "— Thrive Alpha", "```");
  return L.join("\n");
}
