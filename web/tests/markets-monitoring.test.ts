import { test } from "node:test";
import * as assert from "node:assert/strict";
import { calculateValuationChangeAlerts, fetchMonitoringEventHistory, matchPortfolioEvents, type MonitoringEvent, type MonitoringHolding } from "../lib/markets-monitoring";
import type { SavedValuationSnapshot } from "../lib/markets-portfolio";

const holdings: MonitoringHolding[] = [
  { id: "ng", name: "Dangote Cement", ticker: "DANGCEM", country: "Nigeria" },
  { id: "ke", name: "Safaricom", ticker: "SCOM", country: "Kenya" },
  { id: "generic", name: "Standard Group", ticker: "STAN", country: "Kenya" },
];

function event(id: string, headline: string, day: string | null = "2026-10-24"): MonitoringEvent {
  return {
    id, day, headline, publisher: "Example Publisher", url: "https://example.com/story",
    signal_type: "corporate_event", direction: null, country: null, sector: null,
  };
}

test("portfolio event matcher uses exact company names and ticker tokens", () => {
  const result = matchPortfolioEvents(holdings, [
    event("1", "Dangote Cement reports higher revenue"),
    event("2", "SCOM announces new fibre investment"),
    event("3", "A mountain rescue operation is underway"),
  ]);
  assert.equal(result.length, 2);
  assert.deepEqual(result[0].holdings.map((holding) => holding.id), ["ng"]);
  assert.equal(result[0].holdings[0].reason, "company name");
  assert.equal(result[1].holdings[0].reason, "ticker");
});

test("ticker matching respects token boundaries and avoids substring matches", () => {
  const result = matchPortfolioEvents(
    [{ id: "1", name: "Mountain Holdings", ticker: "MTN" }],
    [event("1", "A mountain road is closed"), event("2", "MTN Group expands its network")],
  );
  assert.deepEqual(result.map((item) => item.event.id), ["2"]);
});

test("short single-word names do not generate weak name-only matches", () => {
  const result = matchPortfolioEvents(
    [{ id: "1", name: "Shell", ticker: "" }],
    [event("1", "Shell reports a quarterly update")],
  );
  assert.equal(result.length, 0);
});

test("matches are sorted newest first and duplicate holdings are retained as separate positions", () => {
  const result = matchPortfolioEvents(
    [
      { id: "1", name: "Dangote Cement", ticker: "DANGCEM" },
      { id: "2", name: "Dangote Cement", ticker: "DANGCEM" },
    ],
    [event("old", "Dangote Cement updates outlook", "2026-10-01"), event("new", "Dangote Cement reports results", "2026-10-24")],
  );
  assert.deepEqual(result.map((item) => item.event.id), ["new", "old"]);
  assert.equal(result[0].holdings.length, 2);
});

test("empty portfolio or empty event feed produces no matches", () => {
  assert.deepEqual(matchPortfolioEvents([], [event("1", "Dangote Cement reports results")]), []);
  assert.deepEqual(matchPortfolioEvents(holdings, []), []);
});

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

test("portfolio monitoring suppresses duplicate event records with the same identifier", () => {
  const duplicate = event("duplicate", "Dangote Cement reports quarterly results");
  const result = matchPortfolioEvents(holdings, [duplicate, { ...duplicate }]);
  assert.equal(result.length, 1);
});


test("monitoring fetches every page when the event feed exceeds one page", async () => {
  const all = Array.from({ length: 1201 }, (_, index) => event(String(index), `Company event ${index}`));
  const requests: { offset: number; limit: number }[] = [];
  const result = await fetchMonitoringEventHistory(async (offset, limit) => {
    requests.push({ offset, limit });
    return { count: all.length, events: all.slice(offset, offset + limit) };
  });
  assert.equal(result.events.length, 1201);
  assert.equal(result.totalAvailable, 1201);
  assert.equal(result.truncated, false);
  assert.deepEqual(requests, [
    { offset: 0, limit: 500 },
    { offset: 500, limit: 500 },
    { offset: 1000, limit: 500 },
  ]);
});

test("monitoring reports a bounded partial result instead of implying complete coverage", async () => {
  const all = Array.from({ length: 5200 }, (_, index) => event(String(index), `Company event ${index}`));
  const result = await fetchMonitoringEventHistory(async (offset, limit) => ({
    count: all.length,
    events: all.slice(offset, offset + limit),
  }));
  assert.equal(result.events.length, 5000);
  assert.equal(result.totalAvailable, 5200);
  assert.equal(result.truncated, true);
});

test("monitoring propagates feed failures and rejects invalid page settings", async () => {
  await assert.rejects(
    fetchMonitoringEventHistory(async () => { throw new Error("feed unavailable"); }),
    /feed unavailable/,
  );
  await assert.rejects(
    fetchMonitoringEventHistory(async () => ({ events: [] }), 501, 1000),
    /page size/,
  );
});
