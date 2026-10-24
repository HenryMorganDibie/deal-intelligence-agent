import { test } from "node:test";
import * as assert from "node:assert/strict";
import { matchPortfolioEvents, type MonitoringEvent, type MonitoringHolding } from "../lib/markets-monitoring";

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
