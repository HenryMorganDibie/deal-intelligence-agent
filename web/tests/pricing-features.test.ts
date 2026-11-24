import { test } from "node:test";
import * as assert from "node:assert/strict";
import { planFeatures, type CatalogPlan } from "../lib/pricing";

const plan = (over: Partial<CatalogPlan>): CatalogPlan =>
  ({ id: "pro", label: "Pro", monthly_requests: 3000, seats: 1, self_serve: true, price_month_ngn: 7500, price_year_ngn: 75000, ...over });

test("a plan's feature list quotes the limits the owner set", () => {
  const f = planFeatures(plan({ ai_monthly: 150, alerts_max: 120, monthly_requests: 5000, exports: true })).features;
  assert.ok(f.includes("150 company briefs and research runs a month, no daily cap"));
  assert.ok(f.includes("120 alerts by email, Slack or Teams"));
  assert.ok(f.includes("5,000 API requests a month"));
  assert.ok(f.includes("CSV export of the screener"));
});

test("without limits in the catalog the written list stands; no export drops the line", () => {
  assert.ok(planFeatures(plan({})).features.includes("3,000 API requests a month"));
  assert.ok(!planFeatures(plan({ exports: false })).features.some((x) => x.includes("CSV export")));
  const team = planFeatures(plan({ id: "team", ai_monthly: 600, alerts_max: 700 })).features;
  assert.ok(team.includes("600 briefs and research runs a month") && team.includes("700 alerts"));
});
