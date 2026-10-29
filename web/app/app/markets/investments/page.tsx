"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Container } from "../../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Table, Td, usd } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { get } from "../../../../lib/market";
import { asOf, companyHref, pct, price, quoteWhen, tone } from "../../../../lib/markets-data";
import {
  calculateBond, calculateTreasuryBill,
  type Instruments, type RateType, type TbillBlock, type TbillRow,
} from "../../../../lib/markets-instruments";

const COUNTRY_NAME: Record<string, string> = { NG: "Nigeria", KE: "Kenya" };
const SECTIONS: [string, string][] = [["etfs", "ETFs"], ["tbills", "Treasury bills"], ["property", "Listed property"],
  ["rates", "Policy rates"], ["calculators", "Calculators"]];

function numberField(value: string, fallback = Number.NaN): number {
  const parsed = Number(value);
  return value.trim() !== "" && Number.isFinite(parsed) ? parsed : fallback;
}

function money(value: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
  } catch {
    return `${value.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${currency}`;
  }
}

function rate(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "n/a" : `${v.toFixed(2)}%`;
}

function tenor(days: number): string {
  return days >= 364 ? "1 year (364 days)" : `${days} days`;
}

type BillPrefill = { currency: string; rate: number; rateType: RateType; days: number; basis: 364 | 365 };

function Etfs({ data }: { data: Instruments["etfs"] }) {
  const exposures = useMemo(() => Array.from(new Set(data.rows.map((r) => r.exposure))), [data.rows]);
  const [exposure, setExposure] = useState("");
  const rows = data.rows.filter((r) => !exposure || r.exposure === exposure);
  return (
    <section id="etfs" className="mt-10 scroll-mt-24" aria-labelledby="etfs-h">
      <h2 id="etfs-h" className="h3 text-xl">Exchange-traded funds</h2>
      <p className="mt-1 max-w-3xl text-sm text-[color:var(--muted)]">
        {data.rows.length} funds listed on the Johannesburg Stock Exchange, priced in rand. Each holds an index or a
        commodity, so one trade buys the whole basket. Prices are delayed {data.delay ? data.delay.replace(/ \(.*\)$/, "") : "quotes"}.
      </p>
      <div className="mt-4 flex flex-wrap gap-2 text-xs" role="group" aria-label="Filter by what the fund holds">
        {["", ...exposures].map((e) => (
          <button key={e || "all"} type="button" onClick={() => setExposure(e)} aria-pressed={exposure === e}
            className={`rounded-full border hairline px-3 py-1.5 ${exposure === e ? "bg-white/[0.08]" : "hover:bg-white/[0.03]"}`}>
            {e || "All"}
          </button>
        ))}
      </div>
      {rows.length === 0 ? <p className="mt-4 text-sm text-[color:var(--dim)]">No fund prices have been recorded yet.</p> : (
        <div className="mt-4">
          <Table head={["Fund", "Ticker", "Holds", "Price", "Today", "Year to date", "As of"]} minWidth="46rem">
            {rows.map((r) => (
              <tr key={r.symbol}>
                <Td>{r.name}</Td>
                <Td className="font-mono text-xs">{r.symbol}</Td>
                <Td className="text-[color:var(--muted)]">{r.exposure}</Td>
                <Td>{price(r.price, r.currency)}</Td>
                <Td className={tone(r.chg_1d)}>{pct(r.chg_1d)}</Td>
                <Td className={tone(r.ytd)}>{r.ytd_suspect ? <span title="The source changed price units this year">Not comparable</span> : pct(r.ytd)}</Td>
                <Td className="text-[color:var(--dim)]">{quoteWhen({ delayed: true, quote_time: r.quote_time, date: r.date })}</Td>
              </tr>
            ))}
          </Table>
        </div>
      )}
    </section>
  );
}

