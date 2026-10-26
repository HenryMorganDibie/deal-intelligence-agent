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

import { validHttpUrl, validPastDate } from "./markets-valuation";

export type SavedValuationSnapshot = {
  id: string;
  company: string;
  ticker: string;
  country?: string;
  method: "dcf" | "ddm";
  modelFit: string;
  modelFitConfirmed: boolean;
  currency: string;
  statementSourceUrl: string;
  statementPeriod: string;
  quotePrice: number | null;
  quoteDate: string | null;
  quoteSourceUrl: string | null;
  bearPerShare: number;
  basePerShare: number;
  bullPerShare: number;
  calculatedAt: string;
};

export type PortfolioValuationReview = {
  holdingId: string;
  company: string;
  ticker: string;
  country: string;
  currency: string;
  status: "no-saved-valuation" | "model-not-suitable" | "missing-quote" | "stale-inputs" | "currency-mismatch" | "portfolio-price-mismatch" | "invalid-estimate" | "ready";
  detail: string;
  method?: "dcf" | "ddm";
  quotePrice?: number;
  quoteDate?: string;
  scenarioLow?: number;
  basePerShare?: number;
  scenarioHigh?: number;
  gapPct?: number;
  conclusion?: string;
  statementSourceUrl?: string;
  quoteSourceUrl?: string;
  statementPeriod?: string;
  calculatedAt?: string;
  positionValueBase?: number | null;
  weightedEligible?: boolean;
};

export function parseValuationHistoryBackup(value: unknown): SavedValuationSnapshot[] | null {
  if (!value || typeof value !== "object") return null;
  const backup = value as { version?: unknown; exportedAt?: unknown; valuations?: unknown };
  if (backup.version !== 1 || typeof backup.exportedAt !== "string" ||
      !Number.isFinite(Date.parse(backup.exportedAt)) || !Array.isArray(backup.valuations) ||
      backup.valuations.length < 1 || backup.valuations.length > 5000 ||
      !backup.valuations.every(isSavedValuation)) return null;
  const ids = new Set<string>();
  for (const snapshot of backup.valuations) {
    if (ids.has(snapshot.id)) return null;
    ids.add(snapshot.id);
  }
  return backup.valuations;
}

export function isSavedValuation(value: unknown): value is SavedValuationSnapshot {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<SavedValuationSnapshot>;
  const quoteIsValid = item.quotePrice === null
    ? item.quoteDate === null && item.quoteSourceUrl === null
    : typeof item.quotePrice === "number" && Number.isFinite(item.quotePrice) && item.quotePrice > 0 &&
      typeof item.quoteDate === "string" && validPastDate(item.quoteDate) &&
      typeof item.quoteSourceUrl === "string" && validHttpUrl(item.quoteSourceUrl);
  const calculatedAt = typeof item.calculatedAt === "string" ? Date.parse(item.calculatedAt) : Number.NaN;
  return typeof item.id === "string" && item.id.length > 0 &&
    typeof item.company === "string" && item.company.trim().length > 0 &&
    typeof item.ticker === "string" && (item.country === undefined || typeof item.country === "string") &&
    (item.method === "dcf" || item.method === "ddm") &&
    typeof item.modelFit === "string" && item.modelFit.length > 0 &&
    item.modelFitConfirmed === true &&
    typeof item.currency === "string" && item.currency.length > 0 &&
    typeof item.statementSourceUrl === "string" && validHttpUrl(item.statementSourceUrl) &&
    typeof item.statementPeriod === "string" && validPastDate(item.statementPeriod) &&
    quoteIsValid &&
    typeof item.bearPerShare === "number" && Number.isFinite(item.bearPerShare) &&
    typeof item.basePerShare === "number" && Number.isFinite(item.basePerShare) &&
    typeof item.bullPerShare === "number" && Number.isFinite(item.bullPerShare) &&
    Number.isFinite(calculatedAt) && calculatedAt <= Date.now();
}

function latestMatchingValuation<T extends PortfolioPosition & { id: string; name: string; ticker: string }>(
  holding: T,
  snapshots: readonly SavedValuationSnapshot[],
): SavedValuationSnapshot | undefined {
  const name = holding.name.trim().toLowerCase();
  const ticker = holding.ticker.trim().toUpperCase();
  return snapshots
    .filter((snapshot) => {
      const snapshotTicker = snapshot.ticker.trim().toUpperCase();
      const holdingCountry = holding.country.trim().toLowerCase();
      const snapshotCountry = (snapshot.country ?? "").trim().toLowerCase();
      if (ticker && snapshotTicker) return ticker === snapshotTicker && holdingCountry.length > 0 && snapshotCountry.length > 0 && holdingCountry === snapshotCountry;
      return name === snapshot.company.trim().toLowerCase() && holdingCountry.length > 0 && snapshotCountry.length > 0 && holdingCountry === snapshotCountry;
    })
    .sort((a, b) => Date.parse(b.calculatedAt) - Date.parse(a.calculatedAt))[0];
}

