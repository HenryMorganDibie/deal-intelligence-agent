"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Container } from "../../../components/primitives";
import { DealRows, ErrorNote, Field, Loading, PageHeader, Stat, usd, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { DEAL_TYPES, SECTORS, get, type Deal } from "../../../lib/market";

type Filters = { q: string; country: string; type: string; sector: string; investor: string; since: string };
const EMPTY: Filters = { q: "", country: "", type: "", sector: "", investor: "", since: "" };

export default function DealsPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [rows, setRows] = useState<Deal[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function load(f: Filters) {
    setRows(null);
    setError(null);
    try {
      const r = await get<{ total_in_database: number; deals: Deal[] }>("/api/deals", { ...f, limit: 200 });
      setRows(r.deals);
      setTotal(r.total_in_database);
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
    load(filters);
  }

  const set = (k: keyof Filters) => (e: { target: { value: string } }) => setFilters({ ...filters, [k]: e.target.value });
  const disclosed = (rows ?? []).filter((d) => d.amount_usd);
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
              load(EMPTY);
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
            <Stat label="Matching deals" value={rows.length} note={`${total} in the database`} />
            <Stat label="Disclosed value" value={usd(disclosed.reduce((a, d) => a + (d.amount_usd ?? 0), 0))} note={`${disclosed.length} with amounts`} />
            <Stat
              label="Median disclosed size"
              value={usd(disclosed.length ? [...disclosed].sort((a, b) => (a.amount_usd ?? 0) - (b.amount_usd ?? 0))[Math.floor(disclosed.length / 2)].amount_usd : null)}
            />
          </div>
          <div className="mt-6">
            {rows.length ? <DealRows deals={rows} /> : <p className="py-6 text-sm text-[color:var(--muted)]">No deals match these filters.</p>}
          </div>
        </>
      )}
    </Container>
  );
}
