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
  source_quality: { deal_records: number; event_records: number; source_links_checked: number; official_host_matched_links: number; deal_records_with_official_host: number; deal_records_without_official_host: number; records_without_source_url: number; unverified_or_invalid_source_urls: number; event_records_with_official_host: number; event_records_without_official_host: number; registered_country_hosts: number; registry_status: string; verification_scope: string };
  deals: Deal[];
  deals_total: number;
  events: Event[];
  events_total: number;
  investors: InvestorRow[];
  profile?: CountryProfile;
  history_start?: string;
};

type Mix = { label: string; deals: number; disclosed_value_usd: number };
type CountryProfile = {
  first_year: number | null;
  last_year: number | null;
  deals: number;
  events: number;
  deals_with_amount: number;
  disclosed_value_usd: number;
  median_disclosed_usd: number | null;
  corroborated_deals: number;
  single_source_deals: number;
  by_year: { year: number; deals: number; with_amount: number; disclosed_value_usd: number; events: number }[];
  by_month_last_12: { month: string; deals: number }[];
  sectors: Mix[];
  deal_types: Mix[];
  event_types: { label: string; events: number }[];
  largest_deals: { id: string; headline: string; target: string | null; buyer: string | null; deal_type: string | null; sector: string | null; amount_usd: number; announced: string | null }[];
};

