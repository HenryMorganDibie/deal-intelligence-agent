export type TreasuryBillQuote = {
  faceValue: number;
  discountRatePct: number;
  daysToMaturity: number;
};

export type BondQuote = {
  faceValue: number;
  annualCouponRatePct: number;
  cleanPrice: number;
  yearsToMaturity: number;
  paymentsPerYear?: number;
};

export type TreasuryBillMetrics = {
  purchasePrice: number;
  incomeAtMaturity: number;
  holdingPeriodReturnPct: number;
  simpleAnnualizedInvestmentYieldPct: number;
  bankDiscountYieldPct: number;
};

export type BondMetrics = {
  annualCouponIncome: number;
  currentYieldPct: number;
  yieldToMaturityPct: number | null;
  totalScheduledCoupons: number;
  maturityValue: number;
};

/**
 * Indicative primary-market T-bill math, not a quote.
 * Uses a simple 365-day discount convention; instrument-specific market conventions can differ.
 */
export function calculateTreasuryBill(input: TreasuryBillQuote): TreasuryBillMetrics | null {
  const { faceValue, discountRatePct, daysToMaturity } = input;
  if (!Number.isFinite(faceValue) || faceValue <= 0 ||
      !Number.isFinite(discountRatePct) || discountRatePct < 0 || discountRatePct >= 100 ||
      !Number.isInteger(daysToMaturity) || daysToMaturity < 1 || daysToMaturity > 366) return null;

  const purchasePrice = faceValue * (1 - (discountRatePct / 100) * daysToMaturity / 365);
  if (!Number.isFinite(purchasePrice) || purchasePrice <= 0) return null;
  const incomeAtMaturity = faceValue - purchasePrice;
  return {
    purchasePrice,
    incomeAtMaturity,
    holdingPeriodReturnPct: (incomeAtMaturity / purchasePrice) * 100,
    simpleAnnualizedInvestmentYieldPct: (incomeAtMaturity / purchasePrice) * (365 / daysToMaturity) * 100,
    bankDiscountYieldPct: (incomeAtMaturity / faceValue) * (365 / daysToMaturity) * 100,
  };
}

function bondPriceAtYield(faceValue: number, annualCouponRatePct: number, years: number, annualYieldPct: number, paymentsPerYear: number): number {
  const periods = Math.max(1, Math.round(years * paymentsPerYear));
  const coupon = faceValue * (annualCouponRatePct / 100) / paymentsPerYear;
  const periodYield = annualYieldPct / 100 / paymentsPerYear;
  if (periodYield <= -1) return Number.POSITIVE_INFINITY;
  let value = 0;
  for (let period = 1; period <= periods; period += 1) value += coupon / ((1 + periodYield) ** period);
  value += faceValue / ((1 + periodYield) ** periods);
  return value;
}

/** Calculates coupon income, current yield and an indicative yield to maturity using bisection. */
export function calculateBond(input: BondQuote): BondMetrics | null {
  const { faceValue, annualCouponRatePct, cleanPrice, yearsToMaturity, paymentsPerYear = 2 } = input;
  if (!Number.isFinite(faceValue) || faceValue <= 0 ||
      !Number.isFinite(annualCouponRatePct) || annualCouponRatePct < 0 || annualCouponRatePct > 100 ||
      !Number.isFinite(cleanPrice) || cleanPrice <= 0 ||
      !Number.isFinite(yearsToMaturity) || yearsToMaturity <= 0 || yearsToMaturity > 100 ||
      !Number.isInteger(paymentsPerYear) || paymentsPerYear < 1 || paymentsPerYear > 12) return null;

  const annualCouponIncome = faceValue * annualCouponRatePct / 100;
  const currentYieldPct = (annualCouponIncome / cleanPrice) * 100;
  let low = -0.99 * paymentsPerYear;
  let high = 10 * paymentsPerYear;
  const target = cleanPrice;
  const lowPrice = bondPriceAtYield(faceValue, annualCouponRatePct, yearsToMaturity, low * 100, paymentsPerYear);
  const highPrice = bondPriceAtYield(faceValue, annualCouponRatePct, yearsToMaturity, high * 100, paymentsPerYear);
  if (!Number.isFinite(lowPrice) || lowPrice < target || highPrice > target) {
    return {
      annualCouponIncome,
      currentYieldPct,
      yieldToMaturityPct: null,
      totalScheduledCoupons: Math.max(1, Math.round(yearsToMaturity * paymentsPerYear)),
      maturityValue: faceValue,
    };
  }
  for (let i = 0; i < 120; i += 1) {
    const mid = (low + high) / 2;
    const price = bondPriceAtYield(faceValue, annualCouponRatePct, yearsToMaturity, mid * 100, paymentsPerYear);
    if (price > target) low = mid;
    else high = mid;
  }
  return {
    annualCouponIncome,
    currentYieldPct,
    yieldToMaturityPct: ((low + high) / 2) * 100,
    totalScheduledCoupons: Math.max(1, Math.round(yearsToMaturity * paymentsPerYear)),
    maturityValue: faceValue,
  };
}
