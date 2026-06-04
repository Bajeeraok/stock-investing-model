import type { DecisionMode } from "./decisionMode";
import { horizonLabel, primaryHorizonFromMode } from "./decisionMode";
import type { InvestorDecisionSummary } from "@/components/dashboard/InvestorDecisionSummary";

export function formatTradePlanForClipboard(
  ticker: string,
  summary: InvestorDecisionSummary,
  currentPrice: number,
  mode: DecisionMode,
  riskPct?: number,
  stopPct?: number,
): string {
  const lines: string[] = [];
  const t = ticker.toUpperCase();
  const oa = summary.one_answer;
  const tr = summary.trader_roadmap;
  const primaryKey = primaryHorizonFromMode(mode);
  const primary = summary.horizons[primaryKey];

  lines.push(`# ${t} — manual trade plan`);
  lines.push(`As of: ${new Date().toLocaleString()}`);
  lines.push(`Lens: ${mode}`);
  lines.push(`Price: $${currentPrice > 0 ? currentPrice.toFixed(2) : "—"}`);
  lines.push(`Action: ${oa?.verdict || primary.verdict || summary.overall_verdict}`);
  if (oa?.headline) lines.push(`Headline: ${oa.headline}`);
  if (oa?.bottom_line) lines.push(`Bottom line: ${oa.bottom_line}`);

  const horizon = primaryKey === "short" ? tr?.short : primaryKey === "medium" ? tr?.medium : null;
  if (horizon?.entry_zone) {
    lines.push(
      `${horizonLabel(primaryKey)} entry: $${horizon.entry_zone.low?.toFixed(2)}–$${horizon.entry_zone.high?.toFixed(2)}`,
    );
  } else if (primary.entry_zone) {
    lines.push(
      `${horizonLabel(primaryKey)} entry: $${primary.entry_zone.low?.toFixed(2)}–$${primary.entry_zone.high?.toFixed(2)}`,
    );
  }

  const stop =
    horizon?.stop ??
    (primary.stop_loss != null && primary.stop_loss > 0 ? primary.stop_loss : null);
  const target =
    horizon?.target ??
    (primary.target != null && primary.target > 0 ? primary.target : null);
  if (stop != null) lines.push(`Stop: $${stop.toFixed(2)}`);
  if (target != null) lines.push(`Target: $${target.toFixed(2)}`);

  if (riskPct != null && stopPct != null && currentPrice > 0) {
    const notional = (riskPct / 100) * 100000 / (stopPct / 100); // illustrative on $100k book
    lines.push(`Risk budget: ${riskPct}% · stop ${stopPct}% · ~$${notional.toFixed(0)} notional (illustrative)`);
  }

  lines.push("");
  lines.push("Manual entry only — confirm size and stops in your broker.");
  return lines.join("\n");
}
