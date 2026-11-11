import type { InvestorDecisionSummary } from "@/components/dashboard/InvestorDecisionSummary";
import { band50, pct, splitLevels, type DayRangePayload } from "@/components/dashboard/tickerDetail/DayRangeCard";

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

function line(h: Hz, goalNote = ""): string {
  const z = h.entry_zone;
  const band = z?.low && z?.high ? `${usd(Math.min(z.low, z.high))}–${bare(Math.max(z.low, z.high))}` : "—";
  return `Band ${band} · Stop ${usd(h.stop_loss)} · Goal ${usd(h.target)}${h.target ? goalNote : ""}`;
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
  const [lo50, hi50] = band50(r);
  const time = new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" });
  const out = [
    live ? `*Today's range* (as of ${time} ET)` : `*Next session range* (from ${usd(r.ref_close)} close)`,
    `Most likely close: ${usd(r.close_mid)}`,
    `50% chance close: ${usd(lo50)}–${bare(hi50)}`,
    `80% chance close: ${usd(r.close_low)}–${bare(r.close_high)}`,
  ];
  if (live && r.p_close_green != null) {
    out.push(`Green close ${pct(r.p_close_green)} · red close ${pct(1 - r.p_close_green)} (vs ${usd(r.ref_close)})`);
  }
  const when = live ? "before close" : "next session";
  for (const x of r.ladder ?? []) {
    out.push(`${pct(x.p)} chance ${when}: low reaches ${usd(x.dip)} · high reaches ${usd(x.pop)}`);
  }
  const { near, far } = splitLevels(r);
  for (const l of near) {
    out.push(`${l.label} ${usd(l.price)}: ${l.touched ? `traded there earlier today · ${pct(l.p_reach)} chance again ${when}` : `${pct(l.p_reach)} chance ${when}`}`);
  }
  if (far.length) out.push(`Out of reach ${live ? "today" : "next session"}: ${far.map((l) => `${l.label.toLowerCase()} ${usd(l.price)}`).join(" · ")}`);
  return out;
}

/** assessment_pct is upside to fair value (FV/price − 1); a discount is (FV − price)/FV. */
function whyLine(ra: Retail, word: string, street: boolean): string {
  const u = ra.assessment_pct;
  const fv = street ? "Wall St fair value" : "fair value";
  let val = "";
  if (u != null && u > -100) {
    const disc = (u / (1 + u / 100));
    const prem = (100 / (1 + u / 100)) - 100;
    val = u > 0 ? `${disc.toFixed(0)}% below ${fv}` : `${prem.toFixed(0)}% above ${fv}`;
    if (u > 0 && disc >= 15) val = `well below ${fv} (${disc.toFixed(0)}% discount)`;
  }
  const w = ra.regime_weather_status;
  const trend = w === "stormy" ? "trend stormy" : w === "mixed" ? "trend mixed" : w === "extended" ? "price stretched after a run" : w === "bull" ? "trend healthy" : "";
  const tail = word === "HOLD" ? "Wait." : word === "BUY" ? "Gates clear — staged entry with the stop set." : "";
  if (val && trend) {
    const good = u != null && u > 0;
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
): string {
  const t = ticker.toUpperCase();
  const s = summary as unknown as { horizons: Record<string, Hz>; retail_action?: Retail | null; fair_value?: number | null; fair_value_vs_external?: { street_anchor_usd?: number | null } | null; one_answer?: { verdict?: string; bottom_line?: string } | null; overall_verdict?: string };
  const ra = s.retail_action ?? {};
  const ext = s.fair_value_vs_external;
  const street = !!(ext?.street_anchor_usd && s.fair_value && Math.abs(ext.street_anchor_usd - s.fair_value) / s.fair_value < 0.01);
  const verdict = s.one_answer?.verdict || s.overall_verdict || "";
  const word = callWord(verdict, !!ra.gate_cleared);
  const title = (ra.action_title || "").trim();
  const call = title && title.toUpperCase() !== word ? `${word} · ${title.charAt(0).toLowerCase()}${title.slice(1)}` : word;
  const date = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric" });

  const L: string[] = ["Sharing as per my model — please use it as supplemental information.", ""];
  L.push(`*${t}* ${usd(price)} · ${date}`, call, "");
  L.push("*Swing (weeks)*", line(s.horizons.medium ?? {}), "");
  L.push("*Long-term*", line(s.horizons.long ?? {}, street ? " (Wall St-based)" : ""), "");
  if (dayRange) L.push(...rangeBlock(dayRange), "");
  const why = whyLine(ra, word, street);
  if (why) L.push(`_Why:_ ${why}`);
  const next = ra.next_trigger?.headline?.trim();
  if (next && word === "HOLD") L.push(`_Next:_ ${next}.`);
  L.push("_Educational, not advice._");
  return L.join("\n");
}
