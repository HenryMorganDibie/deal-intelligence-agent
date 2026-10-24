"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Container } from "../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Pill, Stat, usd, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { get, type CoverageRow } from "../../../lib/market";

type PulseCountry = { code: string; name: string } | null;
type PulseDeal = {
  id: string;
  deal_type: string | null;
  target: string | null;
  amount_usd: number | null;
  country: PulseCountry;
  sector: string | null;
  announced: string | null;
  headline: string;
  publisher: string | null;
};
type PulseEvent = {
  id: string;
  signal_type: string | null;
  direction: string | null;
  country: PulseCountry;
  day: string | null;
  headline: string;
  publisher: string | null;
  url: string | null;
};
type Pulse = {
  as_of: string;
  latest_record: string | null;
  deals: {
    total: number;
    countries: number;
    recent: number;
    recent_countries: number;
    recent_disclosed_usd: number;
    recent_disclosed_n: number;
    top_countries: { code: string; name: string; deals: number }[];
    latest: PulseDeal[];
  };
  events: { total: number; recent: number; latest: PulseEvent[] };
};
type Coverage = {
  countries: CoverageRow[];
  summary: {
    countries: number;
    by_tier: Record<string, number>;
    national_news_editions: number;
    full_country_risk_coverage: number;
    with_deals: number;
    with_events: number;
  };
  tiers: Record<string, string>;
};

function compactNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "Not available";
  return value.toLocaleString("en-US");
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "Date not reported";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export default function MarketsPage() {
  const router = useRouter();
  const [company, setCompany] = useState("");
  const [coverageQuery, setCoverageQuery] = useState("");
  const [coverageFilter, setCoverageFilter] = useState("all");
  const [pulse, setPulse] = useState<Pulse | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [pulseError, setPulseError] = useState<string | null>(null);
  const [coverageError, setCoverageError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    get<Pulse>("/api/pulse")
      .then((data) => { if (active) setPulse(data); })
      .catch((error) => {
        if (active) setPulseError(error instanceof ApiError ? error.message : "Market activity could not be loaded.");
      });
    get<Coverage>("/api/coverage")
      .then((data) => { if (active) setCoverage(data); })
      .catch((error) => {
        if (active) setCoverageError(error instanceof ApiError ? error.message : "Coverage information could not be loaded.");
      });
    return () => { active = false; };
  }, []);

  function searchCompany(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = company.trim();
    if (!name) return;
    router.push(`/app/companies?name=${encodeURIComponent(name)}`);
  }

  const latestDeals = pulse?.deals.latest ?? [];
  const latestEvents = pulse?.events.latest ?? [];
  const topDealCountries = pulse?.deals.top_countries.slice(0, 5) ?? [];
  const maxCountryDeals = Math.max(1, ...topDealCountries.map((country) => country.deals));
  const researchReady = coverage?.countries.filter((country) => country.prices && country.statements).length ?? 0;
  const visibleCoverage = (coverage?.countries ?? []).filter((country) => {
    const q = coverageQuery.trim().toLowerCase();
    const matchesQuery = !q || [country.country, country.region, country.exchange ?? "", country.currency, country.iso2].some((value) => value.toLowerCase().includes(q));
    const hasBoth = Boolean(country.prices && country.statements);
    const hasSomeFinancials = Boolean(country.prices || country.statements);
    const hasMarketIntelligence = country.deals > 0 || country.events > 0 || Boolean(country.news?.edition);
    const matchesFilter = coverageFilter === "all" ||
      (coverageFilter === "research-ready" && hasBoth) ||
      (coverageFilter === "partial-financials" && hasSomeFinancials && !hasBoth) ||
      (coverageFilter === "intelligence-only" && !hasSomeFinancials && hasMarketIntelligence);
    return matchesQuery && matchesFilter;
  }).sort((a, b) => a.country.localeCompare(b.country));

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · African investment intelligence" title="Explore Investments">
        Explore African investments using existing company data, market context, transparent valuation models and portfolio analysis. Conclusions are only as reliable as their sources and assumptions; this is decision support, not a promise of returns or an instruction to trade. Coverage differs by country, exchange, instrument and company, and Markets makes those limits visible.
      </PageHeader>

      <section className="panel p-5 sm:p-7" aria-labelledby="market-search-title">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <p className="eyebrow">Start with a company</p>
            <h2 id="market-search-title" className="h3 mt-2 text-xl">Look beyond the ticker.</h2>
            <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">
              Open an existing company profile to inspect available market data, financial statements, trading multiples, source links and accounting checks.
            </p>
          </div>
          <form onSubmit={searchCompany} className="flex w-full gap-2 lg:max-w-xl" role="search">
            <label className="sr-only" htmlFor="markets-company-search">Company name or ticker</label>
            <input
              id="markets-company-search"
              value={company}
              onChange={(event) => setCompany(event.target.value)}
              placeholder="e.g. Dangote Cement, Safaricom, Naspers"
              className="field min-w-0 flex-1"
              required
            />
            <button type="submit" className="btn btn-primary shrink-0">Research company</button>
          </form>
        </div>
        <div className="mt-5 flex flex-wrap gap-2 text-xs text-[color:var(--muted)]">
          <span className="rounded-full border hairline px-3 py-1.5">Africa-wide scope</span>
          <span className="rounded-full border hairline px-3 py-1.5">Source-linked evidence</span>
          <span className="rounded-full border hairline px-3 py-1.5">Coverage-aware analysis</span>
        </div>
      </section>

      <section className="mt-8" aria-labelledby="market-overview-title">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow">Live intelligence from the existing data store</p>
            <h2 id="market-overview-title" className="h3 mt-2 text-xl">African market activity</h2>
          </div>
          <p className="text-xs text-[color:var(--dim)]">
            {pulse?.latest_record ? `Latest dated record: ${formatDate(pulse.latest_record)} · Summary date: ${formatDate(pulse.as_of)}` : pulse?.as_of ? `Summary date: ${formatDate(pulse.as_of)} · No dated record available` : "Summary date appears when data loads"}
          </p>
        </div>
        {pulseError && <ErrorNote message={pulseError} />}
        {!pulse && !pulseError ? <Loading label="Loading African market activity…" /> : null}
        {pulse && (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Deals in database" value={compactNumber(pulse.deals.total)} note={`Across ${compactNumber(pulse.deals.countries)} countries`} />
            <Stat label="Deals in last 30 days" value={compactNumber(pulse.deals.recent)} note={`${compactNumber(pulse.deals.recent_countries)} countries represented`} />
            <Stat label="Corporate events in last 7 days" value={compactNumber(pulse.events.recent)} note="From the existing event feed" />
            <Stat label="Recent disclosed deal value" value={pulse.deals.recent_disclosed_n ? usd(pulse.deals.recent_disclosed_usd) : "Not disclosed"} note={`${compactNumber(pulse.deals.recent_disclosed_n)} recent deals with a disclosed amount`} />
          </div>
        )}
        {pulse && topDealCountries.length > 0 && (
          <section className="panel mt-4 p-5" aria-labelledby="country-deal-flow-title">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="eyebrow">Recorded deal activity</p>
                <h3 id="country-deal-flow-title" className="h3 mt-2 text-base">Markets with the most deals in the database</h3>
              </div>
              <Link href="/app/deals" className="text-xs text-[color:var(--muted)] underline-offset-4 hover:underline">Explore deal records →</Link>
            </div>
            <div className="mt-4 space-y-3">
              {topDealCountries.map((country) => (
                <div key={country.code}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-3 text-xs">
                    <span>{country.name}</span>
                    <span className="kbd text-[color:var(--muted)]">{country.deals.toLocaleString()} recorded deals</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-white/10" role="img" aria-label={`${country.name}: ${country.deals} recorded deals relative to the top country`}>
                    <div className="h-full rounded-full bg-[color:var(--accent)]" style={{ width: `${Math.max(0, Math.min(100, (country.deals / maxCountryDeals) * 100))}%` }} />
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">This ranks records in Deal Intelligence&apos;s dataset, not total investment volume, market size or the quality of each country&apos;s investment opportunities. Differences can reflect source availability and reporting coverage.</p>
          </section>
        )}
        <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">
          These figures describe Deal Intelligence&apos;s recorded deals and corporate events. They are not stock-market performance, trading volume or a measure of every investment made across Africa.
        </p>
      </section>

      <section className="mt-10 grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <div className="min-w-0">
          <div className="mb-4 flex items-end justify-between gap-3">
            <div>
              <p className="eyebrow">Recent signals</p>
              <h2 className="h3 mt-2 text-xl">Company and market developments</h2>
            </div>
            <Link href="/app/countries" className="text-xs text-[color:var(--muted)] underline-offset-4 hover:underline">Explore countries</Link>
          </div>
          {pulse && latestEvents.length === 0 && <p className="panel p-4 text-sm text-[color:var(--muted)]">No events were returned for the current seven-day window.</p>}
          {!pulse && !pulseError && <Loading label="Loading recent events…" />}
          <div className="space-y-3">
            {latestEvents.map((event) => (
              <article key={event.id} className="rounded-xl border hairline bg-white/[0.02] p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Pill value={event.signal_type ?? "event"} />
                  {event.country && <span className="text-xs text-[color:var(--dim)]">{event.country.name}</span>}
                  <span className="text-xs text-[color:var(--dim)]">{formatDate(event.day)}</span>
                </div>
                <h3 className="mt-2 text-sm font-medium leading-relaxed">{event.headline}</h3>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-[color:var(--muted)]">
                  <span>{event.publisher || "Publisher not specified"}</span>
                  {event.url ? <a href={event.url} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">Open source ↗</a> : null}
                </div>
              </article>
            ))}
          </div>
          {pulse && latestDeals.length > 0 && (
            <div className="mt-8">
              <div className="mb-3 flex items-end justify-between gap-3">
                <div>
                  <p className="eyebrow">Deal flow</p>
                  <h3 className="mt-2 text-base font-medium">Recent transactions</h3>
                </div>
                <Link href="/app/deals" className="text-xs text-[color:var(--muted)] underline-offset-4 hover:underline">Browse deals</Link>
              </div>
              <div className="space-y-2">
                {latestDeals.slice(0, 5).map((deal) => (
                  <article key={deal.id} className="flex flex-col gap-2 rounded-xl border hairline p-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{deal.target || "Company not identified"}</p>
                      <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">{deal.headline}</p>
                      <p className="mt-2 text-xs text-[color:var(--dim)]">{[deal.country?.name, deal.sector ? words(deal.sector) : null, formatDate(deal.announced)].filter(Boolean).join(" · ")}</p>
                    </div>
                    <div className="shrink-0 text-left sm:text-right">
                      <p className="text-sm font-medium">{usd(deal.amount_usd)}</p>
                      <p className="mt-1 text-xs text-[color:var(--dim)]">{deal.deal_type ? words(deal.deal_type) : "Transaction"}</p>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          )}
        </div>

        <aside className="space-y-6">
          <section className="panel p-5" aria-labelledby="coverage-title">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="eyebrow">Coverage transparency</p>
                <h2 id="coverage-title" className="h3 mt-2 text-lg">Africa-wide, evidence-led</h2>
              </div>
              <span aria-hidden="true" className="text-2xl">◎</span>
            </div>
            {coverageError && <ErrorNote message={coverageError} />}
            {!coverage && !coverageError ? <Loading label="Loading coverage map…" /> : null}
            {coverage && (
              <>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <Stat label="Countries represented" value={coverage.summary.countries} />
                  <Stat label="Markets with deals" value={coverage.summary.with_deals} />
                </div>
                <div className="mt-4 rounded-lg border hairline p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm">Price + statement coverage</span>
                    <span className="kbd text-sm">{researchReady} / {coverage.countries.length}</span>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">
                    Count of countries whose coverage metadata lists both prices and financial statements. This is a rough availability indicator, not a claim that every listed company in those countries is research-ready.
                  </p>
                </div>
                <div className="mt-4 space-y-3">
                  {Object.entries(coverage.tiers).map(([tier, description]) => (
                    <div key={tier} className="flex items-start gap-2">
                      <Pill value={tier} />
                      <p className="text-xs leading-relaxed text-[color:var(--muted)]">{description}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-6 border-t hairline pt-5">
                  <div className="flex flex-wrap items-end justify-between gap-3">
                    <div>
                      <p className="eyebrow">Country coverage explorer</p>
                      <h3 className="mt-2 text-base font-medium">What can we research in each market?</h3>
                      <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">Coverage metadata is not a guarantee that every company has complete or current data. Provider/source labels reflect the existing coverage registry.</p>
                    </div>
                    <p className="text-xs text-[color:var(--dim)]">{visibleCoverage.length} of {coverage.countries.length} countries</p>
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_0.8fr]">
                    <div>
                      <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="markets-country-search">Search country, exchange or currency</label>
                      <input id="markets-country-search" className="field" value={coverageQuery} onChange={(event) => setCoverageQuery(event.target.value)} placeholder="e.g. Nigeria, NGX, NGN" />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs text-[color:var(--muted)]" htmlFor="markets-coverage-filter">Filter by available coverage</label>
                      <select id="markets-coverage-filter" className="field" value={coverageFilter} onChange={(event) => setCoverageFilter(event.target.value)}>
                        <option value="all">All registered countries</option>
                        <option value="research-ready">Prices and statements listed</option>
                        <option value="partial-financials">Partial financial coverage</option>
                        <option value="intelligence-only">Intelligence, limited financials</option>
                      </select>
                    </div>
                  </div>
                  <div className="mt-4 overflow-x-auto rounded-lg border hairline">
                    <table className="w-full min-w-[48rem] border-collapse text-left text-xs">
                      <thead>
                        <tr className="border-b hairline text-[color:var(--dim)]">
                          {["Country / region", "Exchange / currency", "Coverage tier", "Price data", "Statements", "Deals / events"].map((heading) => <th key={heading} className="whitespace-nowrap px-3 py-3 font-normal">{heading}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {visibleCoverage.map((country) => (
                          <tr key={country.iso2} className="border-b hairline last:border-0">
                            <td className="px-3 py-3"><p className="font-medium">{country.country}</p><p className="mt-1 text-[color:var(--dim)]">{country.region}</p></td>
                            <td className="px-3 py-3"><p>{country.exchange || "No exchange listed"}</p><p className="mt-1 text-[color:var(--dim)]">{country.currency}</p></td>
                            <td className="px-3 py-3"><Pill value={`Tier ${country.tier}`} /></td>
                            <td className="px-3 py-3">{country.prices || "Not listed"}</td>
                            <td className="px-3 py-3">{country.statements || "Not listed"}</td>
                            <td className="px-3 py-3 kbd">{country.deals.toLocaleString()} / {country.events.toLocaleString()}</td>
                          </tr>
                        ))}
                        {visibleCoverage.length === 0 && <tr><td colSpan={6} className="px-3 py-8 text-center text-[color:var(--muted)]">No countries match this search and coverage filter.</td></tr>}
                      </tbody>
                    </table>
                  </div>
                </div>
                <Link href="/app/coverage" className="mt-4 inline-flex text-sm underline-offset-4 hover:underline">Open detailed coverage registry →</Link>
              </>
            )}
          </section>

          <section className="panel p-5" aria-labelledby="portfolio-title">
            <p className="eyebrow">Personal investing</p>
            <h2 id="portfolio-title" className="h3 mt-2 text-lg">Your portfolio, in context.</h2>
            <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">
              Track holdings, allocation, concentration and currency exposure with manual entry or CSV import. Portfolio data stays in this browser and prices are not presented as live quotes.
            </p>
            <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">
              Portfolio holdings are stored in this browser only. Prices and FX rates are user-entered, not live market data.
            </p>
            <Link href="/app/markets/portfolio" className="mt-4 inline-flex text-sm underline-offset-4 hover:underline">Open Portfolio Intelligence →</Link>
          </section>

          <section className="panel p-5" aria-labelledby="valuation-title">
            <p className="eyebrow">Valuation and verdicts</p>
            <h2 id="valuation-title" className="h3 mt-2 text-lg">A clear view, with a countercase.</h2>
            <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">
              Compare transparent DCF and dividend-discount scenarios where the company and data fit the method. Inspect assumptions, sensitivity and the sourced quote, and see when the model cannot support an honest conclusion.
            </p>
            <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">
              These are explicit model outputs, not verified fair value. DCF is restricted to suitable operating companies; unsupported or uncertain profiles do not receive a cheap/expensive verdict. Source quality, currency, quote date and assumptions still require review.
            </p>
            <Link href="/app/markets/valuation" className="mt-4 inline-flex text-sm underline-offset-4 hover:underline">Open Valuation workspace →</Link>
          </section>

          <section className="rounded-xl border hairline p-5">
            <p className="eyebrow">Existing intelligence</p>
            <h2 className="h3 mt-2 text-lg">Continue your research</h2>
            <div className="mt-4 grid gap-2">
              <Link href="/app/markets/valuation" className="btn btn-secondary justify-center">Explore valuation</Link>
              <Link href="/app/markets/portfolio" className="btn btn-ghost justify-center">Open My Portfolio</Link>
              <Link href="/app/markets/compare" className="btn btn-ghost justify-center">Compare opportunities</Link>
              <Link href="/app/markets/monitoring" className="btn btn-ghost justify-center">Monitor portfolio developments</Link>
              <Link href="/app/research" className="btn btn-ghost justify-center">Open Research</Link>
              <Link href="/app/watchlists" className="btn btn-ghost justify-center">Open Alerts and watchlists</Link>
              <Link href="/app/companies" className="btn btn-ghost justify-center">Browse company profiles</Link>
              <Link href="/app/markets/compare" className="btn btn-ghost justify-center">Compare companies</Link>
            </div>
          </section>
        </aside>
      </section>
    </Container>
  );
}
