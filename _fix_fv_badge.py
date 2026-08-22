from pathlib import Path
import re

ROOT = Path(r"C:\Users\hegunda\stock-investing-model")
lib = ROOT / "web" / "lib"
lib.mkdir(parents=True, exist_ok=True)
(lib / "valuationPct.ts").write_text(
    """/** Price vs model fair value: (price - FV) / FV * 100.
 *  Negative = discount to FV (undervalued). Positive = premium (rich).
 *  Do NOT use (FV - price) / price here -- that is \"upside to FV\", not \"vs FV\".
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
""",
    encoding="utf-8",
)
print("wrote valuationPct.ts")

modal = ROOT / "web" / "components" / "dashboard" / "TickerDetailModal.tsx"
t = modal.read_text(encoding="utf-8")
pat = re.compile(
    r"const assessmentPctForHeader = useMemo\(\(\) => \{[\s\S]*?\}, \[detail, effectivePrice\]\);"
)
new = """// Header \"vs FV\" = (price-FV)/FV. Not (FV-price)/price (upside-to-FV / false MOS).
  const assessmentPctForHeader = useMemo(() => {
    const inv = detail?.investor_summary;
    const cp = effectivePrice;
    if (!inv || !cp || !(inv.fair_value > 0)) return 0;
    return ((cp - inv.fair_value) / inv.fair_value) * 100;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail, effectivePrice]);"""
m = pat.search(t)
if not m:
    raise SystemExit("assessmentPctForHeader block not found")
t = t[: m.start()] + new + t[m.end() :]
modal.write_text(t, encoding="utf-8")
print("TickerDetailModal header fixed")

# InvestorDecisionSummary - add parallel pctVsFv for any header-like display;
# keep assessmentPct for gate math but document. Fix MOS gate display if labeled vs FV.
ids = ROOT / "web" / "components" / "dashboard" / "InvestorDecisionSummary.tsx"
if ids.exists():
    it = ids.read_text(encoding="utf-8")
    # Prefer fixing the one formula used when rendering "% vs FV" strings
    it2 = it.replace(
        "Deeply Undervalued (+${Math.abs(input.assessmentPct).toFixed(1)}% Fair Value)",
        "Deeply Undervalued (price ${input.assessmentPct >= 0 ? Math.abs(input.assessmentPct).toFixed(1) + '% below' : Math.abs(input.assessmentPct).toFixed(1) + '% above'} FV)",
    )
    # Safer: change assessmentPct definition to MOS (fv-price)/fv for consistency with "Fair Value" copy
    old_a = "const assessmentPct = currentPrice > 0 ? ((fair_value - currentPrice) / currentPrice) * 100 : 0;"
    new_a = "const assessmentPct = currentPrice > 0 && fair_value > 0 ? ((fair_value - currentPrice) / fair_value) * 100 : 0; // MOS vs FV (not upside-to-FV)"
    if old_a in it:
        it = it.replace(old_a, new_a)
        ids.write_text(it, encoding="utf-8")
        print("InvestorDecisionSummary MOS denominator fixed")
    else:
        print("InvestorDecisionSummary assessmentPct line not found exact")

# DecisionDeck same formula
dd = ROOT / "web" / "components" / "dashboard" / "DecisionDeck.tsx"
if dd.exists():
    dt = dd.read_text(encoding="utf-8")
    old = "currentPrice > 0 ? ((summary.fair_value - currentPrice) / currentPrice) * 100 : 0"
    new = "currentPrice > 0 && summary.fair_value > 0 ? ((summary.fair_value - currentPrice) / summary.fair_value) * 100 : 0"
    if old in dt:
        dd.write_text(dt.replace(old, new), encoding="utf-8")
        print("DecisionDeck fixed")

# executionPlanModel
ep = ROOT / "web" / "components" / "dashboard" / "executionPlanModel.ts"
if ep.exists():
    et = ep.read_text(encoding="utf-8")
    old = "currentPrice > 0 && fair_value > 0 ? ((fair_value - currentPrice) / currentPrice) * 100 : 0;"
    new = "currentPrice > 0 && fair_value > 0 ? ((fair_value - currentPrice) / fair_value) * 100 : 0; // MOS vs FV"
    if old in et:
        ep.write_text(et.replace(old, new), encoding="utf-8")
        print("executionPlanModel fixed")

print("frontend valuation fixes done")
