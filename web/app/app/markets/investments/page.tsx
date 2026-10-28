"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Container } from "../../../../components/primitives";
import { PageHeader } from "../../../../components/app/ui";
import { calculateBond, calculateTreasuryBill } from "../../../../lib/markets-instruments";

type InstrumentGroup = {
  title: string;
  description: string;
  status: string;
  sources: { label: string; href: string }[];
};

const GROUPS: InstrumentGroup[] = [
  {
    title: "Treasury bills",
    description: "Short-dated government securities. Compare discount price, maturity proceeds and annualized yield using a published rate.",
    status: "Calculator available · live auction data integration pending",
    sources: [
      { label: "CBN government securities", href: "https://www.cbn.gov.ng/rates/GovtSecuritiesDrillDown.html?market=NTB" },
      { label: "CBN government securities FAQ", href: "https://www.cbn.gov.ng/FAQS/index.html" },
    ],
  },
  {
    title: "Government and corporate bonds",
    description: "Compare coupon income with market price, maturity and indicative yield to maturity. Credit and liquidity risk vary by issuer.",
    status: "Calculator available · sourced bond inventory pending",
    sources: [
      { label: "Debt Management Office: FGN bonds", href: "https://www.dmo.gov.ng/fgn-bonds?lang=en" },
      { label: "FMDQ market data", href: "https://emarkets.fmdqgroup.com/market/" },
    ],
  },
  {
    title: "ETFs",
    description: "Explore exchange-traded funds by market, index or strategy, with fees, holdings, price and net asset value where published.",
    status: "Instrument discovery and price/NAV ingestion pending",
    sources: [
      { label: "SEC Nigeria: ETF net asset values", href: "https://sec.gov.ng/for-operators/keep-track-of-capital-market-data/net-asset-value-data/" },
    ],
  },
  {
    title: "Money-market and mutual funds",
    description: "Compare reported returns, management fees, dealing frequency, minimum investment, liquidity and risk disclosures.",
    status: "Fund catalogue and performance ingestion pending",
    sources: [
      { label: "SEC Nigeria: net asset value data", href: "https://sec.gov.ng/for-operators/keep-track-of-capital-market-data/net-asset-value-data/" },
    ],
  },
  {
    title: "Fixed deposits",
    description: "Compare institution-published rates, terms, minimum deposits, early-withdrawal rules and deposit protection disclosures.",
    status: "Provider-rate catalogue pending",
    sources: [],
  },
  {
    title: "REITs and listed equities",
    description: "Use listed-market coverage where available; specialist REIT valuation and property-level metrics need separate treatment.",
    status: "Equity coverage available · dedicated REIT metrics pending",
    sources: [
      { label: "Markets screener", href: "/app/markets/screener" },
      { label: "SEC Nigeria market data", href: "https://sec.gov.ng/for-operators/keep-track-of-capital-market-data/" },
    ],
  },
];

function numberField(value: string, fallback = 0): number {
  const parsed = Number(value);
  return value.trim() !== "" && Number.isFinite(parsed) ? parsed : fallback;
}

function money(value: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-NG", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
  } catch {
    return value.toLocaleString("en-NG", { maximumFractionDigits: 2 }) + " " + currency;
  }
}

function pct(value: number | null): string {
  return value == null || !Number.isFinite(value) ? "Not available" : value.toFixed(2) + "%";
}

