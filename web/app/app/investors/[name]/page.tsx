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
        <PageHeader eyebrow={words(p.type) || "Party"} title={p.name}>
          {p.hq ? `Headquarters: ${p.hq}. ` : ""}
          {p.first_seen ? `Active in the database from ${p.first_seen} to ${p.last_seen}.` : "No recorded deals yet."}
        </PageHeader>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Deals" value={p.deal_count} note={Object.entries(p.roles).map(([k, v]) => `${k} ${v}`).join(", ")} />
        <Stat label="Disclosed value" value={usd(p.disclosed_usd)} />
        <Stat label="Top co-investors" value={p.co_investors?.[0]?.name ?? "n/a"} note={p.co_investors?.slice(1, 4).map((c) => c.name).join(", ")} />
      </div>
      <p className="mt-6 text-[0.875rem] text-[color:var(--muted)]">Sectors: {top(p.sectors)}</p>
      <p className="mt-1 text-[0.875rem] text-[color:var(--muted)]">Countries: {top(p.countries)}</p>
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
