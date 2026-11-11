/** Plans as the pricing page and the account's billing page show them. Prices come from the database
 * (billing_catalog); what each plan includes is described here. */

export type CatalogPlan = {
  id: "free" | "pro" | "team" | "institutional";
  label: string;
  monthly_requests: number;
  seats: number;
  self_serve: boolean;
  price_month_ngn: number | null;
  price_year_ngn: number | null;
  price_month_usd?: number | null;
  price_year_usd?: number | null;
  /** Currencies offered at checkout (dollars only once the Paystack account accepts them). */
  currencies?: Currency[];
};

export type Currency = "NGN" | "USD";

/** Used only if the database cannot be reached, so the page still renders; the database is the source of truth. */
export const FALLBACK_CATALOG: CatalogPlan[] = [
  { id: "free", label: "Free", monthly_requests: 30, seats: 1, self_serve: false, price_month_ngn: 0, price_year_ngn: 0, price_month_usd: 0, price_year_usd: 0, currencies: ["NGN"] },
  { id: "pro", label: "Pro", monthly_requests: 3000, seats: 1, self_serve: true, price_month_ngn: 7500, price_year_ngn: 75000, price_month_usd: 7, price_year_usd: 70, currencies: ["NGN"] },
  { id: "team", label: "Team", monthly_requests: 15000, seats: 5, self_serve: true, price_month_ngn: 25000, price_year_ngn: 250000, price_month_usd: 24, price_year_usd: 240, currencies: ["NGN"] },
  { id: "institutional", label: "Institutional", monthly_requests: 100000, seats: 25, self_serve: false, price_month_ngn: null, price_year_ngn: null, price_month_usd: null, price_year_usd: null, currencies: ["NGN"] },
];

export const PLAN_FEATURES: Record<CatalogPlan["id"], { blurb: string; features: string[] }> = {
  free: {
    blurb: "Explore African private markets, no time limit.",
    features: ["Browse every deal, company, investor and fund", "Markets: 1,600+ listed shares, sectors, currencies, Treasury bills",
      "Comparables, country risk and financial statements", "30 company briefs and research runs a month to try",
      "Public deal pages to share", "30 API requests a month"],
  },
  pro: {
    blurb: "For analysts, founders and investors.",
    features: ["Everything in Free", "100 company briefs and research runs a month, no daily cap",
      "100 alerts by email, Slack or Teams", "CSV export of the screener", "3,000 API requests a month"],
  },
  team: {
    blurb: "For funds, advisers and corporate teams.",
    features: ["Everything in Pro", "Up to 5 people", "500 briefs and research runs a month", "500 alerts",
      "15,000 API requests a month", "Priority support"],
  },
  institutional: {
    blurb: "For institutions that need more.",
    features: ["Everything in Team", "Custom data and coverage", "100,000 API requests a month", "Invoicing and onboarding"],
  },
};

export function naira(amount: number): string {
  return `₦${amount.toLocaleString("en-NG")}`;
}

export function money(amount: number, currency: Currency): string {
  return currency === "USD" ? `$${amount.toLocaleString("en-US")}` : naira(amount);
}

export function priceOf(p: CatalogPlan, currency: Currency, yearly: boolean): number | null {
  const v = currency === "USD" ? (yearly ? p.price_year_usd : p.price_month_usd) : (yearly ? p.price_year_ngn : p.price_month_ngn);
  return v ?? null;
}

/** Naira for visitors in Nigeria, dollars elsewhere, when dollars are offered. */
export function defaultCurrency(offered: Currency[]): Currency {
  if (!offered.includes("USD")) return "NGN";
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    const lang = typeof navigator !== "undefined" ? navigator.language || "" : "";
    return zone === "Africa/Lagos" || /-NG$/i.test(lang) ? "NGN" : "USD";
  } catch {
    return "NGN";
  }
}

/** "about $5.56": a naira amount in dollars at the current market rate. */
export function approxDollars(naira: number, ngnPerUsd: number): string {
  return `about $${(naira / ngnPerUsd).toFixed(2)}`;
}
