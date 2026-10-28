"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../../components/primitives";
import { ErrorNote, Field, Loading, PageHeader, Table, Td, usd, words } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { get } from "../../../../lib/market";
import { asOf, companyHref, directoryHref, quoteWhen, pct, price, tone, type Directory, type Screener } from "../../../../lib/markets-data";

const EXCHANGES: [string, string][] = [
  ["", "All exchanges"], ["jse", "Johannesburg"], ["ngx", "Nigeria"], ["egx", "Egypt"], ["nse", "Nairobi"],
  ["bvc", "Casablanca"], ["brvm", "BRVM"], ["gse", "Ghana"], ["sem", "Mauritius"], ["bvmt", "Tunis"],
  ["bse", "Botswana"], ["dse", "Dar es Salaam"], ["luse", "Lusaka"], ["mse", "Malawi"], ["nsx", "Namibia"],
  ["rse", "Rwanda"], ["zse", "Zimbabwe"], ["use", "Uganda"], ["vfex", "Victoria Falls (USD)"],
  ["bvmac", "BVMAC (Central Africa)"], ["bodiva", "Angola"], ["sgbv", "Algeria"], ["ese", "Eswatini"],
  ["merj", "Seychelles (MERJ)"], ["esx", "Ethiopia (no price feed)"],
];
const SORTS: [string, string][] = [["mcap", "Market cap"], ["chg_1d", "Today's change"], ["ytd", "YTD in USD"],
  ["value", "Value traded"], ["pe", "Lowest P/E"], ["dividend", "Dividend yield"], ["name", "Name"]];
const PRIVATE_SORTS: [string, string][] = [["recent", "Latest activity"], ["raised", "Amount raised"],
  ["size", "Latest valuation"], ["deals", "Most deals"], ["name", "Name"]];
const SECTOR_GROUPS = ["Financials", "Telecom", "Technology", "Oil & Gas", "Utilities", "Health Care", "Agriculture",
  "Basic Materials", "Consumer Goods", "Consumer Services", "Industrials", "Real Estate"];

type PrivateFilters = { q: string; country: string; sector: string; sort: string };

function PrivateCompanies() {
  const [f, setF] = useState<PrivateFilters>({ q: "", country: "", sector: "", sort: "recent" });
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Directory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v));
    const t = setTimeout(() => {
      get<Directory>("/api/companies/directory", { ...params, kind: "private", limit: 100, offset })
        .then((d) => { if (active) { setData(d); setError(null); } })
        .catch((e) => { if (active) setError(e instanceof ApiError ? e.message : "Private companies could not be loaded."); });
    }, f.q ? 250 : 0);
    return () => { active = false; clearTimeout(t); };
  }, [f, offset]);

  const set = (k: keyof PrivateFilters) => (e: { target: { value: string } }) => { setOffset(0); setF({ ...f, [k]: e.target.value }); };
  return (
    <>
      <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(e) => e.preventDefault()}>
        <Field label="Search">
          <input value={f.q} onChange={set("q")} placeholder="Company name" className="field" />
        </Field>
        <Field label="Country">
          <input value={f.country} onChange={set("country")} placeholder="Nigeria or NG" className="field" />
        </Field>
        <Field label="Sector">
          <select value={f.sector} onChange={set("sector")} className="field">
            <option value="">All sectors</option>
            {SECTOR_GROUPS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="Sort by">
          <select value={f.sort} onChange={set("sort")} className="field">
            {PRIVATE_SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
      </form>
      {error && <ErrorNote message={error} />}
      {!data && !error && <Loading label="Loading private companies…" />}
      {data && (
        <section className="mt-6">
          <p className="mb-2 text-xs text-[color:var(--dim)]">{data.total.toLocaleString()} private companies{data.total > data.rows.length ? `, ${offset + 1} to ${offset + data.rows.length} shown` : ""}</p>
          <Table head={["Company", "Country", "Sector", "Deals", "Equity raised", "Debt raised", "Last round", "Latest valuation", "Last activity", "Investors"]} minWidth="72rem">
            {data.rows.map((r) => (
              <tr key={r.name + (r.country ?? "")}>
                <Td><Link href={directoryHref(r)} className="hover:underline">{r.name}</Link>{r.acquired ? <span className="block text-xs text-[color:var(--dim)]">acquired</span> : null}</Td>
                <Td className="text-xs">{r.country ?? ""}</Td>
                <Td className="text-xs text-[color:var(--muted)]">{r.sector ?? ""}</Td>
                <Td className="kbd">{r.deal_count}</Td>
                <Td className="kbd">{r.equity_raised_usd ? usd(r.equity_raised_usd) : ""}</Td>
                <Td className="kbd">{r.debt_raised_usd ? usd(r.debt_raised_usd) : ""}</Td>
                <Td className="text-xs">{r.last_round ? words(r.last_round) : r.last_deal_type ? words(r.last_deal_type) : ""}</Td>
                <Td className="kbd">{r.valuation_usd ? <span title={r.valuation_date ?? undefined}>{usd(r.valuation_usd)}</span> : ""}</Td>
                <Td className="text-xs text-[color:var(--dim)]">{r.last_deal_date ?? ""}</Td>
                <Td className="text-xs text-[color:var(--muted)]">{(r.investors ?? []).slice(0, 3).join(", ")}{(r.investor_count ?? 0) > 3 ? ` +${(r.investor_count ?? 0) - 3}` : ""}</Td>
              </tr>
            ))}
          </Table>
          <div className="mt-3 flex gap-3 text-xs">
            {offset > 0 && <button className="underline-offset-4 hover:underline" onClick={() => setOffset(Math.max(0, offset - 100))}>← Previous</button>}
            {offset + data.rows.length < data.total && <button className="underline-offset-4 hover:underline" onClick={() => setOffset(offset + 100)}>Next →</button>}
          </div>
          <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">
            Every company the deals database records as the target of a funding round, loan, acquisition, merger, exit or
            listing. Amounts and valuations are as reported in the press or implied by a disclosed stake and price.
          </p>
        </section>
      )}
    </>
  );
}
const SIZES: [string, string][] = [["", "Any size"], ["10000000", "$10m+"], ["100000000", "$100m+"],
  ["1000000000", "$1bn+"]];

