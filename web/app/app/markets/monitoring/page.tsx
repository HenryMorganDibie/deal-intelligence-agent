"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Container } from "../../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Pill } from "../../../../components/app/ui";
import { get } from "../../../../lib/market";
import { validHttpUrl } from "../../../../lib/markets-valuation";
import { matchPortfolioEvents, type MonitoringEvent, type MonitoringHolding } from "../../../../lib/markets-monitoring";

type StoredPortfolio = { version?: number; holdings?: unknown[] };

const STORAGE_KEY = "deal-intelligence-markets-portfolio-v1";

function readHoldings(): MonitoringHolding[] {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (!saved) return [];
    const parsed = JSON.parse(saved) as StoredPortfolio;
    if (parsed.version !== 1 || !Array.isArray(parsed.holdings)) return [];
    return parsed.holdings.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const holding = item as Partial<MonitoringHolding>;
      if (typeof holding.id !== "string" || typeof holding.name !== "string" || !holding.name.trim()) return [];
      return [{
        id: holding.id,
        name: holding.name.trim(),
        ticker: typeof holding.ticker === "string" ? holding.ticker.trim() : "",
        country: typeof holding.country === "string" ? holding.country.trim() : "",
      }];
    });
  } catch {
    throw new Error("The locally saved portfolio could not be read. Open My Portfolio to check browser storage.");
  }
}

function displayDate(value: string | null): string {
  if (!value) return "Date not reported";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  });
}

