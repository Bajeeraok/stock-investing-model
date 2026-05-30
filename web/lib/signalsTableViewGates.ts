import type { Signal } from "@/app/page";
import {
  buildSignalListGates,
  filterPrimaryTradingGates,
  type SignalListContext,
  type TradingGateRow,
} from "@/components/dashboard/retailActionUX";

export function tradingGateSummaryLabel(gates: TradingGateRow[]): string {
  const primary = filterPrimaryTradingGates(gates);
  const blocked = primary.filter((g) => !g.pass).length;
  const pass = primary.length - blocked;
  if (primary.length === 0) return "—";
  if (blocked === 0) return `${pass}/${primary.length}`;
  return `${pass}/${primary.length} · ${blocked} blocked`;
}

export function gatesForSignal(r: Signal, listContext: SignalListContext): TradingGateRow[] {
  return filterPrimaryTradingGates(buildSignalListGates(r, listContext));
}
