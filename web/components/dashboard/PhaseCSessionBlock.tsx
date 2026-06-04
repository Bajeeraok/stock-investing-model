"use client";

import type { PreMarketData } from "./PreMarketPanel";
import type { RetailMarketDecisions } from "./RetailMarketDecisionsPanel";
import type { TradingLens } from "@/lib/tradingLens";
import { SessionStrip } from "./SessionStrip";
import { TriggerLevelChips } from "./TriggerLevelChips";
import { ScoutPlaybook } from "./ScoutPlaybook";

interface SimplePreMarket {
  es_pct?: number | null;
  nq_pct?: number | null;
  tech_avg_pct?: number | null;
  message?: string | null;
}

/**
 * Phase C — session + triggers + scout playbook block for Overview.
 */
export function PhaseCSessionBlock({
  preMarketFull,
  preMarket,
  market,
  tradingLens,
  onTickerClick,
}: {
  preMarketFull?: PreMarketData | null;
  preMarket?: SimplePreMarket | null;
  market?: RetailMarketDecisions | null;
  tradingLens?: TradingLens;
  onTickerClick?: (ticker: string) => void;
}) {
  const polling = preMarketFull?.polling ?? preMarketFull?.market_catalysts?.polling;
  const intraday = preMarketFull?.market_catalysts?.intraday;
  const showSession = tradingLens === "scout" || tradingLens === "swing";

  if (!showSession) return null;

  return (
    <div className="space-y-3">
      <SessionStrip
        full={preMarketFull}
        simple={preMarket}
        intraday={intraday ?? undefined}
        isRth={polling?.is_rth_et}
        isPremarket={polling?.is_premarket_et}
        onTickerClick={onTickerClick}
      />
      <TriggerLevelChips triggerLevels={market?.trigger_levels} />
      {tradingLens === "scout" && <ScoutPlaybook checklist={market?.morning_checklist} />}
    </div>
  );
}
