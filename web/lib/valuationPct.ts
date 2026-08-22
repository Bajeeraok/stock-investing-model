/** Price vs model fair value: (price - FV) / FV * 100.
 *  Negative = discount to FV (undervalued). Positive = premium (rich).
 *  Do NOT use (FV - price) / price here -- that is "upside to FV", not "vs FV".
 */
export function pctPriceVsFairValue(price: number, fairValue: number): number {
  if (!(price > 0) || !(fairValue > 0)) return 0;
  return ((price - fairValue) / fairValue) * 100;
}

/** Classic margin of safety: (FV - price) / FV * 100. Positive = cushion below FV. */
export function marginOfSafetyPct(price: number, fairValue: number): number {
  if (!(price > 0) || !(fairValue > 0)) return 0;
  return ((fairValue - price) / fairValue) * 100;
}
