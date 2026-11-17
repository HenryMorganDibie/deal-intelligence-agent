"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Container } from "../../../components/primitives";
import { DealRows, ErrorNote, Field, Loading, OpportunityRows, PageHeader, Pagination, Stat, usd, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { trackProductAction } from "../../../lib/tracking";
import { DEAL_TYPES, SECTORS, get, type Deal } from "../../../lib/market";

type Filters = { q: string; country: string; type: string; sector: string; investor: string; since: string; until: string };
const EMPTY: Filters = { q: "", country: "", type: "", sector: "", investor: "", since: "", until: "" };

export default function DealsPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [view, setView] = useState<"deals" | "opportunities">("deals");
  const [rows, setRows] = useState<Deal[] | null>(null);
  const [totalMatching, setTotalMatching] = useState(0);
  const [totalInDatabase, setTotalInDatabase] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(50);
  const [error, setError] = useState<string | null>(null);

  async function load(f: Filters, nextOffset = 0, nextLimit = limit, nextView: "deals" | "opportunities" = view) {
    setOffset(nextOffset);
    setLimit(nextLimit);
    setRows(null);
    setError(null);
    try {
      const endpoint = nextView === "deals" ? "/api/deals" : "/api/opportunities";
      const params = nextView === "deals" ? { ...f, limit: nextLimit, offset: nextOffset } :
        { q: f.q, country: f.country, sector: f.sector, since: f.since, until: f.until, limit: nextLimit, offset: nextOffset };
      const r = await get<{ total_in_database: number; total_matching: number; deals?: Deal[]; opportunities?: Deal[] }>(endpoint, params);
      const loaded = nextView === "deals" ? (r.deals ?? []) : (r.opportunities ?? []);
      setRows(loaded);
      if (nextView === "deals") loaded.forEach((deal, index) => {
        trackProductAction("deal_impression", deal.id, {
          result_position: index + 1,
          has_query: Boolean(f.q.trim()),
          country: f.country.trim().toUpperCase() || undefined,
          deal_type: f.type || undefined,
          sector: f.sector || undefined,
        });
      });
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
    trackProductAction("deal_search_submitted", undefined, {
      has_query: Boolean(filters.q.trim()),
      country: filters.country.trim().toUpperCase() || undefined,
      deal_type: filters.type || undefined,
      sector: filters.sector || undefined,
      has_investor_filter: Boolean(filters.investor.trim()),
      has_date_filter: Boolean(filters.since || filters.until),
    });
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
      <PageHeader eyebrow={view === "deals" ? "Deals" : "Investment opportunities"} title={view === "deals" ? "Private equity, venture, debt and M&A across Africa." : "Proposed investments seeking capital or strategic partners."}>
        {view === "deals" ? (<>
        Funding rounds, debt, acquisitions, exits and fund closes across Africa since 2010, each linked to its sources.
        Amounts are as reported, in US dollars.
        </>) : (<>
          Companies, governments and projects looking for investors or partners. These are proposals, not completed
          deals, so they&apos;re kept out of deal totals.
        </>)}
      </PageHeader>

      <div className="mb-6 flex flex-wrap gap-2" role="tablist" aria-label="Market records">
        <button type="button" role="tab" aria-selected={view === "deals"} className={view === "deals" ? "btn btn-primary" : "btn btn-ghost"} onClick={() => { setView("deals"); load(filters, 0, limit, "deals"); }}>Deals</button>
        <button type="button" role="tab" aria-selected={view === "opportunities"} className={view === "opportunities" ? "btn btn-primary" : "btn btn-ghost"} onClick={() => { setView("opportunities"); load(filters, 0, limit, "opportunities"); }}>Investment opportunities</button>
      </div>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
        <div className="sm:col-span-2">
          <Field label="Search">
            <input value={filters.q} onChange={set("q")} placeholder="Company, investor or keyword" className="field" />
          </Field>
        </div>
        <Field label="Country (ISO)">
          <input value={filters.country} onChange={set("country")} maxLength={3} placeholder="NG" className="field kbd uppercase" />
        </Field>
        {view === "deals" && <Field label="Type">
          <select value={filters.type} onChange={set("type")} className="field">
            <option value="">All types</option>
            {DEAL_TYPES.map((t) => (
              <option key={t} value={t}>
                {words(t)}
              </option>
            ))}
          </select>
        </Field>}
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
        <Field label="From">
          <input type="date" value={filters.since} onChange={set("since")} min="2010-01-01" className="field" />
        </Field>
        <Field label="To">
          <input type="date" value={filters.until} onChange={set("until")} min="2010-01-01" className="field" />
        </Field>
        <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-7">
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
            <Stat label={view === "deals" ? "Matching deals" : "Matching opportunities"} value={totalMatching.toLocaleString()} note={`${totalInDatabase.toLocaleString()} total in database`} />
            {view === "deals" ? <Stat label="Disclosed value on this page" value={usd(disclosed.reduce((a, d) => a + (d.amount_usd ?? 0), 0))} note={`${disclosed.length} with amounts`} /> : null}
            {view === "deals" && <Stat label="Median size on this page" value={usd(medianSize)} />}
          </div>
          <div className="mt-6">
            {rows.length ? <>{view === "deals" ? <DealRows deals={rows} /> :
              <OpportunityRows items={rows} />}
              <Pagination total={totalMatching} offset={offset} limit={limit} onPageChange={(next) => load(filters, next, limit)} onPageSizeChange={(next) => load(filters, 0, next)} /></> : <p className="py-6 text-sm text-[color:var(--muted)]">No {view === "deals" ? "deals" : "investment opportunities"} match these filters.</p>}
          </div>
        </>
      )}
    </Container>
  );
}
