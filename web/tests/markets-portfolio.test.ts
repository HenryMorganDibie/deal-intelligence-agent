import { test } from "node:test";
import * as assert from "node:assert/strict";
import {
  calculateExposureRows,
  calculatePortfolioTotals,
  convertToBase,
  calculatePortfolioValuationReviews,
  calculatePortfolioValuationSummary,
  isSavedValuation,
  type PortfolioPosition,
  type SavedValuationSnapshot,
} from "../lib/markets-portfolio";

const sample: PortfolioPosition[] = [
  { quantity: 2, costPerUnit: 10, currentPrice: 15, fxToBase: 1, country: "Nigeria", sector: "Consumer", assetType: "Stock", currency: "NGN" },
  { quantity: 3, costPerUnit: 100, currentPrice: 200, fxToBase: 0.5, country: "Kenya", sector: "Banking", assetType: "Stock", currency: "KES" },
  { quantity: 5, costPerUnit: 20, currentPrice: null, fxToBase: 1, country: "Nigeria", sector: "Consumer", assetType: "Bond", currency: "NGN" },
  { quantity: 1, costPerUnit: 100, currentPrice: 20, fxToBase: null, country: "South Africa", sector: "Mining", assetType: "Stock", currency: "ZAR" },
];

test("empty portfolio totals are zero and contain no missing-input counts", () => {
  const totals = calculatePortfolioTotals([]);
  assert.equal(totals.pricedHoldings.length, 0);
  assert.equal(totals.totalCurrentValue, 0);
  assert.equal(totals.totalCostOfPriced, 0);
  assert.equal(totals.gainLoss, 0);
  assert.equal(totals.missingPriceCount, 0);
  assert.equal(totals.missingFxCount, 0);
});

test("portfolio totals use only priced and FX-converted holdings", () => {
  const totals = calculatePortfolioTotals(sample);
  assert.equal(totals.pricedHoldings.length, 2);
  assert.equal(totals.totalCurrentValue, 330);
  assert.equal(totals.totalCostOfPriced, 170);
  assert.equal(totals.gainLoss, 160);
  assert.equal(totals.missingPriceCount, 1);
  assert.equal(totals.missingFxCount, 1);
});

test("base-currency conversion rejects missing and invalid FX rates", () => {
  assert.equal(convertToBase(100, 0.5), 50);
  assert.equal(convertToBase(100, null), null);
  assert.equal(convertToBase(100, 0), null);
  assert.equal(convertToBase(Number.NaN, 1), null);
});

test("exposure rows exclude unpriced or unconverted holdings and sum to one", () => {
  const rows = calculateExposureRows(sample, "country");
  assert.equal(rows.length, 2);
  assert.equal(rows[0].label, "Kenya");
  assert.equal(rows[0].value, 300);
  assert.ok(Math.abs(rows.reduce((sum, row) => sum + row.share, 0) - 1) < 1e-12);
});

test("exposure grouping supports sector, asset type and holding currency", () => {
  assert.equal(calculateExposureRows(sample, "sector")[0].label, "Banking");
  assert.equal(calculateExposureRows(sample, "assetType").length, 1);
  assert.equal(calculateExposureRows(sample, "currency")[0].label, "KES");
});

function dayOffset(days: number): string {
  return new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
}

const valuationHolding = {
  id: "holding-1",
  name: "Example Bank",
  ticker: "EXBANK",
  country: "Nigeria",
  sector: "Banking",
  assetType: "Stock",
  currency: "NGN",
  quantity: 10,
  costPerUnit: 80,
  currentPrice: 100,
  fxToBase: 1,
  priceAsOf: dayOffset(0),
  fxAsOf: null,
};

