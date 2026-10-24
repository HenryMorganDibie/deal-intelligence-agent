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

  function openCompany(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = company.trim();
    if (!name) return;
    router.push(`/app/companies?name=${encodeURIComponent(name)}`);
  }

  const latestDeals = pulse?.deals.latest ?? [];
  const latestEvents = pulse?.events.latest ?? [];

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · African investment intelligence" title="Explore Investments">
        Discover companies and market developments, evaluate an investment with transparent assumptions, compare opportunities, and monitor your portfolio. Deal records and analytical estimates are evidence to investigate, not a promise of returns or instructions to trade.
      </PageHeader>

      <section className="panel p-5 sm:p-7" aria-labelledby="investment-start-title">
        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
          <div>
            <p className="eyebrow">Start with an investment</p>
            <h2 id="investment-start-title" className="h3 mt-2 text-xl">Find a company. Then test the case.</h2>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[color:var(--muted)]">
              Open an existing company profile, inspect its available financial evidence, then use the valuation and comparison tools to examine assumptions and alternatives. Missing or weak data should remain visible, not be filled with guesses.
            </p>
            <form onSubmit={openCompany} className="mt-5 flex w-full gap-2" role="search">
              <label className="sr-only" htmlFor="markets-company-search">Company name or ticker</label>
              <input
                id="markets-company-search"
                value={company}
                onChange={(event) => setCompany(event.target.value)}
                placeholder="e.g. Dangote Cement, Safaricom, Naspers"
                className="field min-w-0 flex-1"
                required
              />
              <button type="submit" className="btn btn-primary shrink-0">View company</button>
            </form>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
            <Link href="/app/markets/valuation" className="rounded-xl border hairline p-4 transition-colors hover:bg-white/[0.04]">
              <p className="text-sm font-medium">Evaluate an investment <span aria-hidden="true">→</span></p>
              <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">Inspect DCF or dividend-discount scenarios, assumptions and source dates where the model fits.</p>
            </Link>
            <Link href="/app/markets/compare" className="rounded-xl border hairline p-4 transition-colors hover:bg-white/[0.04]">
              <p className="text-sm font-medium">Compare opportunities <span aria-hidden="true">→</span></p>
              <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">Compare company evidence and available valuation context without treating missing data as a positive signal.</p>
            </Link>
          </div>
        </div>
      </section>

      <section className="mt-8" aria-labelledby="market-activity-title">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow">What has been recorded</p>
            <h2 id="market-activity-title" className="h3 mt-2 text-xl">Market activity</h2>
            <p className="mt-1 text-sm text-[color:var(--muted)]">Private-market transactions and corporate developments from the existing intelligence feed.</p>
          </div>
          <p className="text-xs text-[color:var(--dim)]">
            {pulse?.latest_record ? `Latest dated record: ${formatDate(pulse.latest_record)} · Summary: ${formatDate(pulse.as_of)}` : pulse?.as_of ? `Summary date: ${formatDate(pulse.as_of)} · No dated record available` : "Summary date appears when data loads"}
          </p>
        </div>
        {pulseError && <ErrorNote message={pulseError} />}
        {!pulse && !pulseError ? <Loading label="Loading market activity…" /> : null}
        {pulse && (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Recorded transactions" value={compactNumber(pulse.deals.total)} note={`Across ${compactNumber(pulse.deals.countries)} countries`} />
            <Stat label="Transactions in last 30 days" value={compactNumber(pulse.deals.recent)} note={`${compactNumber(pulse.deals.recent_countries)} countries represented`} />
            <Stat label="Corporate events in last 7 days" value={compactNumber(pulse.events.recent)} note="From the existing event feed" />
            <Stat label="Recent disclosed deal value" value={pulse.deals.recent_disclosed_n ? usd(pulse.deals.recent_disclosed_usd) : "Not disclosed"} note={`${compactNumber(pulse.deals.recent_disclosed_n)} recent transactions with an amount`} />
          </div>
        )}
        <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">
          These counts describe records in Deal Intelligence, not total market size, stock-market performance, trading volume, or the quality of an investment opportunity. Disclosed deal values omit transactions whose amounts were not reported.
        </p>
      </section>

      <section className="mt-10 grid gap-8 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="min-w-0">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="eyebrow">Recent developments</p>
              <h2 className="h3 mt-2 text-xl">What may deserve attention</h2>
            </div>
            <Link href="/app/watchlists" className="text-xs text-[color:var(--muted)] underline-offset-4 hover:underline">Open alerts and watchlists →</Link>
          </div>
          {pulse && latestEvents.length === 0 && <p className="panel p-4 text-sm text-[color:var(--muted)]">No events were returned for the current seven-day window.</p>}
          {!pulse && !pulseError && <Loading label="Loading recent developments…" />}
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
        </div>

        <aside className="space-y-6">
          <section className="panel p-5" aria-labelledby="deal-flow-title">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="eyebrow">Recent deal flow</p>
                <h2 id="deal-flow-title" className="h3 mt-2 text-lg">Transactions to investigate</h2>
              </div>
              <Link href="/app/deals" className="text-xs text-[color:var(--muted)] underline-offset-4 hover:underline">All deals →</Link>
            </div>
            {!pulse && !pulseError ? <Loading label="Loading recent transactions…" /> : null}
            {pulse && latestDeals.length === 0 && <p className="mt-4 text-sm text-[color:var(--muted)]">No recent transactions are available in the current response.</p>}
            <div className="mt-4 space-y-3">
              {latestDeals.slice(0, 5).map((deal) => (
                <article key={deal.id} className="border-b hairline pb-3 last:border-0 last:pb-0">
                  <p className="text-sm font-medium">{deal.target || "Company not identified"}</p>
                  <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">{deal.headline}</p>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-[color:var(--dim)]">
                    <span>{[deal.country?.name, deal.sector ? words(deal.sector) : null, formatDate(deal.announced)].filter(Boolean).join(" · ")}</span>
                    <span>{usd(deal.amount_usd)}</span>
                  </div>
                </article>
              ))}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">A reported transaction is a research lead, not necessarily an investment product available to buy.</p>
          </section>

          <section className="panel p-5" aria-labelledby="portfolio-title">
            <p className="eyebrow">Personal investing</p>
            <h2 id="portfolio-title" className="h3 mt-2 text-lg">Your portfolio, in context.</h2>
            <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">
              Review allocation, concentration, currency exposure and saved valuation changes. Holdings remain in this browser; prices and FX rates are entered manually, not live quotes.
            </p>
            <Link href="/app/markets/portfolio" className="mt-4 inline-flex text-sm underline-offset-4 hover:underline">Open My Portfolio →</Link>
          </section>

          <section className="rounded-xl border hairline p-5" aria-labelledby="coverage-context-title">
            <p className="eyebrow">Know the limits</p>
            <h2 id="coverage-context-title" className="h3 mt-2 text-lg">Check the available evidence.</h2>
            <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">
              Data depth varies by country, exchange, instrument and company. Check the existing Coverage registry before relying on missing or incomplete market information.
            </p>
            <Link href="/app/coverage" className="mt-4 inline-flex text-sm underline-offset-4 hover:underline">View market coverage →</Link>
          </section>
        </aside>
      </section>
    </Container>
  );
}
