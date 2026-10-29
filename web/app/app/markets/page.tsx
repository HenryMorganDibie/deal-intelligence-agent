"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../components/primitives";
import { MarketSearch } from "../../../components/app/MarketSearch";
import { ErrorNote, Loading, PageHeader, Pill, Stat, usd, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { get } from "../../../lib/market";
import { asOf, companyHref, quoteWhen, heat, pct, price, tone, type Mover, type Overview } from "../../../lib/markets-data";

type PulseEvent = {
  id: string;
  signal_type: string | null;
  country: { code: string; name: string } | null;
  day: string | null;
  headline: string;
  headline_en?: string | null;
  publisher: string | null;
  url: string | null;
};
type Pulse = {
  as_of: string;
  deals: {
    recent: number;
    recent_countries: number;
    recent_disclosed_usd: number;
    recent_disclosed_n: number;
    recent_disclosed_median_usd: number | null;
    recent_top3_share: number | null;
    recent_value_by_kind: Record<string, number>;
    top_countries: { code: string; name: string; deals: number }[];
  };
  events: { recent: number; latest: PulseEvent[] };
};

const KIND_LABEL: Record<string, string> = {
  equity: "Equity rounds", debt: "Debt", m_and_a: "M&A", funds: "Fund raises", listings: "Listings", other: "Other",
};

function MoverTable({ title, rows, metric }: { title: string; rows: Mover[]; metric: "chg_1d" | "value" }) {
  return (
    <section className="panel min-w-0 p-5">
      <h3 className="eyebrow">{title}</h3>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-[color:var(--muted)]">No shares qualify in the latest snapshot.</p>
      ) : (
        <ul className="mt-3 divide-y divide-[color:var(--line)]">
          {rows.map((r) => (
            <li key={`${r.exchange}:${r.symbol}`}>
              <Link href={companyHref(r)} className="flex items-center justify-between gap-3 py-2 text-sm hover:opacity-80">
                <span className="min-w-0">
                  <span className="block truncate">{r.name}</span>
                  <span className="text-xs text-[color:var(--dim)]">{r.symbol} · {r.exchange.toUpperCase()}</span>
                </span>
                <span className="shrink-0 text-right">
                  {metric === "chg_1d" ? (
                    <>
                      <span className={`block kbd ${tone(r.chg_1d)}`}>{pct(r.chg_1d, 2)}</span>
                      <span className="text-xs text-[color:var(--dim)]">{price(r.price, r.currency)}{r.delayed ? ` · ${quoteWhen(r)}` : ""}</span>
                    </>
                  ) : (
                    <>
                      <span className="block kbd">{usd(r.value_traded_usd)}</span>
                      <span className={`text-xs ${tone(r.chg_1d)}`}>{pct(r.chg_1d, 2)}</span>
                    </>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function MarketsPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [pulse, setPulse] = useState<Pulse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [heatBy, setHeatBy] = useState<"chg_1d" | "ytd_usd">("chg_1d");
  const [companies, setCompanies] = useState<{ listed: number; private: number } | null>(null);

  useEffect(() => {
    let active = true;
    get<Overview>("/api/markets/overview")
      .then((d) => { if (active) setOverview(d); })
      .catch((e) => { if (active) setError(e instanceof ApiError ? e.message : "Market data could not be loaded."); });
    get<Pulse>("/api/pulse").then((d) => { if (active) setPulse(d); }).catch(() => undefined);
    get<{ counts: { listed: number; private: number } }>("/api/companies/directory", { limit: 1 })
      .then((d) => { if (active) setCompanies(d.counts); }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  const totalCap = overview?.exchanges.reduce((s, t) => s + (t.mcap_usd ?? 0), 0) ?? 0;
  const kinds = Object.entries(pulse?.deals.recent_value_by_kind ?? {});
  const kindTotal = kinds.reduce((s, [, v]) => s + v, 0) || 1;

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets" title="African equity markets, today.">
        Every share on {overview?.coverage.exchanges ?? 18} African exchanges, priced daily, and every private company in
        the deal record, with returns in local currency and in dollars, deal flow and corporate events.
      </PageHeader>

      <MarketSearch />

      {error && <ErrorNote message={error} />}
      {!overview && !error && <Loading label="Loading today's market snapshot…" />}

      {overview && (
        <>
          <section className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Listed shares tracked" value={overview.coverage.shares.toLocaleString()}
              note={`${overview.coverage.priced_today.toLocaleString()} priced in the last week`} />
            <Stat label="Market cap covered" value={usd(totalCap)}
              note={`${overview.coverage.with_market_cap.toLocaleString()} shares with a published cap`} />
            <Stat label="Companies on record" value={companies ? (companies.listed + companies.private).toLocaleString() : overview.coverage.shares.toLocaleString()}
              note={companies ? <><Link className="hover:underline" href="/app/markets/screener">{companies.listed.toLocaleString()} listed</Link> · <Link className="hover:underline" href="/app/markets/screener?view=private">{companies.private.toLocaleString()} private</Link></> : `${overview.coverage.exchanges} exchanges`} />
            <Stat label="Snapshot" value={asOf(overview.captured_at)} note={`FX: ${overview.fx_as_of ? overview.fx_as_of.slice(5, 16) : "n/a"}`} />
          </section>

          <section className="mt-8" aria-labelledby="exchanges-title">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <h2 id="exchanges-title" className="h3 text-xl">Exchanges</h2>
              <Link href="/app/markets/screener" className="text-xs text-[color:var(--muted)] underline-offset-4 hover:underline">Open the screener →</Link>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {overview.exchanges.map((t) => {
                const ytdUsd = t.ytd_usd ?? t.ytd_median_usd;
                const ytdLocal = t.ytd_local ?? t.ytd_median_local;
                const basis = t.ytd_usd != null ? "cap-weighted" : "median share";
                return (
                  <Link key={t.exchange} href={`/app/markets/screener?exchange=${t.exchange}`}
                    className={`rounded-xl border hairline p-4 transition hover:bg-white/[0.03] ${t.stale ? "opacity-60" : ""}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{t.name}</p>
                        <p className="text-xs text-[color:var(--dim)]">{t.index?.name ?? t.exchange.toUpperCase()} · {t.currency}</p>
                      </div>
                      {t.stale ? <Pill value="stale" title="No share priced in the last 7 days" /> : null}
                    </div>
                    <div className="mt-3 flex items-baseline justify-between gap-2">
                      <span className="kbd text-lg">{t.index ? t.index.level.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "n/a"}</span>
                      <span className={`kbd text-sm ${tone(t.index?.chg_1d)}`}>{pct(t.index?.chg_1d, 2)}</span>
                    </div>
                    <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                      <dt className="text-[color:var(--dim)]">YTD in USD</dt>
                      <dd className={`text-right kbd ${tone(ytdUsd)}`} title={basis}>{pct(ytdUsd)}</dd>
                      <dt className="text-[color:var(--dim)]">YTD local</dt>
                      <dd className={`text-right kbd ${tone(ytdLocal)}`} title={basis}>{pct(ytdLocal)}</dd>
                      <dt className="text-[color:var(--dim)]">Currency vs USD</dt>
                      <dd className={`text-right kbd ${tone(t.currency_ytd_vs_usd)}`}>{pct(t.currency_ytd_vs_usd)}</dd>
                      <dt className="text-[color:var(--dim)]">Market cap</dt>
                      <dd className="text-right kbd">{t.mcap_usd ? usd(t.mcap_usd) : "not published"}</dd>
                      <dt className="text-[color:var(--dim)]">Up / down today</dt>
                      <dd className="text-right kbd"><span className="text-verified">{t.advancers}</span> / <span className="text-risk">{t.decliners}</span></dd>
                    </dl>
                    <p className="mt-2 text-[0.6875rem] text-[color:var(--dim)]">{t.listed} shares · as of {asOf(t.as_of)} · YTD {basis}</p>
                  </Link>
                );
              })}
            </div>
          </section>

          <section className="mt-8 grid gap-4 lg:grid-cols-3">
            <MoverTable title="Top gainers today" rows={overview.gainers} metric="chg_1d" />
            <MoverTable title="Top losers today" rows={overview.losers} metric="chg_1d" />
            <MoverTable title="Most traded (value, USD)" rows={overview.most_traded} metric="value" />
          </section>
          <p className="mt-2 text-xs text-[color:var(--dim)]">Movers are shares priced in the last week with a market cap of at least $10m, or on exchanges that publish no cap. Turnover is published by NGX, Nairobi and Johannesburg.</p>

          <section className="mt-8" aria-labelledby="sectors-title">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <h2 id="sectors-title" className="h3 text-xl">Sectors across Africa</h2>
              <div className="flex gap-1 text-xs" role="group" aria-label="Colour sectors by">
                {(["chg_1d", "ytd_usd"] as const).map((k) => (
                  <button key={k} onClick={() => setHeatBy(k)}
                    className={`rounded-full border hairline px-3 py-1 ${heatBy === k ? "bg-white/10" : ""}`}>
                    {k === "chg_1d" ? "Today" : "YTD in USD"}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
              {overview.sectors.map((s) => {
                const v = heatBy === "chg_1d" ? s.chg_1d : s.ytd_usd;
                return (
                  <Link key={s.sector} href={`/app/markets/screener?sector=${encodeURIComponent(s.sector)}`}
                    className="rounded-lg p-3 transition hover:opacity-90" style={{ background: heat(v, heatBy === "chg_1d" ? 0.05 : 0.5) }}>
                    <p className="truncate text-sm font-medium">{s.sector}</p>
                    <p className="kbd mt-1 text-base">{pct(v, heatBy === "chg_1d" ? 2 : 1)}</p>
                    <p className="text-[0.6875rem] text-[color:var(--muted)]">{s.shares} shares · {s.mcap_usd ? usd(s.mcap_usd) : "cap n/a"}</p>
                  </Link>
                );
              })}
            </div>
          </section>

          <section className="mt-8" aria-labelledby="fx-title">
            <h2 id="fx-title" className="h3 mb-3 text-xl">Currencies against the dollar, year to date</h2>
            <div className="-mx-4 overflow-x-auto px-4">
              <div className="flex gap-2">
                {overview.currencies.map((c) => (
                  <div key={c.currency} className="min-w-[7.5rem] rounded-lg border hairline p-3">
                    <p className="text-sm font-medium">{c.currency}</p>
                    <p className={`kbd text-sm ${tone(c.ytd_vs_usd)}`}>{pct(c.ytd_vs_usd)}</p>
                    <p className="text-[0.6875rem] text-[color:var(--dim)]">{c.per_usd.toLocaleString("en-US", { maximumFractionDigits: 2 })} per USD</p>
                  </div>
                ))}
              </div>
            </div>
            <p className="mt-2 text-xs text-[color:var(--dim)]">{overview.method}</p>
          </section>
        </>
      )}

      {pulse && (
        <section className="mt-10 grid gap-6 xl:grid-cols-[1fr_1fr]">
          <div className="min-w-0">
            <div className="mb-3 flex items-end justify-between gap-3">
              <h2 className="h3 text-xl">Private deal flow, last 30 days</h2>
              <Link href="/app/deals" className="text-xs text-[color:var(--muted)] underline-offset-4 hover:underline">Browse deals →</Link>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Stat label="Deals" value={pulse.deals.recent.toLocaleString()} note={`${pulse.deals.recent_countries} countries`} />
              <Stat label="Median disclosed size" value={usd(pulse.deals.recent_disclosed_median_usd)} note={`${pulse.deals.recent_disclosed_n} deals disclose an amount`} />
              <Stat label="Disclosed total" value={usd(pulse.deals.recent_disclosed_usd)}
                note={pulse.deals.recent_top3_share != null ? `${Math.round(pulse.deals.recent_top3_share * 100)}% from the three largest` : undefined} />
            </div>
            {kinds.length > 0 && (
              <div className="panel mt-3 p-4">
                <p className="text-xs text-[color:var(--dim)]">Disclosed value by kind</p>
                <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-white/10">
                  {kinds.map(([k, v], i) => (
                    <div key={k} style={{ width: `${(v / kindTotal) * 100}%`, opacity: 1 - i * 0.15 }} className="bg-[color:var(--accent)]" title={`${KIND_LABEL[k] ?? k}: ${usd(v)}`} />
                  ))}
                </div>
                <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[color:var(--muted)]">
                  {kinds.map(([k, v]) => <li key={k}>{KIND_LABEL[k] ?? words(k)} {usd(v)}</li>)}
                </ul>
              </div>
            )}
          </div>
          <div className="min-w-0">
            <div className="mb-3 flex items-end justify-between gap-3">
              <h2 className="h3 text-xl">Corporate events, last 7 days</h2>
              <Link href="/app/markets/monitoring" className="text-xs text-[color:var(--muted)] underline-offset-4 hover:underline">Monitor holdings →</Link>
            </div>
            {pulse.events.latest.length === 0 && <p className="panel p-4 text-sm text-[color:var(--muted)]">No events in the last seven days.</p>}
            <div className="space-y-2">
              {pulse.events.latest.slice(0, 5).map((e) => (
                <article key={e.id} className="rounded-xl border hairline p-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-[color:var(--dim)]">
                    <Pill value={e.signal_type ?? "event"} />
                    {e.country && <span>{e.country.name}</span>}
                    <span>{asOf(e.day)}</span>
                    {e.headline_en ? <span>Translated from Arabic</span> : null}
                  </div>
                  <h3 className="mt-1.5 text-sm leading-relaxed">
                    {e.url ? <a href={e.url} target="_blank" rel="noreferrer" className="hover:underline">{e.headline_en || e.headline}</a> : (e.headline_en || e.headline)}
                  </h3>
                </article>
              ))}
            </div>
          </div>
        </section>
      )}

      <section className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["/app/markets/screener", "Screener", "Filter every listed share by exchange, sector, size and return."],
          ["/app/markets/investments", "Beyond shares", "JSE ETFs, Treasury bill auctions, listed property and policy rates, with bill and bond calculators."],
          ["/app/markets/valuation", "Valuation", "DCF and dividend models prefilled from filings and today's price."],
          ["/app/markets/portfolio", "Portfolio", "Holdings priced from the daily snapshot, in local currency and dollars."],
          ["/app/markets/compare", "Compare", "Two companies side by side: market data, multiples and deals."],
        ].map(([href, title, body]) => (
          <Link key={href} href={href} className="rounded-xl border hairline p-4 hover:bg-white/[0.03]">
            <p className="text-sm font-medium">{title} →</p>
            <p className="mt-1 text-xs leading-relaxed text-[color:var(--muted)]">{body}</p>
          </Link>
        ))}
      </section>
      <p className="mt-6 text-xs leading-relaxed text-[color:var(--dim)]">
        Prices are end-of-day closes from public exchange price lists; Johannesburg and Lagos are refreshed during
        trading hours with delayed quotes (Johannesburg about 15 minutes behind), marked &ldquo;delayed&rdquo; with
        their time. None are real-time quotes, and nothing here is investment advice.
        Figures marked stale, flagged or withheld are shown that way rather than estimated.
      </p>
    </Container>
  );
}