function savedValuation(overrides: Partial<SavedValuationSnapshot> = {}): SavedValuationSnapshot {
  return {
    id: "valuation-1",
    company: "Example Bank",
    ticker: "EXBANK",
    country: "Nigeria",
    method: "ddm",
    modelFit: "financial-institution",
    modelFitConfirmed: true,
    currency: "NGN",
    statementSourceUrl: "https://example.com/annual-report",
    statementPeriod: dayOffset(-365),
    quotePrice: 100,
    quoteDate: dayOffset(0),
    quoteSourceUrl: "https://example.com/quote",
    bearPerShare: 110,
    basePerShare: 120,
    bullPerShare: 130,
    calculatedAt: new Date().toISOString(),
    ...overrides,
  };
}

test("saved valuation is accepted only with a suitable shape and sourced inputs", () => {
  assert.equal(isSavedValuation(savedValuation()), true);
  assert.equal(isSavedValuation(savedValuation({ statementSourceUrl: "javascript:alert(1)" })), false);
  assert.equal(isSavedValuation(savedValuation({ quoteDate: "2099-01-01" })), false);
});

test("portfolio valuation review only accepts a fresh, matching quote and suitable model", () => {
  const review = calculatePortfolioValuationReviews([valuationHolding], [savedValuation()], "NGN")[0];
  assert.equal(review.status, "ready");
  assert.equal(review.conclusion, "Potentially undervalued on these assumptions");
  assert.ok(review.gapPct != null && Math.abs(review.gapPct - 20) < 1e-9);
  assert.equal(review.weightedEligible, true);
  const summary = calculatePortfolioValuationSummary([review]);
  assert.equal(summary.matchedCount, 1);
  assert.equal(summary.weightedCount, 1);
  assert.ok(summary.weightedGapPct != null && Math.abs(summary.weightedGapPct - 20) < 1e-9);
  assert.equal(summary.potentiallyUndervaluedCount, 1);
});

test("portfolio valuation review blocks stale quotes, currency mismatch and price mismatch", () => {
  const stale = calculatePortfolioValuationReviews([valuationHolding], [savedValuation({ quoteDate: dayOffset(-10) })], "NGN")[0];
  assert.equal(stale.status, "stale-inputs");
  const currency = calculatePortfolioValuationReviews([valuationHolding], [savedValuation({ currency: "KES" })], "NGN")[0];
  assert.equal(currency.status, "currency-mismatch");
  const price = calculatePortfolioValuationReviews([{ ...valuationHolding, currentPrice: 104 }], [savedValuation()], "NGN")[0];
  assert.equal(price.status, "portfolio-price-mismatch");
});

test("portfolio valuation review refuses missing quotes, unsuitable models and non-positive scenarios", () => {
  const missing = calculatePortfolioValuationReviews([valuationHolding], [savedValuation({ quotePrice: null, quoteDate: null, quoteSourceUrl: null })], "NGN")[0];
  assert.equal(missing.status, "missing-quote");
  const unsuitable = calculatePortfolioValuationReviews([valuationHolding], [savedValuation({ method: "dcf", modelFit: "financial-institution" })], "NGN")[0];
  assert.equal(unsuitable.status, "model-not-suitable");
  const invalid = calculatePortfolioValuationReviews([valuationHolding], [savedValuation({ bearPerShare: -5 })], "NGN")[0];
  assert.equal(invalid.status, "invalid-estimate");
});

test("foreign holdings need fresh FX dates to contribute to weighted portfolio gap", () => {
  const foreignHolding = {
    ...valuationHolding,
    currency: "KES",
    fxToBase: 0.01,
    fxAsOf: null,
  };
  const review = calculatePortfolioValuationReviews([foreignHolding], [savedValuation({ currency: "KES" })], "NGN")[0];
  assert.equal(review.status, "ready");
  assert.equal(review.weightedEligible, false);
  const summary = calculatePortfolioValuationSummary([review]);
  assert.equal(summary.matchedCount, 1);
  assert.equal(summary.weightedCount, 0);
  assert.equal(summary.weightedGapPct, null);
});

test("saved valuation matching respects African market country context", () => {
  const otherCountry = calculatePortfolioValuationReviews(
    [valuationHolding],
    [savedValuation({ country: "Kenya" })],
    "NGN",
  )[0];
  assert.equal(otherCountry.status, "no-saved-valuation");
});
