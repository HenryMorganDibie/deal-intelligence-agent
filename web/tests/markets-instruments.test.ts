import { test } from "node:test";
import * as assert from "node:assert/strict";
import { calculateBond, calculateTreasuryBill } from "../lib/markets-instruments";

test("discount-quoted bill prices off face value and matches the CBN true yield", () => {
  const r = calculateTreasuryBill({ faceValue: 1000, ratePct: 15.4, rateType: "discount", daysToMaturity: 91, basis: 365 });
  assert.ok(r);
  assert.ok(Math.abs(r.purchasePrice - 1000 * (1 - 0.154 * 91 / 365)) < 1e-8);
  assert.ok(Math.abs(r.investmentYieldPct - 16.0149) < 0.001);       // CBN-style true yield
  assert.ok(Math.abs(r.discountRatePct - 15.4) < 1e-8);
  assert.ok(r.investmentYieldPct > r.discountRatePct);
});

test("yield-quoted bill discounts to a price that earns that yield", () => {
  const r = calculateTreasuryBill({ faceValue: 100, ratePct: 9.0288, rateType: "yield", daysToMaturity: 364, basis: 364 });
  assert.ok(r);
  assert.ok(Math.abs(r.purchasePrice - 100 / 1.090288) < 1e-8);
  assert.ok(Math.abs(r.investmentYieldPct - 9.0288) < 1e-8);
});

test("Treasury bill rejects invalid rates, tenor, face value and basis", () => {
  assert.equal(calculateTreasuryBill({ faceValue: 0, ratePct: 10, rateType: "discount", daysToMaturity: 91 }), null);
  assert.equal(calculateTreasuryBill({ faceValue: 1000, ratePct: 100, rateType: "discount", daysToMaturity: 91 }), null);
  assert.equal(calculateTreasuryBill({ faceValue: 1000, ratePct: 10, rateType: "discount", daysToMaturity: 0 }), null);
  assert.equal(calculateTreasuryBill({ faceValue: 1000, ratePct: 10, rateType: "discount", daysToMaturity: 91, basis: 300 as 365 }), null);
});

test("bond at par yields its coupon; price is per 100 of face", () => {
  const r = calculateBond({ faceValue: 100000, annualCouponRatePct: 10, pricePer100: 100, yearsToMaturity: 5 });
  assert.ok(r);
  assert.equal(r.purchaseCost, 100000);
  assert.equal(r.annualCouponIncome, 10000);
  assert.equal(r.currentYieldPct, 10);
  assert.ok(r.yieldToMaturityPct != null && Math.abs(r.yieldToMaturityPct - 10) < 0.01);
  assert.equal(r.totalScheduledCoupons, 10);
});

test("discount and premium bond yields respond to price", () => {
  const discount = calculateBond({ faceValue: 1000, annualCouponRatePct: 8, pricePer100: 90, yearsToMaturity: 5 });
  const premium = calculateBond({ faceValue: 1000, annualCouponRatePct: 8, pricePer100: 110, yearsToMaturity: 5 });
  assert.ok(discount?.yieldToMaturityPct != null && discount.yieldToMaturityPct > 8);
  assert.ok(premium?.yieldToMaturityPct != null && premium.yieldToMaturityPct < 8);
});

test("bond rejects invalid inputs", () => {
  assert.equal(calculateBond({ faceValue: 1000, annualCouponRatePct: 8, pricePer100: -1, yearsToMaturity: 5 }), null);
  assert.equal(calculateBond({ faceValue: 1000, annualCouponRatePct: 8, pricePer100: 100, yearsToMaturity: 0 }), null);
});
