"use client";

import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import Link from "next/link";
import { Container } from "../../../../components/primitives";
import { ErrorNote, PageHeader } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { get } from "../../../../lib/market";
import { calculateDcfPerShare, calculateDdmPerShare, validHttpUrl, validPastDate } from "../../../../lib/markets-valuation";
import { isSavedValuation, parseValuationHistoryBackup, type SavedValuationSnapshot } from "../../../../lib/markets-portfolio";

type ModelFit = "standard-operating-company" | "financial-institution" | "mature-dividend-payer" | "negative-or-volatile-fcf" | "early-stage" | "reit-property" | "uncertain";

const VALUATION_STORAGE_KEY = "deal-intelligence-markets-valuations-v1";
const VALUATION_CURRENCIES = ["AED", "AOA", "AUD", "BIF", "BRL", "BWP", "CAD", "CDF", "CHF", "CNY", "CVE", "DJF", "DZD", "EGP", "ERN", "ETB", "EUR", "GBP", "GHS", "GMD", "GNF", "HKD", "IDR", "INR", "JPY", "KES", "KMF", "KRW", "LRD", "LSL", "LYD", "MAD", "MGA", "MXN", "MRU", "MUR", "MWK", "MYR", "MZN", "NAD", "NGN", "NZD", "PHP", "PKR", "RWF", "SAR", "SCR", "SDG", "SGD", "SLE", "SOS", "SSP", "STN", "SZL", "THB", "TND", "TRY", "TZS", "UGX", "USD", "XAF", "XOF", "ZAR", "ZMW", "ZWG", "ZWL"];

