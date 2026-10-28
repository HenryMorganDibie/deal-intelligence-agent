"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../../components/primitives";
import { ErrorNote, Field, Loading, PageHeader, Table, Td, usd } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { get } from "../../../../lib/market";
import { asOf, companyHref, pct, price, tone, type Screener } from "../../../../lib/markets-data";

const EXCHANGES: [string, string][] = [
  ["", "All exchanges"], ["jse", "Johannesburg"], ["ngx", "Nigeria"], ["egx", "Egypt"], ["nse", "Nairobi"],
  ["bvc", "Casablanca"], ["brvm", "BRVM"], ["gse", "Ghana"], ["sem", "Mauritius"], ["bvmt", "Tunis"],
  ["bse", "Botswana"], ["dse", "Dar es Salaam"], ["luse", "Lusaka"], ["mse", "Malawi"], ["nsx", "Namibia"],
  ["rse", "Rwanda"], ["zse", "Zimbabwe"],
];
const SORTS: [string, string][] = [["mcap", "Market cap"], ["chg_1d", "Today's change"], ["ytd", "YTD in USD"],
  ["value", "Value traded"], ["name", "Name"]];
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
  const [f, setF] = useState<Filters | null>(null);
  const [data, setData] = useState<Screener | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
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
      <PageHeader eyebrow="Markets · Screener" title="Every listed share in Africa.">
        Filter by exchange, sector and size; sort by market cap, today&apos;s move, year-to-date return in dollars or
        value traded. <Link href="/app/markets" className="underline-offset-4 hover:underline">Back to markets</Link>
      </PageHeader>

      {f && (
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

      {error && <ErrorNote message={error} />}
      {!data && !error && <Loading label="Loading the screen…" />}
      {data && (
        <section className="mt-6">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-[color:var(--dim)]">
            <span>{data.total.toLocaleString()} shares{data.total > data.rows.length ? `, first ${data.rows.length} shown` : ""}</span>
            <button onClick={download} className="underline-offset-4 hover:underline">Download CSV</button>
          </div>
          <Table head={["Company", "Exchange", "Sector", "Price", "Today", "YTD (local)", "YTD (USD)", "Market cap", "Traded (USD)", "As of"]} minWidth="64rem">
            {data.rows.map((r) => (
              <tr key={`${r.exchange}:${r.symbol}`} className={r.stale ? "opacity-60" : ""}>
                <Td>
                  <Link href={companyHref(r)} className="hover:underline">{r.name}</Link>
                  <span className="block text-xs text-[color:var(--dim)]">{r.symbol}{r.secondary_of ? ` · secondary listing (primary: ${r.secondary_of.toUpperCase()})` : ""}</span>
                </Td>
                <Td className="text-xs">{r.exchange.toUpperCase()}</Td>
                <Td className="text-xs text-[color:var(--muted)]">{r.sector ?? ""}</Td>
                <Td className="kbd whitespace-nowrap">{price(r.price, r.currency)}</Td>
                <Td className={`kbd ${tone(r.chg_1d)}`}>{pct(r.chg_1d, 2)}</Td>
                <Td className={`kbd ${tone(r.ytd)}`}>
                  <span title={r.ytd_suspect ? "Likely unadjusted for a split or bonus issue" : undefined}>{pct(r.ytd)}{r.ytd_suspect ? " ⚑" : ""}</span>
                </Td>
                <Td className={`kbd ${tone(r.ytd_usd)}`}>{r.ytd_suspect ? "n/a" : pct(r.ytd_usd)}</Td>
                <Td className="kbd" >{r.mcap_usd ? usd(r.mcap_usd) : <span className="text-[color:var(--dim)]" title={r.cap_note}>n/a</span>}</Td>
                <Td className="kbd">{r.value_traded_usd ? usd(r.value_traded_usd) : ""}</Td>
                <Td className="text-xs text-[color:var(--dim)]">{asOf(r.date)}{r.stale ? " · stale" : ""}</Td>
              </tr>
            ))}
          </Table>
          <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">
            ⚑ A year-to-date loss beyond 60% is more often a split or bonus issue the source has not adjusted for; it is
            flagged and left out of exchange and sector returns. Market caps above $40bn are withheld as source errors.
            Johannesburg, Nairobi and Tunis publish no cap in the source lists.
          </p>
        </section>
      )}
    </Container>
  );
}