export function calculatePortfolioValuationReviews<
  T extends PortfolioPosition & { id: string; name: string; ticker: string; priceAsOf?: string | null; fxAsOf?: string | null }
>(
  holdings: readonly T[],
  snapshots: readonly SavedValuationSnapshot[],
  baseCurrency: string,
  now = Date.now(),
): PortfolioValuationReview[] {
  return holdings.map((holding) => {
    const common = { holdingId: holding.id, company: holding.name, ticker: holding.ticker, country: holding.country, currency: holding.currency };
    const snapshot = latestMatchingValuation(holding, snapshots);
    if (!snapshot) {
      return { ...common, status: "no-saved-valuation", detail: "No saved valuation review matches this holding. Open the valuation workspace, review the inputs and save the result locally." };
    }
    const suitable = snapshot.modelFitConfirmed &&
      (snapshot.method === "dcf"
        ? snapshot.modelFit === "standard-operating-company"
        : snapshot.modelFit === "financial-institution" || snapshot.modelFit === "mature-dividend-payer");
    if (!suitable) {
      return { ...common, status: "model-not-suitable", method: snapshot.method, detail: "The saved model profile is not suitable for a portfolio valuation conclusion. Reassess the model fit before using the estimate." };
    }
    if (snapshot.quotePrice == null || !snapshot.quoteDate || !snapshot.quoteSourceUrl) {
      return { ...common, status: "missing-quote", method: snapshot.method, detail: "The saved model has no dated, source-linked market quote, so it cannot support a price-versus-value conclusion." };
    }
    const quoteTime = Date.parse(`${snapshot.quoteDate}T00:00:00Z`);
    const statementTime = Date.parse(`${snapshot.statementPeriod}T00:00:00Z`);
    const calculationTime = Date.parse(snapshot.calculatedAt);
    if (now - quoteTime > 7 * 86400000 || now - statementTime > 548 * 86400000 || now - calculationTime > 30 * 86400000) {
      return { ...common, status: "stale-inputs", method: snapshot.method, quotePrice: snapshot.quotePrice, quoteDate: snapshot.quoteDate, statementPeriod: snapshot.statementPeriod, detail: "The saved quote, financial period or valuation run is stale. Refresh the source inputs and save a new valuation before relying on it." };
    }
    if (snapshot.currency !== holding.currency) {
      return { ...common, status: "currency-mismatch", method: snapshot.method, quotePrice: snapshot.quotePrice, quoteDate: snapshot.quoteDate, detail: `Saved valuation currency ${snapshot.currency} does not match this holding's currency ${holding.currency}. Convert and verify the inputs before comparing them.` };
    }
    if (holding.currentPrice == null || !holding.priceAsOf || holding.priceAsOf !== snapshot.quoteDate ||
        Math.abs(holding.currentPrice - snapshot.quotePrice) / snapshot.quotePrice > 0.01) {
      return { ...common, status: "portfolio-price-mismatch", method: snapshot.method, quotePrice: snapshot.quotePrice, quoteDate: snapshot.quoteDate, detail: "The portfolio holding must have the same quote date and a price within 1% of the saved valuation quote. Update the holding price/date or save a new valuation." };
    }
    const scenarioValues = [snapshot.bearPerShare, snapshot.basePerShare, snapshot.bullPerShare];
    if (scenarioValues.some((value) => !Number.isFinite(value) || value <= 0)) {
      return { ...common, status: "invalid-estimate", method: snapshot.method, quotePrice: snapshot.quotePrice, quoteDate: snapshot.quoteDate, detail: "At least one scenario does not produce a positive per-share estimate, so this holding is excluded from portfolio valuation conclusions." };
    }
    const [low, base, high] = scenarioValues;
    const allBelow = scenarioValues.every((value) => value < snapshot.quotePrice!);
    const allAbove = scenarioValues.every((value) => value > snapshot.quotePrice!);
    const conclusion = allBelow && base < snapshot.quotePrice * 0.85
      ? "Potentially overvalued on these assumptions"
      : allAbove && base > snapshot.quotePrice * 1.15
        ? "Potentially undervalued on these assumptions"
        : allBelow
          ? "Price is above all scenarios, but the base-case gap is under 15%"
          : allAbove
            ? "Price is below all scenarios, but the base-case gap is under 15%"
            : "Mixed signal across scenarios";
    const gapPct = (base / snapshot.quotePrice - 1) * 100;
    const fxIsFresh = holding.currency === baseCurrency ||
      (holding.fxToBase != null && holding.fxToBase > 0 && Boolean(holding.fxAsOf) &&
        validPastDate(holding.fxAsOf!) && now - Date.parse(`${holding.fxAsOf}T00:00:00Z`) <= 7 * 86400000);
    const positionValueBase = fxIsFresh
      ? holding.quantity * holding.currentPrice * (holding.currency === baseCurrency ? 1 : holding.fxToBase!)
      : null;
    return {
      ...common,
      status: "ready",
      detail: positionValueBase == null
        ? "The saved valuation matches the holding's dated quote. It is excluded from the portfolio-weighted gap because the foreign-exchange rate/date is missing or stale."
        : "The saved valuation matches the holding's dated quote and passed the source, freshness, currency and model-fit checks. This remains assumption-dependent, not a recommendation.",
      method: snapshot.method,
      quotePrice: snapshot.quotePrice,
      quoteDate: snapshot.quoteDate,
      scenarioLow: Math.min(low, base, high),
      basePerShare: base,
      scenarioHigh: Math.max(low, base, high),
      gapPct,
      conclusion,
      statementSourceUrl: snapshot.statementSourceUrl,
      quoteSourceUrl: snapshot.quoteSourceUrl,
      statementPeriod: snapshot.statementPeriod,
      calculatedAt: snapshot.calculatedAt,
      positionValueBase,
      weightedEligible: positionValueBase != null && positionValueBase > 0,
    };
  });
}

