"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../../components/primitives";
import { DealRows, ErrorNote, Loading, PageHeader, Pill, Stat, Table, Td, num, words } from "../../../../components/app/ui";
import { ApiError } from "../../../../lib/api";
import { get, post, type CountryRisk, type CoverageRow, type CurrencyRisk, type Deal, type Event, type InvestorRow } from "../../../../lib/market";

type CountryResponse = {
  country: { iso2: string; name: string; region: string; languages: string[]; currency: string; exchange: string | null; central_bank: string; securities_regulator: string | null };
  risk: CountryRisk;
  currency: CurrencyRisk;
  coverage: CoverageRow;
  deals: Deal[];
  events: Event[];
  investors: InvestorRow[];
};

export default function CountryPage({ params }: { params: { code: string } }) {
  const [d, setD] = useState<CountryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<{ markdown: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<CountryResponse>(`/api/countries/${encodeURIComponent(params.code)}`)
      .then(setD)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the country."));
  }, [params.code]);

  async function makeReport() {
    setBusy(true);
    try {
      setReport(await post<{ markdown: string }>(`/api/reports/country/${encodeURIComponent(params.code)}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The report could not be generated.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !d) return <Container className="py-14"><ErrorNote message={error} /></Container>;
  if (!d) return <Container className="py-14"><Loading /></Container>;
  const { country: c, risk, currency: cur, coverage: cov } = d;
  return (
    <Container className="max-w-5xl py-10 lg:py-14">
      <Link href="/app/countries" className="text-[0.8125rem] text-[color:var(--muted)] hover:text-[color:var(--text)]">
        ← All countries
      </Link>
      <div className="mt-4">
        <PageHeader eyebrow={c.region} title={c.name}>
          Exchange: {c.exchange ?? "none"}. Central bank: {c.central_bank}. Securities regulator: {c.securities_regulator ?? "n/a"}.
          News languages: {c.languages.join(", ")}.
        </PageHeader>
      </div>
      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label="Country risk" value={risk.score ?? "n/a"} note={<Pill value={risk.tier} />} />
        <Stat label="Currency risk" value={cur.score ?? "n/a"} note={<Pill value={cur.tier} />} />
        <Stat label="Coverage tier" value={cov.tier} note={cov.prices ? "Listing data available" : "News, deals and risk"} />
        <Stat label="Deals recorded" value={cov.deals} note={`${cov.events} corporate events`} />
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <button type="button" onClick={makeReport} disabled={busy} className="btn btn-primary">
          {busy ? "Writing report..." : "Generate research report"}
        </button>
        <Link href={`/app/deals?country=${c.iso2}`} className="btn btn-ghost">
          Deals in {c.name}
        </Link>
      </div>
      {error && <ErrorNote message={error} />}
      {report && <pre className="panel mt-6 whitespace-pre-wrap p-5 font-sans text-[0.875rem] leading-relaxed">{report.markdown}</pre>}

      <h2 className="eyebrow mt-12">Country risk components</h2>
      <p className="mt-2 text-[0.8125rem] text-[color:var(--dim)]">{risk.method}</p>
      <div className="mt-4">
        <Table head={["Component", "Weight", "Risk (0 to 100)", "Formula"]}>
          {risk.components.map((x) => (
            <tr key={x.name}>
              <Td>{words(x.name)}</Td>
              <Td className="kbd">{x.weight}</Td>
              <Td className="kbd">{x.risk ?? "no data"}</Td>
              <Td className="text-[color:var(--muted)]">{x.formula}</Td>
            </tr>
          ))}
        </Table>
      </div>
      <h3 className="eyebrow mt-8">Indicators</h3>
      <div className="mt-3">
        <Table head={["Indicator", "Value", "Year"]} minWidth="28rem">
          {Object.entries(risk.indicators).map(([k, v]) => (
            <tr key={k}>
              <Td>{v.label}</Td>
              <Td className="kbd">{num(v.value, 2)}</Td>
              <Td className="kbd text-[color:var(--muted)]">{v.year}</Td>
            </tr>
          ))}
        </Table>
      </div>

      <h2 className="eyebrow mt-12">Currency: {cur.currency}</h2>
      <p className="mt-2 text-[0.875rem] text-[color:var(--muted)]">
        {words(cur.regime)}. {cur.regime_note}. Spot {cur.spot_per_usd ? num(cur.spot_per_usd, 2) : "n/a"} per USD
        {cur.official_per_usd ? `; official average ${num(cur.official_per_usd.value, 2)} (${cur.official_per_usd.year})` : ""}
        {cur.spot_vs_official_pct != null ? `; spot vs official ${cur.spot_vs_official_pct}%` : ""}. Depreciation last year{" "}
        {cur.last_year_depreciation_pct ?? "n/a"}%, five-year annualised {cur.five_year_annualised_depreciation_pct ?? "n/a"}%,
        volatility {cur.volatility_pct ?? "n/a"} points.
      </p>
      <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">{cur.method}</p>

      <h2 className="eyebrow mt-12">Data coverage and verification</h2>
      <ul className="mt-3 space-y-1 text-[0.875rem] text-[color:var(--muted)]">
        <li>Prices: {cov.prices ?? "none machine-readable"}</li>
        <li>Financial statements: {cov.statements ?? "none machine-readable"}</li>
        <li>Official filings: {cov.filings ?? "none machine-readable; confirmation relies on credible news"}</li>
        <li>
          News: Google News {cov.news.national_edition ? "national" : "language"} edition {cov.news.edition}, languages {cov.news.languages.join(", ")}
        </li>
        <li>Regulators matched: {cov.regulators.join(", ")}{cov.regulator_acronyms.length ? ` (${cov.regulator_acronyms.join(", ")})` : ""}</li>
      </ul>

      <h2 className="eyebrow mt-12">Recent deals</h2>
      <div className="mt-4">{d.deals.length ? <DealRows deals={d.deals} /> : <p className="text-sm text-[color:var(--muted)]">No deals recorded yet.</p>}</div>

      <h2 className="eyebrow mt-12">Corporate events</h2>
      <ul className="mt-3 space-y-2 text-[0.8125rem]">
        {d.events.length === 0 && <li className="text-[color:var(--muted)]">No events recorded yet.</li>}
        {d.events.map((e) => (
          <li key={e.id} className="border-b hairline pb-2">
            <span className="kbd mr-2 text-[0.75rem] text-[color:var(--dim)]">{e.day}</span>
            <Pill value={e.signal_type} />{" "}
            <a href={e.url} target="_blank" rel="noreferrer" className="hover:underline">
              {e.headline}
            </a>{" "}
            <span className="text-[color:var(--dim)]">{e.publisher}</span>
          </li>
        ))}
      </ul>

      {d.investors.length > 0 && (
        <>
          <h2 className="eyebrow mt-12">Most active parties</h2>
          <ul className="mt-3 flex flex-wrap gap-2">
            {d.investors.map((i) => (
              <li key={i.name}>
                <Link href={`/app/investors/${encodeURIComponent(i.name)}`} className="inline-flex rounded-full border hairline px-3 py-1.5 text-[0.8125rem] hover:text-verified">
                  {i.name} <span className="ml-2 text-[color:var(--dim)]">{i.deal_count}</span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </Container>
  );
}