function Tbills({ blocks, onUse }: { blocks: TbillBlock[]; onUse: (p: BillPrefill) => void }) {
  return (
    <section id="tbills" className="mt-12 scroll-mt-24" aria-labelledby="tbills-h">
      <h2 id="tbills-h" className="h3 text-xl">Treasury bills</h2>
      <p className="mt-1 max-w-3xl text-sm text-[color:var(--muted)]">
        Short-dated government debt, sold at weekly or fortnightly auctions. Rates below are the latest results the
        central bank has published. Nigeria quotes a discount rate, so the true yield (what the buyer earns) is shown
        beside it; Kenya quotes the average yield directly.
      </p>
      {blocks.length === 0 ? <p className="mt-4 text-sm text-[color:var(--dim)]">No auction results have been recorded yet.</p> : (
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          {blocks.map((b) => (
            <article key={b.country} className="panel min-w-0 p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-base font-semibold">{COUNTRY_NAME[b.country] ?? b.country} · {b.currency}</h3>
                <a href={b.source_url} target="_blank" rel="noreferrer" className="text-xs underline underline-offset-4 hover:opacity-80">{b.source} ↗</a>
              </div>
              <div className="mt-3">
                <Table head={["Tenor", b.rows[0]?.rate_type === "discount" ? "Stop rate (discount)" : "Average yield",
                  ...(b.rows.some((r) => r.true_yield) ? ["True yield"] : []), "Auction", ""]} minWidth="30rem">
                  {b.rows.map((r: TbillRow) => (
                    <tr key={r.tenor_days}>
                      <Td>{tenor(r.tenor_days)}</Td>
                      <Td className="font-semibold">{rate(r.rate)}</Td>
                      {b.rows.some((x) => x.true_yield) && <Td>{rate(r.true_yield)}</Td>}
                      <Td className="text-[color:var(--dim)]">
                        {r.auction_date ? asOf(r.auction_date) : r.next_auction_date ? `last before ${asOf(r.next_auction_date)}` : "date not reported"}
                        {r.allotted_mn != null && r.offered_mn ? <span className="block text-[0.6875rem]">{Math.round(r.allotted_mn).toLocaleString("en-US")}m of {Math.round(r.offered_mn).toLocaleString("en-US")}m allotted</span> : null}
                      </Td>
                      <Td>
                        <button type="button" className="text-xs underline underline-offset-4 hover:opacity-80"
                          onClick={() => onUse({ currency: b.currency, rate: r.rate, rateType: r.rate_type, days: r.tenor_days, basis: r.basis })}>
                          Use in calculator
                        </button>
                      </Td>
                    </tr>
                  ))}
                </Table>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function Property({ rows }: { rows: Instruments["property"] }) {
  const shown = rows.slice(0, 25);
  return (
    <section id="property" className="mt-12 scroll-mt-24" aria-labelledby="property-h">
      <h2 id="property-h" className="h3 text-xl">Listed property</h2>
      <p className="mt-1 max-w-3xl text-sm text-[color:var(--muted)]">
        Real estate investment trusts and property companies: a share of rental income without owning a building.
        {rows.length > shown.length ? ` The ${shown.length} largest of ${rows.length} are shown; ` : " "}
        the <Link href="/app/markets/screener" className="underline underline-offset-4">screener</Link> filters every listed share by sector.
      </p>
      {shown.length === 0 ? <p className="mt-4 text-sm text-[color:var(--dim)]">No listed property prices have been recorded yet.</p> : (
        <div className="mt-4">
          <Table head={["Company", "Exchange", "Price", "Today", "Year to date", "Market cap", "Dividend yield", "As of"]} minWidth="48rem">
            {shown.map((r) => (
              <tr key={`${r.exchange}-${r.symbol}`}>
                <Td><Link href={companyHref(r)} className="underline-offset-4 hover:underline">{r.name}</Link></Td>
                <Td className="uppercase text-[color:var(--muted)]">{r.exchange}</Td>
                <Td>{price(r.price, r.currency)}</Td>
                <Td className={tone(r.chg_1d)}>{pct(r.chg_1d)}</Td>
                <Td className={tone(r.ytd)}>{pct(r.ytd)}</Td>
                <Td>{r.mcap_usd ? usd(r.mcap_usd) : "n/a"}</Td>
                <Td>{r.dividend_yield != null ? pct(r.dividend_yield) : "n/a"}</Td>
                <Td className="text-[color:var(--dim)]">{quoteWhen(r)}</Td>
              </tr>
            ))}
          </Table>
        </div>
      )}
    </section>
  );
}

function PolicyRates({ rows }: { rows: Instruments["policy_rates"] }) {
  return (
    <section id="rates" className="mt-12 scroll-mt-24" aria-labelledby="rates-h">
      <h2 id="rates-h" className="h3 text-xl">Policy rates</h2>
      <p className="mt-1 max-w-3xl text-sm text-[color:var(--muted)]">
        The central bank rate anchors what deposits, money-market funds and Treasury bills pay in each country. Banks
        set their own deposit rates, which are not collected here.
      </p>
      {rows.length === 0 ? <p className="mt-4 text-sm text-[color:var(--dim)]">No policy rates are available.</p> : (
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {rows.map((r) => (
            <div key={r.country} className="rounded-lg border hairline px-3 py-2.5">
              <p className="text-xs text-[color:var(--muted)]">{r.country_name}</p>
              <p className="mt-0.5 text-lg font-semibold">{rate(r.rate)}</p>
              <p className="text-[0.6875rem] text-[color:var(--dim)]">since {asOf(r.as_of)}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Calculators({ prefill }: { prefill: BillPrefill | null }) {
  const [currency, setCurrency] = useState("NGN");
  const [faceValue, setFaceValue] = useState("1000000");
  const [billRate, setBillRate] = useState("15.4");
  const [rateType, setRateType] = useState<RateType>("discount");
  const [billDays, setBillDays] = useState("91");
  const [basis, setBasis] = useState<"364" | "365">("365");
  const [bondCurrency, setBondCurrency] = useState("NGN");
  const [bondFace, setBondFace] = useState("100000");
  const [coupon, setCoupon] = useState("16");
  const [bondPrice, setBondPrice] = useState("95");
  const [bondYears, setBondYears] = useState("5");

  useEffect(() => {
    if (!prefill) return;
    setCurrency(prefill.currency);
    setBillRate(String(prefill.rate));
    setRateType(prefill.rateType);
    setBillDays(String(prefill.days));
    setBasis(String(prefill.basis) as "364" | "365");
    document.getElementById("calc-bill")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [prefill]);

  const bill = useMemo(() => calculateTreasuryBill({
    faceValue: numberField(faceValue), ratePct: numberField(billRate), rateType,
    daysToMaturity: numberField(billDays), basis: Number(basis) as 364 | 365,
  }), [faceValue, billRate, rateType, billDays, basis]);

  const bond = useMemo(() => calculateBond({
    faceValue: numberField(bondFace), annualCouponRatePct: numberField(coupon), pricePer100: numberField(bondPrice),
    yearsToMaturity: numberField(bondYears), paymentsPerYear: 2,
  }), [bondFace, coupon, bondPrice, bondYears]);

  const currencies = [["NGN", "Nigerian naira"], ["KES", "Kenyan shilling"], ["GHS", "Ghanaian cedi"], ["ZAR", "South African rand"],
    ["EGP", "Egyptian pound"], ["USD", "US dollar"]];

  return (
    <section id="calculators" className="mt-12 grid scroll-mt-24 gap-4 xl:grid-cols-2" aria-label="Fixed income calculators">
      <article id="calc-bill" className="panel min-w-0 scroll-mt-24 p-5">
        <p className="eyebrow">Calculator</p>
        <h2 className="mt-1 text-xl font-semibold">Treasury bill return</h2>
        <p className="mt-2 text-sm text-[color:var(--muted)]">
          What you pay and earn for a bill at a quoted rate. Pick how the rate is quoted: Nigeria uses a discount rate
          on 365 days, Kenya a yield on 364 days. &ldquo;Use in calculator&rdquo; above fills these in.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-sm">Currency
            <select className="field mt-1 w-full" value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {currencies.map(([c, n]) => <option key={c} value={c}>{c} · {n}</option>)}
            </select>
          </label>
          <label className="text-sm">Face value (paid at maturity)
            <input className="field mt-1 w-full" inputMode="decimal" type="number" min="1" value={faceValue} onChange={(e) => setFaceValue(e.target.value)} />
          </label>
          <label className="text-sm">Quoted rate (%)
            <input className="field mt-1 w-full" inputMode="decimal" type="number" min="0" max="99.99" step="0.01" value={billRate} onChange={(e) => setBillRate(e.target.value)} />
          </label>
          <label className="text-sm">Rate quoted as
            <select className="field mt-1 w-full" value={rateType} onChange={(e) => setRateType(e.target.value as RateType)}>
              <option value="discount">Discount rate</option>
              <option value="yield">Yield</option>
            </select>
          </label>
          <label className="text-sm">Days to maturity
            <input className="field mt-1 w-full" inputMode="numeric" type="number" min="1" max="366" step="1" value={billDays} onChange={(e) => setBillDays(e.target.value)} />
          </label>
          <label className="text-sm">Day-count basis
            <select className="field mt-1 w-full" value={basis} onChange={(e) => setBasis(e.target.value as "364" | "365")}>
              <option value="365">365 days</option>
              <option value="364">364 days</option>
            </select>
          </label>
        </div>
        {bill ? (
          <dl className="mt-5 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">You pay</dt><dd className="mt-1 text-lg font-semibold">{money(bill.purchasePrice, currency)}</dd></div>
            <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">You earn at maturity</dt><dd className="mt-1 text-lg font-semibold">{money(bill.incomeAtMaturity, currency)}</dd></div>
            <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Return over the term</dt><dd className="mt-1 text-lg font-semibold">{rate(bill.holdingPeriodReturnPct)}</dd></div>
            <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Annual yield (true yield)</dt><dd className="mt-1 text-lg font-semibold">{rate(bill.investmentYieldPct)}</dd></div>
            <div className="rounded-lg border hairline p-3 sm:col-span-2"><dt className="text-xs text-[color:var(--muted)]">Equivalent discount rate</dt><dd className="mt-1 text-base font-semibold">{rate(bill.discountRatePct)}</dd></div>
          </dl>
        ) : <p className="mt-4 text-sm text-risk">Enter a positive face value, a rate below 100% and between 1 and 366 days.</p>}
        <p className="mt-3 text-xs text-[color:var(--dim)]">Before tax and fees. Withholding tax, where it applies, reduces the return.</p>
      </article>

      <article className="panel min-w-0 p-5">
        <p className="eyebrow">Calculator</p>
        <h2 className="mt-1 text-xl font-semibold">Bond coupon and yield</h2>
        <p className="mt-2 text-sm text-[color:var(--muted)]">
          Coupon income, current yield and yield to maturity for a fixed-coupon bond paying twice a year. The price is
          per 100 of face value, as bonds are quoted, and assumes purchase on a coupon date (no accrued interest).
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-sm">Currency
            <select className="field mt-1 w-full" value={bondCurrency} onChange={(e) => setBondCurrency(e.target.value)}>
              {currencies.map(([c, n]) => <option key={c} value={c}>{c} · {n}</option>)}
            </select>
          </label>
          <label className="text-sm">Face value
            <input className="field mt-1 w-full" inputMode="decimal" type="number" min="1" value={bondFace} onChange={(e) => setBondFace(e.target.value)} />
          </label>
          <label className="text-sm">Annual coupon rate (%)
            <input className="field mt-1 w-full" inputMode="decimal" type="number" min="0" max="100" step="0.01" value={coupon} onChange={(e) => setCoupon(e.target.value)} />
          </label>
          <label className="text-sm">Price per 100 of face
            <input className="field mt-1 w-full" inputMode="decimal" type="number" min="1" step="0.01" value={bondPrice} onChange={(e) => setBondPrice(e.target.value)} />
          </label>
          <label className="text-sm sm:col-span-2">Years to maturity
            <input className="field mt-1 w-full" inputMode="decimal" type="number" min="0.5" max="100" step="0.5" value={bondYears} onChange={(e) => setBondYears(e.target.value)} />
          </label>
        </div>
        {bond ? (
          <dl className="mt-5 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">You pay</dt><dd className="mt-1 text-lg font-semibold">{money(bond.purchaseCost, bondCurrency)}</dd></div>
            <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Coupon income a year</dt><dd className="mt-1 text-lg font-semibold">{money(bond.annualCouponIncome, bondCurrency)}</dd></div>
            <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Current yield</dt><dd className="mt-1 text-lg font-semibold">{rate(bond.currentYieldPct)}</dd></div>
            <div className="rounded-lg bg-white/[0.03] p-3"><dt className="text-xs text-[color:var(--muted)]">Yield to maturity</dt><dd className="mt-1 text-lg font-semibold">{bond.yieldToMaturityPct == null ? "Not solvable for these inputs" : rate(bond.yieldToMaturityPct)}</dd></div>
            <div className="rounded-lg border hairline p-3 sm:col-span-2"><dt className="text-xs text-[color:var(--muted)]">Coupon payments to maturity</dt><dd className="mt-1 text-base font-semibold">{bond.totalScheduledCoupons}</dd></div>
          </dl>
        ) : <p className="mt-4 text-sm text-risk">Enter a positive face value, a coupon up to 100%, a price per 100 and years to maturity.</p>}
        <p className="mt-3 text-xs text-[color:var(--dim)]">An estimate from your inputs, not a dealer quote.</p>
      </article>
    </section>
  );
}

export default function InvestmentExplorerPage() {
  const [data, setData] = useState<Instruments | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<BillPrefill | null>(null);

  useEffect(() => {
    let active = true;
    get<Instruments>("/api/markets/instruments")
      .then((d) => { if (active) setData(d); })
      .catch((e) => { if (active) setError(e instanceof ApiError ? e.message : "Investment data could not be loaded."); });
    return () => { active = false; };
  }, []);

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · Beyond shares" title="ETFs, Treasury bills, property and rates.">
        Exchange-traded funds, government bill auctions, listed property and central bank rates across African
        markets, each with its source and date, plus calculators for bills and bonds.
      </PageHeader>

      <nav className="flex flex-wrap gap-2 text-sm" aria-label="Sections">
        <Link href="/app/markets" className="rounded-full border hairline px-3 py-1.5 hover:bg-white/[0.03]">← Markets</Link>
        {SECTIONS.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="rounded-full border hairline px-3 py-1.5 hover:bg-white/[0.03]">{label}</a>
        ))}
      </nav>

      {error && <ErrorNote message={error} />}
      {!data && !error && <Loading label="Loading ETFs, bills and rates..." />}
      {data && (
        <>
          <Etfs data={data.etfs} />
          <Tbills blocks={data.tbills} onUse={setPrefill} />
          <Property rows={data.property} />
          <PolicyRates rows={data.policy_rates} />
        </>
      )}

      <Calculators prefill={prefill} />

      <section className="mt-10 rounded-xl border hairline p-4">
        <h2 className="text-base font-semibold">What is covered</h2>
        <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">
          {data?.method ?? "Each figure carries its source and date."} ETFs listed in Lagos and Nairobi are not yet in a
          free price feed. Nothing here is an offer to buy or a guarantee of return.
        </p>
      </section>
    </Container>
  );
}
