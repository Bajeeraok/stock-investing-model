/**
 * Retail copy: connects raw Pattern Score (0–100) to regime + valuation so users
 * don't confuse "low score" with "bad company."
 */

export type MarketWeather = "favorable" | "mixed" | "stormy" | "extended" | "unknown";

export function marketWeatherFromRegimeBull(
  regimeBullPct: number | null | undefined,
  momentumExtended?: boolean | null,
): {
  weather: MarketWeather;
  headline: string;
  detail: string;
} {
  if (momentumExtended) {
    return {
      weather: "extended",
      headline: "Market weather: momentum extended",
      detail:
        "At/near highs with aligned MAs — HMM reads low bull % as pullback-risk, not a broken trend. Don't chase new entries.",
    };
  }
  if (regimeBullPct == null || Number.isNaN(Number(regimeBullPct))) {
    return { weather: "unknown", headline: "Market weather", detail: "Regime data unavailable." };
  }
  const rb = Number(regimeBullPct);
  if (rb >= 55) {
    return {
      weather: "favorable",
      headline: "Market weather: favorable",
      detail: "Backdrop skews bullish — tailwind for pattern confirmation.",
    };
  }
  if (rb >= 42) {
    return {
      weather: "mixed",
      headline: "Market weather: mixed",
      detail: "Transition / two-way tape — pattern scores stay noisy.",
    };
  }
  return {
    weather: "stormy",
    headline: "Market weather: stormy",
    detail: "Heavy non-bull weighting — weak pattern scores often reflect the tape, not the name.",
  };
}

export function buildPatternDecisionDriverSummary(params: {
  patternScore: number | null | undefined;
  regimeBullPct: number | null | undefined;
  undervaluationPct: number | null | undefined;
  shortVerdict?: string | null;
}): string {
  const ps = Math.round(Math.min(100, Math.max(0, Number(params.patternScore ?? 0))));
  const rb = params.regimeBullPct;
  const nonBull =
    rb != null && !Number.isNaN(Number(rb))
      ? Math.max(0, Math.min(100, 100 - Number(rb)))
      : null;
  const uv = params.undervaluationPct;
  const verdict = (params.shortVerdict || "WAIT").toUpperCase();

  const regimeTailwind = rb != null && !Number.isNaN(Number(rb)) && Number(rb) >= 48;
  const regimeStormy = rb != null && !Number.isNaN(Number(rb)) && Number(rb) < 42;

  const uvRounded =
    uv != null && !Number.isNaN(Number(uv)) ? Math.round(Number(uv)) : null;

  if (ps >= 60 && regimeTailwind) {
    return `Pattern ${ps}/100 with a supportive regime — still use Roadmaps for price discipline (score ≠ entry timing).`;
  }

  if (ps >= 60 && !regimeTailwind) {
    return `Pattern ${ps}/100 is OK technically, but the broad regime is not fully bullish — keep size modest until backdrop improves.`;
  }

  const valLead =
    uvRounded != null && uvRounded >= 5
      ? `Undervaluation vs model is roughly ${uvRounded}%`
      : uvRounded != null && uvRounded <= -5
        ? `Price sits roughly ${Math.abs(uvRounded)}% above our fair-value anchor`
        : uvRounded != null && uvRounded >= 1
          ? `Valuation is mildly attractive (~${uvRounded}% vs model)`
          : `Valuation vs model is neutral`;

  if (regimeStormy && nonBull != null) {
    const wait =
      verdict === "WAIT" || verdict === "WATCH"
        ? ` Recommendation: ${verdict === "WAIT" ? "do not add" : "stay tactical"} until Pattern Score clears 60 unless your plan is purely very long-term.`
        : "";
    return `${valLead}, but technical momentum reads ${ps}/100 mostly because the backdrop is non-bull heavy (~${Math.round(nonBull)}% non-bull)—that is regime noise, not necessarily a broken stock.${wait}`;
  }

  const wait =
    ps < 60 && (verdict === "WAIT" || verdict === "WATCH")
      ? ` Recommendation: ${verdict === "WAIT" ? "Do not add" : "Wait"} until Pattern Score clears 60 before sizing up short-term trades.`
      : "";

  return `${valLead}; pattern reads ${ps}/100 on chart structure.${wait}`;
}

/** Unified signal card has no FV — tie copy to regime label + action. */
/**
 * When short vs long ML % diverge a lot, explain that horizons are different models / windows.
 */
export function buildMlHorizonGapExplainer(
  shortProb: number | null | undefined,
  mediumProb: number | null | undefined,
  longProb: number | null | undefined,
): string | null {
  const s = Number(shortProb);
  const m = Number(mediumProb);
  const l = Number(longProb);
  if ([s, m, l].some((x) => Number.isNaN(x))) return null;
  const hi = Math.max(s, m, l);
  const lo = Math.min(s, m, l);
  if (hi - lo < 20) return null;
  return (
    "These ML percentages are not three copies of the same guess: each horizon is trained for a different window " +
    "(near-term bounce vs swing vs multi-quarter payoff). The tape can look awful for weeks while longer odds stay higher — " +
    "that mismatch is expected when volatility is high."
  );
}

export function buildPatternDecisionDriverUnified(params: {
  regime: string;
  patternScore: number;
  action: string;
}): string {
  const ps = Math.round(Math.min(100, Math.max(0, params.patternScore)));
  const r = (params.regime || "NEUTRAL").toUpperCase();
  const bearish =
    r.includes("BEAR") || r === "TRANSITION";
  const bullish = r.includes("BULL") && !r.includes("NON");

  if (ps >= 60) {
    return `Pattern ${ps}/100 — chart structure is constructive${bullish ? " with a bullish regime label" : ""}; still confirm entries vs levels below.`;
  }

  if (bearish) {
    return `Pattern ${ps}/100 is depressed partly because regime is ${r.replace(/_/g, " ").toLowerCase()}—that weights technicals down; it does not mean the equity is “junk.” Recommendation: wait for score >60 or use fundamentals-led buys only.`;
  }

  return `Pattern ${ps}/100 reflects chart math under regime ${r.replace(/_/g, " ")}; compare to your fused action (${params.action}).`;
}
