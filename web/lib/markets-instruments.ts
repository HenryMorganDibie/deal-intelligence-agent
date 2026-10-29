// Treasury bill and bond arithmetic, and the types of /api/markets/instruments.

export type RateType = "discount" | "yield";

export type TreasuryBillQuote = {
  faceValue: number;
  ratePct: number;
  rateType: RateType;
  daysToMaturity: number;
  basis?: 360 | 364 | 365;
};

export type BondQuote = {
  faceValue: number;
  annualCouponRatePct: number;
  pricePer100: number;
  yearsToMaturity: number;
  paymentsPerYear?: number;
};

export type TreasuryBillMetrics = {
  purchasePrice: number;
  incomeAtMaturity: number;
  holdingPeriodReturnPct: number;
  investmentYieldPct: number;
  discountRatePct: number;
};

export type BondMetrics = {
  purchaseCost: number;
  annualCouponIncome: number;
  currentYieldPct: number;
  yieldToMaturityPct: number | null;
  totalScheduledCoupons: number;
  maturityValue: number;
};

/**
 * Price and return of a Treasury bill from a quoted rate. A discount rate prices as F * (1 - d * t / B), a yield as
 * F / (1 + y * t / B). Nigeria quotes a discount rate on 365 days (the CBN's true yields match this basis), Ghana a
 * yield on 364 days, the WAEMU states a discount rate on 360 days.
 */
export function calculateTreasuryBill(input: TreasuryBillQuote): TreasuryBillMetrics | null {
  const { faceValue, ratePct, rateType, daysToMaturity, basis = 365 } = input;
  if (!Number.isFinite(faceValue) || faceValue <= 0 ||
      !Number.isFinite(ratePct) || ratePct < 0 || ratePct >= 100 ||
      !Number.isInteger(daysToMaturity) || daysToMaturity < 1 || daysToMaturity > 366 ||
      ![360, 364, 365].includes(basis)) return null;

  const r = ratePct / 100;
  const purchasePrice = rateType === "discount"
    ? faceValue * (1 - r * daysToMaturity / basis)
    : faceValue / (1 + r * daysToMaturity / basis);
  if (!Number.isFinite(purchasePrice) || purchasePrice <= 0) return null;
  const incomeAtMaturity = faceValue - purchasePrice;
  return {
    purchasePrice,
    incomeAtMaturity,
    holdingPeriodReturnPct: (incomeAtMaturity / purchasePrice) * 100,
    investmentYieldPct: (incomeAtMaturity / purchasePrice) * (basis / daysToMaturity) * 100,
    discountRatePct: (incomeAtMaturity / faceValue) * (basis / daysToMaturity) * 100,
  };
}

function bondPriceAtYield(faceValue: number, annualCouponRatePct: number, periods: number, annualYieldPct: number, paymentsPerYear: number): number {
  const coupon = faceValue * (annualCouponRatePct / 100) / paymentsPerYear;
  const periodYield = annualYieldPct / 100 / paymentsPerYear;
  if (periodYield <= -1) return Number.POSITIVE_INFINITY;
  let value = 0;
  for (let period = 1; period <= periods; period += 1) value += coupon / ((1 + periodYield) ** period);
  return value + faceValue / ((1 + periodYield) ** periods);
}

/**
 * Coupon income, current yield and yield to maturity (by bisection) for a fixed-coupon bond bought on a coupon date.
 * The price is per 100 of face value, as bonds are quoted; accrued interest between coupons is not modelled.
 */
export function calculateBond(input: BondQuote): BondMetrics | null {
  const { faceValue, annualCouponRatePct, pricePer100, yearsToMaturity, paymentsPerYear = 2 } = input;
  if (!Number.isFinite(faceValue) || faceValue <= 0 ||
      !Number.isFinite(annualCouponRatePct) || annualCouponRatePct < 0 || annualCouponRatePct > 100 ||
      !Number.isFinite(pricePer100) || pricePer100 <= 0 || pricePer100 > 1000 ||
      !Number.isFinite(yearsToMaturity) || yearsToMaturity <= 0 || yearsToMaturity > 100 ||
      !Number.isInteger(paymentsPerYear) || paymentsPerYear < 1 || paymentsPerYear > 12) return null;

  const purchaseCost = faceValue * pricePer100 / 100;
  const annualCouponIncome = faceValue * annualCouponRatePct / 100;
  const periods = Math.max(1, Math.round(yearsToMaturity * paymentsPerYear));
  const base = { purchaseCost, annualCouponIncome, currentYieldPct: (annualCouponIncome / purchaseCost) * 100,
    totalScheduledCoupons: periods, maturityValue: faceValue };
  let low = -0.99 * paymentsPerYear;
  let high = 10 * paymentsPerYear;
  const lowPrice = bondPriceAtYield(faceValue, annualCouponRatePct, periods, low * 100, paymentsPerYear);
  const highPrice = bondPriceAtYield(faceValue, annualCouponRatePct, periods, high * 100, paymentsPerYear);
  if (!Number.isFinite(lowPrice) || lowPrice < purchaseCost || highPrice > purchaseCost) return { ...base, yieldToMaturityPct: null };
  for (let i = 0; i < 120; i += 1) {
    const mid = (low + high) / 2;
    if (bondPriceAtYield(faceValue, annualCouponRatePct, periods, mid * 100, paymentsPerYear) > purchaseCost) low = mid;
    else high = mid;
  }
  return { ...base, yieldToMaturityPct: ((low + high) / 2) * 100 };
}

export type EtfRow = {
  symbol: string;
  name: string;
  exposure: string;
  currency: string;
  price: number;
  chg_1d: number | null;
  ytd: number | null;
  ytd_suspect?: boolean;
  volume: number | null;
  date: string | null;
  quote_time: string | null;
};

// rate_type "tender" (South Africa) and "average" (Seychelles) are published without a stated convention, so they
// are shown as published and never converted.
export type TbillRow = {
  tenor_days: number;
  tenor_label?: string;
  rate_type: RateType | "tender" | "average";
  rate: number;
  true_yield?: number | null;
  discount_rate?: number | null;
  price?: number | null;
  basis: 360 | 364 | 365 | null;
  auction_date: string | null;
  settlement_date?: string | null;
  next_auction_date?: string | null;
  maturity_date?: string | null;
  offered_mn?: number | null;
  subscribed_mn?: number | null;
  allotted_mn?: number | null;
};

export type TbillBlock = {
  country: string;
  country_name?: string;
  currency: string;
  issuer: string;
  source: string;
  source_url: string;
  captured_at?: string;
  rows: TbillRow[];
  bonds?: { name: string; yield: number; date: string | null }[];
};

export type PropertyRow = {
  exchange: string;
  symbol: string;
  name: string;
  price: number;
  currency?: string | null;
  chg_1d: number | null;
  ytd: number | null;
  mcap_usd: number | null;
  dividend_yield: number | null;
  date: string | null;
  delayed?: boolean;
  quote_time?: string | null;
};

export type PolicyRate = { country: string; country_name: string; rate: number; as_of: string | null; freshness: string | null; source: string | null };

export type Instruments = {
  etfs: { rows: EtfRow[]; delay?: string; captured_at?: string };
  tbills: TbillBlock[];
  property: PropertyRow[];
  policy_rates: PolicyRate[];
  method: string;
};
