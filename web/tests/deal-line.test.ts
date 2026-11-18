import { test } from "node:test";
import * as assert from "node:assert/strict";
import { dealLine, type DealLineInput } from "../lib/deal-line";

const money = (v: number) => `$${v / 1e6}m`;
const deal = (over: Partial<DealLineInput>): DealLineInput =>
  ({ deal_type: "acquisition", stage: "completed", amount_usd: null, investors: [], buyer: null, seller: null, ...over });

test("talks never read as a done deal", () => {
  assert.equal(dealLine(deal({ stage: "rumoured", buyer: "MTN" }), money), "in talks to be acquired by MTN");
  assert.equal(dealLine(deal({ stage: "announced", buyer: "Elektron" }), money), "to be acquired by Elektron");
  assert.equal(dealLine(deal({ stage: "completed", buyer: "Danone" }), money), "acquired by Danone");
});

test("a fund that has not closed is raising, not closed", () => {
  assert.equal(dealLine(deal({ deal_type: "fund_raise", stage: "announced", amount_usd: 50e6 }), money), "raising $50m for a fund");
  assert.equal(dealLine(deal({ deal_type: "fund_raise", stage: "completed", amount_usd: 26e6 }), money), "closed $26m in commitments");
});

test("listings, exits and raises follow the stage", () => {
  assert.equal(dealLine(deal({ deal_type: "ipo", stage: "announced" }), money), "plans to list");
  assert.equal(dealLine(deal({ deal_type: "ipo", stage: "completed", amount_usd: 4e6 }), money), "listed, raising $4m");
  assert.equal(dealLine(deal({ deal_type: "exit", stage: "announced", seller: "Old Mutual" }), money), "stake to be sold by Old Mutual");
  assert.equal(dealLine(deal({ deal_type: "equity_funding", investors: ["A", "B", "C"], amount_usd: 5e6 }), money), "raised $5m from A, B");
  assert.equal(dealLine(deal({ deal_type: "equity_funding", stage: null }), money), "raised new funding");
});
