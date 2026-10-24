"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { Container } from "../../../../components/primitives";
import { ErrorNote, PageHeader } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { get } from "../../../../lib/market";

type Inputs = {
  company: string;
  ticker: string;
  currency: string;
  source: string;
  period: string;
  fcf: string;
  cash: string;
  debt: string;
  shares: string;
  price: string;
  bearGrowth: string;
  baseGrowth: string;
  bullGrowth: string;
  discountRate: string;
  terminalGrowth: string;
};

type Scenario = { name: string; growth: number; enterpriseValue: number; equityValue: number; perShare: number | null };

type CompanyProfile = {
  name: string;
  ticker: string | null;
  market?: { price?: number | null; currency?: string | null; market_cap?: number | null; source?: string; as_at?: string | null } | null;
  financials?: {
    source: string;
    source_url?: string;
    period: { end: string; months: number | null; label?: string } | null;
    currency?: string;
    unit?: string;
    items?: Record<string, { current: number; prior?: number }>;
    verified: boolean;
  };
};

const initial: Inputs = {
  company: "",
  ticker: "",
  currency: "NGN",
  source: "",
  period: "",
  fcf: "",
  cash: "",
  debt: "",
  shares: "",
  price: "",
  bearGrowth: "0",
  baseGrowth: "8",
  bullGrowth: "15",
  discountRate: "18",
  terminalGrowth: "4",
};

function num(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value: number | null, currency: string): string {
  if (value == null || !Number.isFinite(value)) return "Not available";
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 2, notation: Math.abs(value) >= 1e12 ? "compact" : "standard" }).format(value);
  } catch {
    return `${value.toLocaleString("en", { maximumFractionDigits: 2 })} ${currency}`;
  }
}

function compact(value: number): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 }).format(value);
}

function dcf(fcf: number, growthPct: number, discountPct: number, terminalPct: number, cash: number, debt: number, shares: number): number | null {
  const growth = growthPct / 100;
  const discount = discountPct / 100;
  const terminal = terminalPct / 100;
  if (fcf <= 0 || shares <= 0 || discount <= terminal || discount <= -1 || growth <= -1 || terminal <= -1) return null;
  let enterpriseValue = 0;
  let projected = fcf;
  for (let year = 1; year <= 5; year += 1) {
    projected *= 1 + growth;
    enterpriseValue += projected / Math.pow(1 + discount, year);
  }
  const terminalValue = projected * (1 + terminal) / (discount - terminal);
  enterpriseValue += terminalValue / Math.pow(1 + discount, 5);
  const equityValue = enterpriseValue + cash - debt;
  return equityValue / shares;
}

function ScenarioCard({ scenario, currency, price }: { scenario: Scenario; currency: string; price: number | null }) {
  const upside = price != null && price > 0 && scenario.perShare != null ? (scenario.perShare / price - 1) * 100 : null;
  return (
    <article className="rounded-xl border hairline p-4">
      <p className="eyebrow">{scenario.name} case</p>
      <p className="mt-2 text-xl font-semibold">{money(scenario.perShare, currency)}</p>
      <p className="mt-1 text-xs text-[color:var(--muted)]">Implied value per share</p>
      <p className="mt-2 text-xs text-[color:var(--muted)]">Five-year FCF growth assumption: {scenario.growth.toFixed(1)}% annually</p>
      <div className="mt-4 flex items-center justify-between gap-3 border-t hairline pt-3 text-xs">
        <span className="text-[color:var(--muted)]">Implied enterprise value</span>
        <span className="kbd">{money(scenario.enterpriseValue, currency)}</span>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 text-xs">
        <span className="text-[color:var(--muted)]">vs entered market price</span>
        <span className={upside == null ? "kbd" : upside < 0 ? "text-risk kbd" : "text-verified kbd"}>{upside == null ? "No price entered" : `${upside > 0 ? "+" : ""}${upside.toFixed(1)}%`}</span>
      </div>
    </article>
  );
}

