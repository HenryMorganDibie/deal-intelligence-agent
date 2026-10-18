"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Container } from "../../../../components/primitives";
import { DealRows, ErrorNote, Loading, PageHeader, Pagination, Pill, Stat, Table, Td, num, words } from "../../../../components/app/ui";
import { ResultFeedback } from "../../../../components/app/ResultFeedback";
import { ApiError } from "../../../../lib/api";
import { get, post, type CountryRisk, type CoverageRow, type CurrencyRisk, type Deal, type Event, type EvidenceItem, type InvestorRow } from "../../../../lib/market";

type CountryResponse = {
  country: { iso2: string; name: string; region: string; languages: string[]; currency: string; exchange: string | null; central_bank: string; securities_regulator: string | null };
  risk: CountryRisk;
  currency: CurrencyRisk;
  coverage: CoverageRow;
  deals: Deal[];
  deals_total: number;
  events: Event[];
  events_total: number;
  investors: InvestorRow[];
};

function ReportText({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|https?:\/\/[^\s)]+)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text))) {
    parts.push(text.slice(last, match.index));
    if (match[0].startsWith("**")) {
      parts.push(<strong key={match.index}>{match[0].slice(2, -2)}</strong>);
    } else {
      const trimmed = match[0].replace(/[.,;:!?]+$/, "");
      const trailing = match[0].slice(trimmed.length);
      parts.push(<a key={match.index} href={trimmed} target="_blank" rel="noreferrer noopener" className="text-verified hover:underline">{trimmed}</a>);
      parts.push(trailing);
    }
    last = match.index + match[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

function ResearchReport({ markdown }: { markdown: string }) {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  const flushBullets = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={`list-${blocks.length}`} className="list-disc space-y-1 pl-5 text-[0.875rem] leading-relaxed text-[color:var(--muted)]">
          {bullets.map((line, i) => <li key={`${i}-${line}`}><ReportText text={line} /></li>)}
        </ul>,
      );
      bullets = [];
    }
  };

  for (const [i, line] of markdown.split(/\r?\n/).entries()) {
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      flushBullets();
      const className = heading[1].length === 1 ? "h3 text-xl" : "eyebrow";
      blocks.push(
        heading[1].length === 1
          ? <h2 key={`heading-${i}`} className={className}><ReportText text={heading[2]} /></h2>
          : <h3 key={`heading-${i}`} className={className}><ReportText text={heading[2]} /></h3>,
      );
    } else if (/^\s*-\s+/.test(line)) {
      bullets.push(line.replace(/^\s*-\s+/, ""));
    } else if (line.trim()) {
      flushBullets();
      blocks.push(<p key={`paragraph-${i}`} className="text-[0.875rem] leading-relaxed"><ReportText text={line} /></p>);
    } else {
      flushBullets();
    }
  }
  flushBullets();
  return <article className="panel mt-6 space-y-3 p-5">{blocks}</article>;
}

