"use client";

import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import Link from "next/link";
import { MarketsTitle } from "../../../../components/app/MarketsNav";
import { Container } from "../../../../components/primitives";
import { ErrorNote } from "../../../../components/app/ui";
import { calculateExposureRows, calculatePortfolioTotals, calculatePortfolioValuationReviews, calculatePortfolioValuationSummary, convertToBase, isSavedValuation, type SavedValuationSnapshot, ASSET_TYPES, CURRENCIES, normalizeAssetType } from "../../../../lib/markets-portfolio";
import { parseCsv, stringifyCsv } from "../../../../lib/markets-csv";
import { createPortfolioWorkbook, parsePortfolioWorkbook } from "../../../../lib/markets-excel";
import { post } from "../../../../lib/market";

type PricedQuote = { exchange_name: string; symbol: string; price: number; currency: string; date: string | null; stale: boolean } | null;
type PricesResponse = { results: PricedQuote[]; fx: { usd_rates: Record<string, number>; as_of: string | null } };

type Holding = {
  id: string;
  name: string;
  ticker: string;
  country: string;
  sector: string;
  assetType: string;
  currency: string;
  quantity: number;
  costPerUnit: number;
  currentPrice: number | null;
  fxToBase: number | null;
  priceAsOf?: string | null;
  fxAsOf?: string | null;
};

type PortfolioState = { version: 1; baseCurrency: string; holdings: Holding[] };

const STORAGE_KEY = "deal-intelligence-markets-portfolio-v1";
const VALUATION_STORAGE_KEY = "deal-intelligence-markets-valuations-v1";
const CSV_HEADERS = ["name", "ticker", "country", "sector", "asset_type", "currency", "quantity", "cost_per_unit", "current_price", "fx_to_base", "price_as_of", "fx_as_of"];
const VALUATION_STATUS_LABELS = {
  "no-saved-valuation": "No saved valuation",
  "model-not-suitable": "Model fit not accepted",
  "missing-quote": "Quote missing",
  "stale-inputs": "Stale valuation inputs",
  "currency-mismatch": "Currency mismatch",
  "portfolio-price-mismatch": "Portfolio quote mismatch",
  "invalid-estimate": "Invalid scenario estimate",
  ready: "Quality checks passed",
} as const;

const blankForm = {
  name: "",
  ticker: "",
  country: "",
  sector: "",
  assetType: "Stock",
  currency: "USD",
  quantity: "1",
  costPerUnit: "",
  currentPrice: "",
  fxToBase: "1",
  priceAsOf: "",
  fxAsOf: "",
};

function validPastDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value && parsed.getTime() <= Date.now();
}

function isHolding(value: unknown): value is Holding {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<Holding>;
  return typeof item.id === "string" && typeof item.name === "string" && item.name.trim().length > 0 &&
    typeof item.ticker === "string" && typeof item.country === "string" && typeof item.sector === "string" &&
    typeof item.assetType === "string" && typeof item.currency === "string" && CURRENCIES.includes(item.currency) &&
    typeof item.quantity === "number" && Number.isFinite(item.quantity) && item.quantity > 0 &&
    typeof item.costPerUnit === "number" && Number.isFinite(item.costPerUnit) && item.costPerUnit >= 0 &&
    (item.currentPrice === null || (typeof item.currentPrice === "number" && Number.isFinite(item.currentPrice) && item.currentPrice > 0)) &&
    (item.fxToBase === null || (typeof item.fxToBase === "number" && Number.isFinite(item.fxToBase) && item.fxToBase > 0)) &&
    (item.priceAsOf === undefined || item.priceAsOf === null || (typeof item.priceAsOf === "string" && validPastDate(item.priceAsOf))) &&
    (item.fxAsOf === undefined || item.fxAsOf === null || (typeof item.fxAsOf === "string" && validPastDate(item.fxAsOf)));
}

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function amount(value: number | null | undefined, currency: string): string {
  if (value == null || !Number.isFinite(value)) return "Not available";
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
  } catch {
    return `${value.toLocaleString("en", { maximumFractionDigits: 2 })} ${currency}`;
  }
}

type PortfolioTab = "holdings" | "add" | "import" | "exposure" | "valuations";
const PORTFOLIO_TABS: [PortfolioTab, string][] = [
  ["holdings", "Holdings"], ["add", "Add a holding"], ["import", "Import & backup"], ["exposure", "Exposure"], ["valuations", "Valuations"],
];

