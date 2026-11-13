"use client";

import { useCallback, useEffect, useMemo, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { MarketsTitle } from "../../../../components/app/MarketsNav";
import { Container } from "../../../../components/primitives";
import { ErrorNote } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { get, post } from "../../../../lib/market";
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
  market?: { price?: number | null; currency?: string | null; market_cap?: number | null; source?: string; as_at?: string | null;
    shares_outstanding?: number | null; stale?: boolean; age_days?: number } | null;
  listing?: { exchange: string; symbol: string; exchange_name: string } | null;
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

type EvidenceField = { status: string; note?: string; reference?: number | string; reference_date?: string };
type Evidence = {
  grade: "A" | "B" | "C" | "D";
  verdict_allowed: boolean;
  fields: Record<string, EvidenceField>;
  document: { url: string | null; standing: "official" | "company" | "other" | null; status: string; names_company: boolean; states_period: boolean; read_as_statement?: boolean };
  freshness: { statement_age_days: number | null; statement_stale: boolean; price_age_days: number | null; price_stale: boolean };
  reasons: string[];
  method: string;
};
const FIELD_LABEL: Record<string, string> = {
  fcf: "Free cash flow", cash: "Cash", debt: "Debt", dividend_per_share: "Dividend per share", price: "Share price",
  shares: "Shares outstanding", currency: "Currency",
};
const STATUS_LABEL: Record<string, [string, string]> = {
  verified: ["Verified", "text-verified"], found: ["Found in source", "text-verified"],
  found_unofficial: ["Found, unofficial source", "text-caution"], not_found: ["Not found in source", "text-risk"],
  found_unlabelled: ["Not under its line item", "text-caution"],
  differs_from_statement: ["Differs from the statement", "text-caution"],
  mismatch: ["Contradicted", "text-risk"], unchecked: ["Not checked", "text-[color:var(--muted)]"],
};
const STANDING_LABEL: Record<string, string> = {
  official: "exchange or regulator filing", company: "the company's own website", other: "neither an exchange or regulator nor the company",
};

type CostOfEquity = {
  country: string;
  currency: string | null;
  risk_free_usd: number;
  mature_equity_premium: number;
  country_premium: number;
  cost_of_equity_usd: number;
  cost_of_equity_local: number | null;
  local_inflation: number | null;
  us_inflation: number;
};

type ValuationTab = "model" | "saved" | "method";
const VALUATION_TABS: [ValuationTab, string][] = [["model", "Model"], ["saved", "Saved valuations"], ["method", "Method"]];

export default function MarketsValuationPage() {
  const [form, setForm] = useState<Inputs>(initial);
  const [tab, setTab] = useState<ValuationTab>("model");
  const [saved, setSaved] = useState<SavedValuationSnapshot[]>([]);
  const readSaved = useCallback(() => {
    try {
      const parsed: unknown = JSON.parse(window.localStorage.getItem(VALUATION_STORAGE_KEY) || "[]");
      setSaved(Array.isArray(parsed) ? parsed.filter(isSavedValuation).sort((a, b) => b.calculatedAt.localeCompare(a.calculatedAt)) : []);
    } catch { setSaved([]); }
  }, []);
  const pick = (id: ValuationTab) => {
    setTab(id);
    if (id === "saved") readSaved();
    try { window.history.replaceState(null, "", `${window.location.search}#${id}`); } catch { /* ignore */ }
  };
  useEffect(() => {
    readSaved();
    const follow = () => {
      const h = window.location.hash.replace("#", "");
      if (VALUATION_TABS.some(([id]) => id === h)) setTab(h as ValuationTab);
    };
    follow();
    window.addEventListener("hashchange", follow);
    return () => window.removeEventListener("hashchange", follow);
  }, [readSaved]);
  const [error, setError] = useState<string | null>(null);
  const [hasCalculated, setHasCalculated] = useState(false);
  const [listing, setListing] = useState<{ exchange: string; symbol: string; exchange_name: string } | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [evidenceBusy, setEvidenceBusy] = useState(false);
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
      setListing(profile.listing ?? null);
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
      // A quote more than a week old does not anchor a price comparison.
      const hasDatedQuote = Boolean(profile.market?.as_at && profile.market?.price != null && sameCurrency && !profile.market?.stale);
      const publishedShares = profile.market?.shares_outstanding && profile.market.shares_outstanding > 0 ? String(profile.market.shares_outstanding) : "";
      const inferredShares = publishedShares || (hasDatedQuote && profile.market?.market_cap != null && profile.market.market_cap > 0 && profile.market.price != null && profile.market.price > 0
        ? String(profile.market.market_cap / profile.market.price)
        : "");
      const countryCode = typeof profile.country === "string" ? profile.country : null;
      const coe = countryCode
        ? await get<CostOfEquity>("/api/valuation/cost-of-equity", { country: countryCode }).catch(() => null)
        : null;
      const coeRate = coe ? (currency === "USD" ? coe.cost_of_equity_usd : coe.currency === currency ? coe.cost_of_equity_local : null) : null;
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
        discountRate: coeRate != null ? (coeRate * 100).toFixed(1) : current.discountRate,
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
        publishedShares ? "Shares outstanding comes from the exchange's published market capitalisation and price; verify it against the latest filing." : inferredShares ? "Shares outstanding is inferred from market capitalisation divided by price, not independently verified." : "Shares outstanding was not inferred because a dated price, market capitalisation or currency alignment was unavailable.",
        profile.market?.stale ? `The latest price is ${profile.market.age_days} days old, so it was not prefilled.` : "",
        coe && coeRate != null ? `Discount rate set to the ${currency} cost of equity for ${coe.country}: ${(coeRate * 100).toFixed(1)}% (US risk-free ${(coe.risk_free_usd * 100).toFixed(1)}% + equity premium ${(coe.mature_equity_premium * 100).toFixed(1)}% + country premium ${(coe.country_premium * 100).toFixed(1)}%${currency !== "USD" && coe.local_inflation != null ? `, converted at ${(coe.local_inflation * 100).toFixed(1)}% local vs ${(coe.us_inflation * 100).toFixed(1)}% US inflation` : ""}). The country premium is a proxy from the risk score; adjust it if you hold a better estimate.` : "",
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
    (parsed.price == null || (parsed.price > 0 && validPastDate(form.priceDate) && (form.priceSource.trim() === "" || validHttpUrl(form.priceSource))));
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
        ? "Check the source URL, a valid past reporting date, positive FCF and shares, non-negative cash/debt, ordered growth assumptions, discount rate above terminal growth, and confirmation that this is a suitable non-financial operating company. If the profile identifies a bank or insurer, use DDM instead of ordinary-company DCF. A market price also needs a valid past quote date."
        : "Check the source URL, a valid past reporting date, positive annual dividend per share, ordered dividend-growth assumptions, discount rate above terminal growth, and confirmation that the company is a mature dividend payer with a sustainable payout. A market price also needs a valid past quote date.");
      setHasCalculated(false);
      return;
    }
    if (scenarios.length !== 3 || scenarios.some((scenario) => scenario.perShare == null || !Number.isFinite(scenario.perShare))) {
      setError("The entered assumptions do not produce a valid valuation. Review the cash flows, discount rate and terminal growth.");
      setHasCalculated(false);
      return;
    }
    setHasCalculated(true);
    void checkEvidence();
  }

  // Each input checked on the server against the exchange's close and shares, the parsed filing, and the cited
  // document itself; a URL on its own proves nothing.
  async function checkEvidence() {
    setEvidenceBusy(true);
    setEvidence(null);
    try {
      setEvidence(await post<Evidence>("/api/valuation/evidence", {
        company: form.company.trim(), ticker: form.ticker.trim(), country: form.country.trim(),
        exchange: listing?.exchange ?? "", symbol: listing?.symbol ?? "", method: form.method, currency: form.currency,
        period: form.period, source: form.source.trim(), price: parsed.price, price_date: form.priceDate,
        price_source: form.priceSource.trim(), shares: parsed.shares, fcf: parsed.fcf, cash: parsed.cash,
        debt: parsed.debt, dividend_per_share: parsed.dividendPerShare,
      }));
    } catch {
      setEvidence(null);
    } finally {
      setEvidenceBusy(false);
    }
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
      readSaved();
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
      readSaved();
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
  const verdict = hasCalculated && evidence?.verdict_allowed && base?.perShare != null && price != null && validScenarioValues.length === 3
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
  const rangeConclusion = hasCalculated && evidence?.verdict_allowed && price != null && validScenarioValues.length === 3
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

  const methodWord = form.method === "dcf" ? "free cash flow" : "dividend";
  const conclusion = verdict ?? rangeConclusion ?? (price != null && evidence && !evidence.verdict_allowed ? "No verdict: the inputs are not sufficiently evidenced" : null);

  return (
    <Container className="pb-10 pt-6 lg:pb-14">
      <MarketsTitle title="Valuation">Bear, base and bull estimates against a dated market price. Missing figures are never invented.</MarketsTitle>

      <div role="tablist" aria-label="Valuation" className="-mx-1 mb-6 flex flex-wrap gap-1.5 px-1">
        {VALUATION_TABS.map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => pick(id)}
                  className={`rounded-full px-3 py-1 text-[0.8125rem] transition-colors ${
                    tab === id ? "bg-white/[0.09] text-[color:var(--text)]" : "text-[color:var(--muted)] hover:text-[color:var(--text)]"}`}>
            {label}{id === "saved" && saved.length ? <span className="ml-1 text-[color:var(--dim)]">{saved.length}</span> : null}
          </button>
        ))}
      </div>

      {tab === "model" && (
        <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <section aria-label="Inputs" className="min-w-0">
            {error && <div className="mb-4"><ErrorNote message={error} /></div>}
            {profileError && <div className="mb-4"><ErrorNote message={profileError} /></div>}
            {profileMessage && <p className="mb-4 text-[0.8125rem] text-[color:var(--muted)]" role="status">{profileMessage}</p>}
            <form className="space-y-8" onSubmit={calculate}>
              <Step n={1} title="Company">
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
                  <div className="flex items-end">
                    <button type="button" className="btn btn-secondary w-full" onClick={loadCompanyProfile} disabled={profileBusy}>{profileBusy ? "Loading…" : "Load financials from Companies"}</button>
                  </div>
                </div>
                <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">Loads what the company profile has; nothing missing is guessed. Check the figures and source before calculating.</p>
              </Step>

              <Step n={2} title="Method and source">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-method">Valuation method *</label>
                    <select id="valuation-method" className="field" value={form.method} onChange={set("method")}>
                      <option value="dcf">Discounted cash flow (non-financial operating companies)</option>
                      <option value="ddm">Dividend discount (banks, insurers, mature dividend payers)</option>
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
                    <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-source">Source link for the figures *</label>
                    <input id="valuation-source" className="field" required type="url" value={form.source} onChange={set("source")} placeholder="https://… annual report or statement" />
                  </div>
                </div>
              </Step>

              <Step n={3} title={form.method === "dcf" ? "Cash flow and balance sheet" : "Dividend"}
                    hint={form.method === "dcf" ? "All in the same units (not thousands or millions); shares as a count." : "The latest annual dividend per share, in the quote's currency."}>
                <div className="grid gap-3 sm:grid-cols-2">
                  {form.method === "dcf" ? (
                    <>
                      <NumericField id="valuation-fcf" label="Latest annual unlevered free cash flow *" value={form.fcf} onChange={set("fcf")} placeholder="Positive" />
                      <NumericField id="valuation-shares" label="Shares outstanding *" value={form.shares} onChange={set("shares")} placeholder="Number of shares" />
                      <NumericField id="valuation-cash" label="Cash and cash equivalents *" value={form.cash} onChange={set("cash")} />
                      <NumericField id="valuation-debt" label="Interest-bearing debt *" value={form.debt} onChange={set("debt")} />
                    </>
                  ) : (
                    <NumericField id="valuation-dividend" label={`Latest annual dividend per share (${form.currency}) *`} value={form.dividendPerShare} onChange={set("dividendPerShare")} placeholder="Positive" />
                  )}
                </div>
              </Step>

              <Step n={4} title="Market price" hint="Optional. Without a dated quote the model will not call the share cheap or expensive. Listed prices are checked against the exchange's close.">
                <div className="grid gap-3 sm:grid-cols-2">
                  <NumericField id="valuation-price" label={`Price per share (${form.currency})`} value={form.price} onChange={set("price")} />
                  <div>
                    <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-price-date">Quote date</label>
                    <input id="valuation-price-date" className="field" type="date" value={form.priceDate} onChange={set("priceDate")} />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-price-source">Quote source link</label>
                    <input id="valuation-price-source" className="field" type="url" value={form.priceSource} onChange={set("priceSource")} placeholder="https://… exchange or data source" />
                  </div>
                </div>
              </Step>

              <Step n={5} title="Is the model suitable?">
                <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="valuation-model-fit">Company / instrument profile *</label>
                <select id="valuation-model-fit" className="field" value={form.modelFit} onChange={set("modelFit")}>
                  <option value="uncertain">Unsure / not yet assessed</option>
                  <option value="standard-operating-company">Established non-financial operating company with positive, representative FCF</option>
                  <option value="financial-institution">Bank, insurer, lender or other financial institution</option>
                  <option value="mature-dividend-payer">Mature dividend payer in another sector</option>
                  <option value="negative-or-volatile-fcf">Negative or highly volatile free cash flow</option>
                  <option value="early-stage">Early-stage / pre-profit business</option>
                  <option value="reit-property">REIT / property investment company</option>
                </select>
                <label className="mt-3 flex items-start gap-2 text-[0.8125rem] text-[color:var(--muted)]">
                  <input type="checkbox" className="mt-1" checked={modelFitConfirmed} onChange={(event) => setModelFitConfirmed(event.target.checked)} />
                  <span>{form.method === "dcf" ? "Non-financial operating company; free cash flow is positive and representative; currency and units match the source." : "Mature dividend payer; the dividend is sustainable; the currency matches the source."}</span>
                </label>
                {sectorRequiresDdm && form.method === "dcf" ? <p className="mt-2 text-[0.8125rem] text-risk">The company profile shows a financial-sector business, so DCF is blocked. Switch to dividend discount and enter the annual dividend.</p> : null}
              </Step>

              <Step n={6} title="Scenarios" hint={`Five years of annual ${methodWord} growth, then terminal growth, which must be below the ${form.method === "dcf" ? "discount rate" : "cost of equity"}.`}>
                <div className="grid gap-3 sm:grid-cols-3">
                  <NumericField id="valuation-bear" label={form.method === "dcf" ? "Bear-case annual FCF growth (%)" : "Bear-case annual dividend growth (%)"} value={form.bearGrowth} onChange={set("bearGrowth")} />
                  <NumericField id="valuation-base" label={form.method === "dcf" ? "Base-case annual FCF growth (%)" : "Base-case annual dividend growth (%)"} value={form.baseGrowth} onChange={set("baseGrowth")} />
                  <NumericField id="valuation-bull" label={form.method === "dcf" ? "Bull-case annual FCF growth (%)" : "Bull-case annual dividend growth (%)"} value={form.bullGrowth} onChange={set("bullGrowth")} />
                  <NumericField id="valuation-discount" label={form.method === "dcf" ? "Discount rate / WACC (%)" : "Cost of equity (%)"} value={form.discountRate} onChange={set("discountRate")} />
                  <NumericField id="valuation-terminal" label="Terminal growth (%)" value={form.terminalGrowth} onChange={set("terminalGrowth")} />
                </div>
              </Step>
              <button className="btn btn-primary w-full sm:w-auto" type="submit">Calculate scenarios</button>
            </form>
          </section>

          <section aria-label="Result" className="min-w-0 xl:sticky xl:top-20 xl:self-start">
            {!hasCalculated ? (
              <div className="rounded-xl border border-dashed hairline p-6">
                <h2 className="text-[0.9375rem] text-[color:var(--text)]">No valuation yet</h2>
                <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">Fill in the steps and calculate. The result appears here: bear, base and bull value per share, the range against the quote, a sensitivity table and a check of each input against its source.</p>
              </div>
            ) : (
              <>
                <p className="text-[0.8125rem] text-[color:var(--dim)]">{form.company}{form.ticker ? ` · ${form.ticker}` : ""} · period ended {form.period} · <a href={form.source} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">source ↗</a></p>
                <h2 className="mt-1 text-[1.25rem] text-[color:var(--text)]">{conclusion ?? "No market-price comparison"}</h2>
                {scenarioLow != null && scenarioHigh != null && (
                  <p className="mt-1 text-[0.875rem] text-[color:var(--muted)]">Range <span className="kbd text-[color:var(--text)]">{money(scenarioLow, form.currency)} – {money(scenarioHigh, form.currency)}</span>{price != null ? <> against <span className="kbd text-[color:var(--text)]">{money(price, form.currency)}</span>{form.priceDate ? ` on ${form.priceDate}` : ""}</> : null}</p>
                )}
                {statementAgeDays != null && statementAgeDays > 548 ? <p className="mt-2 text-[0.8125rem] text-risk">The financial period is over 18 months old.</p> : null}
                {price != null && quoteAgeDays != null && quoteAgeDays > 7 ? <p className="mt-2 text-[0.8125rem] text-risk">The quote is {quoteAgeDays} days old.</p> : null}

                <div className="mt-5 grid grid-cols-3 gap-4 border-y hairline py-4">
                  {scenarios.map((sc) => {
                    const upside = price != null && price > 0 && sc.perShare != null ? (sc.perShare / price - 1) * 100 : null;
                    return (
                      <div key={sc.name} className="min-w-0">
                        <p className="text-[0.75rem] text-[color:var(--dim)]">{sc.name} · {sc.growth.toFixed(1)}%</p>
                        <p className="kbd mt-0.5 truncate text-[1.125rem] text-[color:var(--text)]">{money(sc.perShare, form.currency)}</p>
                        <p className={`kbd text-[0.75rem] ${upside == null ? "text-[color:var(--dim)]" : upside < 0 ? "text-risk" : "text-verified"}`}>{upside == null ? "no quote" : `${upside > 0 ? "+" : ""}${upside.toFixed(1)}% vs price`}</p>
                      </div>
                    );
                  })}
                </div>

                <div className="mt-6">
                  <h3 className="text-[0.875rem] text-[color:var(--text)]">Sensitivity, base case</h3>
                  <p className="mt-0.5 text-[0.75rem] text-[color:var(--dim)]">Value per share as the {form.method === "dcf" ? "discount rate" : "cost of equity"} (rows) and terminal growth (columns) move.</p>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full min-w-[26rem] border-collapse text-left text-[0.8125rem]">
                      <thead>
                        <tr className="border-b hairline text-[color:var(--dim)]">
                          <th className="py-2 pr-3 font-normal" />
                          {sensitivity[0]?.cells.map((cell) => <th key={cell.terminalGrowth} className="py-2 pr-3 font-normal">{cell.terminalGrowth.toFixed(1)}%</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {sensitivity.map((row) => (
                          <tr key={row.discountRate} className="border-b hairline last:border-0">
                            <th className="py-2 pr-3 font-normal text-[color:var(--muted)]">{row.discountRate.toFixed(1)}%</th>
                            {row.cells.map((cell) => <td key={cell.terminalGrowth} className="kbd py-2 pr-3">{cell.value == null ? "–" : money(cell.value, form.currency)}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="mt-6" aria-live="polite">
                  <div className="flex items-center gap-2">
                    <h3 className="text-[0.875rem] text-[color:var(--text)]">Evidence for the inputs</h3>
                    {evidence ? <span className={`rounded-full border px-2 py-0.5 text-[0.6875rem] ${evidence.grade === "A" || evidence.grade === "B" ? "text-verified border-verified/35" : "text-risk border-risk/40"}`}>Grade {evidence.grade}</span> : null}
                  </div>
                  {evidenceBusy && <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]" role="status">Checking each input against exchange data, the filing and the cited document…</p>}
                  {!evidenceBusy && !evidence && <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">The check could not run. <button type="button" className="underline" onClick={() => void checkEvidence()}>Try again</button></p>}
                  {evidence && (
                    <>
                      <table className="mt-2 w-full text-left text-[0.8125rem]">
                        <tbody className="divide-y divide-white/[0.07] border-y hairline">
                          {Object.entries(evidence.fields).map(([k, f]) => (
                            <tr key={k}>
                              <td className="py-1.5 pr-3 text-[color:var(--muted)]">{FIELD_LABEL[k] ?? k}</td>
                              <td className={`py-1.5 pr-3 ${STATUS_LABEL[f.status]?.[1] ?? ""}`}>{STATUS_LABEL[f.status]?.[0] ?? f.status}</td>
                              <td className="py-1.5 text-[0.75rem] text-[color:var(--dim)]">{f.note}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <p className="mt-2 text-[0.75rem] text-[color:var(--muted)]">
                        Source document: {evidence.document.standing ? STANDING_LABEL[evidence.document.standing] : "none"}
                        {evidence.document.status === "ok"
                          ? `; ${evidence.document.names_company ? "names the company" : "does not name the company"}, ${evidence.document.states_period ? "states the period" : "does not state the period"}${evidence.document.read_as_statement ? ", read as a financial statement" : ""}.`
                          : evidence.document.url ? `; could not be read (${evidence.document.status}).` : "."}
                      </p>
                      {evidence.reasons.length > 0 && <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[0.75rem] text-[color:var(--muted)]">{evidence.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
                    </>
                  )}
                </div>

                <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2">
                  <button type="button" className="btn btn-secondary" onClick={saveValuationLocally}>Save to portfolio</button>
                  <Link href={`/app/companies?name=${encodeURIComponent(form.company)}`} className="text-[0.8125rem] text-[color:var(--muted)] underline-offset-4 hover:text-[color:var(--text)] hover:underline">Company profile</Link>
                  <Link href={`/app/research?question=${encodeURIComponent(countercaseQuestion)}`} className="text-[0.8125rem] text-[color:var(--muted)] underline-offset-4 hover:text-[color:var(--text)] hover:underline">Research the countercase</Link>
                </div>
                {savedMessage && <p className="mt-2 text-[0.8125rem] text-[color:var(--muted)]" role="status" aria-live="polite">{savedMessage}</p>}
                <p className="mt-4 text-[0.75rem] text-[color:var(--dim)]">A mechanical comparison of the quote with three scenarios, not a target price or a recommendation. The 15% band around the base case is a display convention.</p>
              </>
            )}
          </section>
        </div>
      )}

      {tab === "saved" && (
        <section aria-label="Saved valuations">
          {saved.length === 0 ? (
            <p className="text-[0.8125rem] text-[color:var(--muted)]">Nothing saved yet. Calculate a valuation and choose Save to portfolio; it is then set against the holding on the Portfolio page.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[46rem] text-left text-[0.8125rem]">
                <thead className="text-[color:var(--dim)]"><tr><th className="py-2.5 pr-3 font-normal">Company</th><th className="py-2.5 pr-3 font-normal">Method</th><th className="py-2.5 pr-3 font-normal">Bear · base · bull</th><th className="py-2.5 pr-3 font-normal">Quote</th><th className="py-2.5 pr-3 font-normal">Saved</th><th className="py-2.5 font-normal" /></tr></thead>
                <tbody className="divide-y divide-white/[0.07] border-t hairline">
                  {saved.map((v) => (
                    <tr key={v.id}>
                      <td className="py-2.5 pr-3 text-[color:var(--text)]">{v.company}{v.ticker ? <span className="text-[color:var(--dim)]"> · {v.ticker}</span> : null}</td>
                      <td className="py-2.5 pr-3 text-[color:var(--muted)]">{v.method === "dcf" ? "DCF" : "Dividend discount"}</td>
                      <td className="kbd py-2.5 pr-3">{[v.bearPerShare, v.basePerShare, v.bullPerShare].map((x) => money(x, v.currency)).join(" · ")}</td>
                      <td className="kbd py-2.5 pr-3">{v.quotePrice != null ? `${money(v.quotePrice, v.currency)}${v.quoteDate ? `, ${v.quoteDate}` : ""}` : "–"}</td>
                      <td className="kbd py-2.5 pr-3 text-[color:var(--muted)]">{v.calculatedAt.slice(0, 10)}</td>
                      <td className="whitespace-nowrap py-2.5 text-[0.75rem]">
                        <button type="button" className="text-[color:var(--muted)] underline-offset-4 hover:underline" onClick={() => { setForm((c) => ({ ...c, company: v.company, ticker: v.ticker ?? "", country: v.country ?? c.country })); pick("model"); }}>Revalue</button>
                        {v.statementSourceUrl ? <a href={v.statementSourceUrl} target="_blank" rel="noreferrer" className="ml-3 text-[color:var(--muted)] underline-offset-4 hover:underline">Source ↗</a> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-8 border-t hairline pt-6">
            <h2 className="text-[0.9375rem] text-[color:var(--text)]">Back up</h2>
            <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">Saved valuations live in this browser. The backup holds assumptions and source links, not portfolio holdings.</p>
            <div className="mt-3 flex flex-wrap items-end gap-4">
              <button type="button" className="btn btn-secondary" onClick={exportValuationHistory}>Export saved valuation history</button>
              <label className="block text-xs text-[color:var(--muted)]">
                Restore valuation history from JSON backup
                <input className="field mt-1.5" type="file" accept=".json,application/json" onChange={importValuationHistory} aria-describedby="valuation-backup-help" />
              </label>
            </div>
            <p id="valuation-backup-help" className="mt-2 text-[0.75rem] text-[color:var(--dim)]">Up to 2 MB; checked before anything is replaced, and you are asked first.</p>
            {backupMessage ? <p className="mt-3 text-[0.8125rem] text-[color:var(--muted)]" role="status" aria-live="polite">{backupMessage}</p> : null}
          </div>
        </section>
      )}

      {tab === "method" && (
        <section aria-label="Method" className="max-w-3xl space-y-6 text-[0.875rem] text-[color:var(--muted)]">
          <div>
            <h2 className="text-[0.9375rem] text-[color:var(--text)]">Discounted cash flow</h2>
            <p className="mt-1">Five years of unlevered free cash flow at each scenario&apos;s growth rate, plus a terminal value, discounted at the WACC; add cash, subtract debt, divide by shares. Not for banks, insurers, early-stage businesses, REITs or companies with negative or volatile free cash flow.</p>
          </div>
          <div>
            <h2 className="text-[0.9375rem] text-[color:var(--text)]">Dividend discount</h2>
            <p className="mt-1">Five years of dividends per share at each scenario&apos;s growth rate, plus a terminal value, discounted at the cost of equity. Not for companies whose dividends are absent, irregular or likely to change.</p>
          </div>
          <div>
            <h2 className="text-[0.9375rem] text-[color:var(--text)]">Evidence check</h2>
            <p className="mt-1">Each input is checked against the exchange&apos;s data, the company&apos;s filed statements and the cited document, and graded A to D. A verdict on the quote is given only when the inputs are well enough evidenced.</p>
          </div>
          <div>
            <h2 className="text-[0.9375rem] text-[color:var(--text)]">What it does not do</h2>
            <p className="mt-1">No adjustment yet for non-operating assets, leases, pension deficits, preferred shares, minority interests, dilution, cyclicality or country-specific discount rates. A result is not a target price or an instruction to buy or sell.</p>
          </div>
        </section>
      )}
    </Container>
  );
}

function Step({ n, title, hint, children }: { n: number; title: string; hint?: string; children: ReactNode }) {
  return (
    <fieldset>
      <legend className="flex items-baseline gap-2 text-[0.9375rem] text-[color:var(--text)]"><span className="kbd text-[0.75rem] text-[color:var(--dim)]">{n}</span>{title}</legend>
      {hint && <p className="mt-0.5 text-[0.75rem] text-[color:var(--dim)]">{hint}</p>}
      <div className="mt-3">{children}</div>
    </fieldset>
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