export function calculatePortfolioValuationSummary(reviews: readonly PortfolioValuationReview[]) {
  const ready = reviews.filter((review) => review.status === "ready");
  const weighted = ready.filter((review) => review.weightedEligible && review.positionValueBase != null && review.gapPct != null);
  const totalWeight = weighted.reduce((sum, review) => sum + (review.positionValueBase ?? 0), 0);
  const weightedGapPct = totalWeight > 0
    ? weighted.reduce((sum, review) => sum + (review.gapPct ?? 0) * (review.positionValueBase ?? 0), 0) / totalWeight
    : null;
  return {
    matchedCount: ready.length,
    weightedCount: weighted.length,
    weightedGapPct,
    potentiallyOvervaluedCount: ready.filter((review) => review.conclusion === "Potentially overvalued on these assumptions").length,
    potentiallyUndervaluedCount: ready.filter((review) => review.conclusion === "Potentially undervalued on these assumptions").length,
  };
}


export const ASSET_TYPES = ["Stock", "ETF", "Bond", "Treasury bill", "Money-market fund", "Mutual fund", "REIT", "Fixed deposit", "Other"] as const;

const ASSET_TYPE_ALIASES: Record<string, (typeof ASSET_TYPES)[number]> = {
  stock: "Stock", stocks: "Stock", equity: "Stock", equities: "Stock", share: "Stock", shares: "Stock",
  "ordinary share": "Stock", "ordinary shares": "Stock", "listed equity": "Stock", "common stock": "Stock",
  etf: "ETF", etfs: "ETF", "exchange traded fund": "ETF", "exchange-traded fund": "ETF",
  bond: "Bond", bonds: "Bond", "corporate bond": "Bond", "government bond": "Bond", eurobond: "Bond", note: "Bond", notes: "Bond",
  "treasury bill": "Treasury bill", "treasury bills": "Treasury bill", "t-bill": "Treasury bill", "t-bills": "Treasury bill", tbill: "Treasury bill",
  "money market": "Money-market fund", "money-market": "Money-market fund", "money market fund": "Money-market fund", "money-market fund": "Money-market fund", mmf: "Money-market fund",
  "mutual fund": "Mutual fund", "mutual funds": "Mutual fund", fund: "Mutual fund", "unit trust": "Mutual fund", "collective investment scheme": "Mutual fund",
  reit: "REIT", reits: "REIT", "real estate investment trust": "REIT",
  "fixed deposit": "Fixed deposit", "term deposit": "Fixed deposit", deposit: "Fixed deposit", "time deposit": "Fixed deposit",
  other: "Other", cash: "Other",
};

/** One of ASSET_TYPES for a typed or imported asset type ("Equity" is a Stock), or null when it is not recognised. */
export function normalizeAssetType(value: string | null | undefined): (typeof ASSET_TYPES)[number] | null {
  const key = (value ?? "").trim().toLowerCase().replace(/\s+/g, " ");
  if (!key) return "Other";
  return ASSET_TYPE_ALIASES[key] ?? ASSET_TYPES.find((type) => type.toLowerCase() === key) ?? null;
}

export const CURRENCIES = ["AED", "AOA", "AUD", "BIF", "BRL", "BWP", "CAD", "CDF", "CHF", "CNY", "CVE", "DJF", "DZD", "EGP", "ERN", "ETB", "EUR", "GBP", "GHS", "GMD", "GNF", "HKD", "IDR", "INR", "JPY", "KES", "KMF", "KRW", "LRD", "LSL", "LYD", "MAD", "MGA", "MXN", "MRU", "MUR", "MWK", "MYR", "MZN", "NAD", "NGN", "NZD", "PHP", "PKR", "RWF", "SAR", "SCR", "SDG", "SGD", "SLE", "SOS", "SSP", "STN", "SZL", "THB", "TND", "TRY", "TZS", "UGX", "USD", "XAF", "XOF", "ZAR", "ZMW", "ZWG", "ZWL"];
