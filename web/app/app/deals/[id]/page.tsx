"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../../components/primitives";
import { DealRows, ErrorNote, Loading, PageHeader, Stat, usd, words } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { VerificationPanel } from "../../../../components/app/Verification";
import { get, type Comparables, type Deal, type FieldAccuracy, type Verification } from "../../../../lib/market";

type DealResponse = {
  deal: Deal;
  verification?: Verification;
  field_accuracy?: FieldAccuracy;
  parties: { name: string; role: string }[];
  comparables: Comparables;
};

export default function DealPage({ params }: { params: { id: string } }) {
  const [data, setData] = useState<DealResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<DealResponse>(`/api/deals/${encodeURIComponent(params.id)}`)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the deal."));
  }, [params.id]);

  if (error) return <Container className="py-14"><ErrorNote message={error} /></Container>;
  if (!data) return <Container className="py-14"><Loading /></Container>;
  const { deal: d, parties, comparables, verification, field_accuracy } = data;
  const valuation = d.reported_valuation_usd ?? d.implied_valuation_usd;
  return (
    <Container className="max-w-5xl py-10 lg:py-14">
      <Link href="/app/deals" className="text-[0.8125rem] text-[color:var(--muted)] hover:text-[color:var(--text)]">
        ← All deals
      </Link>
      <div className="mt-4">
        <PageHeader eyebrow={`${words(d.deal_type)} · ${words(d.stage)}`} title={d.target ?? d.headline}>
          {d.headline}
        </PageHeader>
      </div>
      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label="Amount" value={usd(d.amount_usd)} note={d.amount && d.currency !== "USD" ? `${d.amount.toLocaleString()} ${d.currency}` : undefined} />
        <Stat label="Valuation" value={usd(valuation)} note={d.reported_valuation_usd ? "Reported" : d.implied_valuation_usd ? "Implied by stake and price" : undefined} />
        <Stat label="Stake" value={d.stake_pct ? `${d.stake_pct}%` : "n/a"} note={d.round ? words(d.round) : undefined} />
        <Stat label="First reported" value={d.announced ?? "n/a"} note={`${d.country ?? "Pan-African"} · ${words(d.sector) || "Sector n/a"}`} />
      </div>

      <h2 className="eyebrow mt-10">Parties</h2>
      <ul className="mt-3 flex flex-wrap gap-2">
        {parties.map((p) => (
          <li key={p.name + p.role}>
            <Link
              href={`/app/investors/${encodeURIComponent(p.name)}`}
              className="inline-flex rounded-full border hairline px-3 py-1.5 text-[0.8125rem] hover:text-verified"
            >
              {p.name} <span className="ml-2 text-[color:var(--dim)]">{p.role}</span>
            </Link>
          </li>
        ))}
        {d.target && (
          <li>
            <Link
              href={`/app/companies?name=${encodeURIComponent(d.target)}${d.country ? `&country=${d.country}` : ""}`}
              className="inline-flex rounded-full border hairline px-3 py-1.5 text-[0.8125rem] hover:text-verified"
            >
              {d.target} <span className="ml-2 text-[color:var(--dim)]">target profile</span>
            </Link>
          </li>
        )}
      </ul>

      {verification ? (
        <VerificationPanel v={verification} accuracy={field_accuracy ?? null} />
      ) : (
        <>
          <h2 className="eyebrow mt-10">Sources ({d.sources.length})</h2>
          <ul className="mt-3 space-y-1.5 text-[0.8125rem]">
            {d.sources.map((s, i) => (
              <li key={i}>
                <a href={s.url} target="_blank" rel="noreferrer" className="hover:underline">
                  {s.publisher || "Source"}
                </a>{" "}
                <span className="text-[color:var(--dim)]">{s.date}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <h2 className="eyebrow mt-10">Comparable deals</h2>
      <p className="mt-2 text-[0.8125rem] text-[color:var(--dim)]">{comparables.method}</p>
      {comparables.size_usd && (
        <p className="mt-2 text-[0.8125rem] text-[color:var(--muted)]">
          Size across {comparables.size_usd.n} comparables: median {usd(comparables.size_usd.median)}, interquartile{" "}
          {usd(comparables.size_usd.p25)} to {usd(comparables.size_usd.p75)}.
        </p>
      )}
      <div className="mt-4">
        {comparables.deals.length ? <DealRows deals={comparables.deals} showWhy /> : <p className="text-sm text-[color:var(--muted)]">No comparable deals yet.</p>}
      </div>
    </Container>
  );
}
