import { test } from "node:test";
import * as assert from "node:assert/strict";
import {
  calculateExposureRows,
  calculatePortfolioTotals,
  convertToBase,
  type PortfolioPosition,
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
