"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Container } from "../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Pill, Stat, usd, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { get } from "../../../lib/market";

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
  const [pulse, setPulse] = useState<Pulse | null>(null);
  const [pulseError, setPulseError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    get<Pulse>("/api/pulse")
      .then((data) => { if (active) setPulse(data); })
      .catch((error) => {
        if (active) setPulseError(error instanceof ApiError ? error.message : "Market activity could not be loaded.");
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
  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · African investment intelligence" title="Explore Investments">
        Explore African investments using existing company data, market context, transparent valuation models and portfolio analysis. Conclusions are only as reliable as their sources and assumptions; this is decision support, not a promise of returns or an instruction to trade. Coverage differs by country, exchange, instrument and company. See the Coverage registry for market-by-market availability and limitations.
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
          <Link href="/app/coverage" className="rounded-full border hairline px-3 py-1.5 underline-offset-4 hover:underline">View market coverage →</Link>
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