export default function MarketsValuationPage() {
  const [form, setForm] = useState<Inputs>(initial);
  const [error, setError] = useState<string | null>(null);
  const [hasCalculated, setHasCalculated] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const set = (key: keyof Inputs) => (event: { target: { value: string } }) => {
    setForm((current) => ({ ...current, [key]: event.target.value }));
    setHasCalculated(false);
  };

  async function loadCompanyProfile() {
    const name = form.company.trim();
    if (!name) {
      setProfileError("Enter a company name before loading its existing profile.");
      setProfileMessage(null);
      return;
    }
    setProfileBusy(true);
    setProfileError(null);
    setProfileMessage(null);
    try {
      const profile = await get<CompanyProfile>("/api/companies/profile", {
        name,
        ticker: form.ticker.trim(),
      });
      const financials = profile.financials;
      if (!financials) {
        setProfileError("The existing company profile did not return machine-readable financial statements. You can still enter sourced figures manually.");
        return;
      }
      const items = financials.items ?? {};
      const value = (key: string) => {
        const current = items[key]?.current;
        return typeof current === "number" && Number.isFinite(current) ? String(current) : "";
      };
      const supportedCurrencies = ["NGN", "KES", "ZAR", "GHS", "EGP", "XOF", "XAF", "MAD", "TZS", "UGX", "RWF", "ETB", "MUR", "USD", "EUR", "GBP"];
      const currency = financials.currency && supportedCurrencies.includes(financials.currency.toUpperCase())
        ? financials.currency.toUpperCase()
        : form.currency;
      const sameCurrency = Boolean(profile.market?.currency && profile.market.currency.toUpperCase() === currency);
      const hasDatedQuote = Boolean(profile.market?.as_at && profile.market?.price != null && sameCurrency);
      const inferredShares = sameCurrency && profile.market?.market_cap != null && profile.market.market_cap > 0 && profile.market.price != null && profile.market.price > 0
        ? String(profile.market.market_cap / profile.market.price)
        : "";
      setForm((current) => ({
        ...current,
        company: profile.name || current.company,
        ticker: profile.ticker || current.ticker,
        currency,
        source: financials.source_url || "",
        period: financials.period?.end || "",
        fcf: value("free_cash_flow"),
        cash: value("cash"),
        debt: value("total_debt"),
        shares: inferredShares,
        price: hasDatedQuote ? String(profile.market!.price) : "",
      }));
      setHasCalculated(false);
      setProfileMessage([
        `Financial fields loaded from ${financials.source}.`,
        financials.verified ? "The profile reports its available accounting checks as passed." : "The profile does not report all available accounting checks as passed.",
        inferredShares ? "Shares outstanding is inferred from market capitalisation divided by price, not independently verified." : "Shares outstanding was not inferred because market price, market capitalisation or currency alignment was unavailable.",
        hasDatedQuote ? `A price dated ${profile.market?.as_at} was prefilled from ${profile.market?.source || "the company profile"}.` : "Current price was left blank because the profile did not provide a dated quote in the statement currency.",
        financials.source_url ? "" : "No direct financial statement URL was returned; add a source URL before calculating.",
        "Review every field, especially units, debt, share count and the source period, before calculating.",
      ].filter(Boolean).join(" "));
    } catch (err) {
      setProfileError(err instanceof ApiError ? err.message : "Could not load the existing company profile.");
    } finally {
      setProfileBusy(false);
    }
  }

  const parsed = useMemo(() => ({
    fcf: num(form.fcf), cash: num(form.cash), debt: num(form.debt), shares: num(form.shares), price: num(form.price),
    bearGrowth: num(form.bearGrowth), baseGrowth: num(form.baseGrowth), bullGrowth: num(form.bullGrowth),
    discountRate: num(form.discountRate), terminalGrowth: num(form.terminalGrowth),
  }), [form]);

  const scenarios = useMemo((): Scenario[] => {
    const { fcf, cash, debt, shares, bearGrowth, baseGrowth, bullGrowth, discountRate, terminalGrowth } = parsed;
    if ([fcf, cash, debt, shares, bearGrowth, baseGrowth, bullGrowth, discountRate, terminalGrowth].some((v) => v == null)) return [];
    return [
      { name: "Bear", growth: bearGrowth!, enterpriseValue: 0, equityValue: 0, perShare: dcf(fcf!, bearGrowth!, discountRate!, terminalGrowth!, cash!, debt!, shares!) },
      { name: "Base", growth: baseGrowth!, enterpriseValue: 0, equityValue: 0, perShare: dcf(fcf!, baseGrowth!, discountRate!, terminalGrowth!, cash!, debt!, shares!) },
      { name: "Bull", growth: bullGrowth!, enterpriseValue: 0, equityValue: 0, perShare: dcf(fcf!, bullGrowth!, discountRate!, terminalGrowth!, cash!, debt!, shares!) },
    ].map((scenario) => {
      const perShare = scenario.perShare;
      return { ...scenario, enterpriseValue: perShare == null ? 0 : perShare * shares! - cash! + debt!, equityValue: perShare == null ? 0 : perShare * shares! };
    });
  }, [parsed]);

  const validInputs = parsed.fcf != null && parsed.fcf > 0 && parsed.cash != null && parsed.cash >= 0 &&
    parsed.debt != null && parsed.debt >= 0 && parsed.shares != null && parsed.shares > 0 &&
    parsed.bearGrowth != null && parsed.baseGrowth != null && parsed.bullGrowth != null &&
    parsed.bearGrowth <= parsed.baseGrowth && parsed.baseGrowth <= parsed.bullGrowth &&
    parsed.discountRate != null && parsed.discountRate > 0 && parsed.discountRate <= 60 &&
    parsed.terminalGrowth != null && parsed.terminalGrowth >= -5 && parsed.terminalGrowth <= 8 &&
    parsed.discountRate > parsed.terminalGrowth &&
    (parsed.price == null || parsed.price > 0) && form.company.trim().length > 0 &&
    form.source.trim().length > 0 && form.period.trim().length > 0;

  function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const growths = [parsed.bearGrowth, parsed.baseGrowth, parsed.bullGrowth];
    if (!validInputs || growths.some((value) => value == null || value <= -100 || value > 100)) {
      setError("Check required inputs: company, source URL, reporting period, positive free cash flow and shares outstanding, non-negative cash/debt, ordered bear ≤ base ≤ bull growth assumptions, and a discount rate above terminal growth.");
      setHasCalculated(false);
      return;
    }
    if (scenarios.some((scenario) => scenario.perShare == null || !Number.isFinite(scenario.perShare))) {
      setError("The entered assumptions do not produce a valid valuation. Review the cash flows, discount rate and terminal growth.");
      setHasCalculated(false);
      return;
    }
    setHasCalculated(true);
  }

  const base = scenarios.find((scenario) => scenario.name === "Base");
  const price = parsed.price;
  const verdict = hasCalculated && base?.perShare != null && price != null
    ? (base.perShare < price * 0.85 ? "Potentially overvalued on these assumptions" : base.perShare > price * 1.15 ? "Potentially undervalued on these assumptions" : "Within 15% of the base-case estimate")
    : null;

  const sensitivity = hasCalculated && parsed.fcf != null && parsed.cash != null && parsed.debt != null &&
    parsed.shares != null && parsed.baseGrowth != null && parsed.discountRate != null && parsed.terminalGrowth != null
    ? [-2, 0, 2].map((discountOffset) => ({
        discountRate: parsed.discountRate! + discountOffset,
        cells: [-1, 0, 1].map((terminalOffset) => {
          const terminalGrowth = parsed.terminalGrowth! + terminalOffset;
          return {
            terminalGrowth,
            value: dcf(parsed.fcf!, parsed.baseGrowth!, parsed.discountRate! + discountOffset, terminalGrowth, parsed.cash!, parsed.debt!, parsed.shares!),
          };
        }),
      }))
    : [];

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · Valuation" title="A valuation with a countercase.">
        Build an explicit five-year discounted-cash-flow scenario from financial inputs you can trace to a source. The tool does not fetch or invent a current price, financial statement, share count or exchange rate. The conclusion is only as reliable as the inputs and assumptions you enter.
      </PageHeader>

      <div className="mb-6 flex flex-wrap gap-3">
        <Link href="/app/markets" className="text-sm text-[color:var(--muted)] underline-offset-4 hover:underline">← Markets overview</Link>
        <Link href="/app/companies" className="text-sm text-[color:var(--muted)] underline-offset-4 hover:underline">Open company financials →</Link>
        <Link href="/app/markets/portfolio" className="text-sm text-[color:var(--muted)] underline-offset-4 hover:underline">Portfolio Intelligence →</Link>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <section className="panel p-5 sm:p-6" aria-labelledby="inputs-title">
          <p className="eyebrow">Transparent inputs</p>
          <h2 id="inputs-title" className="h3 mt-2 text-xl">Set the evidence and assumptions</h2>
          {error && <div className="mt-4"><ErrorNote message={error} /></div>}
          {profileError && <div className="mt-4"><ErrorNote message={profileError} /></div>}
          {profileMessage && <p className="mt-4 text-xs leading-relaxed text-[color:var(--muted)]" role="status">{profileMessage}</p>}
          <form className="mt-5 space-y-5" onSubmit={calculate}>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-company">Company / instrument *</label>
                <input id="valuation-company" className="field" required value={form.company} onChange={set("company")} placeholder="e.g. Dangote Cement" />
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-ticker">Ticker (optional)</label>
                <input id="valuation-ticker" className="field" value={form.ticker} onChange={set("ticker")} placeholder="DANGCEM.LG" />
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-currency">Statement currency</label>
                <select id="valuation-currency" className="field" value={form.currency} onChange={set("currency")}>
                  {["NGN", "KES", "ZAR", "GHS", "EGP", "XOF", "XAF", "MAD", "TZS", "UGX", "RWF", "ETB", "MUR", "USD", "EUR", "GBP"].map((currency) => <option key={currency} value={currency}>{currency}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-period">Financial period end *</label>
                <input id="valuation-period" className="field" required value={form.period} onChange={set("period")} placeholder="e.g. 2025-12-31" />
              </div>
              <div className="sm:col-span-2">
                <button type="button" className="btn btn-secondary w-full" onClick={loadCompanyProfile} disabled={profileBusy}>{profileBusy ? "Loading existing company profile…" : "Load financials from Companies"}</button>
                <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">This reuses existing company data where available. It will not guess missing figures, and you must review the loaded values and source before calculating.</p>
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-source">Source URL for the financial inputs *</label>
                <input id="valuation-source" className="field" required type="url" value={form.source} onChange={set("source")} placeholder="https://... official filing or statement" />
              </div>
            </div>

            <div>
              <h3 className="text-sm font-medium">Financial inputs</h3>
              <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">Enter monetary values in the same currency units throughout (do not mix thousands, millions or billions). Shares outstanding must be in individual shares, not millions. Use free cash flow to the firm, not net income or dividends. Cash and debt start blank so missing values cannot silently become zero.</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <NumericField id="valuation-fcf" label="Latest annual unlevered free cash flow *" value={form.fcf} onChange={set("fcf")} placeholder="Positive value required" />
                <NumericField id="valuation-shares" label="Shares outstanding *" value={form.shares} onChange={set("shares")} placeholder="Individual shares" />
                <NumericField id="valuation-cash" label="Cash and cash equivalents *" value={form.cash} onChange={set("cash")} />
                <NumericField id="valuation-debt" label="Interest-bearing debt *" value={form.debt} onChange={set("debt")} />
                <NumericField id="valuation-price" label="Current price per share (optional)" value={form.price} onChange={set("price")} placeholder="Use a dated, sourced quote" />
              </div>
            </div>

            <div>
              <h3 className="text-sm font-medium">Scenario assumptions</h3>
              <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">Growth rates are constant annual free-cash-flow growth for five years. The discount rate should reflect business and country risk. Terminal growth must be below the discount rate.</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <NumericField id="valuation-bear" label="Bear-case annual FCF growth (%)" value={form.bearGrowth} onChange={set("bearGrowth")} />
                <NumericField id="valuation-base" label="Base-case annual FCF growth (%)" value={form.baseGrowth} onChange={set("baseGrowth")} />
                <NumericField id="valuation-bull" label="Bull-case annual FCF growth (%)" value={form.bullGrowth} onChange={set("bullGrowth")} />
                <NumericField id="valuation-discount" label="Discount rate / WACC (%)" value={form.discountRate} onChange={set("discountRate")} />
                <NumericField id="valuation-terminal" label="Terminal growth (%)" value={form.terminalGrowth} onChange={set("terminalGrowth")} />
              </div>
            </div>
            <button className="btn btn-primary w-full" type="submit">Calculate scenarios</button>
          </form>
        </section>

        <div className="space-y-6">
          <section className="panel p-5 sm:p-6" aria-labelledby="results-title">
            <p className="eyebrow">Deterministic model</p>
            <h2 id="results-title" className="h3 mt-2 text-xl">Bear, base and bull valuation</h2>
            {!hasCalculated ? (
              <div className="mt-5 rounded-xl border border-dashed hairline p-6">
                <h3 className="text-sm font-medium">No valuation calculated yet</h3>
                <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">Enter sourced inputs and assumptions, then calculate. The page intentionally starts empty instead of showing illustrative values as if they were real market data.</p>
              </div>
            ) : (
              <>
                <p className="mt-3 text-xs leading-relaxed text-[color:var(--muted)]">{form.company}{form.ticker ? ` (${form.ticker})` : ""} · period ended {form.period} · source <a href={form.source} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">open filing ↗</a></p>
                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  {scenarios.map((scenario) => <ScenarioCard key={scenario.name} scenario={scenario} currency={form.currency} price={price} />)}
                </div>
                <div className="mt-6">
                  <h3 className="text-sm font-medium">Base-case sensitivity</h3>
                  <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">Implied value per share when the discount rate moves by ±2 percentage points and terminal growth by ±1 point. Cells where terminal growth meets or exceeds the discount rate are not calculated.</p>
                  <div className="mt-3 overflow-x-auto rounded-lg border hairline">
                    <table className="w-full min-w-[28rem] border-collapse text-left text-xs">
                      <thead>
                        <tr className="border-b hairline text-[color:var(--dim)]">
                          <th className="px-3 py-2 font-normal">Discount rate / Terminal growth</th>
                          {sensitivity[0]?.cells.map((cell) => <th key={cell.terminalGrowth} className="px-3 py-2 font-normal">{cell.terminalGrowth.toFixed(1)}%</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {sensitivity.map((row) => (
                          <tr key={row.discountRate} className="border-b hairline last:border-0">
                            <th className="px-3 py-2 font-normal text-[color:var(--muted)]">{row.discountRate.toFixed(1)}%</th>
                            {row.cells.map((cell) => <td key={cell.terminalGrowth} className="px-3 py-2 kbd">{cell.value == null ? "N/A" : money(cell.value, form.currency)}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="mt-4 rounded-xl border hairline p-4">
                  <p className="eyebrow">Base-case conclusion</p>
                  <h3 className="mt-2 text-lg font-semibold">{verdict ?? "No market-price comparison"}</h3>
                  <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">
                    {verdict
                      ? "This is a mechanical comparison against the entered quote, not a recommendation. A 15% band is a display convention, not a statistical confidence interval."
                      : "Enter a positive current share price from a dated source to compare it with the base-case estimate. Without a quote, the model will not call the stock cheap or expensive."}
                  </p>
                </div>
              </>
            )}
          </section>

          <section className="panel p-5" aria-labelledby="method-title">
            <p className="eyebrow">Method and limitations</p>
            <h2 id="method-title" className="h3 mt-2 text-lg">What this model can and cannot say</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-[color:var(--muted)]">
              <li>Discounts five annual free-cash-flow projections and a terminal value; then adds cash, subtracts debt and divides by shares outstanding.</li>
              <li>It is unsuitable when free cash flow is negative or structurally volatile, or for many banks, insurers, early-stage firms and instruments where this model&apos;s assumptions do not fit.</li>
              <li>It does not independently verify the source, accounting basis, share count, currency, dilution, minority interests or latest price.</li>
              <li>It does not yet adjust for non-operating assets, leases, pension deficits, preferred shares, minority interests, cyclicality or country-specific discount-rate calibration.</li>
              <li>A model output is not a target price or a buy/sell instruction. Review assumptions and contrary evidence before drawing a conclusion.</li>
            </ul>
          </section>

          <section className="rounded-xl border hairline p-5">
            <p className="eyebrow">Next step</p>
            <h2 className="h3 mt-2 text-lg">Put the result in context.</h2>
            <div className="mt-4 grid gap-2">
              <Link href={`/app/companies?name=${encodeURIComponent(form.company)}`} className="btn btn-secondary justify-center">Review company profile</Link>
              <Link href="/app/markets/portfolio" className="btn btn-ghost justify-center">Open Portfolio Intelligence</Link>
              <Link href="/app/research" className="btn btn-ghost justify-center">Research the countercase</Link>
            </div>
          </section>
        </div>
      </div>
    </Container>
  );
}

function NumericField({ id, label, value, onChange, placeholder }: { id: string; label: string; value: string; onChange: (event: { target: { value: string } }) => void; placeholder?: string }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor={id}>{label}</label>
      <input id={id} className="field" type="number" step="any" value={value} onChange={onChange} placeholder={placeholder} />
    </div>
  );
}
