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
};

export default function CountriesPage() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<"risk" | "name" | "deals">("risk");
  const [region, setRegion] = useState("");

  useEffect(() => {
    get<{ countries: Row[]; data_as_of: string }>("/api/countries")
      .then((r) => {
        setRows(r.countries);
        setAsOf(r.data_as_of);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load countries."));
  }, []);

  const shown = useMemo(() => {
    const r = (rows ?? []).filter((c) => !region || c.region === region);
    return [...r].sort((a, b) =>
      sort === "name" ? a.name.localeCompare(b.name) : sort === "deals" ? b.deals - a.deals : (b.risk_score ?? 0) - (a.risk_score ?? 0),
    );
  }, [rows, sort, region]);

  return (
    <Container className="py-10 lg:py-14">
      <PageHeader eyebrow="Countries" title="All 54 African countries: risk, currency and coverage.">
        Country risk is a transparent 0 to 100 score from World Bank governance and macroeconomic indicators
        {asOf ? ` (retrieved ${asOf})` : ""}; every component and formula is shown on the country page. The coverage tier
        states how far signals can be verified in that market.
      </PageHeader>
      <div className="flex flex-wrap gap-3">
        <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} className="field w-auto" aria-label="Sort">
          <option value="risk">Sort by risk</option>
          <option value="name">Sort by name</option>
          <option value="deals">Sort by deal count</option>
        </select>
        <select value={region} onChange={(e) => setRegion(e.target.value)} className="field w-auto" aria-label="Region">
          <option value="">All regions</option>
          {["Northern Africa", "Western Africa", "Middle Africa", "Eastern Africa", "Southern Africa"].map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
      </div>
      {error && <ErrorNote message={error} />}
      <div className="mt-6">
        {rows === null ? (
          <Loading />
        ) : (
          <Table head={["Country", "Region", "Risk score", "Risk tier", "Data coverage", "Coverage tier", "Deals", "Events", "Currency"]}>
            {shown.map((c) => (
              <tr key={c.iso2}>
                <Td>
                  <Link href={`/app/countries/${c.iso2}`} className="hover:underline">
                    {c.name}
                  </Link>
                  <span className="kbd ml-2 text-[0.75rem] text-[color:var(--dim)]">{c.iso2}</span>
                </Td>
                <Td className="text-[color:var(--muted)]">{c.region}</Td>
                <Td className="kbd">{c.risk_score ?? "n/a"}</Td>
                <Td>
                  <Pill value={c.risk_tier} />
                </Td>
                <Td className="text-[color:var(--muted)]">{Math.round(c.risk_coverage * 100)}%</Td>
                <Td>
                  <Pill value={c.coverage_tier} />
                </Td>
                <Td>{c.deals}</Td>
                <Td>{c.events}</Td>
                <Td className="kbd">{c.currency}</Td>
              </tr>
            ))}
          </Table>
        )}
      </div>
    </Container>
  );
}