export default function InvestmentExplorerPage() {
  const [currency, setCurrency] = useState("NGN");
  const [faceValue, setFaceValue] = useState("1000000");
  const [discountRate, setDiscountRate] = useState("18");
  const [billDays, setBillDays] = useState("182");
  const [bondFace, setBondFace] = useState("100000");
  const [coupon, setCoupon] = useState("16");
  const [bondPrice, setBondPrice] = useState("95000");
  const [bondYears, setBondYears] = useState("5");

  const bill = useMemo(() => calculateTreasuryBill({
    faceValue: numberField(faceValue),
    discountRatePct: numberField(discountRate, Number.NaN),
    daysToMaturity: numberField(billDays, Number.NaN),
  }), [faceValue, discountRate, billDays]);

  const bond = useMemo(() => calculateBond({
    faceValue: numberField(bondFace),
    annualCouponRatePct: numberField(coupon, Number.NaN),
    cleanPrice: numberField(bondPrice),
    yearsToMaturity: numberField(bondYears, Number.NaN),
    paymentsPerYear: 2,
  }), [bondFace, coupon, bondPrice, bondYears]);

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · Explore investments" title="Beyond stocks: compare investment instruments.">
        Explore fixed income, funds, ETFs, deposits and listed assets in one Africa-first investment workspace.
        Calculators work with inputs you provide; live availability and market data are shown only when verified sources are integrated.
      </PageHeader>

      <div className="mt-6 flex flex-wrap gap-2 text-sm">
        <Link href="/app/markets" className="rounded-full border hairline px-3 py-1.5 hover:bg-white/[0.03]">← Markets overview</Link>
        <Link href="/app/markets/portfolio" className="rounded-full border hairline px-3 py-1.5 hover:bg-white/[0.03]">My portfolio</Link>
        <Link href="/app/markets/compare" className="rounded-full border hairline px-3 py-1.5 hover:bg-white/[0.03]">Compare companies</Link>
      </div>

      <section className="mt-8" aria-labelledby="instrument-catalogue">
        <div className="mb-3">
          <h2 id="instrument-catalogue" className="h3 text-xl">Investment categories</h2>
          <p className="mt-1 text-sm text-[color:var(--muted)]">Nigeria-first, with country-by-country expansion based on verified source coverage.</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {GROUPS.map((group) => (
            <article key={group.title} className="rounded-xl border hairline p-4">
              <h3 className="text-base font-semibold">{group.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">{group.description}</p>
              <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">{group.status}</p>
              {group.sources.length > 0 && (
                <ul className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs">
                  {group.sources.map((source) => (
                    <li key={source.href + source.label}>
                      <a href={source.href} target={source.href.startsWith("/") ? undefined : "_blank"} rel={source.href.startsWith("/") ? undefined : "noreferrer"} className="underline underline-offset-4 hover:opacity-80">{source.label} ↗</a>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="mt-10 grid gap-4 xl:grid-cols-2" aria-label="Fixed income calculators">
        <article className="panel min-w-0 p-5">
          <p className="eyebrow">Calculator 01</p>
          <h2 className="mt-1 text-xl font-semibold">Treasury bill return</h2>
          <p className="mt-2 text-sm text-[color:var(--muted)]">Enter a quoted discount rate and days to maturity. This uses a simple 365-day convention for illustration; use the auction's published true yield for an actual offer.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="text-sm">Currency
              <select className="field mt-1 w-full" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                <option value="NGN">NGN · Nigerian naira</option>
                <option value="GHS">GHS · Ghanaian cedi</option>
                <option value="KES">KES · Kenyan shilling</option>
                <option value="ZAR">ZAR · South African rand</option>
                <option value="USD">USD · US dollar</option>
              </select>
            </label>
            <label className="text-sm">Face value
              <input className="field mt-1 w-full" inputMode="decimal" type="number" min="1" value={faceValue} onChange={(e) => setFaceValue(e.target.value)} />
            </label>
            <label className="text-sm">Discount rate (%)
              <input className="field mt-1 w-full" inputMode="decimal" type="number" min="0" max="99.99" step="0.01" value={discountRate} onChange={(e) => setDiscountRate(e.target.value)} />
            </label>
            <label className="text-sm">Days to maturity
              <select className="field mt-1 w-full" value={billDays} onChange={(e) => setBillDays(e.target.value)}>
                <option value="91">91 days</option>
                <option value="182">182 days</option>
                <option value="364">364 days</option>
              </select>
            </label>
          </div>
          {bill ? (
            <dl className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Indicative purchase price</dt><dd className="mt-1 text-lg font-semibold">{money(bill.purchasePrice, currency)}</dd></div>
              <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Income at maturity</dt><dd className="mt-1 text-lg font-semibold">{money(bill.incomeAtMaturity, currency)}</dd></div>
              <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Holding-period return</dt><dd className="mt-1 text-lg font-semibold">{pct(bill.holdingPeriodReturnPct)}</dd></div>
              <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Simple annualized investment yield</dt><dd className="mt-1 text-lg font-semibold">{pct(bill.simpleAnnualizedInvestmentYieldPct)}</dd></div>
              <div className="sm:col-span-2 rounded-lg border hairline p-3"><dt className="text-xs text-[color:var(--muted)]">Bank discount yield (different convention)</dt><dd className="mt-1 text-base font-semibold">{pct(bill.bankDiscountYieldPct)}</dd></div>
            </dl>
          ) : <p className="mt-4 text-sm text-[color:var(--risk)]">Enter a positive face value, a discount rate below 100%, and a valid tenor.</p>}
        </article>

        <article className="panel min-w-0 p-5">
          <p className="eyebrow">Calculator 02</p>
          <h2 className="mt-1 text-xl font-semibold">Bond coupon and yield</h2>
          <p className="mt-2 text-sm text-[color:var(--muted)]">Estimate annual coupon income, current yield and an indicative yield to maturity using a fixed coupon and semiannual payments. This is a simplified estimate, not a dealer quote.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="text-sm">Face value
              <input className="field mt-1 w-full" type="number" min="1" value={bondFace} onChange={(e) => setBondFace(e.target.value)} />
            </label>
            <label className="text-sm">Annual coupon rate (%)
              <input className="field mt-1 w-full" type="number" min="0" max="100" step="0.01" value={coupon} onChange={(e) => setCoupon(e.target.value)} />
            </label>
            <label className="text-sm">Market price
              <input className="field mt-1 w-full" type="number" min="1" value={bondPrice} onChange={(e) => setBondPrice(e.target.value)} />
            </label>
            <label className="text-sm">Years to maturity
              <input className="field mt-1 w-full" type="number" min="0.5" max="100" step="0.5" value={bondYears} onChange={(e) => setBondYears(e.target.value)} />
            </label>
          </div>
          {bond ? (
            <dl className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Annual coupon income</dt><dd className="mt-1 text-lg font-semibold">{money(bond.annualCouponIncome, currency)}</dd></div>
              <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Current yield</dt><dd className="mt-1 text-lg font-semibold">{pct(bond.currentYieldPct)}</dd></div>
              <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Indicative yield to maturity</dt><dd className="mt-1 text-lg font-semibold">{pct(bond.yieldToMaturityPct)}</dd></div>
              <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Scheduled coupon payments</dt><dd className="mt-1 text-lg font-semibold">{bond.totalScheduledCoupons}</dd></div>
            </dl>
          ) : <p className="mt-4 text-sm text-[color:var(--risk)]">Enter valid face value, coupon, market price and time to maturity.</p>}
        </article>
      </section>

      <section className="mt-8 rounded-xl border hairline p-4">
        <h2 className="text-base font-semibold">Data integrity comes first</h2>
        <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">
          This first release adds working calculators and a source-linked instrument map, not a claim that every asset is already available for purchase. Rates, prices, fund returns and NAVs will only appear as market observations after a source adapter is implemented and its date, currency, methodology and coverage are checked. Nothing here executes trades or guarantees returns.
        </p>
      </section>
    </Container>
  );
}
