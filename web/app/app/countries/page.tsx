"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Container } from "../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Pill, Table, Td } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { get } from "../../../lib/market";

type Row = {
  iso2: string; name: string; region: string; currency: string; exchange: string | null; risk_score: number | null;
  risk_tier: string | null; risk_coverage: number; coverage_tier: string; deals: number; events: number;
  deal_value_usd?: number; first_year?: number | null; deals_last_12m?: number;
  source_quality?: { source_links_checked: number; official_host_matched_links: number; registered_country_hosts: number; registry_status: string };
};

const REGIONS = ["Northern Africa", "Western Africa", "Middle Africa", "Eastern Africa", "Southern Africa"];

const compactUsd = (n?: number) => n ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 1, notation: "compact" }).format(n) : "None";

function scoreLabel(score: number | null) {
  return score == null ? "Not available" : `${score}/100`;
}

export default function CountriesPage() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<"risk" | "name" | "deals" | "events" | "coverage" | "value" | "recent">("deals");
  const [region, setRegion] = useState("");
  const [query, setQuery] = useState("");
  const [riskTier, setRiskTier] = useState("");
  const [coverageTier, setCoverageTier] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    get<{ countries: Row[]; data_as_of: string }>("/api/countries")
      .then((r) => {
        setRows(r.countries);
        setAsOf(r.data_as_of);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load countries."));
  }, []);

  const shown = useMemo(() => {
    const q = query.trim().toLocaleLowerCase();
    const filtered = (rows ?? []).filter((c) =>
      (!q || [c.name, c.iso2, c.region, c.currency, c.exchange ?? ""].some((v) => v.toLocaleLowerCase().includes(q))) &&
      (!region || c.region === region) &&
      (!riskTier || (c.risk_tier ?? "").toLowerCase() === riskTier) &&
      (!coverageTier || c.coverage_tier.toLowerCase() === coverageTier) &&
      (!activeOnly || c.deals > 0 || c.events > 0),
    );
    return [...filtered].sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name);
      if (sort === "deals") return b.deals - a.deals || a.name.localeCompare(b.name);
      if (sort === "events") return b.events - a.events || a.name.localeCompare(b.name);
      if (sort === "value") return (b.deal_value_usd ?? 0) - (a.deal_value_usd ?? 0) || a.name.localeCompare(b.name);
      if (sort === "recent") return (b.deals_last_12m ?? 0) - (a.deals_last_12m ?? 0) || a.name.localeCompare(b.name);
      if (sort === "coverage") return b.risk_coverage - a.risk_coverage || a.name.localeCompare(b.name);
      if (a.risk_score == null) return b.risk_score == null ? a.name.localeCompare(b.name) : 1;
      if (b.risk_score == null) return -1;
      return b.risk_score - a.risk_score || a.name.localeCompare(b.name);
    });
  }, [rows, sort, region, query, riskTier, coverageTier, activeOnly]);

  const selectedRows = useMemo(() => (rows ?? []).filter((c) => selected.includes(c.iso2)), [rows, selected]);
  const activeFilters = Number(Boolean(query.trim())) + Number(Boolean(region)) + Number(Boolean(riskTier)) +
    Number(Boolean(coverageTier)) + Number(activeOnly);

  function toggleCompare(code: string) {
    setSelected((current) => current.includes(code)
      ? current.filter((item) => item !== code)
      : current.length < 4 ? [...current, code] : current);
  }

  function clearFilters() {
    setQuery("");
    setRegion("");
    setRiskTier("");
    setCoverageTier("");
    setActiveOnly(false);
  }

  return (
    <Container className="py-10 lg:py-14">
      <PageHeader eyebrow="Market intelligence · 54 markets" title="Explore African markets with evidence, not guesswork.">
        Compare country risk, deal and event activity, currencies and data coverage. Risk is a transparent 0–100 analytical score built from available governance and macroeconomic indicators, not a prediction of returns. {asOf ? `Dataset retrieved ${asOf}.` : ""}
      </PageHeader>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="panel p-4">
          <p className="text-xs text-[color:var(--dim)]">Markets in directory</p>
          <p className="mt-1 text-2xl font-medium">{rows?.length ?? "—"}</p>
          <p className="mt-1 text-xs text-[color:var(--muted)]">Country profiles available</p>
        </div>
        <div className="panel p-4">
          <p className="text-xs text-[color:var(--dim)]">Markets with recorded activity</p>
          <p className="mt-1 text-2xl font-medium">{rows ? rows.filter((c) => c.deals > 0 || c.events > 0).length : "—"}</p>
          <p className="mt-1 text-xs text-[color:var(--muted)]">At least one deal or corporate event in the dataset</p>
        </div>
        <div className="panel p-4">
          <p className="text-xs text-[color:var(--dim)]">Selected for comparison</p>
          <p className="mt-1 text-2xl font-medium">{selected.length} / 4</p>
          <p className="mt-1 text-xs text-[color:var(--muted)]">Choose up to four markets below</p>
        </div>
      </div>

      <section className="panel mt-6 p-4 sm:p-5" aria-label="Country filters">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="block">
            <span className="mb-1.5 block text-xs text-[color:var(--muted)]">Search countries</span>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Country, code, currency or exchange" className="field w-full" />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs text-[color:var(--muted)]">Region</span>
            <select value={region} onChange={(e) => setRegion(e.target.value)} className="field w-full">
              <option value="">All regions</option>
              {REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs text-[color:var(--muted)]">Risk tier</span>
            <select value={riskTier} onChange={(e) => setRiskTier(e.target.value)} className="field w-full">
              <option value="">All risk tiers</option>
              {["low", "moderate", "elevated", "high", "severe"].map((r) => <option key={r} value={r}>{r[0].toUpperCase() + r.slice(1)}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs text-[color:var(--muted)]">Evidence coverage</span>
            <select value={coverageTier} onChange={(e) => setCoverageTier(e.target.value)} className="field w-full">
              <option value="">All coverage tiers</option>
              {["a", "b", "c"].map((r) => <option key={r} value={r}>Tier {r.toUpperCase()}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs text-[color:var(--muted)]">Sort markets</span>
            <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} className="field w-full">
              <option value="deals">Most recorded deals</option>
              <option value="value">Largest disclosed deal value</option>
              <option value="recent">Most deals in the last 12 months</option>
              <option value="events">Most corporate events</option>
              <option value="risk">Risk score (high to low)</option>
              <option value="coverage">Highest risk-data coverage</option>
              <option value="name">Country name (A–Z)</option>
            </select>
          </label>
          <div className="flex items-end justify-between gap-3">
            <label className="flex items-center gap-2 pb-2 text-sm text-[color:var(--muted)]">
              <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} />
              Recorded deal or event activity
            </label>
            <button type="button" onClick={clearFilters} className="btn btn-ghost shrink-0" disabled={activeFilters === 0}>Reset</button>
          </div>
        </div>
        <p className="mt-3 text-xs text-[color:var(--dim)]" aria-live="polite">
          Showing {shown.length} of {rows?.length ?? "—"} markets{activeFilters ? ` · ${activeFilters} active filter${activeFilters === 1 ? "" : "s"}` : ""}. A market with no recorded activity may reflect limited source coverage, not proof that no activity occurred.
        </p>
      </section>

      {error && <ErrorNote message={error} />}

      {selectedRows.length > 0 && (
        <section className="panel mt-5 p-4 sm:p-5" aria-label="Country comparison">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-medium">Market comparison</h2>
              <p className="mt-1 text-xs text-[color:var(--muted)]">Side-by-side descriptive indicators. Coverage differs by market, so counts are not automatically like-for-like.</p>
            </div>
            <button type="button" className="btn btn-ghost" onClick={() => setSelected([])}>Clear comparison</button>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[38rem] border-collapse text-left text-sm">
              <thead><tr className="border-b hairline"><th className="py-2 pr-4 font-normal text-[color:var(--dim)]">Indicator</th>{selectedRows.map((c) => <th key={c.iso2} className="py-2 pr-4 font-medium"><Link className="hover:underline" href={`/app/countries/${c.iso2}`}>{c.name}</Link></th>)}</tr></thead>
              <tbody>
                {[
                  ["Region", (c: Row) => c.region],
                  ["Risk score", (c: Row) => scoreLabel(c.risk_score)],
                  ["Risk tier", (c: Row) => c.risk_tier ?? "Not available"],
                  ["Risk-data coverage", (c: Row) => `${Math.round(c.risk_coverage * 100)}%`],
                  ["Evidence coverage tier", (c: Row) => c.coverage_tier],
                  ["Recorded deals", (c: Row) => c.deals.toLocaleString()],
                  ["Deals in the last 12 months", (c: Row) => (c.deals_last_12m ?? 0).toLocaleString()],
                  ["Disclosed deal value", (c: Row) => compactUsd(c.deal_value_usd)],
                  ["Record starts", (c: Row) => c.first_year ? String(c.first_year) : "No dated deals"],
                  ["Corporate events", (c: Row) => c.events.toLocaleString()],
                  ["Currency", (c: Row) => c.currency],
                  ["Exchange", (c: Row) => c.exchange ?? "Not listed"],
                ].map(([label, value]) => (
                  <tr key={label as string} className="border-b hairline">
                    <th className="py-2.5 pr-4 font-normal text-[color:var(--muted)]">{label as string}</th>
                    {selectedRows.map((c) => <td key={c.iso2} className="py-2.5 pr-4 align-top">{(value as (c: Row) => string)(c)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <div className="mt-6">
        {rows === null ? <Loading label="Loading country intelligence…" /> : shown.length === 0 ? (
          <div className="panel p-8 text-center">
            <h2 className="font-medium">No markets match these filters</h2>
            <p className="mt-2 text-sm text-[color:var(--muted)]">Try a different search or reset the filters.</p>
            <button type="button" className="btn btn-ghost mt-4" onClick={clearFilters}>Reset filters</button>
          </div>
        ) : (
          <Table head={["Compare", "Country", "Region", "Risk score", "Risk tier", "Risk-data coverage", "Evidence tier", "Official-source links", "Deals", "Last 12 mo", "Disclosed value", "Since", "Events", "Currency"]} minWidth="90rem">
            {shown.map((c) => (
              <tr key={c.iso2}>
                <Td>
                  <input
                    type="checkbox"
                    checked={selected.includes(c.iso2)}
                    disabled={!selected.includes(c.iso2) && selected.length >= 4}
                    onChange={() => toggleCompare(c.iso2)}
                    aria-label={`Compare ${c.name}`}
                    title={selected.length >= 4 && !selected.includes(c.iso2) ? "Compare up to four countries" : `Compare ${c.name}`}
                  />
                </Td>
                <Td>
                  <Link href={`/app/countries/${c.iso2}`} className="font-medium hover:underline">{c.name}</Link>
                  <span className="kbd ml-2 text-xs text-[color:var(--dim)]">{c.iso2}</span>
                  {c.exchange && <span className="mt-1 block text-xs text-[color:var(--dim)]">{c.exchange}</span>}
                </Td>
                <Td className="text-[color:var(--muted)]">{c.region}</Td>
                <Td className="kbd">{c.risk_score ?? "n/a"}</Td>
                <Td><Pill value={c.risk_tier} /></Td>
                <Td>
                  <div className="min-w-20">
                    <div className="kbd">{Math.round(c.risk_coverage * 100)}%</div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[color:var(--line)]">
                      <div className="h-full rounded-full bg-[color:var(--verified)]" style={{ width: `${Math.max(0, Math.min(100, c.risk_coverage * 100))}%` }} />
                    </div>
                  </div>
                </Td>
                <Td><Pill value={c.coverage_tier} title="Coverage tier reflects available market data and verification coverage, not country quality." /></Td>
                <Td>
                  <span className="kbd">{c.source_quality?.official_host_matched_links ?? 0} / {c.source_quality?.source_links_checked ?? 0}</span>
                  <span className="mt-1 block text-xs text-[color:var(--dim)]">{c.source_quality?.registry_status === "needs_host_review" ? "Host registry needs review" : "Official host matches"}</span>
                </Td>
                <Td className="kbd">{c.deals.toLocaleString()}</Td>
                <Td className="kbd">{(c.deals_last_12m ?? 0).toLocaleString()}</Td>
                <Td className="kbd">{compactUsd(c.deal_value_usd)}</Td>
                <Td className="kbd text-[color:var(--muted)]">{c.first_year ?? "—"}</Td>
                <Td className="kbd">{c.events.toLocaleString()}</Td>
                <Td className="kbd">{c.currency}</Td>
              </tr>
            ))}
          </Table>
        )}
      </div>
      <p className="mt-4 text-xs leading-relaxed text-[color:var(--dim)]">
        Interpretation note: risk-data coverage is the share of expected inputs available to the risk model; it is not the probability that the risk score is correct. Evidence coverage tier describes the breadth of available market datasets. Review the country page for component formulas, indicator years, currency methodology and source limitations before comparing markets.
      </p>
    </Container>
  );
}
