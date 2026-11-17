import { test } from "node:test";
import * as assert from "node:assert/strict";
import { calculateValuationChangeAlerts } from "../lib/markets-monitoring";
import type { SavedValuationSnapshot } from "../lib/markets-portfolio";

function valuationSnapshot(overrides: Partial<SavedValuationSnapshot> = {}): SavedValuationSnapshot {
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
    statementPeriod: "2025-12-31",
    quotePrice: 100,
    quoteDate: "2026-10-20",
    quoteSourceUrl: "https://example.com/quote",
    bearPerShare: 90,
    basePerShare: 100,
    bullPerShare: 110,
    calculatedAt: "2026-10-21T12:00:00.000Z",
    ...overrides,
  };
}

test("valuation monitoring flags material changes in same-company saved estimates", () => {
  const alerts = calculateValuationChangeAlerts([
    valuationSnapshot({ id: "old", basePerShare: 100, calculatedAt: "2026-10-21T12:00:00.000Z" }),
    valuationSnapshot({ id: "new", basePerShare: 115, calculatedAt: "2026-10-24T12:00:00.000Z", statementPeriod: "2026-06-30" }),
  ]);
  assert.equal(alerts.length, 1);
  assert.equal(alerts[0].company, "Example Bank");
  assert.ok(Math.abs(alerts[0].changePct - 15) < 1e-9);
  assert.equal(alerts[0].previousBasePerShare, 100);
  assert.equal(alerts[0].currentBasePerShare, 115);
});

test("valuation monitoring ignores small changes and keeps countries separate", () => {
  const alerts = calculateValuationChangeAlerts([
    valuationSnapshot({ id: "old", basePerShare: 100, calculatedAt: "2026-10-21T12:00:00.000Z" }),
    valuationSnapshot({ id: "small", basePerShare: 105, calculatedAt: "2026-10-24T12:00:00.000Z" }),
    valuationSnapshot({ id: "ke", country: "Kenya", basePerShare: 150, calculatedAt: "2026-10-24T13:00:00.000Z" }),
  ]);
  assert.equal(alerts.length, 0);
});

test("valuation monitoring does not compare different model methods or currencies", () => {
  const alerts = calculateValuationChangeAlerts([
    valuationSnapshot({ id: "old", basePerShare: 100, calculatedAt: "2026-10-21T12:00:00.000Z" }),
    valuationSnapshot({ id: "method", basePerShare: 150, method: "dcf", modelFit: "standard-operating-company", calculatedAt: "2026-10-24T12:00:00.000Z" }),
  ]);
  assert.equal(alerts.length, 0);
});