export default function MarketsPortfolioPage() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [baseCurrency, setBaseCurrency] = useState("USD");
  const [form, setForm] = useState({ ...blankForm, currency: "USD" });
  const [ready, setReady] = useState(false);
  const [storageWarning, setStorageWarning] = useState<string | null>(null);
  const [storageLoadFailed, setStorageLoadFailed] = useState(false);
  const [savedValuations, setSavedValuations] = useState<SavedValuationSnapshot[]>([]);
  const [valuationStorageWarning, setValuationStorageWarning] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The open tab follows the address (#import), so a link can open it directly; with none picked, an empty
  // portfolio opens on Add and a filled one on Holdings.
  const [picked, setPicked] = useState<PortfolioTab | null>(null);
  const pick = (id: PortfolioTab) => {
    setPicked(id);
    try { window.history.replaceState(null, "", `#${id}`); } catch { /* ignore */ }
  };
  useEffect(() => {
    const follow = () => {
      const h = window.location.hash.replace("#", "");
      if (PORTFOLIO_TABS.some(([id]) => id === h)) setPicked(h as PortfolioTab);
    };
    follow();
    window.addEventListener("hashchange", follow);
    return () => window.removeEventListener("hashchange", follow);
  }, []);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as Partial<PortfolioState>;
        if (parsed.version !== 1 || !Array.isArray(parsed.holdings) ||
            !parsed.holdings.every(isHolding) || typeof parsed.baseCurrency !== "string" ||
            !CURRENCIES.includes(parsed.baseCurrency)) {
          throw new Error("The saved portfolio has an unsupported version or invalid rows. It has been left unchanged to avoid losing data; export or recover it before editing.");
        }
        setHoldings(parsed.holdings);
        setBaseCurrency(parsed.baseCurrency);
        setForm({ ...blankForm, currency: parsed.baseCurrency, fxToBase: "1" });
      }
    } catch (loadError) {
      setStorageLoadFailed(true);
      setStorageWarning(loadError instanceof Error ? loadError.message : "This browser could not read the saved portfolio. It has been left unchanged to avoid data loss.");
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(VALUATION_STORAGE_KEY);
      if (!raw) return;
      const parsed: unknown = JSON.parse(raw);
      if (!Array.isArray(parsed) || !parsed.every(isSavedValuation)) {
        throw new Error("Saved valuation reviews could not be validated. The stored data has been left unchanged.");
      }
      setSavedValuations(parsed);
    } catch (loadError) {
      setValuationStorageWarning(loadError instanceof Error ? loadError.message : "Saved valuation reviews could not be read from this browser.");
    }
  }, []);

  useEffect(() => {
    if (!ready || storageLoadFailed) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, baseCurrency, holdings } satisfies PortfolioState));
      setStorageWarning(null);
    } catch {
      setStorageWarning("Browser storage is unavailable or full. Export a CSV backup before leaving this page.");
    }
  }, [baseCurrency, holdings, ready, storageLoadFailed]);

  const portfolioTotals = useMemo(() => calculatePortfolioTotals(holdings), [holdings]);
  const { pricedHoldings, totalCurrentValue, gainLoss: pricedGain, missingPriceCount, missingFxCount } = portfolioTotals;
  const countryExposure = useMemo(() => calculateExposureRows(holdings, "country"), [holdings]);
  const sectorExposure = useMemo(() => calculateExposureRows(holdings, "sector"), [holdings]);
  const assetTypeExposure = useMemo(() => calculateExposureRows(holdings, "assetType"), [holdings]);
  const currencyExposure = useMemo(() => calculateExposureRows(holdings, "currency"), [holdings]);
  const valuationReviews = useMemo(() => calculatePortfolioValuationReviews(holdings, savedValuations, baseCurrency), [holdings, savedValuations, baseCurrency]);
  const valuationSummary = useMemo(() => calculatePortfolioValuationSummary(valuationReviews), [valuationReviews]);
  const largestPosition = useMemo(() => {
    const values = pricedHoldings.map((holding) => ({
      name: holding.name,
      ticker: holding.ticker,
      value: convertToBase(holding.quantity * (holding.currentPrice ?? 0), holding.fxToBase) ?? 0,
    })).sort((a, b) => b.value - a.value);
    return values[0] && totalCurrentValue > 0 ? { ...values[0], share: values[0].value / totalCurrentValue } : null;
  }, [pricedHoldings, totalCurrentValue]);
  const undatedPrices = holdings.filter((holding) => holding.currentPrice != null && !holding.priceAsOf).length;
  const stalePrices = holdings.filter((holding) => holding.currentPrice != null && Boolean(holding.priceAsOf) && (Date.now() - new Date(`${holding.priceAsOf}T00:00:00Z`).getTime()) > 7 * 86400000).length;
  const undatedFx = holdings.filter((holding) => holding.currency !== baseCurrency && holding.fxToBase != null && !holding.fxAsOf).length;
  const staleFx = holdings.filter((holding) => holding.currency !== baseCurrency && holding.fxToBase != null && Boolean(holding.fxAsOf) && (Date.now() - new Date(`${holding.fxAsOf}T00:00:00Z`).getTime()) > 7 * 86400000).length;

  const portfolioInsights = useMemo(() => {
    const insights: { title: string; detail: string }[] = [];
    if (holdings.length === 0) {
      insights.push({ title: "Start with your holdings", detail: "Add a few positions or import a CSV. These insights use only the prices, FX rates and classifications you enter." });
      return insights;
    }
    if (largestPosition) {
      insights.push({
        title: largestPosition.share >= 0.25 ? "Review single-position concentration" : "Largest position",
        detail: `${largestPosition.name} represents ${(largestPosition.share * 100).toFixed(1)}% of priced and converted portfolio value. This is a simple sizing signal, not a judgement about the investment itself.`,
      });
    } else {
      insights.push({ title: "Portfolio value is not yet measurable", detail: "Enter current prices and valid FX rates before position sizes can be compared." });
    }
    if (countryExposure[0]) {
      insights.push({
        title: countryExposure[0].share >= 0.6 ? "Review geographic concentration" : "Largest country exposure",
        detail: `${countryExposure[0].label} accounts for ${(countryExposure[0].share * 100).toFixed(1)}% of priced and converted value. Unpriced holdings are excluded from this share.`,
      });
    }
    if (sectorExposure[0]) {
      insights.push({
        title: sectorExposure[0].share >= 0.6 ? "Review sector concentration" : "Largest sector exposure",
        detail: `${sectorExposure[0].label} accounts for ${(sectorExposure[0].share * 100).toFixed(1)}% of priced and converted value. The labels are user-supplied and may not capture overlapping business risks.`,
      });
    }
    if (missingPriceCount > 0 || missingFxCount > 0) {
      insights.push({
        title: "Complete the valuation inputs",
        detail: `${missingPriceCount} holding(s) lack a current price and ${missingFxCount} lack a usable FX rate. Update these before treating portfolio totals or allocation percentages as complete.`,
      });
    } else {
      insights.push({ title: "Entered holdings are priced and converted", detail: "All listed holdings have a current price and FX conversion, but the results still depend on the accuracy and date of your manual inputs." });
    }
    if (undatedPrices > 0 || stalePrices > 0 || undatedFx > 0 || staleFx > 0) {
      insights.push({ title: "Check price and FX freshness", detail: `${undatedPrices} holding(s) have no price date, ${stalePrices} have prices older than 7 days, ${undatedFx} foreign-currency holding(s) have no FX date, and ${staleFx} have FX rates older than 7 days. Refresh prices and FX updates both from the daily snapshot.` });
    }
    return insights;
  }, [holdings.length, largestPosition, countryExposure, sectorExposure, missingPriceCount, missingFxCount, undatedPrices, stalePrices, undatedFx, staleFx]);

  function updateForm(key: keyof typeof blankForm, value: string) {
    setForm((current) => ({
      ...current,
      [key]: value,
      ...(key === "currentPrice" ? { priceAsOf: "" } : {}),
      ...(key === "fxToBase" ? { fxAsOf: "" } : {}),
    }));
  }

  function addHolding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const quantity = Number(form.quantity);
    const costPerUnit = Number(form.costPerUnit);
    const currentPrice = form.currentPrice.trim() === "" ? null : Number(form.currentPrice);
    const fxToBase = form.currency === baseCurrency ? 1 : (form.fxToBase.trim() === "" ? null : Number(form.fxToBase));
    if (!form.name.trim() || !form.currency.trim() || !form.costPerUnit.trim() || !Number.isFinite(quantity) || quantity <= 0 ||
        !CURRENCIES.includes(form.currency) || !Number.isFinite(costPerUnit) || costPerUnit < 0 ||
        (currentPrice != null && (!Number.isFinite(currentPrice) || currentPrice <= 0)) ||
        (fxToBase != null && (!Number.isFinite(fxToBase) || fxToBase <= 0)) ||
        (form.priceAsOf !== "" && !validPastDate(form.priceAsOf)) || (form.fxAsOf !== "" && !validPastDate(form.fxAsOf))) {
      setError("Check the holding name, positive quantity, cost basis, optional current price and FX conversion rate.");
      return;
    }
    const duplicate = holdings.some((holding) =>
      (form.ticker.trim() && holding.ticker.toUpperCase() === form.ticker.trim().toUpperCase()) ||
      (holding.name.trim().toLowerCase() === form.name.trim().toLowerCase() && holding.country.trim().toLowerCase() === form.country.trim().toLowerCase()),
    );
    setHoldings((current) => [...current, {
      id: newId(),
      name: form.name.trim(),
      ticker: form.ticker.trim().toUpperCase(),
      country: form.country.trim(),
      sector: form.sector.trim(),
      assetType: form.assetType,
      currency: form.currency.trim().toUpperCase(),
      quantity,
      costPerUnit,
      currentPrice,
      fxToBase,
      priceAsOf: currentPrice == null ? null : (form.priceAsOf || null),
      fxAsOf: form.currency === baseCurrency || fxToBase == null ? null : (form.fxAsOf || null),
    }]);
    setForm({ ...blankForm, currency: baseCurrency });
    setMessage(duplicate
      ? "Holding added, but it matches an existing name/ticker and country. Check whether this is a separate lot or an accidental duplicate. Use Refresh prices and FX to price it from the daily exchange snapshot."
      : "Holding added. Use Refresh prices and FX to price listed holdings from the daily exchange snapshot.");
    pick("holdings");
  }

  async function importRows(rows: string[][], format: "CSV" | "Excel") {
    setError(null);
    setMessage(null);
    try {
      if (rows.length < 2) throw new Error(`The ${format} file must include a header row and at least one holding.`);
      const headers = rows[0].map((header) => header.trim().toLowerCase().replace(/[ -]+/g, "_"));
      const missing = ["name", "currency", "quantity", "cost_per_unit"].filter((header) => !headers.includes(header));
      if (missing.length) throw new Error(`Missing required ${format} columns: ${missing.join(", ")}.`);
      const col = (row: string[], name: string) => {
        const index = headers.indexOf(name);
        return index < 0 ? "" : (row[index] ?? "").trim();
      };
      const imported: Holding[] = [];
      let skipped = 0;
      const unknownTypes = new Set<string>();
      let duplicateCount = 0;
      const seen = new Set(holdings.map((holding) => `${holding.ticker.toUpperCase()}|${holding.name.trim().toLowerCase()}|${holding.country.trim().toLowerCase()}`));
      for (const row of rows.slice(1)) {
        const name = col(row, "name");
        const currency = col(row, "currency").toUpperCase();
        const quantity = Number(col(row, "quantity"));
        const costText = col(row, "cost_per_unit");
        const costPerUnit = Number(costText);
        const currentText = col(row, "current_price");
        const fxText = col(row, "fx_to_base");
        const priceAsOf = col(row, "price_as_of");
        const fxAsOf = col(row, "fx_as_of");
        const currentPrice = currentText === "" ? null : Number(currentText);
        const fxToBase = currency === baseCurrency ? 1 : fxText === "" ? null : Number(fxText);
        if (!name || !CURRENCIES.includes(currency) || !costText || !Number.isFinite(quantity) || quantity <= 0 ||
            !Number.isFinite(costPerUnit) || costPerUnit < 0 ||
            (currentPrice != null && (!Number.isFinite(currentPrice) || currentPrice <= 0)) ||
            (fxToBase != null && (!Number.isFinite(fxToBase) || fxToBase <= 0)) ||
            (priceAsOf !== "" && !validPastDate(priceAsOf)) || (fxAsOf !== "" && !validPastDate(fxAsOf))) {
          skipped += 1;
          continue;
        }
        const assetType = normalizeAssetType(col(row, "asset_type"));
        if (!assetType) unknownTypes.add(col(row, "asset_type"));
        const ticker = col(row, "ticker").toUpperCase();
        const country = col(row, "country");
        const identity = `${ticker}|${name.toLowerCase()}|${country.trim().toLowerCase()}`;
        if (seen.has(identity) || (ticker && holdings.some((holding) => holding.ticker.toUpperCase() === ticker))) duplicateCount += 1;
        seen.add(identity);
        imported.push({
          id: newId(), name, currency, quantity, costPerUnit, currentPrice, fxToBase,
          ticker,
          country,
          sector: col(row, "sector"),
          assetType: assetType ?? "Other",
          priceAsOf: currentPrice == null ? null : (priceAsOf || null),
          fxAsOf: currency === baseCurrency || fxToBase == null ? null : (fxAsOf || null),
        });
      }
      if (!imported.length) throw new Error(`No valid holdings were found in the ${format} file. Check required columns and numeric values.`);
      setHoldings((current) => [...current, ...imported]);
      pick("holdings");
      setMessage(`Imported ${imported.length} holding(s) from ${format}${skipped ? `; skipped ${skipped} invalid row(s)` : ""}${duplicateCount ? `; detected ${duplicateCount} possible duplicate position(s)` : ""}${unknownTypes.size ? `; asset type(s) ${[...unknownTypes].slice(0, 5).map((t) => `"${t}"`).join(", ")} not recognised and recorded as Other` : ""}. Review duplicates, FX conversion rates and current prices before relying on totals.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not import this ${format} file.`);
    }
  }

  async function importCsv(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      await importRows(parseCsv(await file.text()), "CSV");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not import this CSV file.");
    }
  }

  async function importExcel(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error("Excel files must be 5 MB or smaller.");
      await importRows(parsePortfolioWorkbook(await file.arrayBuffer()), "Excel");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not import this Excel workbook.");
    }
  }

  function exportCsv() {
    const rows = [
      CSV_HEADERS,
      ...holdings.map((holding) => [
        holding.name, holding.ticker, holding.country, holding.sector, holding.assetType, holding.currency,
        holding.quantity, holding.costPerUnit, holding.currentPrice, holding.fxToBase, holding.priceAsOf ?? "", holding.fxAsOf ?? "",
      ]),
    ];
    const csv = stringifyCsv(rows);
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "deal-intelligence-portfolio.csv";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function exportExcel() {
    const rows = [
      CSV_HEADERS,
      ...holdings.map((holding) => [
        holding.name, holding.ticker, holding.country, holding.sector, holding.assetType, holding.currency,
        holding.quantity, holding.costPerUnit, holding.currentPrice, holding.fxToBase, holding.priceAsOf ?? "", holding.fxAsOf ?? "",
      ]),
    ];
    const bytes = createPortfolioWorkbook(rows);
    const exactBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
    const url = URL.createObjectURL(new Blob([exactBuffer], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "deal-intelligence-portfolio.xlsx";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function downloadExcelTemplate() {
    const bytes = createPortfolioWorkbook([
      CSV_HEADERS,
      ["Example African Bank", "EXBANK", "Kenya", "Banking", "Stock", "KES", 10, 120, 135, 0.0075, "", ""],
    ]);
    const exactBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
    const url = URL.createObjectURL(new Blob([exactBuffer], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "portfolio-import-template.xlsx";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function updateHoldingDate(id: string, key: "priceAsOf" | "fxAsOf", raw: string) {
    if (raw && !validPastDate(raw)) return;
    setHoldings((current) => current.map((holding) => {
      if (holding.id !== id) return holding;
      if (key === "priceAsOf" && holding.currentPrice == null) return holding;
      if (key === "fxAsOf" && (holding.currency === baseCurrency || holding.fxToBase == null)) return holding;
      return { ...holding, [key]: raw || null };
    }));
  }

  function updateHoldingNumber(id: string, key: "currentPrice" | "fxToBase", raw: string) {
    const value = raw.trim() === "" ? null : Number(raw);
    if (value != null && (!Number.isFinite(value) || value < 0 || (key === "fxToBase" && value === 0) || (key === "currentPrice" && value === 0))) return;
    setHoldings((current) => current.map((holding) => {
      if (holding.id !== id) return holding;
      if (key === "fxToBase" && holding.currency === baseCurrency) return { ...holding, fxToBase: 1 };
      if (key === "currentPrice") return { ...holding, currentPrice: value, priceAsOf: null };
      return { ...holding, fxToBase: value, fxAsOf: null };
    }));
  }

  const [pricing, setPricing] = useState(false);

  // Prices each holding from the daily exchange snapshot (by ticker, else by name) and converts with the day's
  // dollar rates. Holdings the snapshot cannot match keep the price entered for them.
  async function refreshPrices() {
    setPricing(true);
    setError(null);
    try {
      const r = await post<PricesResponse>("/api/markets/prices", {
        items: holdings.map((h) => ({ name: h.name, ticker: h.ticker, country: h.country, currency: h.currency })),
      });
      const fxDay = r.fx.as_of ? new Date(r.fx.as_of).toISOString().slice(0, 10) : null;
      const perUsd = (c: string) => r.fx.usd_rates[c.toUpperCase()];
      let priced = 0, converted = 0, stale = 0;
      setHoldings((current) => current.map((h, i) => {
        const q = r.results[i];
        let next = h;
        if (q && q.date) {
          next = { ...next, currentPrice: q.price, priceAsOf: q.date };
          priced += 1;
          if (q.stale) stale += 1;
        }
        if (h.currency === baseCurrency) {
          next = { ...next, fxToBase: 1, fxAsOf: null };
        } else if (perUsd(h.currency) && perUsd(baseCurrency) && fxDay) {
          next = { ...next, fxToBase: perUsd(baseCurrency) / perUsd(h.currency), fxAsOf: fxDay };
          converted += 1;
        }
        return next;
      }));
      setMessage(`Priced ${priced} of ${holdings.length} holding(s) from the daily exchange snapshot${stale ? ` (${stale} with a price more than a week old)` : ""}; converted ${converted} at the day's rates. Unmatched holdings keep their entered prices.`);
    } catch {
      setError("Prices could not be refreshed. Entered prices are unchanged.");
    } finally {
      setPricing(false);
    }
  }

  function preparePortfolioWatchlist() {
    const uniqueCompanies = [...new Map(holdings.map((holding) => {
      const value = holding.name.trim();
      return [value.toLowerCase(), value] as const;
    })).values()].filter(Boolean);
    if (!uniqueCompanies.length) return;
    try {
      window.sessionStorage.setItem("deal-intelligence:portfolio-watchlist-prefill", JSON.stringify({ name: "Portfolio monitoring", companies: uniqueCompanies }));
      window.location.href = "/watchlists?from=portfolio";
    } catch {
      setError("The watchlist draft could not be prefilled in this browser. You can still copy company names into the existing Watchlists page manually.");
    }
  }

  function removeHolding(id: string) {
    setHoldings((current) => current.filter((holding) => holding.id !== id));
    setMessage("Holding removed.");
  }

  function clearPortfolio() {
    if (!window.confirm("Delete every holding saved in this browser? This cannot be undone unless you exported a backup.")) return;
    setHoldings([]);
    setMessage("Portfolio cleared from this browser.");
    setError(null);
  }

  const tab: PortfolioTab = picked ?? (holdings.length ? "holdings" : "add");
  const unpriced = holdings.length - pricedHoldings.length;
  const today = new Date().toISOString().slice(0, 10);
  const stale = (d: string | null | undefined) => !!d && Date.now() - new Date(`${d}T00:00:00Z`).getTime() > 7 * 86400000;

  return (
    <Container className="pb-10 pt-6 lg:pb-14">
      <MarketsTitle title="Portfolio" actions={
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[0.75rem] text-[color:var(--dim)]">
            <span className="mb-1 block">Reporting currency</span>
            <select id="base-currency" aria-label="Portfolio reporting currency" className="field h-9 py-1" value={baseCurrency} onChange={(event) => {
              const nextCurrency = event.target.value;
              if (holdings.length > 0 && !window.confirm("Changing the reporting currency resets existing FX conversion rates. Holding prices and cost basis stay unchanged, but you will need to re-enter FX rates for non-base-currency holdings. Continue?")) return;
              setBaseCurrency(nextCurrency);
              setHoldings((current) => current.map((holding) => ({ ...holding, fxToBase: holding.currency === nextCurrency ? 1 : null, fxAsOf: null })));
              setForm({ ...blankForm, currency: nextCurrency, fxToBase: "1" });
              if (holdings.length > 0) setMessage("Reporting currency changed. FX rates for holdings in other currencies were cleared; refresh or re-enter them before relying on totals.");
            }}>
              {CURRENCIES.map((currency) => <option key={currency} value={currency}>{currency}</option>)}
            </select>
          </label>
          <button type="button" className="btn btn-primary h-9" onClick={refreshPrices} disabled={holdings.length === 0 || pricing}>{pricing ? "Pricing…" : "Refresh prices and FX"}</button>
        </div>
      }>Holdings priced from the daily close, in your reporting currency. Everything you enter stays in this browser.</MarketsTitle>

      <div className="mb-6 grid grid-cols-2 gap-4 border-y hairline py-4 sm:grid-cols-5">
        <Fig label="Holdings" value={String(holdings.length)} sub={unpriced ? `${unpriced} not priced` : holdings.length ? "all priced" : undefined} />
        <Fig label={`Market value (${baseCurrency})`} value={amount(totalCurrentValue, baseCurrency)} />
        <Fig label="Gain / loss" value={amount(pricedGain, baseCurrency)} tone={pricedGain > 0 ? "up" : pricedGain < 0 ? "down" : undefined} sub="priced holdings, before fees" />
        <Fig label="Largest position" value={largestPosition ? `${(largestPosition.share * 100).toFixed(1)}%` : "–"} sub={largestPosition?.name} />
        <Fig label="Valuations matched" value={`${valuationSummary.matchedCount}/${holdings.length}`} sub="saved models in date" />
      </div>

      <div role="tablist" aria-label="Portfolio" className="-mx-1 mb-6 flex flex-wrap gap-1.5 px-1">
        {PORTFOLIO_TABS.map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => pick(id)}
                  className={`rounded-full px-3 py-1 text-[0.8125rem] transition-colors ${
                    tab === id ? "bg-white/[0.09] text-[color:var(--text)]" : "text-[color:var(--muted)] hover:text-[color:var(--text)]"}`}>
            {label}{id === "holdings" && holdings.length ? <span className="ml-1 text-[color:var(--dim)]">{holdings.length}</span> : null}
          </button>
        ))}
      </div>

      {storageWarning && <ErrorNote message={storageWarning} />}
      {error && <ErrorNote message={error} />}
      {message && <p className="mb-4 text-[0.8125rem] text-[color:var(--muted)]" role="status">{message}</p>}

      {tab === "holdings" && (
        <section aria-label="Holdings">
          {!ready ? <p className="py-6 text-sm text-[color:var(--dim)]" role="status">Loading your locally saved portfolio…</p> : null}
          {ready && holdings.length === 0 ? (
            <div className="rounded-xl border border-dashed hairline p-8 text-center">
              <h3 className="text-base font-medium">Your portfolio starts here.</h3>
              <p className="mx-auto mt-2 max-w-xl text-sm text-[color:var(--muted)]">
                <button type="button" onClick={() => pick("add")} className="underline underline-offset-4">Add a holding</button> or <button type="button" onClick={() => pick("import")} className="underline underline-offset-4">import a CSV or Excel file</button>.
              </p>
            </div>
          ) : null}
          {holdings.length > 0 && (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[60rem] border-collapse text-left text-[0.8125rem]">
                  <thead>
                    <tr className="border-b hairline text-[color:var(--dim)]">
                      {["Investment", "Country · sector", "Units", "Cost / unit", "Price", `FX to ${baseCurrency}`, `Value (${baseCurrency})`, "Gain / loss", ""].map((heading) => (
                        <th key={heading} className="whitespace-nowrap py-2.5 pr-3 font-normal">{heading}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {holdings.map((holding) => {
                      const cost = convertToBase(holding.quantity * holding.costPerUnit, holding.fxToBase);
                      const value = holding.currentPrice == null ? null : convertToBase(holding.quantity * holding.currentPrice, holding.fxToBase);
                      const gain = value == null || cost == null ? null : value - cost;
                      const q = `company=${encodeURIComponent(holding.name)}${holding.ticker ? `&ticker=${encodeURIComponent(holding.ticker)}` : ""}`;
                      return (
                        <tr key={holding.id} className="border-b hairline align-top last:border-0">
                          <td className="py-2.5 pr-3">
                            <Link href={`/companies?name=${encodeURIComponent(holding.name)}${holding.ticker ? `&ticker=${encodeURIComponent(holding.ticker)}` : ""}`} className="text-[color:var(--text)] underline-offset-4 hover:underline">{holding.name}</Link>
                            <p className="mt-0.5 text-[0.75rem] text-[color:var(--dim)]">{[holding.ticker, holding.assetType, holding.currency].filter(Boolean).join(" · ")}</p>
                          </td>
                          <td className="py-2.5 pr-3 text-[color:var(--muted)]">{[holding.country || "–", holding.sector || "–"].join(" · ")}</td>
                          <td className="kbd py-2.5 pr-3">{holding.quantity.toLocaleString("en", { maximumFractionDigits: 6 })}</td>
                          <td className="kbd py-2.5 pr-3">{amount(holding.costPerUnit, holding.currency)}</td>
                          <td className="py-2.5 pr-3">
                            <input className="field h-8 w-28 py-1" type="number" min="0.000000001" step="any" value={holding.currentPrice ?? ""} onChange={(event) => updateHoldingNumber(holding.id, "currentPrice", event.target.value)} aria-label={`Current price for ${holding.name} in ${holding.currency}`} placeholder="Price" />
                            <input className="field mt-1 h-8 w-28 py-1 text-[0.75rem]" type="date" max={today} value={holding.priceAsOf ?? ""} disabled={holding.currentPrice == null} onChange={(event) => updateHoldingDate(holding.id, "priceAsOf", event.target.value)} aria-label={`Price date for ${holding.name}`} />
                            {stale(holding.priceAsOf) && <p className="mt-0.5 text-[0.6875rem] text-[color:var(--dim)]">Over 7 days old</p>}
                          </td>
                          <td className="py-2.5 pr-3">
                            {holding.currency === baseCurrency ? <span className="kbd text-[color:var(--dim)]">1</span> : (
                              <>
                                <input className="field h-8 w-28 py-1" type="number" min="0.000000001" step="any" value={holding.fxToBase ?? ""} onChange={(event) => updateHoldingNumber(holding.id, "fxToBase", event.target.value)} aria-label={`FX rate for ${holding.name} to ${baseCurrency}`} placeholder="FX" />
                                <input className="field mt-1 h-8 w-28 py-1 text-[0.75rem]" type="date" max={today} value={holding.fxAsOf ?? ""} disabled={holding.fxToBase == null} onChange={(event) => updateHoldingDate(holding.id, "fxAsOf", event.target.value)} aria-label={`FX rate date for ${holding.name}`} />
                                {stale(holding.fxAsOf) && <p className="mt-0.5 text-[0.6875rem] text-[color:var(--dim)]">Over 7 days old</p>}
                              </>
                            )}
                          </td>
                          <td className="kbd py-2.5 pr-3">{value == null ? "–" : amount(value, baseCurrency)}</td>
                          <td className={`kbd py-2.5 pr-3 ${gain != null && gain > 0 ? "text-verified" : gain != null && gain < 0 ? "text-risk" : ""}`}>{gain == null ? "–" : amount(gain, baseCurrency)}</td>
                          <td className="whitespace-nowrap py-2.5 text-[0.75rem]">
                            <Link href={`/markets/valuation?${q}`} className="text-[color:var(--muted)] underline-offset-4 hover:underline">Value</Link>
                            <button type="button" className="ml-3 text-[color:var(--muted)] underline-offset-4 hover:underline" onClick={() => removeHolding(holding.id)} aria-label={`Remove ${holding.name}`}>Remove</button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-[0.8125rem]">
                <button type="button" className="text-[color:var(--muted)] underline-offset-4 hover:text-[color:var(--text)] hover:underline" onClick={preparePortfolioWatchlist}>Watch these companies for events</button>
                <Link href="/markets/portfolio/cloud" className="text-[color:var(--muted)] underline-offset-4 hover:text-[color:var(--text)] hover:underline">Cloud portfolios and team workspaces</Link>
              </p>
            </>
          )}
        </section>
      )}

      {tab === "add" && (
        <section aria-label="Add a holding" className="max-w-2xl">
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={addHolding}>
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-name">Company or investment name *</label>
              <input id="holding-name" className="field" required value={form.name} onChange={(event) => updateForm("name", event.target.value)} placeholder="e.g. Dangote Cement" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-ticker">Ticker / identifier</label>
              <input id="holding-ticker" className="field" value={form.ticker} onChange={(event) => updateForm("ticker", event.target.value)} placeholder="DANGCEM" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-type">Asset type</label>
              <select id="holding-type" className="field" value={form.assetType} onChange={(event) => updateForm("assetType", event.target.value)}>
                {ASSET_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-country">Country / market</label>
              <input id="holding-country" className="field" value={form.country} onChange={(event) => updateForm("country", event.target.value)} placeholder="Nigeria" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-sector">Sector</label>
              <input id="holding-sector" className="field" value={form.sector} onChange={(event) => updateForm("sector", event.target.value)} placeholder="Banking" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-currency">Holding currency</label>
              <select id="holding-currency" className="field" value={form.currency} onChange={(event) => { const currency = event.target.value; setForm((current) => ({ ...current, currency, fxToBase: currency === baseCurrency ? "1" : "", fxAsOf: "" })); }}>
                {CURRENCIES.map((currency) => <option key={currency} value={currency}>{currency}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-quantity">Quantity / units *</label>
              <input id="holding-quantity" className="field" type="number" min="0.000001" step="any" required value={form.quantity} onChange={(event) => updateForm("quantity", event.target.value)} />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-cost">Cost per unit ({form.currency}) *</label>
              <input id="holding-cost" className="field" type="number" min="0" step="any" required value={form.costPerUnit} onChange={(event) => updateForm("costPerUnit", event.target.value)} placeholder="Purchase price" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-price">Current price ({form.currency})</label>
              <input id="holding-price" className="field" type="number" min="0.000000001" step="any" value={form.currentPrice} onChange={(event) => updateForm("currentPrice", event.target.value)} placeholder="Optional: Refresh fills listed shares" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-price-date">Price date</label>
              <input id="holding-price-date" className="field" type="date" max={today} value={form.priceAsOf} onChange={(event) => updateForm("priceAsOf", event.target.value)} disabled={!form.currentPrice.trim()} />
            </div>
            {form.currency !== baseCurrency && (
              <>
                <div>
                  <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-fx">FX to {baseCurrency}</label>
                  <input id="holding-fx" className="field" type="number" min="0.000000001" step="any" value={form.fxToBase} onChange={(event) => updateForm("fxToBase", event.target.value)} placeholder={`${baseCurrency} per 1 ${form.currency}`} />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-fx-date">FX rate date</label>
                  <input id="holding-fx-date" className="field" type="date" max={today} value={form.fxAsOf} onChange={(event) => updateForm("fxAsOf", event.target.value)} disabled={!form.fxToBase.trim()} />
                </div>
              </>
            )}
            <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
              <button className="btn btn-primary" type="submit">Add holding</button>
              <p className="text-[0.75rem] text-[color:var(--dim)]">Leave price or FX blank and Refresh prices fills listed shares from the daily close.</p>
            </div>
          </form>
        </section>
      )}

      {tab === "import" && (
        <section aria-label="Import and backup" className="grid gap-8 lg:grid-cols-2">
          <div>
            <h2 className="text-[0.9375rem] text-[color:var(--text)]">Import</h2>
            <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">
              Columns <code>name</code>, <code>currency</code>, <code>quantity</code>, <code>cost_per_unit</code>; optionally <code>ticker</code>, <code>country</code>, <code>sector</code>, <code>asset_type</code>, <code>current_price</code>, <code>fx_to_base</code>, <code>price_as_of</code>, <code>fx_as_of</code>. Excel: first sheet, no formulas, up to 5 MB and 5,000 rows.
            </p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-xs text-[color:var(--muted)]" htmlFor="portfolio-csv">Choose CSV file</label>
                <input id="portfolio-csv" className="field mt-1.5" type="file" accept=".csv,text/csv" onChange={importCsv} />
              </div>
              <div>
                <label className="block text-xs text-[color:var(--muted)]" htmlFor="portfolio-excel">Choose Excel workbook (.xlsx)</label>
                <input id="portfolio-excel" className="field mt-1.5" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={importExcel} />
              </div>
            </div>
            <p className="mt-3 flex flex-wrap gap-4 text-[0.8125rem]">
              <button type="button" className="text-[color:var(--muted)] underline-offset-4 hover:text-[color:var(--text)] hover:underline" onClick={() => {
                const example = [CSV_HEADERS.join(","), ["Example African Bank", "EXBANK", "Kenya", "Banking", "Stock", "KES", 10, 120, 135, 0.0075, "", ""].join(",")].join("\r\n");
                const blob = new Blob([example + "\r\n"], { type: "text/csv;charset=utf-8" });
                const url = URL.createObjectURL(blob);
                const anchor = document.createElement("a");
                anchor.href = url;
                anchor.download = "portfolio-import-template.csv";
                document.body.appendChild(anchor);
                anchor.click();
                anchor.remove();
                window.setTimeout(() => URL.revokeObjectURL(url), 1000);
              }}>CSV template</button>
              <button type="button" className="text-[color:var(--muted)] underline-offset-4 hover:text-[color:var(--text)] hover:underline" onClick={downloadExcelTemplate}>Excel template</button>
            </p>
          </div>
          <div>
            <h2 className="text-[0.9375rem] text-[color:var(--text)]">Back up</h2>
            <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">The portfolio lives in this browser only. Export a copy before clearing browser data or moving to another device.</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" className="btn btn-secondary" onClick={exportCsv} disabled={holdings.length === 0}>Export CSV backup</button>
              <button type="button" className="btn btn-secondary" onClick={exportExcel} disabled={holdings.length === 0}>Export Excel backup</button>
              <button type="button" className="btn btn-ghost" onClick={clearPortfolio} disabled={holdings.length === 0}>Clear portfolio</button>
            </div>
          </div>
        </section>
      )}

      {tab === "exposure" && (
        <section aria-label="Exposure">
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            <ExposureList title="Country" rows={countryExposure} currency={baseCurrency} />
            <ExposureList title="Sector" rows={sectorExposure} currency={baseCurrency} />
            <ExposureList title="Asset type" rows={assetTypeExposure} currency={baseCurrency} />
            <ExposureList title="Holding currency" rows={currencyExposure} currency={baseCurrency} />
          </div>
          {portfolioInsights.length > 0 && holdings.length > 0 && (
            <div className="mt-8 grid gap-x-8 gap-y-4 border-t hairline pt-6 md:grid-cols-2" aria-label="What stands out">
              {portfolioInsights.map((insight) => (
                <div key={insight.title}><p className="text-[0.875rem] text-[color:var(--text)]">{insight.title}</p><p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">{insight.detail}</p></div>
              ))}
            </div>
          )}
          <p className="mt-6 text-[0.75rem] text-[color:var(--dim)]">From your prices, FX rates and classifications; holdings without either are left out. Not a risk score or advice.</p>
        </section>
      )}

      {tab === "valuations" && (
        <section aria-label="Valuations">
          <p className="max-w-3xl text-[0.8125rem] text-[color:var(--muted)]">
            Models saved in <Link href="/markets/valuation" className="underline underline-offset-4">Valuation</Link>, set against each holding. A match needs a suitable model, fresh sources, the same currency and a portfolio price and date equal to the saved quote.
          </p>
          {valuationStorageWarning ? <div className="mt-3"><ErrorNote message={valuationStorageWarning} /></div> : null}
          <div className="mt-4 grid grid-cols-2 gap-4 border-y hairline py-4 sm:grid-cols-4">
            <Fig label="Matched" value={`${valuationSummary.matchedCount}/${holdings.length}`} />
            <Fig label="Weighted base-case gap" value={valuationSummary.weightedGapPct == null ? "–" : `${valuationSummary.weightedGapPct > 0 ? "+" : ""}${valuationSummary.weightedGapPct.toFixed(1)}%`} sub={`${valuationSummary.weightedCount} with fresh FX`} />
            <Fig label="Below every scenario" value={String(valuationSummary.potentiallyUndervaluedCount)} sub="base gap over 15%" />
            <Fig label="Above every scenario" value={String(valuationSummary.potentiallyOvervaluedCount)} sub="base gap over 15%" />
          </div>
          {holdings.length === 0 ? (
            <p className="mt-4 text-[0.8125rem] text-[color:var(--dim)]">Add a holding to compare it with a saved valuation.</p>
          ) : (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[48rem] text-left text-[0.8125rem]">
                <thead className="text-[color:var(--dim)]"><tr><th className="py-2.5 pr-3 font-normal">Holding</th><th className="py-2.5 pr-3 font-normal">Status</th><th className="py-2.5 pr-3 font-normal">Bear to bull</th><th className="py-2.5 pr-3 font-normal">Base</th><th className="py-2.5 pr-3 font-normal">Quote</th><th className="py-2.5 pr-3 font-normal">Gap</th><th className="py-2.5 font-normal" /></tr></thead>
                <tbody className="divide-y divide-white/[0.07] border-t hairline">
                  {valuationReviews.map((review) => {
                    const ready = review.status === "ready";
                    return (
                      <tr key={review.holdingId} className="align-top">
                        <td className="py-2.5 pr-3 text-[color:var(--text)]">{review.company}{review.ticker ? <span className="text-[color:var(--dim)]"> · {review.ticker}</span> : null}</td>
                        <td className="py-2.5 pr-3"><span title={review.detail} className="text-[color:var(--muted)]">{VALUATION_STATUS_LABELS[review.status]}</span>{ready && review.conclusion ? <p className="mt-0.5 max-w-xs text-[0.75rem] text-[color:var(--dim)]">{review.conclusion}</p> : <p className="mt-0.5 max-w-xs text-[0.75rem] text-[color:var(--dim)]">{review.detail}</p>}</td>
                        <td className="kbd py-2.5 pr-3">{ready ? `${amount(review.scenarioLow, review.currency)} – ${amount(review.scenarioHigh, review.currency)}` : "–"}</td>
                        <td className="kbd py-2.5 pr-3">{ready ? amount(review.basePerShare, review.currency) : "–"}</td>
                        <td className="kbd py-2.5 pr-3">{ready ? amount(review.quotePrice, review.currency) : "–"}</td>
                        <td className="kbd py-2.5 pr-3">{ready && review.gapPct != null ? `${review.gapPct > 0 ? "+" : ""}${review.gapPct.toFixed(1)}%` : "–"}</td>
                        <td className="whitespace-nowrap py-2.5 text-[0.75rem]">
                          <Link href={`/markets/valuation?company=${encodeURIComponent(review.company)}${review.ticker ? `&ticker=${encodeURIComponent(review.ticker)}` : ""}${review.country ? `&country=${encodeURIComponent(review.country)}` : ""}`} className="text-[color:var(--muted)] underline-offset-4 hover:underline">{ready ? "Update" : "Value"}</Link>
                          {ready && review.statementSourceUrl ? <a href={review.statementSourceUrl} target="_blank" rel="noreferrer" className="ml-3 text-[color:var(--muted)] underline-offset-4 hover:underline">Source ↗</a> : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <p className="mt-10 text-[0.75rem] text-[color:var(--dim)]">
        Not a brokerage connection or advice. Totals leave out holdings without a usable price or FX rate; gain/loss excludes fees, taxes, dividends and corporate actions.
      </p>
    </Container>
  );
}

function Fig({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "up" | "down" }) {
  return (
    <div className="min-w-0">
      <p className="text-[0.75rem] text-[color:var(--dim)]">{label}</p>
      <p className={`kbd mt-0.5 truncate text-[1.125rem] ${tone === "up" ? "text-verified" : tone === "down" ? "text-risk" : "text-[color:var(--text)]"}`}>{value}</p>
      {sub && <p className="truncate text-[0.75rem] text-[color:var(--muted)]">{sub}</p>}
    </div>
  );
}

function ExposureList({ title, rows, currency }: { title: string; rows: { label: string; value: number; share: number }[]; currency: string }) {
  return (
    <div>
      <h3 className="text-[0.8125rem] text-[color:var(--muted)]">{title}</h3>
      {rows.length === 0 ? <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">Nothing priced yet.</p> : (
        <ul className="mt-3 space-y-3">
          {rows.map((row) => (
            <li key={row.label}>
              <div className="flex items-baseline justify-between gap-2 text-xs">
                <span className="min-w-0 truncate">{row.label}</span>
                <span className="shrink-0 kbd text-[color:var(--muted)]">{(row.share * 100).toFixed(1)}% · {amount(row.value, currency)}</span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-[color:var(--muted)]" style={{ width: `${Math.max(0, Math.min(100, row.share * 100))}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
