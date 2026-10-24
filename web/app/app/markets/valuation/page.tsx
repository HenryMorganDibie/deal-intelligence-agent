"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { Container } from "../../../../components/primitives";
import { ErrorNote, PageHeader } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { get } from "../../../../lib/market";

type ModelFit = "standard-operating-company" | "financial-institution" | "mature-dividend-payer" | "negative-or-volatile-fcf" | "early-stage" | "reit-property" | "uncertain";

type Inputs = {
  method: "dcf" | "ddm";
  company: string;
  ticker: string;
  modelFit: ModelFit;
  currency: string;
  source: string;
  period: string;
  fcf: string;
  dividendPerShare: string;
  cash: string;
  debt: string;
  shares: string;
  price: string;
  priceDate: string;
  priceSource: string;
  bearGrowth: string;
  baseGrowth: string;
  bullGrowth: string;
  discountRate: string;
  terminalGrowth: string;
};

type Scenario = { name: string; growth: number; growthLabel: string; enterpriseValue: number | null; equityValue: number | null; perShare: number | null };

type CompanyProfile = {
  name: string;
  ticker: string | null;
  identity?: { sector?: string | null; industry?: string | null } | null;
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
  method: "dcf",
  company: "",
  ticker: "",
  modelFit: "uncertain",
  currency: "NGN",
  source: "",
  period: "",
  fcf: "",
  dividendPerShare: "",
  cash: "",
  debt: "",
  shares: "",
  price: "",
  priceDate: "",
  priceSource: "",
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

function validHttpUrl(value: string): boolean {
  try {
    const url = new URL(value.trim());
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function validPastDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value && parsed.getTime() <= Date.now();
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

function ddm(dividendPerShare: number, growthPct: number, discountPct: number, terminalPct: number): number | null {
  const growth = growthPct / 100;
  const discount = discountPct / 100;
  const terminal = terminalPct / 100;
  if (dividendPerShare <= 0 || discount <= terminal || discount <= -1 || growth <= -1 || terminal <= -1) return null;
  let projectedDividend = dividendPerShare;
  let value = 0;
  for (let year = 1; year <= 5; year += 1) {
    projectedDividend *= 1 + growth;
    value += projectedDividend / Math.pow(1 + discount, year);
  }
  const terminalValue = projectedDividend * (1 + terminal) / (discount - terminal);
  value += terminalValue / Math.pow(1 + discount, 5);
  return Number.isFinite(value) ? value : null;
}

function ScenarioCard({ scenario, currency, price }: { scenario: Scenario; currency: string; price: number | null }) {
  const upside = price != null && price > 0 && scenario.perShare != null ? (scenario.perShare / price - 1) * 100 : null;
  return (
    <article className="rounded-xl border hairline p-4">
      <p className="eyebrow">{scenario.name} case</p>
      <p className="mt-2 text-xl font-semibold">{money(scenario.perShare, currency)}</p>
      <p className="mt-1 text-xs text-[color:var(--muted)]">Implied value per share</p>
      <p className="mt-2 text-xs text-[color:var(--muted)]">Five-year {scenario.growthLabel} assumption: {scenario.growth.toFixed(1)}% annually</p>
      <div className="mt-4 flex items-center justify-between gap-3 border-t hairline pt-3 text-xs">
        <span className="text-[color:var(--muted)]">{scenario.enterpriseValue == null ? "Enterprise value" : "Implied enterprise value"}</span>
        <span className="kbd">{scenario.enterpriseValue == null ? "Not applicable to DDM" : money(scenario.enterpriseValue, currency)}</span>
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
  const [detectedSector, setDetectedSector] = useState("");
  const [modelFitConfirmed, setModelFitConfirmed] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const set = <K extends keyof Inputs,>(key: K) => (event: { target: { value: string } }) => {
    setForm((current) => ({ ...current, [key]: event.target.value as Inputs[K] }));
    if (key === "method" || key === "modelFit") setModelFitConfirmed(false);
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
      const sector = String(profile.identity?.sector || profile.identity?.industry || "");
      setDetectedSector(sector);
      const financialInstitution = /bank|financial services|financial institution|insurance|insurer|microfinance|lender|credit provider/i.test(sector);
      if (financialInstitution) {
        setForm((current) => ({ ...current, method: "ddm", modelFit: "financial-institution" }));
        setModelFitConfirmed(false);
      }
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
      const inferredShares = hasDatedQuote && profile.market?.market_cap != null && profile.market.market_cap > 0 && profile.market.price != null && profile.market.price > 0
        ? String(profile.market.market_cap / profile.market.price)
        : "";
      setForm((current) => ({
        ...current,
        company: profile.name || current.company,
        ticker: profile.ticker || current.ticker,
        method: financialInstitution ? "ddm" : current.method,
        modelFit: financialInstitution ? "financial-institution" : current.modelFit,
        currency,
        source: financials.source_url || "",
        period: financials.period?.end || "",
        fcf: value("free_cash_flow"),
        cash: value("cash"),
        debt: value("total_debt"),
        shares: inferredShares,
        price: hasDatedQuote ? String(profile.market!.price) : "",
        priceDate: hasDatedQuote ? String(profile.market?.as_at).slice(0, 10) : "",
        priceSource: "",
      }));
      setHasCalculated(false);
      setModelFitConfirmed(false);
      setProfileMessage([
        `Financial fields loaded from ${financials.source}.`,
        sector ? `Company sector reported by the profile: ${sector}.` : "",
        financialInstitution ? "The sector suggests a bank or financial institution, so the page switched to the dividend discount model. Confirm dividend sustainability before calculating; ordinary-company DCF is not suitable for banks or insurers." : "",
        financials.verified ? "The profile reports its available accounting checks as passed." : "The profile does not report all available accounting checks as passed.",
        inferredShares ? "Shares outstanding is inferred from market capitalisation divided by price, not independently verified." : "Shares outstanding was not inferred because a dated price, market capitalisation or currency alignment was unavailable.",
        hasDatedQuote ? `A price dated ${String(profile.market?.as_at).slice(0, 10)} was prefilled from ${profile.market?.source || "the company profile"}; add its source URL before calculating a price comparison.` : "Current price was left blank because the profile did not provide a dated quote in the statement currency.",
        financials.source_url ? "" : "No direct financial statement URL was returned; add a source URL before calculating.",
        "Review every field, especially units, debt, share count, dividend sustainability and the source period, before calculating.",
      ].filter(Boolean).join(" "));
    } catch (err) {
      setProfileError(err instanceof ApiError ? err.message : "Could not load the existing company profile.");
    } finally {
      setProfileBusy(false);
    }
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const company = params.get("company")?.trim() ?? "";
    const ticker = params.get("ticker")?.trim() ?? "";
    if (!company && !ticker) return;
    setForm((current) => ({ ...current, company: company || current.company, ticker: ticker || current.ticker }));
    setProfileMessage("Company details were prefilled from your portfolio. Load the existing company profile to fetch supported financial fields, then verify all figures and sources before calculating.");
  }, []);

  const parsed = useMemo(() => ({
    fcf: num(form.fcf), dividendPerShare: num(form.dividendPerShare), cash: num(form.cash), debt: num(form.debt), shares: num(form.shares), price: num(form.price),
    bearGrowth: num(form.bearGrowth), baseGrowth: num(form.baseGrowth), bullGrowth: num(form.bullGrowth),
    discountRate: num(form.discountRate), terminalGrowth: num(form.terminalGrowth),
  }), [form]);

  const scenarios = useMemo((): Scenario[] => {
    const { fcf, dividendPerShare, cash, debt, shares, bearGrowth, baseGrowth, bullGrowth, discountRate, terminalGrowth } = parsed;
    if ([bearGrowth, baseGrowth, bullGrowth, discountRate, terminalGrowth].some((value) => value == null)) return [];
    const assumptions = [
      { name: "Bear", growth: bearGrowth!, growthLabel: form.method === "dcf" ? "FCF growth" : "dividend growth" },
      { name: "Base", growth: baseGrowth!, growthLabel: form.method === "dcf" ? "FCF growth" : "dividend growth" },
      { name: "Bull", growth: bullGrowth!, growthLabel: form.method === "dcf" ? "FCF growth" : "dividend growth" },
    ];
    if (form.method === "ddm") {
      if (dividendPerShare == null || dividendPerShare <= 0) return [];
      return assumptions.map((scenario) => ({
        ...scenario,
        enterpriseValue: null,
        equityValue: null,
        perShare: ddm(dividendPerShare, scenario.growth, discountRate!, terminalGrowth!),
      }));
    }
    if ([fcf, cash, debt, shares].some((value) => value == null)) return [];
    return assumptions.map((scenario) => {
      const perShare = dcf(fcf!, scenario.growth, discountRate!, terminalGrowth!, cash!, debt!, shares!);
      return {
        ...scenario,
        perShare,
        enterpriseValue: perShare == null ? null : perShare * shares! - cash! + debt!,
        equityValue: perShare == null ? null : perShare * shares!,
      };
    });
  }, [form.method, parsed]);
  const growthInputsValid = parsed.bearGrowth != null && parsed.baseGrowth != null && parsed.bullGrowth != null &&
    parsed.bearGrowth <= parsed.baseGrowth && parsed.baseGrowth <= parsed.bullGrowth &&
    [parsed.bearGrowth, parsed.baseGrowth, parsed.bullGrowth].every((value) => value != null && value > -100 && value <= 100) &&
    parsed.discountRate != null && parsed.discountRate > 0 && parsed.discountRate <= 60 &&
    parsed.terminalGrowth != null && parsed.terminalGrowth >= -5 && parsed.terminalGrowth <= 8 &&
    parsed.discountRate > parsed.terminalGrowth;
  const sourceInputsValid = form.company.trim().length > 0 && validHttpUrl(form.source) && validPastDate(form.period) &&
    (parsed.price == null || (parsed.price > 0 && validHttpUrl(form.priceSource) && validPastDate(form.priceDate)));
  const sectorRequiresDdm = /bank|financial services|financial institution|insurance|insurer|microfinance|lender|credit provider/i.test(detectedSector);
  const modelFitAllowsDcf = form.modelFit === "standard-operating-company";
  const modelFitAllowsDdm = form.modelFit === "financial-institution" || form.modelFit === "mature-dividend-payer";
  const modelChoiceValid = modelFitConfirmed && (form.method === "dcf" ? modelFitAllowsDcf && !sectorRequiresDdm : modelFitAllowsDdm);
  const modelInputsValid = form.method === "dcf"
    ? parsed.fcf != null && parsed.fcf > 0 && parsed.cash != null && parsed.cash >= 0 && parsed.debt != null && parsed.debt >= 0 && parsed.shares != null && parsed.shares > 0
    : parsed.dividendPerShare != null && parsed.dividendPerShare > 0;
  const validInputs = growthInputsValid && sourceInputsValid && modelChoiceValid && modelInputsValid;

  function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!validInputs) {
      setError(form.method === "dcf"
        ? "Check the source URL, a valid past reporting date, positive FCF and shares, non-negative cash/debt, ordered growth assumptions, discount rate above terminal growth, and confirmation that this is a suitable non-financial operating company. If the profile identifies a bank or insurer, use DDM instead of ordinary-company DCF. A market price also needs an HTTP(S) source URL and a valid past quote date."
        : "Check the source URL, a valid past reporting date, positive annual dividend per share, ordered dividend-growth assumptions, discount rate above terminal growth, and confirmation that the company is a mature dividend payer with a sustainable payout. A market price also needs an HTTP(S) source URL and a valid past quote date.");
      setHasCalculated(false);
      return;
    }
    if (scenarios.length !== 3 || scenarios.some((scenario) => scenario.perShare == null || !Number.isFinite(scenario.perShare))) {
      setError("The entered assumptions do not produce a valid valuation. Review the cash flows, discount rate and terminal growth.");
      setHasCalculated(false);
      return;
    }
    setHasCalculated(true);
  }

  const base = scenarios.find((scenario) => scenario.name === "Base");
  const price = parsed.price;
  const statementAgeDays = validPastDate(form.period) ? Math.floor((Date.now() - new Date(`${form.period}T00:00:00Z`).getTime()) / 86400000) : null;
  const quoteAgeDays = validPastDate(form.priceDate) ? Math.floor((Date.now() - new Date(`${form.priceDate}T00:00:00Z`).getTime()) / 86400000) : null;
  const validScenarioValues = scenarios.map((scenario) => scenario.perShare).filter((value): value is number => value != null && Number.isFinite(value));
  const scenarioLow = validScenarioValues.length ? Math.min(...validScenarioValues) : null;
  const scenarioHigh = validScenarioValues.length ? Math.max(...validScenarioValues) : null;
  const verdict = hasCalculated && base?.perShare != null && price != null
    ? (base.perShare < price * 0.85 ? "Price is more than 15% above the base-case estimate" : base.perShare > price * 1.15 ? "Price is more than 15% below the base-case estimate" : "Price is within 15% of the base-case estimate")
    : null;
  const rangeConclusion = hasCalculated && price != null && validScenarioValues.length === 3
    ? validScenarioValues.every((value) => value < price) ? "Entered price is above all three scenario estimates"
      : validScenarioValues.every((value) => value > price) ? "Entered price is below all three scenario estimates"
        : "The conclusion changes across scenarios"
    : null;

  const sensitivityInputsValid = form.method === "dcf"
    ? parsed.fcf != null && parsed.cash != null && parsed.debt != null && parsed.shares != null
    : parsed.dividendPerShare != null && parsed.dividendPerShare > 0;
  const sensitivity = hasCalculated && sensitivityInputsValid && parsed.baseGrowth != null && parsed.discountRate != null && parsed.terminalGrowth != null
    ? [-2, 0, 2].map((discountOffset) => ({
        discountRate: parsed.discountRate! + discountOffset,
        cells: [-1, 0, 1].map((terminalOffset) => {
          const terminalGrowth = parsed.terminalGrowth! + terminalOffset;
          const value = form.method === "dcf"
            ? dcf(parsed.fcf!, parsed.baseGrowth!, parsed.discountRate! + discountOffset, terminalGrowth, parsed.cash!, parsed.debt!, parsed.shares!)
            : ddm(parsed.dividendPerShare!, parsed.baseGrowth!, parsed.discountRate! + discountOffset, terminalGrowth);
          return { terminalGrowth, value };
        }),
      }))
    : [];

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · Valuation" title="A valuation with a countercase.">
        Choose a model that fits the business, then compare bear, base and bull estimates against a dated, sourced market price. You can load existing company financials, but missing figures are not invented and sources are not independently verified.
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
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-method">Valuation method *</label>
                <select id="valuation-method" className="field" value={form.method} onChange={set("method")}>
                  <option value="dcf">Discounted cash flow (non-financial operating companies)</option>
                  <option value="ddm">Dividend discount (mature dividend payers)</option>
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-currency">Statement / dividend currency</label>
                <select id="valuation-currency" className="field" value={form.currency} onChange={set("currency")}>
                  {["NGN", "KES", "ZAR", "GHS", "EGP", "XOF", "XAF", "MAD", "TZS", "UGX", "RWF", "ETB", "MUR", "DZD", "AOA", "BWP", "BIF", "CVE", "KMF", "CDF", "DJF", "ERN", "SZL", "GMD", "GNF", "LSL", "LRD", "LYD", "MGA", "MWK", "MRU", "MZN", "NAD", "STN", "SCR", "SLE", "SOS", "SSP", "SDG", "TND", "ZMW", "ZWG", "USD", "EUR", "GBP"].map((currency) => <option key={currency} value={currency}>{currency}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-period">Financial period end *</label>
                <input id="valuation-period" className="field" type="date" required value={form.period} onChange={set("period")} />
              </div>
              <div className="sm:col-span-2">
                <button type="button" className="btn btn-secondary w-full" onClick={loadCompanyProfile} disabled={profileBusy}>{profileBusy ? "Loading existing company profile…" : "Load financials from Companies"}</button>
                <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">This reuses existing company data where available. It will not guess missing figures, and you must review the loaded values and source before calculating.</p>
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-source">Source URL for the financial inputs (HTTP or HTTPS) *</label>
                <input id="valuation-source" className="field" required type="url" value={form.source} onChange={set("source")} placeholder="https://... official filing or statement" />
              </div>
            </div>

            <div>
              <h3 className="text-sm font-medium">{form.method === "dcf" ? "Cash-flow inputs" : "Dividend inputs"}</h3>
              {form.method === "dcf" ? (
                <>
                  <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">Use annual unlevered free cash flow from a source you can inspect. Keep cash flow, cash and debt in the same absolute currency units, not mixed thousands, millions or billions. Shares must be individual shares, not millions.</p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <NumericField id="valuation-fcf" label="Latest annual unlevered free cash flow *" value={form.fcf} onChange={set("fcf")} placeholder="Positive value required" />
                    <NumericField id="valuation-shares" label="Shares outstanding *" value={form.shares} onChange={set("shares")} placeholder="Individual shares" />
                    <NumericField id="valuation-cash" label="Cash and cash equivalents *" value={form.cash} onChange={set("cash")} />
                    <NumericField id="valuation-debt" label="Interest-bearing debt *" value={form.debt} onChange={set("debt")} />
                  </div>
                </>
              ) : (
                <>
                  <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">Use the latest annual dividend per share in the same currency as the quoted share price. The model assumes five years of dividend growth followed by a stable terminal growth rate; do not use it where dividends are absent or unsustainable.</p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <NumericField id="valuation-dividend" label={`Latest annual dividend per share (${form.currency}) *`} value={form.dividendPerShare} onChange={set("dividendPerShare")} placeholder="Positive annual dividend" />
                  </div>
                </>
              )}
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <NumericField id="valuation-price" label={`Current price per share in ${form.currency} (optional)`} value={form.price} onChange={set("price")} placeholder="Use a dated, sourced quote" />
                <div>
                  <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-price-date">Quote date (required if price entered)</label>
                  <input id="valuation-price-date" className="field" type="date" value={form.priceDate} onChange={set("priceDate")} />
                </div>
                <div className="sm:col-span-2">
                  <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-price-source">Quote source URL (HTTP or HTTPS, required if price entered)</label>
                  <input id="valuation-price-source" className="field" type="url" value={form.priceSource} onChange={set("priceSource")} placeholder="https://... exchange or market-data source" />
                </div>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-medium">Model suitability check</h3>
              <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">This is a suitability gate, not a formality. Ordinary-company DCF is limited to established non-financial businesses with positive, representative free cash flow. DDM is limited to mature dividend payers with sustainable payouts. Other business types need different models, which this workspace does not yet provide.</p>
              <label className="mb-1.5 mt-3 block text-xs text-[color:var(--muted)]" htmlFor="valuation-model-fit">Company / instrument profile *</label>
              <select id="valuation-model-fit" className="field" value={form.modelFit} onChange={set("modelFit")}>
                <option value="uncertain">Unsure / not yet assessed</option>
                <option value="standard-operating-company">Established non-financial operating company with positive, representative FCF</option>
                <option value="financial-institution">Bank, insurer, lender or other financial institution</option>
                <option value="mature-dividend-payer">Mature dividend payer in another sector</option>
                <option value="negative-or-volatile-fcf">Negative or highly volatile free cash flow</option>
                <option value="early-stage">Early-stage / pre-profit business</option>
                <option value="reit-property">REIT / property investment company</option>
              </select>
              <label className="mt-3 flex items-start gap-2 text-xs leading-relaxed text-[color:var(--muted)]">
                <input type="checkbox" className="mt-0.5" checked={modelFitConfirmed} onChange={(event) => setModelFitConfirmed(event.target.checked)} />
                <span>{form.method === "dcf" ? "I have checked that this is a non-financial operating company and the entered free cash flow is positive and reasonably representative." : "I have checked that this is a mature dividend payer and the entered annual dividend is sustainable."}</span>
              </label>
              {sectorRequiresDdm && form.method === "dcf" ? <p className="mt-2 text-xs text-[color:var(--risk)]">The existing company profile identifies a financial-sector business. This workspace blocks ordinary-company DCF for that profile; switch to DDM and enter a sourced annual dividend per share.</p> : null}
            </div>

            <div>
              <h3 className="text-sm font-medium">Scenario assumptions</h3>
              <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">{form.method === "dcf" ? "Growth rates are annual free-cash-flow growth for five years. Use a discount rate that reflects business and country risk." : "Growth rates are annual dividend growth for five years. Use the cost of equity, not WACC, for discounting dividends."} Terminal growth must be below the discount rate.</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <NumericField id="valuation-bear" label={form.method === "dcf" ? "Bear-case annual FCF growth (%)" : "Bear-case annual dividend growth (%)"} value={form.bearGrowth} onChange={set("bearGrowth")} />
                <NumericField id="valuation-base" label={form.method === "dcf" ? "Base-case annual FCF growth (%)" : "Base-case annual dividend growth (%)"} value={form.baseGrowth} onChange={set("baseGrowth")} />
                <NumericField id="valuation-bull" label={form.method === "dcf" ? "Bull-case annual FCF growth (%)" : "Bull-case annual dividend growth (%)"} value={form.bullGrowth} onChange={set("bullGrowth")} />
                <NumericField id="valuation-discount" label={form.method === "dcf" ? "Discount rate / WACC (%)" : "Cost of equity (%)"} value={form.discountRate} onChange={set("discountRate")} />
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
                {statementAgeDays != null && statementAgeDays > 548 ? <p className="mt-2 rounded-lg border hairline p-3 text-xs leading-relaxed text-[color:var(--muted)]">Freshness warning: this financial period is more than 18 months old. Refresh the statements before relying on the valuation.</p> : null}
                {price != null && quoteAgeDays != null && quoteAgeDays > 7 ? <p className="mt-2 rounded-lg border hairline p-3 text-xs leading-relaxed text-[color:var(--muted)]">Freshness warning: the entered quote is {quoteAgeDays} days old. The comparison may not reflect the current market price.</p> : null}
                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  {scenarios.map((scenario) => <ScenarioCard key={scenario.name} scenario={scenario} currency={form.currency} price={price} />)}
                </div>
                {scenarioLow != null && scenarioHigh != null && (
                  <div className="mt-4 rounded-xl border hairline p-4">
                    <p className="eyebrow">Scenario range, not a confidence interval</p>
                    <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2">
                      <p className="text-lg font-semibold">{money(scenarioLow, form.currency)} – {money(scenarioHigh, form.currency)}</p>
                      <p className="text-xs text-[color:var(--muted)]">Across bear/base/bull assumptions</p>
                    </div>
                    {price != null && form.priceDate && form.priceSource && (
                      <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">Compared with quote dated {form.priceDate} from <a href={form.priceSource} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">the entered market-price source ↗</a>. Quote currency is assumed to match {form.currency}; the tool does not independently verify that alignment.</p>
                    )}
                  </div>
                )}
                <div className="mt-6">
                  <h3 className="text-sm font-medium">Base-case sensitivity</h3>
                  <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">Implied value per share when the {form.method === "dcf" ? "discount rate" : "cost of equity"} moves by ±2 percentage points and terminal growth by ±1 point. Cells where terminal growth meets or exceeds the discount rate are not calculated.</p>
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
                  <h3 className="mt-2 text-lg font-semibold">{rangeConclusion ?? verdict ?? "No market-price comparison"}</h3>
                  <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">
                    {rangeConclusion
                      ? "This conclusion is mechanical and applies only to the three entered DCF scenarios. It is not a recommendation or proof of mispricing; the output can be wrong if the inputs, accounting basis or assumptions are wrong. Review the source and countercase before acting."
                      : verdict
                        ? "This is a mechanical comparison against the entered quote, not a recommendation. A 15% band is a display convention, not a statistical confidence interval."
                        : "Enter a positive current share price from a dated source to compare it with the scenario range. Without a quote, the model will not call the stock cheap or expensive."}
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
