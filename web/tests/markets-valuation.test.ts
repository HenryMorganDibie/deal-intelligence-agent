import { test } from "node:test";
import * as assert from "node:assert/strict";
import {
  calculateDcfPerShare,
  calculateDdmPerShare,
  validHttpUrl,
  validPastDate,
} from "../lib/markets-valuation";

test("DCF returns a finite per-share value for valid operating-company inputs", () => {
  const value = calculateDcfPerShare(100, 8, 12, 3, 20, 10, 100);
  assert.ok(value != null && Number.isFinite(value) && value > 0);
});

test("DCF value decreases when the discount rate rises", () => {
  const lowerRate = calculateDcfPerShare(100, 8, 10, 3, 20, 10, 100);
  const higherRate = calculateDcfPerShare(100, 8, 15, 3, 20, 10, 100);
  assert.ok(lowerRate != null && higherRate != null && lowerRate > higherRate);
});

test("DCF rejects negative cash flow, negative cash/debt inputs and invalid terminal assumptions", () => {
  assert.equal(calculateDcfPerShare(-1, 8, 12, 3, 20, 10, 100), null);
  assert.equal(calculateDcfPerShare(100, 8, 12, 3, -1, 10, 100), null);
  assert.equal(calculateDcfPerShare(100, 8, 12, 3, 20, 10, 0), null);
  assert.equal(calculateDcfPerShare(100, 8, 3, 3, 20, 10, 100), null);
});

test("DDM returns a finite value and falls as cost of equity rises", () => {
  const lowerRate = calculateDdmPerShare(5, 5, 10, 3);
  const higherRate = calculateDdmPerShare(5, 5, 15, 3);
  assert.ok(lowerRate != null && higherRate != null && lowerRate > higherRate && higherRate > 0);
});

test("DDM rejects absent dividends and terminal growth at or above cost of equity", () => {
  assert.equal(calculateDdmPerShare(0, 5, 12, 3), null);
  assert.equal(calculateDdmPerShare(5, 5, 3, 3), null);
});

test("source URLs must use HTTP or HTTPS", () => {
  assert.equal(validHttpUrl("https://example.com/filing.pdf"), true);
  assert.equal(validHttpUrl("http://example.com/quote"), true);
  assert.equal(validHttpUrl("javascript:alert(1)"), false);
  assert.equal(validHttpUrl("not a URL"), false);
});

test("dates must be real ISO dates in the past or today", () => {
  assert.equal(validPastDate("2020-12-31"), true);
  assert.equal(validPastDate("2024-02-30"), false);
  assert.equal(validPastDate("not-a-date"), false);
  const tomorrow = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10);
  assert.equal(validPastDate(tomorrow), false);
});