const compactUsd = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 1, notation: "compact" }).format(n);

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
  const [riskHistory, setRiskHistory] = useState<{ year: number; score: number | null; tier: string | null; coverage: number; input_years: Record<string, number>; indicator_count: number }[]>([]);
  const [marketHistory, setMarketHistory] = useState<{ year: number; deal_records: number; event_records: number; disclosed_deal_value_usd: number; deals_with_official_host: number; events_with_official_host: number; source_links_checked: number; official_host_matched_links: number; dated_records: number }[]>([]);
  const [marketHistoryNote, setMarketHistoryNote] = useState<string>("");
  const [historyMeta, setHistoryMeta] = useState<{ source: string; source_url: string; retrieved: string | null; method: string; archived_snapshots: { snapshot_date: string; score: number | null; tier: string | null; data_as_of: string | null }[]; snapshot_note: string } | null>(null);

  useEffect(() => {
    get<CountryResponse>(`/api/countries/${encodeURIComponent(params.code)}`)
      .then(setD)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the country."));
  }, [params.code]);

  useEffect(() => {
    let cancelled = false;
    get<{ rows: typeof riskHistory; source: string; source_url: string; retrieved: string | null; method: string; archived_snapshots: { snapshot_date: string; score: number | null; tier: string | null; data_as_of: string | null }[]; snapshot_note: string; market_activity: typeof marketHistory; market_activity_note: string }>(`/api/countries/${encodeURIComponent(params.code)}/history`)
      .then((result) => {
        if (cancelled) return;
        setRiskHistory(result.rows);
        setMarketHistory(result.market_activity ?? []);
        setMarketHistoryNote(result.market_activity_note ?? "Activity counts reflect records currently held, not a complete census of transactions.");
        setHistoryMeta({ source: result.source, source_url: result.source_url, retrieved: result.retrieved, method: result.method, archived_snapshots: result.archived_snapshots, snapshot_note: result.snapshot_note });
      })
      .catch(() => { if (!cancelled) setHistoryMeta(null); });
    return () => { cancelled = true; };
  }, [params.code]);

  const profile = d?.profile;
  // Plot only years with a complete annual composite score; each country starts at its first valid point.
  const availableRiskPoints = riskHistory.filter((point) => point.score !== null);
  const monthlyDealFlow = useMemo(() => {
    const now = new Date();
    const counts = new Map((profile?.by_month_last_12 ?? []).map((m) => [m.month, m.deals] as const));
    return Array.from({ length: 12 }, (_, i) => {
      const date = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - (11 - i), 1));
      const key = date.toISOString().slice(0, 7);
      return { key, label: date.toLocaleDateString("en", { month: "short", timeZone: "UTC" }), count: counts.get(key) ?? 0 };
    });
  }, [profile]);
  const maxMonthlyDeals = Math.max(1, ...monthlyDealFlow.map((month) => month.count));
  const maxYearDeals = Math.max(1, ...(profile?.by_year ?? []).map((y) => y.deals));
  const sectorMix = (profile?.sectors ?? []).slice(0, 8);
  const maxSectorCount = Math.max(1, ...sectorMix.map((row) => row.deals));

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

      <div className="panel mt-5 p-4">
        <h2 className="text-sm font-medium">Official-source verification</h2>
        <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">{d.source_quality.verification_scope}</p>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Official host-matched links" value={d.source_quality.official_host_matched_links} note={`of ${d.source_quality.source_links_checked} source links checked`} />
          <Stat label="Deals with official-host evidence" value={d.source_quality.deal_records_with_official_host} note={`of ${d.source_quality.deal_records} recorded deals`} />
          <Stat label="Missing source URLs" value={d.source_quality.records_without_source_url} note="Deal/event records without a source URL" />
          <Stat label="Unverified or invalid URLs" value={d.source_quality.unverified_or_invalid_source_urls} note={`${d.source_quality.registered_country_hosts} country hosts registered`} />
        </div>
        <p className="mt-3 text-xs text-[color:var(--dim)]">Registry status: {d.source_quality.registry_status.replaceAll("_", " ")}. A host match verifies the publisher domain against the configured registry, not every claim on the page. Unmatched records remain unverified, not automatically false.</p>
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


      <h2 className="eyebrow mt-12">Market activity{profile?.first_year ? ` since ${profile.first_year}` : ""}</h2>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[color:var(--muted)]">
        Every deal and event record held for {c.name}, from the start of the record (history begins in{" "}
        {(d.history_start ?? "2010").slice(0, 4)}). Counts are records found in published news and filings, not a census of
        every transaction; earlier years are thinner and fewer amounts were disclosed. Values add up disclosed amounts only.
      </p>
      {!profile ? <Loading label="Loading market activity…" /> : (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label={`Deals ${profile.first_year ?? ""}–${profile.last_year ?? ""}`} value={profile.deals.toLocaleString()} note={`${profile.events.toLocaleString()} corporate events`} />
            <Stat label="Disclosed deal value" value={profile.disclosed_value_usd ? compactUsd(profile.disclosed_value_usd) : "None"} note={`${profile.deals_with_amount.toLocaleString()} deals with an amount`} />
            <Stat label="Median disclosed deal" value={profile.median_disclosed_usd ? compactUsd(profile.median_disclosed_usd) : "n/a"} note="Among deals with an amount" />
            <Stat label="Corroborated deals" value={profile.corroborated_deals.toLocaleString()} note={`Two or more independent stories; ${profile.single_source_deals.toLocaleString()} single-source`} />
          </div>

          <section className="panel mt-5 p-4 sm:p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-medium">Deal flow by year</h3>
              <span className="text-xs text-[color:var(--dim)]">Deals by announcement year; hover for value and events</span>
            </div>
            {profile.by_year.length === 0 ? (
              <p className="mt-4 text-sm text-[color:var(--muted)]">No dated deal records yet. Check coverage before concluding that no deals occurred.</p>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <div className="flex h-40 min-w-[32rem] items-end gap-1.5 border-b hairline pb-1">
                  {profile.by_year.map((y) => (
                    <div key={y.year} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1"
                      title={`${y.year}: ${y.deals} deals, ${y.with_amount} with an amount${y.disclosed_value_usd ? ` (${compactUsd(y.disclosed_value_usd)})` : ""}, ${y.events} events`}>
                      <span className="text-[10px] text-[color:var(--dim)]">{y.deals || ""}</span>
                      <div className="w-full max-w-8 rounded-t bg-verified/80" style={{ height: `${Math.max(y.deals ? 4 : 0, (y.deals / maxYearDeals) * 100)}px` }} />
                    </div>
                  ))}
                </div>
                <div className="mt-2 flex min-w-[32rem] gap-1.5">
                  {profile.by_year.map((y) => <span key={y.year} className="min-w-0 flex-1 truncate text-center text-[10px] text-[color:var(--dim)]">{String(y.year).slice(2)}</span>)}
                </div>
              </div>
            )}
          </section>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <section className="panel p-4 sm:p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="font-medium">Last 12 months</h3>
                <span className="text-xs text-[color:var(--dim)]">Deals by announcement month</span>
              </div>
              <div className="mt-4 flex h-32 items-end gap-1.5 border-b hairline pb-1">
                {monthlyDealFlow.map((month) => (
                  <div key={month.key} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1" title={`${month.key}: ${month.count} deals`}>
                    <span className="text-[10px] text-[color:var(--dim)]">{month.count || ""}</span>
                    <div className="w-full max-w-7 rounded-t bg-verified/80" style={{ height: `${Math.max(month.count ? 4 : 0, (month.count / maxMonthlyDeals) * 76)}px` }} />
                  </div>
                ))}
              </div>
              <div className="mt-2 flex gap-1.5">
                {monthlyDealFlow.map((month) => <span key={month.key} className="min-w-0 flex-1 truncate text-center text-[10px] text-[color:var(--dim)]">{month.label}</span>)}
              </div>
            </section>

            <section className="panel p-4 sm:p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="font-medium">Sectors</h3>
                <span className="text-xs text-[color:var(--dim)]">All {profile.deals.toLocaleString()} deals</span>
              </div>
              {sectorMix.length === 0 ? <p className="mt-4 text-sm text-[color:var(--muted)]">No sector data yet.</p> : (
                <div className="mt-4 space-y-3">
                  {sectorMix.map((row) => (
                    <div key={row.label}>
                      <div className="mb-1 flex items-center justify-between gap-3 text-xs">
                        <span>{words(row.label)}</span>
                        <span className="kbd text-[color:var(--muted)]">{row.deals.toLocaleString()}{row.disclosed_value_usd ? ` · ${compactUsd(row.disclosed_value_usd)}` : ""}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-[color:var(--line)]">
                        <div className="h-full rounded-full bg-verified/80" style={{ width: `${(row.deals / maxSectorCount) * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <section className="panel p-4 sm:p-5">
              <h3 className="font-medium">Deal types</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {profile.deal_types.map((row) => (
                  <span key={row.label} className="inline-flex items-center gap-2 rounded-full border hairline px-3 py-1.5 text-xs">
                    {words(row.label)} <span className="kbd text-[color:var(--dim)]">{row.deals.toLocaleString()}</span>
                  </span>
                ))}
              </div>
            </section>
            <section className="panel p-4 sm:p-5">
              <h3 className="font-medium">Corporate events by type</h3>
              {profile.event_types.length === 0 ? <p className="mt-3 text-sm text-[color:var(--muted)]">No events recorded yet.</p> : (
                <div className="mt-3 flex flex-wrap gap-2">
                  {profile.event_types.map((row) => (
                    <span key={row.label} className="inline-flex items-center gap-2 rounded-full border hairline px-3 py-1.5 text-xs">
                      {words(row.label)} <span className="kbd text-[color:var(--dim)]">{row.events.toLocaleString()}</span>
                    </span>
                  ))}
                </div>
              )}
            </section>
          </div>

          {profile.largest_deals.length > 0 && (
            <section className="mt-4">
              <h3 className="font-medium">Largest disclosed deals</h3>
              <div className="mt-3">
                <Table head={["Date", "Deal", "Type", "Amount"]} minWidth="40rem">
                  {profile.largest_deals.map((deal) => (
                    <tr key={deal.id}>
                      <Td className="kbd text-[color:var(--muted)]">{deal.announced ?? "n/a"}</Td>
                      <Td><Link href={`/app/deals/${encodeURIComponent(deal.id)}`} className="hover:underline">{deal.headline}</Link></Td>
                      <Td className="text-[color:var(--muted)]">{deal.deal_type ? words(deal.deal_type) : "n/a"}</Td>
                      <Td className="kbd">{compactUsd(deal.amount_usd)}</Td>
                    </tr>
                  ))}
                </Table>
              </div>
            </section>
          )}
        </>
      )}

      <h2 className="eyebrow mt-12">Historical country risk</h2>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[color:var(--muted)]">
        Reconstructed from World Bank observations, not archived historical scores. Coverage is the share of weighted risk components with usable inputs, not an official data-quality measure. A composite score is shown only when all seven components are available; otherwise the year and input coverage remain visible without a score. Input years can differ within a row.
      </p>
      {availableRiskPoints.length > 0 ? (
        <div className="panel mt-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-[color:var(--muted)]">{availableRiskPoints.length} annual points · shown from {availableRiskPoints[0].year}, the first year with a complete score · source dataset retrieved {historyMeta?.retrieved ?? "date unavailable"}</p>
            {historyMeta?.source_url && <a href={historyMeta.source_url} target="_blank" rel="noreferrer noopener" className="text-xs text-verified hover:underline">Open World Bank source API</a>}
          </div>
          <div className="mt-5 grid grid-cols-4 gap-3 sm:grid-cols-8">
            {availableRiskPoints.map((point) => (
              <div key={point.year} className="min-w-0">
                <div className="flex h-32 items-end rounded bg-[color:var(--surface)] p-1">
                  <div title={`${point.score}/100 · ${point.tier}`}
                    className="w-full rounded-t bg-[color:var(--accent)]"
                    style={{ height: `${Math.max(3, point.score ?? 0)}%`, opacity: 0.85 }} />
                </div>
                <p className="mt-2 text-center text-xs font-medium">{point.year}</p>
                <p className="text-center text-xs text-[color:var(--muted)]">{point.score}</p>
              </div>
            ))}
          </div>
          {historyMeta && <p className="mt-4 text-xs leading-relaxed text-[color:var(--dim)]">{historyMeta.method}</p>}
          <div className="mt-5 border-t hairline pt-4">
            <p className="text-sm font-medium">Latest archived snapshot</p>
            {historyMeta?.archived_snapshots.length ? (
              <div className="mt-2 overflow-x-auto">
                <Table head={["Capture date", "Risk score", "Tier", "Source data as of"]}>
                  {historyMeta.archived_snapshots.slice().sort((a, b) => b.snapshot_date.localeCompare(a.snapshot_date)).slice(0, 1).map((point) => <tr key={point.snapshot_date}>
                    <Td>{point.snapshot_date}</Td><Td className="kbd">{point.score ?? "n/a"}</Td><Td>{point.tier ?? "n/a"}</Td><Td>{point.data_as_of ?? "n/a"}</Td>
                  </tr>)}
                </Table>
              </div>
            ) : <p className="mt-1 text-xs text-[color:var(--muted)]">{historyMeta?.snapshot_note ?? "Historical snapshot archive is not currently available."}</p>}
          </div>
        </div>
      ) : <p className="mt-3 text-sm text-[color:var(--muted)]">No complete annual country-risk scores are available for this market yet. The chart will begin at the first year all seven weighted components can be calculated.</p>}

      <h2 className="eyebrow mt-12">Historical market activity</h2>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[color:var(--muted)]">
        Counts include only dated records currently held. Missing years are omitted because they may reflect missing coverage, not zero activity. Official-host matches verify the publisher domain, not the transaction claim itself.
      </p>
      {marketHistory.length > 0 ? (
        <div className="panel mt-4 overflow-x-auto p-4 sm:p-5">
          <Table head={["Year", "Deal records", "Corporate events", "Disclosed deal value", "Official-host deals", "Official-host events", "Official links / checked"]} minWidth="60rem">
            {marketHistory.map((point) => <tr key={point.year}>
              <Td className="kbd">{point.year}</Td>
              <Td className="kbd">{point.deal_records.toLocaleString()}</Td>
              <Td className="kbd">{point.event_records.toLocaleString()}</Td>
              <Td className="kbd">{point.disclosed_deal_value_usd ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0, notation: "compact" }).format(point.disclosed_deal_value_usd) : "Not disclosed"}</Td>
              <Td className="kbd">{point.deals_with_official_host.toLocaleString()}</Td>
              <Td className="kbd">{point.events_with_official_host.toLocaleString()}</Td>
              <Td className="kbd">{point.official_host_matched_links} / {point.source_links_checked}</Td>
            </tr>)}
          </Table>
          <p className="mt-3 text-xs leading-relaxed text-[color:var(--muted)]">{marketHistoryNote}</p>
        </div>
      ) : <p className="mt-3 text-sm text-[color:var(--muted)]">No dated deal/event records are currently available for a historical activity timeline.</p>}

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