export default function MarketsMonitoringPage() {
  const [holdings, setHoldings] = useState<MonitoringHolding[]>([]);
  const [portfolioReady, setPortfolioReady] = useState(false);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [events, setEvents] = useState<MonitoringEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  useEffect(() => {
    try {
      setHoldings(readHoldings());
    } catch (error) {
      setPortfolioError(error instanceof Error ? error.message : "The local portfolio could not be read.");
    } finally {
      setPortfolioReady(true);
    }
  }, []);

  const loadEvents = useCallback(async () => {
    setEventsLoading(true);
    setEventsError(null);
    const since = new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10);
    try {
      const response = await get<{ events: MonitoringEvent[]; count?: number }>("/api/events", { since, limit: 100, offset: 0 });
      setEvents(Array.isArray(response.events) ? response.events : []);
      setLastUpdated(new Date().toISOString());
    } catch (error) {
      setEventsError(error instanceof Error ? error.message : "Market events could not be loaded.");
    } finally {
      setEventsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (portfolioReady && holdings.length > 0) void loadEvents();
  }, [portfolioReady, holdings.length, loadEvents]);

  const matches = useMemo(() => matchPortfolioEvents(holdings, events), [holdings, events]);

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · Investment monitoring" title="Developments that may affect your holdings">
        Review recent African corporate events that match company names or ticker symbols in your locally saved portfolio. Matches are candidate links to investigate, not verified materiality assessments or personalised recommendations.
      </PageHeader>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Link href="/app/markets" className="text-sm text-[color:var(--muted)] underline-offset-4 hover:underline">← Back to Markets</Link>
        <div className="flex flex-wrap gap-2">
          <Link href="/app/markets/portfolio" className="btn btn-secondary">My Portfolio</Link>
          <Link href="/app/watchlists" className="btn btn-ghost">Existing Watchlists</Link>
          <button type="button" className="btn btn-primary" onClick={() => void loadEvents()} disabled={eventsLoading || !portfolioReady || holdings.length === 0}>
            {eventsLoading ? "Refreshing…" : "Refresh events"}
          </button>
        </div>
      </div>

      {portfolioError ? <ErrorNote message={portfolioError} /> : null}

      {!portfolioReady ? <Loading label="Reading your portfolio from this browser…" /> : null}

      {portfolioReady && !portfolioError && holdings.length === 0 ? (
        <section className="panel p-6 sm:p-8">
          <p className="eyebrow">Start with your holdings</p>
          <h2 className="h3 mt-2 text-xl">Monitoring works from your portfolio, not a guessed watchlist.</h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[color:var(--muted)]">
            Add company names or ticker symbols to My Portfolio first. This page reads those entries in your browser and requests the general market-events feed without uploading your holdings.
          </p>
          <Link href="/app/markets/portfolio" className="btn btn-primary mt-5">Set up My Portfolio</Link>
        </section>
      ) : null}

      {portfolioReady && holdings.length > 0 ? (
        <>
          <section className="grid gap-3 sm:grid-cols-3">
            <div className="panel p-4"><p className="text-xs text-[color:var(--muted)]">Portfolio positions</p><p className="mt-2 text-2xl font-semibold">{holdings.length}</p><p className="mt-1 text-xs text-[color:var(--dim)]">Read locally from this browser</p></div>
            <div className="panel p-4"><p className="text-xs text-[color:var(--muted)]">Events reviewed</p><p className="mt-2 text-2xl font-semibold">{events.length}</p><p className="mt-1 text-xs text-[color:var(--dim)]">Up to 100 events from the last 90 days</p></div>
            <div className="panel p-4"><p className="text-xs text-[color:var(--muted)]">Possible portfolio matches</p><p className="mt-2 text-2xl font-semibold">{matches.length}</p><p className="mt-1 text-xs text-[color:var(--dim)]">Name/ticker matches; not confirmed impact</p></div>
          </section>

          <section className="mt-8" aria-labelledby="matches-title">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="eyebrow">Candidate alerts</p>
                <h2 id="matches-title" className="h3 mt-2 text-xl">Recent company developments</h2>
              </div>
              <p className="text-xs text-[color:var(--dim)]">{lastUpdated ? `Feed refreshed ${displayDate(lastUpdated)}` : "Feed has not refreshed yet"}</p>
            </div>

            {eventsError ? <ErrorNote message={eventsError} /> : null}
            {eventsLoading && events.length === 0 ? <Loading label="Loading recent corporate events…" /> : null}
            {!eventsLoading && !eventsError && events.length === 0 ? (
              <div className="rounded-xl border hairline p-5 text-sm text-[color:var(--muted)]">No events were returned for this period. Try refreshing later; the feed may be empty or temporarily unavailable.</div>
            ) : null}
            {!eventsLoading && !eventsError && events.length > 0 && matches.length === 0 ? (
              <div className="rounded-xl border hairline p-5">
                <h3 className="text-sm font-medium">No exact name or ticker matches found</h3>
                <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">That does not mean there are no relevant developments. Company aliases, subsidiaries, translated names and ticker omissions can prevent a match. Open Watchlists for the existing monitored-company alert workflow.</p>
                <Link href="/app/watchlists" className="mt-3 inline-flex text-sm underline-offset-4 hover:underline">Open Watchlists →</Link>
              </div>
            ) : null}

            <div className="space-y-3">
              {matches.map(({ event, holdings: relatedHoldings }) => (
                <article key={event.id} className="rounded-xl border hairline p-4 sm:p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Pill value={event.signal_type || "corporate event"} />
                    {event.direction ? <Pill value={event.direction} /> : null}
                    {event.country ? <span className="text-xs text-[color:var(--dim)]">{event.country}</span> : null}
                    <span className="text-xs text-[color:var(--dim)]">{displayDate(event.day)}</span>
                  </div>
                  <h3 className="mt-3 text-sm font-medium leading-relaxed">{event.headline}</h3>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className="text-xs text-[color:var(--muted)]">Possible match for</span>
                    {relatedHoldings.map((holding) => (
                      <Link key={holding.id} href={`/app/markets/valuation?company=${encodeURIComponent(holding.name)}${holding.ticker ? `&ticker=${encodeURIComponent(holding.ticker)}` : ""}${holding.country ? `&country=${encodeURIComponent(holding.country)}` : ""}`} className="rounded-full border hairline px-2.5 py-1 text-xs underline-offset-4 hover:underline">
                        {holding.name}{holding.ticker ? ` · ${holding.ticker}` : ""}
                      </Link>
                    ))}
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">
                    Matched by {relatedHoldings.map((holding) => holding.name).join(", ")} using {relatedHoldings.map((holding) => {
                      const match = matches.find((item) => item.event.id === event.id)?.holdings.find((candidate) => candidate.id === holding.id);
                      return match?.reason ?? "name";
                    }).join(", ")}. Check the source and company identity before treating this as relevant.
                  </p>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-[color:var(--muted)]">
                    <span>{event.publisher || "Publisher not reported"}</span>
                    {event.url && validHttpUrl(event.url) ? <a href={event.url} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">Open source ↗</a> : <span>Source link not available</span>}
                  </div>
                </article>
              ))}
            </div>
          </section>
        </>
      ) : null}

      <div className="mt-8 rounded-xl border hairline p-4 text-xs leading-relaxed text-[color:var(--dim)]">
        Privacy and reliability: holdings are read from browser-local storage and are never sent to the events API. The page requests only a general 90-day event feed. Matching is conservative but can still miss aliases or produce false positives; this is not a push notification service, an automatic impact score, or a verified alert that a holding's value has changed.
      </div>
    </Container>
  );
}
