import type { InvestorDecisionSummary } from "@/components/dashboard/InvestorDecisionSummary";
import { pct, type DayRangePayload } from "@/components/dashboard/tickerDetail/DayRangeCard";

/** SPY/QQQ said-vs-happened summary (from /api/market-pulse scorecard.summary). */
export type PulseTrack = Record<string, { days: number; direction_hit_pct: number | null; direction_calls: number; range_coverage_pct: number | null }>;

type Hz = { entry_zone?: { low?: number | null; high?: number | null } | null; stop_loss?: number | null; target?: number | null };
type Retail = {
  action_title?: string;
  gate_cleared?: boolean;
  dynamic_subtitle?: string;
  assessment_pct?: number | null;
  regime_weather_status?: "bull" | "stormy" | "mixed" | "extended" | string | null;
  next_trigger?: { headline?: string } | null;
};

const usd = (v?: number | null) => (v != null && v > 0 ? `$${v.toFixed(2)}` : "—");
const bare = (v?: number | null) => (v != null && v > 0 ? v.toFixed(2) : "—");

function line(h: Hz): string {
  const z = h.entry_zone;
  const band = z?.low && z?.high ? `${usd(Math.min(z.low, z.high))}–${bare(Math.max(z.low, z.high))}` : "—";
  return `Band ${band} · Stop ${usd(h.stop_loss)} · Goal ${usd(h.target)}`;
}

function callWord(verdict: string, gateCleared: boolean): string {
  const v = verdict.toUpperCase();
  if (v.includes("SELL")) return "SELL";
  if (v.includes("REDUCE") || v.includes("TRIM")) return "REDUCE";
  if (v.includes("AVOID")) return "AVOID";
  if ((v.includes("BUY") || v.includes("ACCUMULATE")) && gateCleared) return "BUY";
  return "HOLD";
}

function rangeBlock(r: DayRangePayload): string[] {
  const live = r.phase === "intraday";
  const mid = r.close_mid;
  const half = (v: number) => mid * Math.exp(Math.log(v / mid) * (0.6745 / 1.2816));
  const time = new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" });
  const out = [
    live ? `*Today's range* (as of ${time} ET)` : `*Next session range* (from ${usd(r.ref_close)} close)`,
    `Likely close (50%): ${usd(half(r.close_low))}–${bare(half(r.close_high))}`,
    `Wider range (80%): ${usd(r.close_low)}–${bare(r.close_high)}`,
  ];
  if (live && r.p_close_green != null) {
    out.push(`Green close ${pct(r.p_close_green)} · red close ${pct(1 - r.p_close_green)} (vs ${usd(r.ref_close)})`);
  }
  for (const l of r.levels.filter((x) => x.label !== "Owner band top")) {
    out.push(`${l.label} ${usd(l.price)}: ${l.touched ? "traded there today" : `${pct(l.p_reach)} chance ${live ? "today" : "next session"}`}`);
  }
  return out;
}

function whyLine(ra: Retail, word: string): string {
  const a = ra.assessment_pct;
  const val =
    a == null ? "" : a >= 15 ? `well below fair value (${a.toFixed(0)}% discount)` : a > 0 ? `${a.toFixed(0)}% below fair value` : `${Math.abs(a).toFixed(0)}% above fair value`;
  const w = ra.regime_weather_status;
  const trend = w === "stormy" ? "trend stormy" : w === "mixed" ? "trend mixed" : w === "extended" ? "price stretched after a run" : w === "bull" ? "trend healthy" : "";
  const tail = word === "HOLD" ? "Wait." : word === "BUY" ? "Gates clear — staged entry with the stop set." : "";
  if (val && trend) {
    const good = a != null && a > 0;
    const bad = w !== "bull";
    return `${val}${good === bad ? ", but " : " and "}${trend}. ${tail}`.replace(/^./, (c) => c.toUpperCase()).trim();
  }
  return (ra.dynamic_subtitle || "").trim();
}

/** Plain WhatsApp post (bold/italic markers, no tables). */
export function formatWhatsAppTeaser(
  ticker: string,
  summary: InvestorDecisionSummary,
  price: number,
  dayRange?: DayRangePayload | null,
  track?: PulseTrack | null,
): string {
  const t = ticker.toUpperCase();
  const s = summary as unknown as { horizons: Record<string, Hz>; retail_action?: Retail | null; one_answer?: { verdict?: string; bottom_line?: string } | null; overall_verdict?: string };
  const ra = s.retail_action ?? {};
  const verdict = s.one_answer?.verdict || s.overall_verdict || "";
  const word = callWord(verdict, !!ra.gate_cleared);
  const title = (ra.action_title || "").trim();
  const call = title && title.toUpperCase() !== word ? `${word} · ${title.charAt(0).toLowerCase()}${title.slice(1)}` : word;
  const date = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric" });

  const L: string[] = ["Sharing as per my model — please use it as supplemental information.", ""];
  L.push(`*${t}* ${usd(price)} · ${date}`, call, "");
  L.push("*Swing (weeks)*", line(s.horizons.medium ?? {}), "");
  L.push("*Long-term*", line(s.horizons.long ?? {}), "");
  if (dayRange) L.push(...rangeBlock(dayRange), "");
  const why = whyLine(ra, word);
  if (why) L.push(`_Why:_ ${why}`);
  const next = ra.next_trigger?.headline?.trim();
  if (next && word === "HOLD") L.push(`_Next:_ ${next}.`);
  const tr = track?.["10:30"] ?? track?.pre_open;
  if (tr && tr.days > 0 && tr.direction_hit_pct != null) {
    L.push(`_Model's SPY/QQQ day calls: direction right ${Math.round(tr.direction_hit_pct)}% over the last ${tr.days} days._`);
  }
  L.push("_Educational, not advice._");
  return L.join("\n");
}
