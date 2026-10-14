"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Pill, Stat, Table, Td, usd } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { get, type CoverageRow } from "../../../lib/market";

type Matrix = {
  countries: CoverageRow[];
  summary: { countries: number; by_tier: Record<string, number>; national_news_editions: number; full_country_risk_coverage: number; with_deals: number; with_events: number };
  tiers: Record<string, string>;
};

export default function CoveragePage() {
  const [m, setM] = useState<Matrix | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    get<Matrix>("/api/coverage").then(setM).catch((err) => setError(err instanceof ApiError ? err.message : "Could not load coverage."));
  }, []);
  return (
    <Container className="py-10 lg:py-14">
      <PageHeader eyebrow="Coverage and verification" title="What the product reads in each country, and how far it can be verified.">
        Every country gets news search in its own languages, deal and event extraction, regulator detection and country
        risk. Listing data and official filings exist only where exchanges publish them in machine-readable form; the tier
        says how a signal there can be confirmed.
      </PageHeader>
      {error && <ErrorNote message={error} />}
      {!m ? (
        <Loading />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            <Stat label="Countries covered" value={m.summary.countries} note={`${m.summary.national_news_editions} with a national news edition`} />
            <Stat label="Tier A / B / C" value={`${m.summary.by_tier.A ?? 0} / ${m.summary.by_tier.B ?? 0} / ${m.summary.by_tier.C ?? 0}`} />
            <Stat label="Full risk-data coverage" value={m.summary.full_country_risk_coverage} note="All seven components available" />
            <Stat label="Countries with deals" value={m.summary.with_deals} note={`${m.summary.with_events} with corporate events`} />
          </div>
          <dl className="mt-6 space-y-1 text-[0.8125rem] text-[color:var(--muted)]">
            {Object.entries(m.tiers).map(([t, d]) => (
              <div key={t} className="flex gap-2">
                <dt>
                  <Pill value={t} />
                </dt>
                <dd>{d}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-8">
            <Table head={["Country", "Tier", "Exchange", "Prices", "Statements", "Filings", "News", "Risk data", "Deals", "Events"]} minWidth="64rem">
              {m.countries.map((c) => (
                <tr key={c.iso2}>
                  <Td>
                    <Link href={`/app/countries/${c.iso2}`} className="hover:underline">
                      {c.country}
                    </Link>
                  </Td>
                  <Td>
                    <Pill value={c.tier} />
                  </Td>
                  <Td className="text-[color:var(--muted)]">{c.exchange ?? "None"}</Td>
                  <Td className="text-[color:var(--muted)]">{c.prices ?? "None"}</Td>
                  <Td className="text-[color:var(--muted)]">{c.statements ?? "None"}</Td>
                  <Td className="text-[color:var(--muted)]">{c.filings ?? "None"}</Td>
                  <Td className="text-[color:var(--muted)]">
                    {c.news.national_edition ? "National" : "Language"} ({c.news.languages.join(", ")})
                  </Td>
                  <Td className="kbd">{Math.round(c.country_risk.coverage * 100)}%</Td>
                  <Td>
                    {c.deals}
                    {c.deal_value_usd ? <span className="block text-[0.75rem] text-[color:var(--dim)]">{usd(c.deal_value_usd)}</span> : null}
                  </Td>
                  <Td>{c.events}</Td>
                </tr>
              ))}
            </Table>
          </div>
        </>
      )}
    </Container>
  );
}
