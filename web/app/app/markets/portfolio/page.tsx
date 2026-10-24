"use client";

import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import Link from "next/link";
import { Container } from "../../../../components/primitives";
import { ErrorNote, PageHeader, Stat } from "../../../../components/app/ui";

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
};

type PortfolioState = { version: 1; baseCurrency: string; holdings: Holding[] };

const STORAGE_KEY = "deal-intelligence-markets-portfolio-v1";
const CURRENCIES = ["AOA", "BIF", "BWP", "CDF", "CVE", "DJF", "DZD", "EGP", "ERN", "ETB", "EUR", "GHS", "GMD", "GNF", "KMF", "KES", "LRD", "LSL", "LYD", "MAD", "MGA", "MRO", "MUR", "MWK", "MZN", "NAD", "NGN", "RWF", "SCR", "SDG", "SLE", "SOS", "SSP", "STN", "SZL", "TND", "TZS", "UGX", "USD", "XAF", "XOF", "ZAR", "ZMW", "ZWL"];
const ASSET_TYPES = ["Stock", "ETF", "Bond", "Treasury bill", "Money-market fund", "Mutual fund", "REIT", "Fixed deposit", "Other"];
const CSV_HEADERS = ["name", "ticker", "country", "sector", "asset_type", "currency", "quantity", "cost_per_unit", "current_price", "fx_to_base"];

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
};

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  const input = text.replace(/^\uFEFF/, "");
  for (let i = 0; i < input.length; i += 1) {
    const char = input[i];
    if (char === '"') {
      if (quoted && input[i + 1] === '"') {
        field += '"';
        i += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      row.push(field.trim());
      field = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && input[i + 1] === "\n") i += 1;
      row.push(field.trim());
      if (row.some((cell) => cell !== "")) rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  row.push(field.trim());
  if (row.some((cell) => cell !== "")) rows.push(row);
  if (quoted) throw new Error("The CSV contains an unclosed quoted field.");
  return rows;
}

function csvEscape(value: string | number | null): string {
  const text = value == null ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function amount(value: number | null | undefined, currency: string): string {
  if (value == null || !Number.isFinite(value)) return "Not available";
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
  } catch {
    return `${value.toLocaleString("en", { maximumFractionDigits: 2 })} ${currency}`;
  }
}

function convert(value: number, fxToBase: number | null): number | null {
  return fxToBase != null && Number.isFinite(fxToBase) && fxToBase > 0 ? value * fxToBase : null;
}

function exposureRows(holdings: Holding[], key: "country" | "sector" | "assetType" | "currency") {
  const totals = new Map<string, number>();
  for (const holding of holdings) {
    if (holding.currentPrice == null || holding.fxToBase == null) continue;
    const label = holding[key].trim() || "Unclassified";
    const value = convert(holding.quantity * holding.currentPrice, holding.fxToBase);
    if (value != null) totals.set(label, (totals.get(label) ?? 0) + value);
  }
  const total = [...totals.values()].reduce((sum, value) => sum + value, 0);
  return [...totals.entries()]
    .map(([label, value]) => ({ label, value, share: total > 0 ? value / total : 0 }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);
}

export default function MarketsPortfolioPage() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [baseCurrency, setBaseCurrency] = useState("USD");
  const [form, setForm] = useState({ ...blankForm, currency: "USD" });
  const [ready, setReady] = useState(false);
  const [storageWarning, setStorageWarning] = useState<string | null>(null);
  const [storageLoadFailed, setStorageLoadFailed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as Partial<PortfolioState>;
        if (parsed.version === 1 && Array.isArray(parsed.holdings)) {
          setHoldings(parsed.holdings.filter((item): item is Holding =>
            Boolean(item && typeof item.id === "string" && typeof item.name === "string" &&
              typeof item.currency === "string" && Number.isFinite(item.quantity) &&
              Number.isFinite(item.costPerUnit)),
          ));
          if (typeof parsed.baseCurrency === "string" && CURRENCIES.includes(parsed.baseCurrency)) {
            setBaseCurrency(parsed.baseCurrency);
            setForm({ ...blankForm, currency: parsed.baseCurrency, fxToBase: "1" });
          }
        }
      }
    } catch {
      setStorageLoadFailed(true);
      setStorageWarning("This browser could not read the saved portfolio. You can still work with the current session, but changes may not persist.");
    } finally {
      setReady(true);
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

  const pricedHoldings = useMemo(
    () => holdings.filter((holding) => holding.currentPrice != null && holding.fxToBase != null && holding.fxToBase > 0),
    [holdings],
  );
  const totalCurrentValue = pricedHoldings.reduce((sum, holding) => sum + (convert(holding.quantity * (holding.currentPrice ?? 0), holding.fxToBase) ?? 0), 0);
  const totalCostOfPriced = pricedHoldings.reduce((sum, holding) => sum + (convert(holding.quantity * holding.costPerUnit, holding.fxToBase) ?? 0), 0);
  const pricedGain = totalCurrentValue - totalCostOfPriced;
  const countryExposure = useMemo(() => exposureRows(holdings, "country"), [holdings]);
  const sectorExposure = useMemo(() => exposureRows(holdings, "sector"), [holdings]);
  const assetTypeExposure = useMemo(() => exposureRows(holdings, "assetType"), [holdings]);
  const currencyExposure = useMemo(() => exposureRows(holdings, "currency"), [holdings]);
  const largestPosition = useMemo(() => {
    const values = pricedHoldings.map((holding) => ({
      name: holding.name,
      ticker: holding.ticker,
      value: convert(holding.quantity * (holding.currentPrice ?? 0), holding.fxToBase) ?? 0,
    })).sort((a, b) => b.value - a.value);
    return values[0] && totalCurrentValue > 0 ? { ...values[0], share: values[0].value / totalCurrentValue } : null;
  }, [pricedHoldings, totalCurrentValue]);
  const missingPriceCount = holdings.filter((holding) => holding.currentPrice == null).length;
  const missingFxCount = holdings.filter((holding) => holding.fxToBase == null || holding.fxToBase <= 0).length;

  function updateForm(key: keyof typeof blankForm, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function addHolding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const quantity = Number(form.quantity);
    const costPerUnit = Number(form.costPerUnit);
    const currentPrice = form.currentPrice.trim() === "" ? null : Number(form.currentPrice);
    const fxToBase = form.currency === baseCurrency ? 1 : (form.fxToBase.trim() === "" ? null : Number(form.fxToBase));
    if (!form.name.trim() || !form.currency.trim() || !Number.isFinite(quantity) || quantity <= 0 ||
        !CURRENCIES.includes(form.currency) || !Number.isFinite(costPerUnit) || costPerUnit < 0 ||
        (currentPrice != null && (!Number.isFinite(currentPrice) || currentPrice <= 0)) ||
        (fxToBase != null && (!Number.isFinite(fxToBase) || fxToBase <= 0))) {
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
    }]);
    setForm({ ...blankForm, currency: baseCurrency });
    setMessage(duplicate
      ? "Holding added, but it matches an existing name/ticker and country. Check whether this is a separate lot or an accidental duplicate. Prices and FX rates are manual, not live."
      : "Holding added. Values are based on the prices and FX rates you entered, not live market feeds.");
  }

  async function importCsv(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError(null);
    setMessage(null);
    try {
      const rows = parseCsv(await file.text());
      if (rows.length < 2) throw new Error("The CSV must include a header row and at least one holding.");
      const headers = rows[0].map((header) => header.trim().toLowerCase().replace(/[ -]+/g, "_"));
      const missing = ["name", "currency", "quantity", "cost_per_unit"].filter((header) => !headers.includes(header));
      if (missing.length) throw new Error(`Missing required CSV columns: ${missing.join(", ")}.`);
      const col = (row: string[], name: string) => {
        const index = headers.indexOf(name);
        return index < 0 ? "" : (row[index] ?? "").trim();
      };
      const imported: Holding[] = [];
      let skipped = 0;
      let duplicateCount = 0;
      const seen = new Set(holdings.map((holding) => `${holding.ticker.toUpperCase()}|${holding.name.trim().toLowerCase()}|${holding.country.trim().toLowerCase()}`));
      for (const row of rows.slice(1)) {
        const name = col(row, "name");
        const currency = col(row, "currency").toUpperCase();
        const quantity = Number(col(row, "quantity"));
        const costPerUnit = Number(col(row, "cost_per_unit"));
        const currentText = col(row, "current_price");
        const fxText = col(row, "fx_to_base");
        const currentPrice = currentText === "" ? null : Number(currentText);
        const fxToBase = currency === baseCurrency ? 1 : fxText === "" ? null : Number(fxText);
        if (!name || !CURRENCIES.includes(currency) || !Number.isFinite(quantity) || quantity <= 0 ||
            !Number.isFinite(costPerUnit) || costPerUnit < 0 ||
            (currentPrice != null && (!Number.isFinite(currentPrice) || currentPrice <= 0)) ||
            (fxToBase != null && (!Number.isFinite(fxToBase) || fxToBase <= 0))) {
          skipped += 1;
          continue;
        }
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
          assetType: col(row, "asset_type") || "Other",
        });
      }
      if (!imported.length) throw new Error("No valid holdings were found. Check the required columns and numeric values.");
      setHoldings((current) => [...current, ...imported]);
      setMessage(`Imported ${imported.length} holding(s)${skipped ? `; skipped ${skipped} invalid row(s)` : ""}${duplicateCount ? `; detected ${duplicateCount} possible duplicate position(s)` : ""}. Review duplicates, FX conversion rates and current prices before relying on totals.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not import this CSV.");
    }
  }

  function exportCsv() {
    const rows = [
      CSV_HEADERS,
      ...holdings.map((holding) => [
        holding.name, holding.ticker, holding.country, holding.sector, holding.assetType, holding.currency,
        holding.quantity, holding.costPerUnit, holding.currentPrice, holding.fxToBase,
      ]),
    ];
    const csv = rows.map((row) => row.map(csvEscape).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "deal-intelligence-portfolio.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function updateHoldingNumber(id: string, key: "currentPrice" | "fxToBase", raw: string) {
    const value = raw.trim() === "" ? null : Number(raw);
    if (value != null && (!Number.isFinite(value) || value < 0 || (key === "fxToBase" && value === 0))) return;
    setHoldings((current) => current.map((holding) => {
      if (holding.id !== id) return holding;
      if (key === "fxToBase" && holding.currency === baseCurrency) return { ...holding, fxToBase: 1 };
      return { ...holding, [key]: value };
    }));
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

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · Portfolio Intelligence" title="Your portfolio, in context.">
        Add holdings manually or import a CSV to understand your exposure and review the prices and assumptions behind portfolio totals. Everything is stored in this browser only; no broker connection or server upload is used.
      </PageHeader>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Link href="/app/markets" className="text-sm text-[color:var(--muted)] underline-offset-4 hover:underline">← Back to Markets</Link>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-secondary" onClick={exportCsv} disabled={holdings.length === 0}>Export CSV backup</button>
          <button type="button" className="btn btn-ghost" onClick={clearPortfolio} disabled={holdings.length === 0}>Clear portfolio</button>
        </div>
      </div>

      {storageWarning && <ErrorNote message={storageWarning} />}
      {error && <ErrorNote message={error} />}
      {message && <p className="mb-4 text-sm text-[color:var(--muted)]" role="status">{message}</p>}

      <section className="panel p-5 sm:p-6" aria-labelledby="portfolio-settings-title">
        <div className="grid gap-4 sm:grid-cols-[1fr_2fr] sm:items-end">
          <div>
            <label htmlFor="base-currency" className="mb-1.5 block text-xs text-[color:var(--muted)]">Portfolio reporting currency</label>
            <select id="base-currency" className="field" value={baseCurrency} onChange={(event) => {
              const nextCurrency = event.target.value;
              if (holdings.length > 0 && !window.confirm("Changing the reporting currency resets existing FX conversion rates. Holding prices and cost basis stay unchanged, but you will need to re-enter FX rates for non-base-currency holdings. Continue?")) return;
              setBaseCurrency(nextCurrency);
              setHoldings((current) => current.map((holding) => ({ ...holding, fxToBase: holding.currency === nextCurrency ? 1 : null })));
              setForm({ ...blankForm, currency: nextCurrency, fxToBase: "1" });
              if (holdings.length > 0) setMessage("Reporting currency changed. FX rates for holdings in other currencies were cleared; re-enter current rates before relying on portfolio totals.");
            }}>
              {CURRENCIES.map((currency) => <option key={currency} value={currency}>{currency}</option>)}
            </select>
          </div>
          <div>
            <h2 id="portfolio-settings-title" className="text-sm font-medium">Your data stays on this device</h2>
            <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">
              Prices and exchange rates are manual inputs, not live quotes. For holdings in a different currency, enter the number of {baseCurrency} units represented by one unit of that holding&apos;s currency. Change the reporting currency only after checking the FX rates.
            </p>
          </div>
        </div>
      </section>

      <section className="mt-6" aria-labelledby="portfolio-summary-title">
        <div className="mb-3">
          <p className="eyebrow">Portfolio snapshot</p>
          <h2 id="portfolio-summary-title" className="h3 mt-2 text-xl">What the entered data supports</h2>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Holdings" value={holdings.length} note="Manual entries and CSV imports" />
          <Stat label="Priced and FX-converted" value={pricedHoldings.length} note="Eligible for current-value calculations" />
          <Stat label={`Entered market value (${baseCurrency})`} value={amount(totalCurrentValue, baseCurrency)} note="Excludes holdings without price or FX inputs" />
          <Stat label="Unpriced or unconverted" value={holdings.length - pricedHoldings.length} note="Not included in market value or exposure" />
        </div>
        <div className="mt-3 rounded-lg border hairline p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium">Gain/loss on priced holdings</p>
            <p className={`text-sm font-medium ${pricedGain > 0 ? "text-verified" : pricedGain < 0 ? "text-risk" : ""}`}>{amount(pricedGain, baseCurrency)}</p>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">
            Compared with recorded cost basis for the same priced and FX-converted holdings only. This is an indicative unrealised difference; it excludes fees, taxes, distributions, corporate actions and any FX-rate history.
          </p>
        </div>
      </section>

      <section className="mt-6 panel p-5" aria-labelledby="concentration-title">
        <p className="eyebrow">Portfolio intelligence</p>
        <h2 id="concentration-title" className="h3 mt-2 text-lg">Concentration and data-quality checks</h2>
        <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">These checks describe the holdings and manual inputs you supplied. They are not a calibrated risk score, a forecast, or investment advice.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-lg border hairline p-3"><p className="text-xs text-[color:var(--muted)]">Largest priced position</p><p className="mt-2 text-sm font-medium">{largestPosition ? `${(largestPosition.share * 100).toFixed(1)}% · ${largestPosition.name}` : "Not available"}</p><p className="mt-1 text-xs text-[color:var(--dim)]">Based on entered prices and FX only</p></div>
          <div className="rounded-lg border hairline p-3"><p className="text-xs text-[color:var(--muted)]">Missing current prices</p><p className="mt-2 text-sm font-medium">{missingPriceCount}</p><p className="mt-1 text-xs text-[color:var(--dim)]">Excluded from current value</p></div>
          <div className="rounded-lg border hairline p-3"><p className="text-xs text-[color:var(--muted)]">Missing FX conversion</p><p className="mt-2 text-sm font-medium">{missingFxCount}</p><p className="mt-1 text-xs text-[color:var(--dim)]">Excluded from base-currency totals</p></div>
          <div className="rounded-lg border hairline p-3"><p className="text-xs text-[color:var(--muted)]">Priced and converted</p><p className="mt-2 text-sm font-medium">{pricedHoldings.length} of {holdings.length}</p><p className="mt-1 text-xs text-[color:var(--dim)]">Coverage of your entered portfolio</p></div>
        </div>
        <div className="mt-4 space-y-2 text-sm">
          {largestPosition && largestPosition.share >= 0.25 ? <p className="rounded-lg border hairline p-3"><strong>Single-position concentration:</strong> {largestPosition.name} is {(largestPosition.share * 100).toFixed(1)}% of entered, priced portfolio value. A 25% threshold is a simple review trigger, not a universal risk limit.</p> : null}
          {countryExposure[0]?.share >= 0.6 ? <p className="rounded-lg border hairline p-3"><strong>Country concentration:</strong> {countryExposure[0].label} represents {(countryExposure[0].share * 100).toFixed(1)}% of priced value. Consider whether this reflects your intended geographic exposure.</p> : null}
          {sectorExposure[0]?.share >= 0.6 ? <p className="rounded-lg border hairline p-3"><strong>Sector concentration:</strong> {sectorExposure[0].label} represents {(sectorExposure[0].share * 100).toFixed(1)}% of priced value. This simple flag does not account for businesses with overlapping sector exposure.</p> : null}
          {holdings.length > 0 && (missingPriceCount > 0 || missingFxCount > 0) ? <p className="rounded-lg border hairline p-3"><strong>Incomplete valuation:</strong> {missingPriceCount} holding(s) have no current price and {missingFxCount} have no usable FX conversion. Portfolio totals and exposures are incomplete until these are resolved.</p> : null}
          {holdings.length === 0 ? <p className="rounded-lg border hairline p-3">Add holdings to see concentration checks. No portfolio data is sent to the server.</p> : null}
          {largestPosition && largestPosition.share < 0.25 && (countryExposure[0]?.share ?? 0) < 0.6 && (sectorExposure[0]?.share ?? 0) < 0.6 && missingPriceCount === 0 && missingFxCount === 0 ? <p className="rounded-lg border hairline p-3">No simple concentration or missing-input flag was triggered by the entered data. This does not mean the portfolio is low-risk.</p> : null}
        </div>
      </section>

      <section className="mt-8 grid gap-6 xl:grid-cols-2">
        <div className="panel p-5">
          <p className="eyebrow">Add an investment</p>
          <h2 className="h3 mt-2 text-lg">Enter a holding</h2>
          <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={addHolding}>
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
              <select id="holding-currency" className="field" value={form.currency} onChange={(event) => { const currency = event.target.value; setForm((current) => ({ ...current, currency, fxToBase: currency === baseCurrency ? "1" : "" })); }}>
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
              <input id="holding-price" className="field" type="number" min="0" step="any" value={form.currentPrice} onChange={(event) => updateForm("currentPrice", event.target.value)} placeholder="Optional; manually entered" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="holding-fx">FX to {baseCurrency}</label>
              <input id="holding-fx" className="field" type="number" min="0.000000001" step="any" value={form.currency === baseCurrency ? "1" : form.fxToBase} disabled={form.currency === baseCurrency} onChange={(event) => updateForm("fxToBase", event.target.value)} placeholder="Base currency per unit" />
            </div>
            <p className="sm:col-span-2 text-xs leading-relaxed text-[color:var(--dim)]">
              If the holding currency equals the reporting currency, FX is 1. For another currency, provide a positive conversion rate. Leaving it blank excludes that holding from base-currency totals and exposure charts.
            </p>
            <button className="btn btn-primary sm:col-span-2" type="submit">Add holding</button>
          </form>
        </div>

        <div className="space-y-6">
          <section className="panel p-5" aria-labelledby="csv-title">
            <p className="eyebrow">Bulk import</p>
            <h2 id="csv-title" className="h3 mt-2 text-lg">Import a CSV</h2>
            <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">
              Required columns: <code>name</code>, <code>currency</code>, <code>quantity</code>, <code>cost_per_unit</code>. Optional columns: <code>ticker</code>, <code>country</code>, <code>sector</code>, <code>asset_type</code>, <code>current_price</code> and <code>fx_to_base</code>.
            </p>
            <label className="mt-4 block text-xs text-[color:var(--muted)]" htmlFor="portfolio-csv">Choose CSV file</label>
            <input id="portfolio-csv" className="field mt-2" type="file" accept=".csv,text/csv" onChange={importCsv} />
            <button type="button" className="btn btn-secondary mt-3" onClick={() => {
              const example = [CSV_HEADERS.join(","), ["Example African Bank", "EXBANK", "Kenya", "Banking", "Stock", "KES", 10, 120, 135, 0.0075].join(",")].join("\r\n");
              const blob = new Blob([example + "\r\n"], { type: "text/csv;charset=utf-8" });
              const url = URL.createObjectURL(blob);
              const anchor = document.createElement("a");
              anchor.href = url;
              anchor.download = "portfolio-import-template.csv";
              anchor.click();
              URL.revokeObjectURL(url);
            }}>Download CSV template</button>
          </section>

          <section className="panel p-5" aria-labelledby="exposure-title">
            <p className="eyebrow">Portfolio composition</p>
            <h2 id="exposure-title" className="h3 mt-2 text-lg">Where the priced holdings sit</h2>
            <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">
              All four exposure views use manually entered current prices and FX rates. Holdings without either are excluded; these are not live valuations.
            </p>
            <div className="mt-4 grid gap-5 sm:grid-cols-2">
              <ExposureList title="By country" rows={countryExposure} currency={baseCurrency} />
              <ExposureList title="By sector" rows={sectorExposure} currency={baseCurrency} />
              <ExposureList title="By asset type" rows={assetTypeExposure} currency={baseCurrency} />
              <ExposureList title="By holding currency" rows={currencyExposure} currency={baseCurrency} />
            </div>
          </section>
        </div>
      </section>

      <section className="mt-8" aria-labelledby="portfolio-insights-title">
        <div className="mb-4">
          <p className="eyebrow">Portfolio Intelligence</p>
          <h2 id="portfolio-insights-title" className="h3 mt-2 text-xl">What stands out in your entered holdings</h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[color:var(--muted)]">These are transparent concentration and completeness checks calculated from your own entered prices, FX rates and classifications. They are not predictions, live risk scores or buy/sell recommendations.</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {portfolioInsights.map((insight) => <article key={insight.title} className="rounded-xl border hairline p-4"><p className="text-sm font-medium">{insight.title}</p><p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">{insight.detail}</p></article>)}
        </div>
      </section>

      <section className="mt-8" aria-labelledby="holdings-title">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow">Your holdings</p>
            <h2 id="holdings-title" className="h3 mt-2 text-xl">Portfolio register</h2>
          </div>
          <p className="text-xs text-[color:var(--dim)]">{ready ? "Saved locally in this browser" : "Loading local portfolio…"}</p>
        </div>
        {!ready ? <p className="py-6 text-sm text-[color:var(--dim)]" role="status">Loading your locally saved portfolio…</p> : null}
        {ready && holdings.length === 0 ? (
          <div className="rounded-xl border border-dashed hairline p-8 text-center">
            <h3 className="text-base font-medium">Your portfolio starts here.</h3>
            <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-[color:var(--muted)]">Add a holding above or import a CSV. This page will not invent prices or pretend to have broker access.</p>
          </div>
        ) : null}
        {holdings.length > 0 && (
          <div className="overflow-x-auto rounded-xl border hairline">
            <table className="w-full min-w-[68rem] border-collapse text-left text-xs">
              <thead>
                <tr className="border-b hairline text-[color:var(--dim)]">
                  {["Investment", "Type", "Country / sector", "Units", "Cost / unit", "Entered price", `FX to ${baseCurrency}`, `Value (${baseCurrency})`, "Gain / loss", ""].map((heading) => (
                    <th key={heading} className="whitespace-nowrap px-3 py-3 font-normal">{heading}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {holdings.map((holding) => {
                  const cost = convert(holding.quantity * holding.costPerUnit, holding.fxToBase);
                  const value = holding.currentPrice == null ? null : convert(holding.quantity * holding.currentPrice, holding.fxToBase);
                  const gain = value == null || cost == null ? null : value - cost;
                  return (
                    <tr key={holding.id} className="border-b hairline last:border-0">
                      <td className="px-3 py-3">
                        <Link href={`/app/companies?name=${encodeURIComponent(holding.name)}${holding.ticker ? `&ticker=${encodeURIComponent(holding.ticker)}` : ""}`} className="font-medium underline-offset-4 hover:underline">{holding.name}</Link>
                        {holding.ticker ? <p className="mt-1 text-[color:var(--dim)]">{holding.ticker}</p> : null}
                        <p className="mt-1 text-[color:var(--dim)]">{holding.currency}{holding.fxToBase == null ? " · FX missing" : ""}</p>
                        <Link href={`/app/companies?name=${encodeURIComponent(holding.name)}&ticker=${encodeURIComponent(holding.ticker)}`} className="mt-2 inline-flex text-[color:var(--muted)] underline-offset-4 hover:underline">Research →</Link>
                      </td>
                      <td className="px-3 py-3">{holding.assetType}</td>
                      <td className="px-3 py-3">{[holding.country || "Unclassified", holding.sector || "Unclassified"].join(" · ")}</td>
                      <td className="px-3 py-3 kbd">{holding.quantity.toLocaleString("en", { maximumFractionDigits: 6 })}</td>
                      <td className="px-3 py-3 kbd">{amount(holding.costPerUnit, holding.currency)}</td>
                      <td className="px-3 py-3 kbd">{holding.currentPrice == null ? "Not entered" : amount(holding.currentPrice, holding.currency)}</td>
                      <td className="px-3 py-3 kbd">{value == null ? "Not available" : amount(value, baseCurrency)}</td>
                      <td className={`px-3 py-3 kbd ${gain != null && gain > 0 ? "text-verified" : gain != null && gain < 0 ? "text-risk" : ""}`}>{gain == null ? "Not available" : amount(gain, baseCurrency)}</td>
                      <td className="px-3 py-3"><button type="button" className="text-[color:var(--muted)] underline-offset-4 hover:underline" onClick={() => removeHolding(holding.id)} aria-label={`Remove ${holding.name}`}>Remove</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="mt-8 rounded-xl border hairline p-4 text-xs leading-relaxed text-[color:var(--dim)]">
        This is an early portfolio workspace, not a live brokerage connection or personalised financial advice. Prices and FX rates are user-entered. Totals exclude holdings without usable conversion rates, and gain/loss excludes fees, taxes, dividends and corporate actions. Clearing browser data or using another device may remove access to this portfolio; export a backup if needed.
      </div>
    </Container>
  );
}

function ExposureList({ title, rows, currency }: { title: string; rows: { label: string; value: number; share: number }[]; currency: string }) {
  return (
    <div>
      <h3 className="text-sm font-medium">{title}</h3>
      {rows.length === 0 ? <p className="mt-2 text-xs text-[color:var(--dim)]">Add priced holdings with FX rates to calculate exposure.</p> : (
        <ul className="mt-3 space-y-3">
          {rows.map((row) => (
            <li key={row.label}>
              <div className="flex items-baseline justify-between gap-2 text-xs">
                <span className="min-w-0 truncate">{row.label}</span>
                <span className="shrink-0 kbd text-[color:var(--muted)]">{(row.share * 100).toFixed(1)}% · {amount(row.value, currency)}</span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-[color:var(--accent)]" style={{ width: `${Math.max(0, Math.min(100, row.share * 100))}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
