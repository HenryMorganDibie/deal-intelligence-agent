export type PortfolioPosition = {
  quantity: number;
  costPerUnit: number;
  currentPrice: number | null;
  fxToBase: number | null;
  country: string;
  sector: string;
  assetType: string;
  currency: string;
};

export type ExposureKey = "country" | "sector" | "assetType" | "currency";

export function convertToBase(value: number, fxToBase: number | null): number | null {
  return Number.isFinite(value) && fxToBase != null && Number.isFinite(fxToBase) && fxToBase > 0
    ? value * fxToBase
    : null;
}

export function calculatePortfolioTotals<T extends PortfolioPosition>(holdings: readonly T[]) {
  const pricedHoldings = holdings.filter((holding) =>
    holding.currentPrice != null && Number.isFinite(holding.currentPrice) && holding.currentPrice > 0 &&
    holding.fxToBase != null && Number.isFinite(holding.fxToBase) && holding.fxToBase > 0 &&
    Number.isFinite(holding.quantity) && holding.quantity > 0,
  );
  const totalCurrentValue = pricedHoldings.reduce(
    (sum, holding) => sum + (convertToBase(holding.quantity * (holding.currentPrice ?? 0), holding.fxToBase) ?? 0),
    0,
  );
  const totalCostOfPriced = pricedHoldings.reduce(
    (sum, holding) => sum + (convertToBase(holding.quantity * holding.costPerUnit, holding.fxToBase) ?? 0),
    0,
  );
  return {
    pricedHoldings,
    totalCurrentValue,
    totalCostOfPriced,
    gainLoss: totalCurrentValue - totalCostOfPriced,
    missingPriceCount: holdings.filter((holding) => holding.currentPrice == null || !Number.isFinite(holding.currentPrice) || holding.currentPrice <= 0).length,
    missingFxCount: holdings.filter((holding) => holding.fxToBase == null || !Number.isFinite(holding.fxToBase) || holding.fxToBase <= 0).length,
  };
}

export function calculateExposureRows<T extends PortfolioPosition>(
  holdings: readonly T[],
  key: ExposureKey,
) {
  const totals = new Map<string, number>();
  for (const holding of holdings) {
    if (holding.currentPrice == null || !Number.isFinite(holding.currentPrice) || holding.currentPrice <= 0 ||
        holding.fxToBase == null || !Number.isFinite(holding.fxToBase) || holding.fxToBase <= 0 ||
        !Number.isFinite(holding.quantity) || holding.quantity <= 0) continue;
    const label = holding[key].trim() || "Unclassified";
    const value = convertToBase(holding.quantity * holding.currentPrice, holding.fxToBase);
    if (value != null && Number.isFinite(value) && value > 0) totals.set(label, (totals.get(label) ?? 0) + value);
  }
  const total = [...totals.values()].reduce((sum, value) => sum + value, 0);
  return [...totals.entries()]
    .map(([label, value]) => ({ label, value, share: total > 0 ? value / total : 0 }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);
}
