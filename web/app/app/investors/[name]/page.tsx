"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Stat, Table, Td, usd, words } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { get } from "../../../../lib/market";

type Profile = {
  name: string;
  type: string | null;
  hq: string | null;
  deal_count: number;
  roles: Record<string, number>;
  disclosed_usd?: number;
  sectors?: Record<string, number>;
  countries?: Record<string, number>;
  co_investors?: { name: string; deals: number }[];
  first_seen?: string | null;
  last_seen?: string | null;
  recent: { id: string; role: string; deal_type: string; target: string | null; amount_usd: number | null; announced: string | null; country: string | null; headline: string }[];
  type_inferred?: boolean;
  lead_count?: number;
  typical_round_usd?: number | null;
  activity_by_year?: Record<string, number>;
  rounds_by_stage?: Record<string, number>;
  portfolio?: { company: string; first_deal: string | null; role: string; deal_id: string; status: string; status_date: string | null }[];
  fund_lifecycle?: { fund: string | null; announced: string; amount_usd: number | null; years_since: number; phase: string; note: string } | null;
};

export default function InvestorPage({ params }: { params: { name: string } }) {
  const name = decodeURIComponent(params.name);
  const [p, setP] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Profile>(`/api/investors/${encodeURIComponent(name)}`)
      .then(setP)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the profile."));
  }, [name]);

  if (error) return <Container className="py-14"><ErrorNote message={error} /></Container>;
  if (!p) return <Container className="py-14"><Loading /></Container>;
  const top = (o?: Record<string, number>) => Object.entries(o ?? {}).map(([k, v]) => `${words(k)} (${v})`).join(", ") || "n/a";
  return (
    <Container className="max-w-5xl py-10 lg:py-14">
      <Link href="/app/investors" className="text-[0.8125rem] text-[color:var(--muted)] hover:text-[color:var(--text)]">
        ← All investors
      </Link>
      <div className="mt-4">
        <PageHeader eyebrow={(words(p.type) || "Party") + (p.type_inferred ? " (inferred)" : "")} title={p.name}>
          {p.hq ? `Headquarters: ${p.hq}. ` : ""}
          {p.first_seen ? `Active in the database from ${p.first_seen} to ${p.last_seen}.` : "No recorded deals yet."}
        </PageHeader>
        <Link href={`/app/watchlists?follow=${encodeURIComponent(p.name)}`} className="btn btn-ghost mt-4 inline-flex h-9 px-4 text-sm">
          Follow this investor
        </Link>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Deals" value={p.deal_count} note={Object.entries(p.roles).map(([k, v]) => `${k} ${v}`).join(", ")} />
        <Stat label="Rounds led" value={p.lead_count ?? 0} note="Where the article names the lead investor" />
        <Stat label="Typical round" value={usd(p.typical_round_usd ?? undefined)} note="Median size of rounds joined, not its own cheque" />
        <Stat label="Value of deals involved" value={usd(p.disclosed_usd)} />
        <Stat label="Top co-investors" value={p.co_investors?.[0]?.name ?? "n/a"} note={p.co_investors?.slice(1, 4).map((c) => c.name).join(", ")} />
        <Stat label="Activity by year" value={Object.entries(p.activity_by_year ?? {}).slice(-1).map(([y, n]) => `${n} in ${y}`)[0] ?? "n/a"}
          note={Object.entries(p.activity_by_year ?? {}).slice(-5).map(([y, n]) => `${y}: ${n}`).join(" · ")} />
      </div>
      {p.fund_lifecycle && (
        <div className="panel mt-6 p-5">
          <h2 className="eyebrow">Latest fund</h2>
          <p className="mt-2 text-[0.9375rem]">
            {p.fund_lifecycle.fund ?? "Fund"}, announced {p.fund_lifecycle.announced}
            {p.fund_lifecycle.amount_usd ? `, ${usd(p.fund_lifecycle.amount_usd)}` : ""}.{" "}
            Likely <strong>{p.fund_lifecycle.phase}</strong> ({p.fund_lifecycle.years_since} years since the announcement).
          </p>
          <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">{p.fund_lifecycle.note}</p>
        </div>
      )}
      <p className="mt-6 text-[0.875rem] text-[color:var(--muted)]">Sectors: {top(p.sectors)}</p>
      <p className="mt-1 text-[0.875rem] text-[color:var(--muted)]">Countries: {top(p.countries)}</p>
      {p.rounds_by_stage && Object.keys(p.rounds_by_stage).length > 0 && (
        <p className="mt-1 text-[0.875rem] text-[color:var(--muted)]">Rounds by stage: {top(p.rounds_by_stage)}</p>
      )}
      {p.portfolio && p.portfolio.length > 0 && (
        <>
          <h2 className="eyebrow mt-10">Portfolio and what happened since</h2>
          <div className="mt-4">
            <Table head={["Company", "First deal", "Role", "Since then"]}>
              {p.portfolio.map((c) => (
                <tr key={c.deal_id}>
                  <Td><Link href={`/app/deals/${c.deal_id}`} className="hover:underline">{c.company}</Link></Td>
                  <Td className="kbd whitespace-nowrap text-[0.75rem] text-[color:var(--muted)]">{c.first_deal ?? ""}</Td>
                  <Td>{c.role}</Td>
                  <Td className="text-[color:var(--muted)]">{c.status}{c.status_date ? ` (${c.status_date})` : ""}</Td>
                </tr>
              ))}
            </Table>
          </div>
        </>
      )}
      <h2 className="eyebrow mt-10">Recent transactions</h2>
      <div className="mt-4">
        <Table head={["Date", "Role", "Type", "Counterparty", "Amount", "Country"]}>
          {p.recent.map((r) => (
            <tr key={r.id + r.role}>
              <Td className="kbd whitespace-nowrap text-[0.75rem] text-[color:var(--muted)]">{r.announced ?? ""}</Td>
              <Td>{r.role}</Td>
              <Td>{words(r.deal_type)}</Td>
              <Td>
                <Link href={`/app/deals/${r.id}`} className="hover:underline">
                  {r.target ?? "Deal"}
                </Link>
                <span className="block text-[0.75rem] text-[color:var(--dim)]">{r.headline}</span>
              </Td>
              <Td className="whitespace-nowrap">{usd(r.amount_usd)}</Td>
              <Td>{r.country ?? "Pan-African"}</Td>
            </tr>
          ))}
        </Table>
      </div>
    </Container>
  );
}
