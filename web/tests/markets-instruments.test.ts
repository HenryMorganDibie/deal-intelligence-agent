import test from "node:test";
import * as assert from "node:assert/strict";
import { calculateBond, calculateTreasuryBill } from "../lib/markets-instruments";

test("Treasury bill separates purchase discount from investment yield", () => {
  const result = calculateTreasuryBill({ faceValue: 1000, discountRatePct: 10, daysToMaturity: 182 });
  assert.ok(result);
  assert.ok(result.purchasePrice < 1000);
  assert.ok(result.incomeAtMaturity > 0);
  assert.ok(result.simpleAnnualizedInvestmentYieldPct > result.bankDiscountYieldPct);
  assert.ok(Math.abs(result.purchasePrice - (1000 * (1 - 0.1 * 182 / 365))) < 1e-8);
});

test("Treasury bill rejects invalid rates, tenor and face value", () => {
  assert.equal(calculateTreasuryBill({ faceValue: 0, discountRatePct: 10, daysToMaturity: 91 }), null);
  assert.equal(calculateTreasuryBill({ faceValue: 1000, discountRatePct: 100, daysToMaturity: 91 }), null);
  assert.equal(calculateTreasuryBill({ faceValue: 1000, discountRatePct: 10, daysToMaturity: 0 }), null);
});

test("bond calculates coupon income, current yield and yield to maturity", () => {
  const result = calculateBond({ faceValue: 1000, annualCouponRatePct: 10, cleanPrice: 1000, yearsToMaturity: 5 });
  assert.ok(result);
  assert.equal(result.annualCouponIncome, 100);
  assert.equal(result.currentYieldPct, 10);
  assert.ok(result.yieldToMaturityPct != null);
  assert.ok(Math.abs((result.yieldToMaturityPct ?? 0) - 10) < 0.01);
  assert.equal(result.totalScheduledCoupons, 10);
});

test("premium and discount bond yields respond to price", () => {
  const discount = calculateBond({ faceValue: 1000, annualCouponRatePct: 8, cleanPrice: 900, yearsToMaturity: 5 });
  const premium = calculateBond({ faceValue: 1000, annualCouponRatePct: 8, cleanPrice: 1100, yearsToMaturity: 5 });
  assert.ok(discount?.yieldToMaturityPct != null && discount.yieldToMaturityPct > 8);
  assert.ok(premium?.yieldToMaturityPct != null && premium.yieldToMaturityPct < 8);
});

test("bond rejects invalid inputs", () => {
  assert.equal(calculateBond({ faceValue: 1000, annualCouponRatePct: 8, cleanPrice: -1, yearsToMaturity: 5 }), null);
  assert.equal(calculateBond({ faceValue: 1000, annualCouponRatePct: 8, cleanPrice: 1000, yearsToMaturity: 0 }), null);
});