export default function CountryPage({ params }: { params: { code: string } }) {
  const [d, setD] = useState<CountryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<{ markdown: string; result_id: string; evidence: EvidenceItem[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [dealOffset, setDealOffset] = useState(0);
  const [dealLimit, setDealLimit] = useState(25);
  const [eventOffset, setEventOffset] = useState(0);
  const [eventLimit, setEventLimit] = useState(25);
  const [marketDeals, setMarketDeals] = useState<Deal[]>([]);
  const [marketTotals, setMarketTotals] = useState({ deals: 0, events: 0 });
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
  const [riskHistory, setRiskHistory] = useState<{ year: number; score: number | null; tier: string | null; coverage: number; input_years: Record<string, number>; indicator_count: number }[]>([]);
  const [historyMeta, setHistoryMeta] = useState<{ source: string; source_url: string; retrieved: string | null; method: string; archived_snapshots: { snapshot_date: string; score: number | null; tier: string | null; data_as_of: string | null }[]; snapshot_note: string } | null>(null);

  useEffect(() => {
    get<CountryResponse>(`/api/countries/${encodeURIComponent(params.code)}`)
      .then(setD)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the country."));
  }, [params.code]);

  useEffect(() => {
    let cancelled = false;
    get<{ rows: typeof riskHistory; source: string; source_url: string; retrieved: string | null; method: string; archived_snapshots: { snapshot_date: string; score: number | null; tier: string | null; data_as_of: string | null }[]; snapshot_note: string }>(`/api/countries/${encodeURIComponent(params.code)}/history`)
      .then((result) => {
        if (cancelled) return;
        setRiskHistory(result.rows);
        setHistoryMeta({ source: result.source, source_url: result.source_url, retrieved: result.retrieved, method: result.method, archived_snapshots: result.archived_snapshots, snapshot_note: result.snapshot_note });
      })
      .catch(() => { if (!cancelled) setHistoryMeta(null); });
    setAnalyticsLoading(true);
    Promise.all([
      get<{ deals: Deal[]; total_matching: number }>("/api/deals", { country: params.code.toUpperCase(), limit: 100, offset: 0 }),
      get<{ events: Event[]; count: number }>("/api/events", { country: params.code.toUpperCase(), limit: 500, offset: 0 }),
    ]).then(([dealResult, eventResult]) => {
      if (cancelled) return;
      setMarketDeals(dealResult.deals);
      setMarketTotals({ deals: dealResult.total_matching, events: eventResult.count });
    }).catch(() => {
      // The country page remains usable if the optional aggregate requests fail.
    }).finally(() => {
      if (!cancelled) setAnalyticsLoading(false);
    });
    return () => { cancelled = true; };
  }, [params.code]);

  const sectorMix = useMemo(() => {
    const counts = new Map<string, number>();
    for (const deal of marketDeals) {
      const label = deal.sector?.trim() || "Unclassified";
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  }, [marketDeals]);

  const dealTypeMix = useMemo(() => {
    const counts = new Map<string, number>();
    for (const deal of marketDeals) {
      const label = deal.deal_type?.trim() || "Unclassified";
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  }, [marketDeals]);

  const monthlyDealFlow = useMemo(() => {
    const now = new Date();
    const months = Array.from({ length: 12 }, (_, i) => {
      const date = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - (11 - i), 1));
      return { key: date.toISOString().slice(0, 7), label: date.toLocaleDateString("en", { month: "short", timeZone: "UTC" }), count: 0 };
    });
    const byMonth = new Map(months.map((month) => [month.key, month] as const));
    for (const deal of marketDeals) {
      if (!deal.announced) continue;
      const month = byMonth.get(deal.announced.slice(0, 7));
      if (month) month.count += 1;
    }
    return months;
  }, [marketDeals]);

  const maxMonthlyDeals = Math.max(1, ...monthlyDealFlow.map((month) => month.count));
  const maxSectorCount = Math.max(1, ...sectorMix.map(([, count]) => count));

  async function loadDeals(offset: number, limit: number) {
    setDealOffset(offset);
    setDealLimit(limit);
    try {
      const result = await get<{ deals: Deal[]; total_matching: number }>(`/api/deals`, {
        country: params.code.toUpperCase(), limit, offset,
      });
      setD((current) => current ? { ...current, deals: result.deals, deals_total: result.total_matching } : current);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load country deals.");
    }
  }

  async function loadEvents(offset: number, limit: number) {
    setEventOffset(offset);
    setEventLimit(limit);
    try {
      const result = await get<{ events: Event[]; count: number }>(`/api/events`, {
        country: params.code.toUpperCase(), limit, offset,
      });
      setD((current) => current ? { ...current, events: result.events, events_total: result.count } : current);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load country events.");
    }
  }

  async function makeReport() {
    setBusy(true);
    setError(null);
    try {
      setReport(await post<{ markdown: string; result_id: string; evidence: EvidenceItem[] }>(`/api/reports/country/${encodeURIComponent(params.code)}`));
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
      {report && (
        <>
          <p className="mt-3 text-[0.8125rem] text-[color:var(--dim)]">
            Report evidence: {report.evidence.length} items. Dates shown in the report are source dates, not refresh timestamps.
          </p>
          <ResearchReport markdown={report.markdown} />
          <ResultFeedback resultType="country_report" resultId={report.result_id} />
        </>
      )}


      <h2 className="eyebrow mt-12">Market activity overview</h2>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[color:var(--muted)]">
        This view summarizes the country’s currently recorded deal and event dataset. Deal and event totals count available records, not every transaction or announcement in the real economy. The charts use up to 100 retrieved deal records; if more records exist, the distributions may not cover the full dataset. Coverage and disclosure vary by market.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Deals in dataset" value={analyticsLoading ? "Loading…" : marketTotals.deals.toLocaleString()} note="Matching records returned by the API" />
        <Stat label="Corporate events" value={analyticsLoading ? "Loading…" : marketTotals.events.toLocaleString()} note="Matching event records" />
        <Stat label="Multi-source corroborated" value={analyticsLoading ? "Loading…" : marketDeals.filter((deal) => deal.verification === "corroborated").length.toLocaleString()} note="Corroborated records among the retrieved deals" />
        <Stat label="Deals with disclosed value" value={analyticsLoading ? "Loading…" : marketDeals.filter((deal) => deal.amount_usd != null && deal.amount_usd > 0).length.toLocaleString()} note="Among retrieved deal records, not all market transactions" />
      </div>
      {!analyticsLoading && marketDeals.length > 0 && (
        <p className="mt-2 text-xs text-[color:var(--dim)]">
          Of the {marketDeals.length.toLocaleString()} retrieved deal records, {(marketDeals.filter((deal) => deal.verification === "single source").length).toLocaleString()} are currently labelled single-source. Multi-source corroboration means multiple independent stories were detected, not necessarily official filing confirmation.
        </p>
      )}

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <section className="panel p-4 sm:p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="font-medium">Recorded deal flow</h3>
            <span className="text-xs text-[color:var(--dim)]">Last 12 months by announcement date</span>
          </div>
          {analyticsLoading ? <Loading label="Loading deal activity…" /> : marketDeals.length === 0 ? (
            <p className="mt-4 text-sm text-[color:var(--muted)]">No deal records were returned for this market. Check coverage before concluding that no deals occurred.</p>
          ) : (
            <div className="mt-4">
              <div className="flex h-36 items-end gap-1.5 border-b hairline pb-1">
                {monthlyDealFlow.map((month) => (
                  <div key={month.key} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1" title={`${month.key}: ${month.count} recorded deals`}>
                    <span className="text-[10px] text-[color:var(--dim)]">{month.count || ""}</span>
                    <div className="w-full max-w-7 rounded-t bg-verified/80" style={{ height: `${Math.max(month.count ? 5 : 0, (month.count / maxMonthlyDeals) * 78)}px` }} />
                  </div>
                ))}
              </div>
              <div className="mt-2 flex gap-1.5">
                {monthlyDealFlow.map((month) => <span key={month.key} className="min-w-0 flex-1 truncate text-center text-[10px] text-[color:var(--dim)]">{month.label}</span>)}
              </div>
              <p className="mt-3 text-xs text-[color:var(--dim)]">Only records with an announcement date in this window are counted. Undated deals are not plotted.</p>
            </div>
          )}
        </section>

        <section className="panel p-4 sm:p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="font-medium">Sector distribution</h3>
            <span className="text-xs text-[color:var(--dim)]">{marketDeals.length.toLocaleString()} records analyzed</span>
          </div>
          {analyticsLoading ? <Loading label="Loading sector mix…" /> : sectorMix.length === 0 ? (
            <p className="mt-4 text-sm text-[color:var(--muted)]">Sector distribution is unavailable until deal records are returned.</p>
          ) : (
            <div className="mt-4 space-y-3">
              {sectorMix.map(([sector, count]) => (
                <div key={sector}>
                  <div className="mb-1 flex items-center justify-between gap-3 text-xs">
                    <span>{words(sector)}</span>
                    <span className="kbd text-[color:var(--muted)]">{count.toLocaleString()}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-[color:var(--line)]">
                    <div className="h-full rounded-full bg-verified/80" style={{ width: `${(count / maxSectorCount) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="mt-3 text-xs text-[color:var(--dim)]">Distribution is based on classified retrieved deal records; unclassified records are shown separately when present.</p>
        </section>
      </div>

      <section className="panel mt-4 p-4 sm:p-5">
        <h3 className="font-medium">Deal-type mix</h3>
        {analyticsLoading ? <Loading label="Loading deal types…" /> : dealTypeMix.length === 0 ? (
          <p className="mt-3 text-sm text-[color:var(--muted)]">No deal-type breakdown is available yet.</p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-2">
            {dealTypeMix.map(([type, count]) => (
              <span key={type} className="inline-flex items-center gap-2 rounded-full border hairline px-3 py-1.5 text-xs">
                {words(type)} <span className="kbd text-[color:var(--dim)]">{count.toLocaleString()}</span>
              </span>
            ))}
          </div>
        )}
      </section>

      <h2 className="eyebrow mt-12">Historical country risk</h2>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[color:var(--muted)]">
        Annual scores are reconstructed from the available historical World Bank indicator series, using only observations dated in or before each year. They are not archived historical data vintages, and publisher revisions can change prior scores. The input year for each indicator can differ when a newer observation is unavailable.
      </p>
      {riskHistory.length > 0 ? (
        <div className="panel mt-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-[color:var(--muted)]">{riskHistory.filter((r) => r.score !== null).length} annual points · source dataset retrieved {historyMeta?.retrieved ?? "date unavailable"}</p>
            {historyMeta?.source_url && <a href={historyMeta.source_url} target="_blank" rel="noreferrer noopener" className="text-xs text-verified hover:underline">Open World Bank source API</a>}
          </div>
          <div className="mt-5 grid grid-cols-4 gap-3 sm:grid-cols-8">
            {riskHistory.map((point) => (
              <div key={point.year} className="min-w-0">
                <div className="flex h-32 items-end rounded bg-[color:var(--surface)] p-1">
                  <div title={point.score === null ? "No score available" : `${point.score}/100 · ${point.tier}`}
                    className="w-full rounded-t bg-[color:var(--accent)]"
                    style={{ height: `${point.score === null ? 0 : Math.max(3, point.score)}%`, opacity: point.score === null ? 0.15 : 0.85 }} />
                </div>
                <p className="mt-2 text-center text-xs font-medium">{point.year}</p>
                <p className="text-center text-xs text-[color:var(--muted)]">{point.score === null ? "n/a" : point.score}</p>
              </div>
            ))}
          </div>
          {historyMeta && <p className="mt-4 text-xs leading-relaxed text-[color:var(--dim)]">{historyMeta.method}</p>}
          <div className="mt-5 border-t hairline pt-4">
            <p className="text-sm font-medium">Archived daily snapshots</p>
            {historyMeta?.archived_snapshots.length ? (
              <div className="mt-2 overflow-x-auto">
                <Table head={["Capture date", "Risk score", "Tier", "Indicator dataset date"]}>
                  {historyMeta.archived_snapshots.map((point) => <tr key={point.snapshot_date}>
                    <Td>{point.snapshot_date}</Td><Td className="kbd">{point.score ?? "n/a"}</Td><Td>{point.tier ?? "n/a"}</Td><Td>{point.data_as_of ?? "n/a"}</Td>
                  </tr>)}
                </Table>
              </div>
            ) : <p className="mt-1 text-xs text-[color:var(--muted)]">{historyMeta?.snapshot_note ?? "Historical snapshot archive is not currently available."}</p>}
          </div>
        </div>
      ) : <p className="mt-3 text-sm text-[color:var(--muted)]">Historical risk series is not available for this market yet.</p>}

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
      <div className="mt-4">
        {d.deals.length ? (
          <>
            <DealRows deals={d.deals} />
            <Pagination total={d.deals_total} offset={dealOffset} limit={dealLimit}
              onPageChange={(next) => loadDeals(next, dealLimit)}
              onPageSizeChange={(next) => loadDeals(0, next)} />
          </>
        ) : <p className="text-sm text-[color:var(--muted)]">No deals recorded yet.</p>}
      </div>

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
      {d.events.length > 0 && (
        <Pagination total={d.events_total} offset={eventOffset} limit={eventLimit}
          onPageChange={(next) => loadEvents(next, eventLimit)}
          onPageSizeChange={(next) => loadEvents(0, next)} />
      )}

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