type Filters = { exchange: string; sector: string; min_mcap_usd: string; q: string; sort: string; include_stale: string };
const EMPTY: Filters = { exchange: "", sector: "", min_mcap_usd: "", q: "", sort: "mcap", include_stale: "" };

function toCsv(rows: Screener["rows"]): string {
  const head = ["exchange", "symbol", "name", "sector", "currency", "price", "chg_1d", "ytd", "ytd_usd", "mcap_usd", "date"];
  const cell = (v: unknown) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
  return [head.join(","), ...rows.map((r) => head.map((k) => cell((r as Record<string, unknown>)[k])).join(","))].join("\n");
}

export default function ScreenerPage() {
  const [view, setView] = useState<"listed" | "private">("listed");
  const [f, setF] = useState<Filters | null>(null);
  const [data, setData] = useState<Screener | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("view") === "private") setView("private");
    setF({ ...EMPTY, ...Object.fromEntries([...q.entries()].filter(([k]) => k in EMPTY)) });
  }, []);

  useEffect(() => {
    if (!f) return;
    let active = true;
    const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v));
    window.history.replaceState(null, "", `?${new URLSearchParams(params)}`);
    const t = setTimeout(() => {
      get<Screener>("/api/markets/screener", { ...params, limit: 300 })
        .then((d) => { if (active) { setData(d); setError(null); } })
        .catch((e) => { if (active) setError(e instanceof ApiError ? e.message : "The screener could not be loaded."); });
    }, f.q ? 250 : 0);
    return () => { active = false; clearTimeout(t); };
  }, [f]);

  const set = (k: keyof Filters) => (e: { target: { value: string } }) => f && setF({ ...f, [k]: e.target.value });

  function download() {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([toCsv(data.rows)], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "african-equities-screen.csv" });
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · Screener" title="Every company in Africa we can see.">
        Listed shares on 18 exchanges, priced daily, and private companies from the deals database. Filter by
        exchange, country, sector and size. <Link href="/app/markets" className="underline-offset-4 hover:underline">Back to markets</Link>
      </PageHeader>

      <div className="mb-5 flex gap-2" role="tablist" aria-label="Company type">
        {(["listed", "private"] as const).map((v) => (
          <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}
            className={`rounded-full border hairline px-4 py-1.5 text-sm ${view === v ? "bg-white/10" : ""}`}>
            {v === "listed" ? "Listed shares" : "Private companies"}
          </button>
        ))}
      </div>

      {view === "private" && <PrivateCompanies />}

      {view === "listed" && f && (
        <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6" onSubmit={(e) => e.preventDefault()}>
          <Field label="Search">
            <input value={f.q} onChange={set("q")} placeholder="Name or ticker" className="field" />
          </Field>
          <Field label="Exchange">
            <select value={f.exchange} onChange={set("exchange")} className="field">
              {EXCHANGES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
          <Field label="Sector">
            <select value={f.sector} onChange={set("sector")} className="field">
              <option value="">All sectors</option>
              {(data?.sectors ?? (f.sector ? [f.sector] : [])).map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Market cap">
            <select value={f.min_mcap_usd} onChange={set("min_mcap_usd")} className="field">
              {SIZES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
          <Field label="Sort by">
            <select value={f.sort} onChange={set("sort")} className="field">
              {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
          <Field label="Prices">
            <select value={f.include_stale} onChange={set("include_stale")} className="field">
              <option value="">Priced in the last week</option>
              <option value="true">Include stale prices</option>
            </select>
          </Field>
        </form>
      )}

      {view === "listed" && error && <ErrorNote message={error} />}
      {view === "listed" && !data && !error && <Loading label="Loading the screen…" />}
      {view === "listed" && data && (
        <section className="mt-6">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-[color:var(--dim)]">
            <span>{data.total.toLocaleString()} shares{data.total > data.rows.length ? `, first ${data.rows.length} shown` : ""}</span>
            <button onClick={download} className="underline-offset-4 hover:underline">Download CSV</button>
          </div>
          <Table head={["Company", "Exchange", "Sector", "Price", "Today", "YTD (local)", "YTD (USD)", "Market cap", "P/E", "Yield", "Traded (USD)", "As of"]} minWidth="72rem">
            {data.rows.map((r) => (
              <tr key={`${r.exchange}:${r.symbol}`} className={r.stale ? "opacity-60" : ""}>
                <Td>
                  <Link href={companyHref(r)} className="hover:underline">{r.name}</Link>
                  <span className="block text-xs text-[color:var(--dim)]">{r.symbol}{r.secondary_of ? ` · secondary listing (primary: ${r.secondary_of.toUpperCase()})` : ""}{r.priced_from ? ` · priced from its ${r.priced_from.toUpperCase()} listing` : ""}{r.foreign_primary ? " · listed primarily abroad" : ""}</span>
                </Td>
                <Td className="text-xs">{r.exchange.toUpperCase()}</Td>
                <Td className="text-xs text-[color:var(--muted)]">{r.sector ?? ""}</Td>
                <Td className="kbd whitespace-nowrap">{r.price != null ? price(r.price, r.currency) : <span className="text-[color:var(--dim)]">no price feed</span>}</Td>
                <Td className={`kbd ${tone(r.chg_1d)}`}>{pct(r.chg_1d, 2)}</Td>
                <Td className={`kbd ${tone(r.ytd)}`}>
                  <span title={r.ytd_suspect ? "Likely unadjusted for a split or bonus issue" : undefined}>{pct(r.ytd)}{r.ytd_suspect ? " ⚑" : ""}</span>
                </Td>
                <Td className={`kbd ${tone(r.ytd_usd)}`}>{r.ytd_suspect ? "n/a" : pct(r.ytd_usd)}</Td>
                <Td className="kbd" >{r.mcap_usd ? usd(r.mcap_usd) : <span className="text-[color:var(--dim)]" title={r.cap_note}>n/a</span>}</Td>
                <Td className="kbd">{r.pe != null ? r.pe.toFixed(1) : ""}</Td>
                <Td className="kbd">{r.dividend_yield != null ? `${(r.dividend_yield * 100).toFixed(1)}%` : ""}</Td>
                <Td className="kbd">{r.value_traded_usd ? usd(r.value_traded_usd) : ""}</Td>
                <Td className="text-xs text-[color:var(--dim)]">{quoteWhen(r)}{r.stale ? " · stale" : ""}</Td>
              </tr>
            ))}
          </Table>
          <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">
            ⚑ A year-to-date loss beyond 60% is more often a split or bonus issue the source has not adjusted for; it is
            flagged and left out of exchange and sector returns. Market caps above $40bn are withheld as source errors.
            Caps of groups listed primarily abroad (BHP, AB InBev) are their worldwide caps and stay out of exchange
            totals. Namibian shares also listed in Johannesburg take their JSE close (the currencies are pegged one for
            one). Ethiopia&apos;s exchange publishes its listings but no daily prices.
          </p>
        </section>
      )}
    </Container>
  );
}
