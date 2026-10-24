import type { Dispatch, SetStateAction } from "react";
import type { ConfidenceData, PlaybookScenario, RegimeTransitionData } from "../../ConfidenceBreakdown";
import type { UnifiedSignalData } from "../../PatternSignalCard";
import type { PriceTargetsData } from "../../PriceTargetsPanel";
import type { TradingGateRow } from "../../retailActionUX";
import type { DecisionMode } from "@/lib/decisionMode";
import type { PositionIntent } from "@/lib/positionIntent";
import type { WhySubTab } from "../../TickerDetailWhyNav";
import type { HorizonPlaybooksBundle } from "../../HorizonPlaybookCard";
import type { CatalystNoteCard } from "../../tradingPlatformUX";
import type { TickerDetail, RetailActionStatus, ModalTab, PortfolioImpactContext } from "../../TickerDetailModal";
import type { buildExecutionPlanViewModel } from "../../executionPlanModel";

/**
 * Shared prop bag for the extracted tab bodies — the modal computes every
 * derived value once (gates, prices, playbook state) and hands the same ctx to
 * each tab component. Keeps the per-tab signatures small while the extraction
 * stays a pure JSX move.
 */
export interface TabCtx {
  ticker: string;
  detail: TickerDetail;
  wide: boolean;
  decisionMode: DecisionMode;
  positionIntent: PositionIntent | null;
  effectivePrice: number | null;
  quoteDailyMovePct: number | null;
  headerActionStatus: RetailActionStatus;
  tradingGates: TradingGateRow[];
  gatesPassedCount: number;
  gatesTotal: number;
  confidence: ConfidenceData | null;
  unified: UnifiedSignalData | null;
  priceTargets: PriceTargetsData | null;
  executionVm: ReturnType<typeof buildExecutionPlanViewModel>;
  ltEntryTiersOpen: boolean;
  setLtEntryTiersOpen: Dispatch<SetStateAction<boolean>>;
  quickRefOpen: boolean;
  setQuickRefOpen: Dispatch<SetStateAction<boolean>>;
  debugPanelOpen: boolean;
  setDebugPanelOpen: Dispatch<SetStateAction<boolean>>;
  moreContextOpen: boolean;
  setMoreContextOpen: Dispatch<SetStateAction<boolean>>;
  metricsGuideOpen: boolean;
  setMetricsGuideOpen: Dispatch<SetStateAction<boolean>>;
  portfolioImpactContext: PortfolioImpactContext | null;
  playbookStage3: PlaybookScenario | null;
  regimeShift: RegimeTransitionData | null;
  horizonPlaybooksBundle: HorizonPlaybooksBundle | null;
  modalNewsRail: {
    label: string | null;
    score: number | null;
    headlineCount: number | null;
    headlines: { title: string; url?: string | null }[];
    catalystNote: string | null;
    sentimentCaveat: string | null;
    catalystCards: CatalystNoteCard[];
  };
  overviewVerdict: string | null;
  patternVerdict: string | null;
  hasVerdictConflict: boolean;
  periods: string[];
  whySubTab: WhySubTab;
  setWhySubTab: Dispatch<SetStateAction<WhySubTab>>;
  setModalTab: Dispatch<SetStateAction<ModalTab>>;
  openWhyValuation: () => void;
  setLivePrice: (p: number | null) => void;
  setLiveChangePct: (pct: number | null) => void;
  setPositionIntentLocal: Dispatch<SetStateAction<PositionIntent | null>>;
  setDecisionModeLocal: Dispatch<SetStateAction<DecisionMode>>;
}
