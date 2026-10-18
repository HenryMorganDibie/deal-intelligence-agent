"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Container } from "../../../components/primitives";
import { DealRows, ErrorNote, Field, Loading, PageHeader, Pagination, Stat, usd, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { DEAL_TYPES, SECTORS, get, type Deal } from "../../../lib/market";

type Filters = { q: string; country: string; type: string; sector: string; investor: string; since: string };
const EMPTY: Filters = { q: "", country: "", type: "", sector: "", investor: "", since: "" };

export default function DealsPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [rows, setRows] = useState<Deal[] | null>(null);
  const [totalMatching, setTotalMatching] = useState(0);
  const [totalInDatabase, setTotalInDatabase] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(50);
  const [error, setError] = useState<string | null>(null);

  async function load(f: Filters, nextOffset = 0, nextLimit = limit) {
    setOffset(nextOffset);
    setLimit(nextLimit);
    setRows(null);
    setError(null);
    try {
      const r = await get<{ total_in_database: number; total_matching: number; deals: Deal[] }>("/api/deals", { ...f, limit: nextLimit, offset: nextOffset });
      setRows(r.deals);
      setTotalMatching(r.total_matching);
      setTotalInDatabase(r.total_in_database);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load deals.");
      setRows([]);
    }
  }

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const f = { ...EMPTY, ...Object.fromEntries([...q.entries()].filter(([k]) => k in EMPTY)) } as Filters;
    setFilters(f);
    load(f);
  }, []);

  function submit(e: FormEvent) {
    e.preventDefault();
    load(filters, 0, limit);
  }

  const set = (k: keyof Filters) => (e: { target: { value: string } }) => setFilters({ ...filters, [k]: e.target.value });
  const disclosed = (rows ?? []).filter((d) => d.amount_usd);
  const disclosedAmounts = disclosed.flatMap((d) => (d.amount_usd ? [d.amount_usd] : [])).sort((a, b) => a - b);
  const medianSize = disclosedAmounts.length
    ? (disclosedAmounts[Math.floor((disclosedAmounts.length - 1) / 2)] + disclosedAmounts[Math.floor(disclosedAmounts.length / 2)]) / 2
    : null;
  return (
    <Container className="py-10 lg:py-14">
      <PageHeader eyebrow="Deals" title="Private equity, venture, debt and M&A across Africa.">
        Transactions extracted daily from African business and private-capital publications in English, French and
        Portuguese, with every source linked. Amounts are as reported, converted to US dollars at the year&apos;s official
        rate. Undisclosed deals that no one reports cannot appear.
      </PageHeader>

      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <div className="sm:col-span-2">
          <Field label="Search">
            <input value={filters.q} onChange={set("q")} placeholder="Company, investor or keyword" className="field" />
          </Field>
        </div>
        <Field label="Country (ISO)">
          <input value={filters.country} onChange={set("country")} maxLength={3} placeholder="NG" className="field kbd uppercase" />
        </Field>
        <Field label="Type">
          <select value={filters.type} onChange={set("type")} className="field">
            <option value="">All types</option>
            {DEAL_TYPES.map((t) => (
              <option key={t} value={t}>
                {words(t)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Sector">
          <select value={filters.sector} onChange={set("sector")} className="field">
            <option value="">All sectors</option>
            {SECTORS.map((s) => (
              <option key={s} value={s}>
                {words(s)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Since">
          <input type="date" value={filters.since} onChange={set("since")} className="field" />
        </Field>
        <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-6">
          <button type="submit" className="btn btn-primary">
            Search
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              setFilters(EMPTY);
              load(EMPTY, 0, limit);
            }}
          >
            Reset
          </button>
        </div>
      </form>

      {error && <ErrorNote message={error} />}
      {rows === null ? (
        <Loading />
      ) : (
        <>
          <div className="mt-8 grid gap-3 sm:grid-cols-3">
            <Stat label="Matching deals" value={totalMatching.toLocaleString()} note={`${totalInDatabase.toLocaleString()} total in database`} />
            <Stat label="Disclosed value on this page" value={usd(disclosed.reduce((a, d) => a + (d.amount_usd ?? 0), 0))} note={`${disclosed.length} with amounts`} />
            <Stat
              label="Median size on this page"
              value={usd(medianSize)}
            />
          </div>
          <div className="mt-6">
            {rows.length ? <><DealRows deals={rows} /><Pagination total={totalMatching} offset={offset} limit={limit} onPageChange={(next) => load(filters, next, limit)} onPageSizeChange={(next) => load(filters, 0, next)} /></> : <p className="py-6 text-sm text-[color:var(--muted)]">No deals match these filters.</p>}
          </div>
        </>
      )}
    </Container>
  );
}