type Inputs = {
  method: "dcf" | "ddm";
  company: string;
  ticker: string;
  country: string;
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
  country?: { code?: string; name?: string } | string | null;
  country_name?: string | null;
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
  country: "",
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
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [backupMessage, setBackupMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const company = params.get("company")?.trim() ?? "";
    const ticker = params.get("ticker")?.trim() ?? "";
    const country = params.get("country")?.trim() ?? "";
    if (company || ticker || country) {
      setForm((current) => ({ ...current, company: company || current.company, ticker: ticker || current.ticker, country: country || current.country }));
    }
  }, []);
  const set = <K extends keyof Inputs,>(key: K) => (event: { target: { value: string } }) => {
    setForm((current) => ({ ...current, [key]: event.target.value as Inputs[K] }));
    if (key === "method" || key === "modelFit") setModelFitConfirmed(false);
    if (key === "company" || key === "ticker") setDetectedSector("");   // a loaded sector belongs to the previous company
    setSavedMessage(null);
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
    setSavedMessage(null);
    try {
      const profile = await get<CompanyProfile>("/api/companies/profile", {
        name,
        ticker: form.ticker.trim(),
        country: form.country.trim(),
      });
      const financials = profile.financials;
      const profileCountry = profile.country_name || (typeof profile.country === "string" ? profile.country : profile.country?.name) || "";
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
      const statementCurrency = financials.currency && VALUATION_CURRENCIES.includes(financials.currency.toUpperCase())
        ? financials.currency.toUpperCase()
        : null;
      const currency = statementCurrency || "NGN";
      const sameCurrency = Boolean(statementCurrency && profile.market?.currency && profile.market.currency.toUpperCase() === statementCurrency);
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
        country: current.country || profileCountry,
        source: financials.source_url || "",
        period: String(financials.period?.end || "").slice(0, 10),
        fcf: value("unlevered_free_cash_flow") || value("fcff"),
        dividendPerShare: value("annual_dividend_per_share") || value("dividend_per_share"),
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
        statementCurrency ? "" : "The source did not return a supported statement currency; the form defaulted to NGN. Change it to match the cited source before calculating.",
        financialInstitution ? "The sector suggests a bank or financial institution, so the page switched to the dividend discount model. Confirm dividend sustainability before calculating; ordinary-company DCF is not suitable for banks or insurers." : "",
        "A generic free_cash_flow field is not automatically treated as unlevered FCFF. If no explicitly labelled FCFF field is available, verify the correct figure in the source and enter it manually.",
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
        perShare: calculateDdmPerShare(dividendPerShare, scenario.growth, discountRate!, terminalGrowth!),
      }));
    }
    if ([fcf, cash, debt, shares].some((value) => value == null)) return [];
    return assumptions.map((scenario) => {
      const perShare = calculateDcfPerShare(fcf!, scenario.growth, discountRate!, terminalGrowth!, cash!, debt!, shares!);
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
  const sourceInputsValid = form.company.trim().length > 0 && VALUATION_CURRENCIES.includes(form.currency) && validHttpUrl(form.source) && validPastDate(form.period) &&
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
    setSavedMessage(null);
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

  function saveValuationLocally() {
    if (!hasCalculated || scenarios.length !== 3 || scenarios.some((scenario) => scenario.perShare == null)) return;
    const snapshot: SavedValuationSnapshot = {
      id: `${form.ticker.trim().toUpperCase() || form.company.trim().toLowerCase()}-${Date.now()}`,
      company: form.company.trim(),
      ticker: form.ticker.trim().toUpperCase(),
      country: form.country.trim(),
      method: form.method,
      modelFit: form.modelFit,
      modelFitConfirmed,
      currency: form.currency,
      statementSourceUrl: form.source,
      statementPeriod: form.period,
      quotePrice: parsed.price,
      quoteDate: parsed.price == null ? null : form.priceDate,
      quoteSourceUrl: parsed.price == null ? null : form.priceSource,
      bearPerShare: scenarios[0].perShare!,
      basePerShare: scenarios[1].perShare!,
      bullPerShare: scenarios[2].perShare!,
      calculatedAt: new Date().toISOString(),
    };
    try {
      const raw = window.localStorage.getItem(VALUATION_STORAGE_KEY);
      let existing: SavedValuationSnapshot[] = [];
      if (raw) {
        const parsedStored: unknown = JSON.parse(raw);
        if (!Array.isArray(parsedStored) || !parsedStored.every(isSavedValuation)) {
          throw new Error("Saved valuation data could not be validated. It was left unchanged to avoid data loss.");
        }
        existing = parsedStored;
      }
      const sameIssuer = (item: SavedValuationSnapshot) => {
        const sameCountry = Boolean(snapshot.country && item.country && snapshot.country.trim().toLowerCase() === item.country.trim().toLowerCase());
        if (snapshot.ticker && item.ticker) return snapshot.ticker === item.ticker.trim().toUpperCase() && sameCountry;
        return snapshot.company.trim().toLowerCase() === item.company.trim().toLowerCase() && sameCountry;
      };
      const history = [...existing.filter(sameIssuer), snapshot]
        .sort((a, b) => Date.parse(b.calculatedAt) - Date.parse(a.calculatedAt))
        .slice(0, 10);
      const otherIssuers = existing.filter((item) => !sameIssuer(item));
      window.localStorage.setItem(VALUATION_STORAGE_KEY, JSON.stringify([...otherIssuers, ...history]));
      setSavedMessage("Saved locally in this browser. Up to 10 dated snapshots per company are kept so Markets can flag material changes in your model estimate. Portfolio reviews still require matching currency, quote date and price, and a suitable model.");
    } catch (saveError) {
      setSavedMessage(saveError instanceof Error ? saveError.message : "Could not save this valuation in browser storage.");
    }
  }

  function exportValuationHistory() {
    try {
      const raw = window.localStorage.getItem(VALUATION_STORAGE_KEY);
      const parsed: unknown = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(parsed) || !parsed.every(isSavedValuation)) {
        throw new Error("Saved valuation history could not be validated. It was left unchanged; check the stored data before exporting.");
      }
      if (parsed.length === 0) {
        setBackupMessage("There is no saved valuation history to export yet. Calculate and save a valuation first.");
        return;
      }
      const backup = JSON.stringify({ version: 1, exportedAt: new Date().toISOString(), valuations: parsed }, null, 2);
      const url = URL.createObjectURL(new Blob([backup], { type: "application/json;charset=utf-8" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "deal-intelligence-valuation-history.json";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setBackupMessage(`Exported ${parsed.length} saved valuation snapshot(s). Keep this file somewhere safe; it contains your financial assumptions and source links.`);
    } catch (backupError) {
      setBackupMessage(backupError instanceof Error ? backupError.message : "Could not export saved valuation history.");
    }
  }

  async function importValuationHistory(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      if (file.size > 2 * 1024 * 1024) throw new Error("Valuation-history backups must be 2 MB or smaller.");
      const raw = await file.text();
      const parsed: unknown = JSON.parse(raw);
      const snapshots = parseValuationHistoryBackup(parsed);
      if (!snapshots) throw new Error("This is not a valid Deal Intelligence valuation-history backup. No saved data was changed.");
      if (!window.confirm(`Replace the valuation history in this browser with ${snapshots.length} snapshot(s) from this backup? Export the current history first if you need to keep it.`)) {
        setBackupMessage("Valuation-history restore cancelled. Existing saved data was not changed.");
        return;
      }
      window.localStorage.setItem(VALUATION_STORAGE_KEY, JSON.stringify(snapshots));
      setBackupMessage(`Restored ${snapshots.length} saved valuation snapshot(s) to this browser. Portfolio holdings were not changed.`);
    } catch (backupError) {
      setBackupMessage(backupError instanceof Error ? backupError.message : "Could not restore valuation history.");
    }
  }

  const base = scenarios.find((scenario) => scenario.name === "Base");
  const price = parsed.price;
  const statementAgeDays = validPastDate(form.period) ? Math.floor((Date.now() - new Date(`${form.period}T00:00:00Z`).getTime()) / 86400000) : null;
  const quoteAgeDays = validPastDate(form.priceDate) ? Math.floor((Date.now() - new Date(`${form.priceDate}T00:00:00Z`).getTime()) / 86400000) : null;
  const validScenarioValues = scenarios.map((scenario) => scenario.perShare).filter((value): value is number => value != null && Number.isFinite(value));
  const scenarioLow = validScenarioValues.length ? Math.min(...validScenarioValues) : null;
  const scenarioHigh = validScenarioValues.length ? Math.max(...validScenarioValues) : null;
  const verdict = hasCalculated && base?.perShare != null && price != null && validScenarioValues.length === 3
    ? validScenarioValues.every((value) => value < price) && base.perShare < price * 0.85
      ? "Potentially overvalued on these assumptions"
      : validScenarioValues.every((value) => value > price) && base.perShare > price * 1.15
        ? "Potentially undervalued on these assumptions"
        : validScenarioValues.every((value) => value < price)
          ? "Price is above all three scenario estimates, but the base-case gap is under 15%"
          : validScenarioValues.every((value) => value > price)
            ? "Price is below all three scenario estimates, but the base-case gap is under 15%"
            : "Mixed signal: the conclusion changes across scenarios"
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
            ? calculateDcfPerShare(parsed.fcf!, parsed.baseGrowth!, parsed.discountRate! + discountOffset, terminalGrowth, parsed.cash!, parsed.debt!, parsed.shares!)
            : calculateDdmPerShare(parsed.dividendPerShare!, parsed.baseGrowth!, parsed.discountRate! + discountOffset, terminalGrowth);
          return { terminalGrowth, value };
        }),
      }))
    : [];

  const countercaseQuestion = [
    `Challenge, do not confirm, the ${form.method === "dcf" ? "DCF" : "dividend discount"} valuation for ${form.company}${form.ticker ? ` (${form.ticker})` : ""}.`,
    `Period ${form.period}; assumptions: bear/base/bull ${form.bearGrowth}/${form.baseGrowth}/${form.bullGrowth}% growth, discount ${form.discountRate}%, terminal ${form.terminalGrowth}%.`,
    price != null ? `Entered quote: ${form.price} ${form.currency}, dated ${form.priceDate}.` : "No market quote was supplied.",
    "Use current primary evidence to test cash-flow or dividend sustainability, debt and dilution, source freshness, currency, country, sector and regulatory risks. Separate confirmed facts, inference and unknowns; state what would invalidate the model conclusion.",
  ].join(" ").slice(0, 500);

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
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-country">Country / market *</label>
                <input id="valuation-country" className="field" required value={form.country} onChange={set("country")} placeholder="e.g. Nigeria" />
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
                  {VALUATION_CURRENCIES.map((currency) => <option key={currency} value={currency}>{currency}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-period">Financial / dividend period end *</label>
                <input id="valuation-period" className="field" type="date" required value={form.period} onChange={set("period")} />
              </div>
              <div className="sm:col-span-2">
                <button type="button" className="btn btn-secondary w-full" onClick={loadCompanyProfile} disabled={profileBusy}>{profileBusy ? "Loading existing company profile…" : "Load financials from Companies"}</button>
                <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">This reuses existing company data where available. It will not guess missing figures, and you must review the loaded values and source before calculating.</p>
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-source">Source URL for the financial / dividend inputs (HTTP or HTTPS) *</label>
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
                <span>{form.method === "dcf" ? "I have checked that this is a non-financial operating company, the entered free cash flow is positive and representative, and the currency and units match the cited source." : "I have checked that this is a mature dividend payer, the entered annual dividend is sustainable, and the currency matches the cited source."}</span>
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
                          <th className="px-3 py-2 font-normal">{form.method === "dcf" ? "Discount rate" : "Cost of equity"} / Terminal growth</th>
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
                  <p className="eyebrow">Conclusion across scenarios</p>
                  <h3 className="mt-2 text-lg font-semibold">{verdict ?? rangeConclusion ?? "No market-price comparison"}</h3>
                  <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">
                    {verdict || rangeConclusion
                      ? "This is a mechanical comparison of the entered quote with the three model scenarios, not a recommendation or proof of mispricing; the 15% base-case band is a display convention, not a statistical confidence interval. The output can be wrong if the inputs, accounting basis or assumptions are wrong. Review the source and countercase before acting."
                      : "Enter a positive current share price from a dated source to compare it with the scenario range. Without a quote, the model will not call the stock cheap or expensive."}
                  </p>
                </div>
                <div className="mt-4 rounded-xl border hairline p-4">
                  <button type="button" className="btn btn-secondary w-full" onClick={saveValuationLocally}>Save valuation to Portfolio Intelligence</button>
                  {savedMessage ? <p className="mt-3 text-xs leading-relaxed text-[color:var(--muted)]" role="status" aria-live="polite">{savedMessage}</p> : <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">Saved valuation scenarios stay in this browser. They are not uploaded to the server. Export a backup before clearing browser data or moving to another device.</p>}
                </div>
              </>
            )}
          </section>

          <section className="mt-6 panel p-5 sm:p-6" aria-labelledby="valuation-backup-title">
            <p className="eyebrow">Local data backup</p>
            <h2 id="valuation-backup-title" className="h3 mt-2 text-lg">Keep your valuation history portable.</h2>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[color:var(--muted)]">Export or restore saved valuation snapshots at any time, even before calculating a new model in this session. These JSON backups include valuation assumptions and source links, not portfolio holdings. Portfolio holdings use the separate CSV/XLSX backup controls in My Portfolio.</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <button type="button" className="btn btn-secondary justify-center" onClick={exportValuationHistory}>Export saved valuation history</button>
              <label className="block text-xs leading-relaxed text-[color:var(--muted)]">
                Restore valuation history from JSON backup
                <input className="field mt-2" type="file" accept=".json,application/json" onChange={importValuationHistory} aria-describedby="valuation-backup-help" />
              </label>
            </div>
            <p id="valuation-backup-help" className="mt-2 text-xs leading-relaxed text-[color:var(--dim)]">Import validates the file, is limited to 2 MB, and asks before replacing saved history.</p>
            {backupMessage ? <p className="mt-3 text-xs leading-relaxed text-[color:var(--muted)]" role="status" aria-live="polite">{backupMessage}</p> : null}
          </section>

          <section className="panel p-5" aria-labelledby="method-title">
            <p className="eyebrow">Method and limitations</p>
            <h2 id="method-title" className="h3 mt-2 text-lg">What this model can and cannot say</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-[color:var(--muted)]">
              <li>{form.method === "dcf" ? "Projects five years of unlevered free cash flow, discounts cash flows and terminal value, adds cash, subtracts debt and divides by shares outstanding." : "Projects five years of annual dividends per share and discounts dividends plus terminal value using the cost of equity."}</li>
              <li>{form.method === "dcf" ? "It is unsuitable for banks, insurers, early-stage businesses, REITs and firms with negative or structurally volatile free cash flow." : "It is unsuitable when dividends are absent, irregular or unsustainable, or when payout policy is likely to change materially."}</li>
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
              <Link href={`/app/research?question=${encodeURIComponent(countercaseQuestion)}`} className="btn btn-ghost justify-center">Research the countercase</Link>
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
