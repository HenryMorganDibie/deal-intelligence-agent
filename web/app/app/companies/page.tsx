"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { Container } from "../../../components/primitives";
import { DealRows, ErrorNote, Field, Loading, PageHeader, Pill, Stat, Table, Td, num, usd, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { get, type Comparables, type Deal } from "../../../lib/market";

type Item = { current: number; prior?: number; line?: string };
type Financials = {
  source: string;
  source_url?: string;
  filed?: string;
  period: { end: string; months: number | null; label?: string } | null;
  currency?: string;
  unit?: string;
  basis?: string;
  items: Record<string, Item>;
  checks: { check: string; passed: boolean; lhs: number; rhs: number }[];
  verified: boolean;
  status?: Record<string, string>;
};
type Profile = {
  name: string;
  ticker: string | null;
  country: string | null;
  country_name: string | null;
  exchange: string | null;
  sources: string[];
  identity?: Record<string, unknown> & { board?: string[]; business?: string; source?: string };
  market?: Record<string, unknown> | null;
  multiples?: Record<string, number>;
  multiples_withheld?: string;
  listing?: { exchange: string; exchange_name: string; symbol: string; name: string; sector: string | null; secondary_of?: string | null };
  financials?: Financials;
  financials_note?: string;
  filings?: { title: string; url: string; filed: string }[];
  sec_cross_check?: { period: string; field: string; yahoo: number; sec_filing: number; match: boolean }[];
  private_markets: {
    deal_count: number;
    total_raised_usd: number | null;
    equity_raised_usd: number | null;
    debt_raised_usd: number | null;
    last_round: string | null;
    valuations: { announced: string; usd: number; basis: string }[];
    investors_and_lenders: string[];
    deals: Deal[];
  };
  valuation: {
    latest_mark: { valuation_usd: number; basis: string; announced: string } | null;
    comparables: Comparables;
    public_bridge?: {
      sector: string; scope: "country" | "africa"; country: string | null; peers: number; valuation_usd: number;
      announced: string | null; rank_percentile: number; larger_than: number; peer_median_cap_usd: number;
      peer_ytd_usd: number | null; note: string;
      largest_peers: { exchange: string; symbol: string; name: string; mcap_usd: number; ytd_usd: number | null }[];
    } | null;
  };
};

const ORDER = [
  "revenue", "cost_of_sales", "gross_profit", "net_interest_income", "operating_profit", "ebitda", "finance_costs",
  "profit_before_tax", "income_tax", "profit_after_tax", "eps", "total_assets", "total_liabilities", "total_equity",
  "total_debt", "loans_to_customers", "customer_deposits", "cash", "operating_cash_flow", "investing_cash_flow",
  "financing_cash_flow", "capex", "free_cash_flow",
];
const MULTIPLES: Record<string, string> = {
  trailingPE: "P/E (trailing)", forwardPE: "P/E (forward)", priceToBook: "Price / book", enterpriseToRevenue: "EV / revenue",
  enterpriseToEbitda: "EV / EBITDA", dividendYield: "Dividend yield", beta: "Beta",
};

function compact(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(2)}bn`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}m`;
  return num(v, 2);
}

type CompanyEvent = { id: string; signal_type: string | null; day: string | null; headline: string; headline_en?: string | null; url?: string | null; publisher?: string | null };

function pctText(v: unknown, digits = 1): string {
  return typeof v === "number" && Number.isFinite(v) ? `${v > 0 ? "+" : ""}${v.toFixed(digits)}%` : "n/a";
}

function toneOf(v: unknown): string {
  return typeof v !== "number" || v === 0 ? "" : v > 0 ? "text-verified" : "text-risk";
}

// The words that find a company's news: its name without the corporate suffix.
function newsName(name: string): string {
  return name.replace(/\b(plc|ltd|limited|holdings?|group|company|corporation|s\.?a\.?|inc)\.?$/i, "").trim();
}

export default function CompaniesPage() {
  const [form, setForm] = useState({ name: "", ticker: "", country: "", cik: "" });
  const [listing, setListing] = useState<{ exchange: string; symbol: string } | null>(null);
  const [events, setEvents] = useState<CompanyEvent[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [p, setP] = useState<Profile | null>(null);

  async function load(f = form, exact = listing) {
    if (!f.name.trim()) return;
    setBusy(true);
    setError(null);
    setP(null);
    setEvents(null);
    try {
      const profile = await get<Profile>("/api/companies/profile", {
        name: f.name.trim(), ticker: f.ticker.trim(), country: f.country.trim(), cik: f.cik.trim(),
        exchange: exact?.exchange, symbol: exact?.symbol,
      });
      setP(profile);
      const since = new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10);
      get<{ events: CompanyEvent[] }>("/api/events", { q: newsName(profile.listing?.name ?? profile.name), since, limit: 12 })
        .then((r) => setEvents(r.events))
        .catch(() => setEvents([]));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not build the profile.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const f = { name: q.get("name") ?? "", ticker: q.get("ticker") ?? "", country: q.get("country") ?? "", cik: q.get("cik") ?? "" };
    const exact = q.get("exchange") && q.get("symbol") ? { exchange: q.get("exchange")!, symbol: q.get("symbol")! } : null;
    if (f.name) {
      setForm(f);
      setListing(exact);
      load(f, exact);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(e: FormEvent) {
    e.preventDefault();
    const q = new URLSearchParams(Object.entries(form).filter(([, v]) => v));
    window.history.replaceState(null, "", `?${q}`);
    setListing(null);
    load(form, null);
  }

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const fin = p?.financials;
  const financialsStatus = fin?.verified
    ? "verified"
    : fin?.checks.some((check) => !check.passed)
      ? "inconsistent"
      : "unchecked";
  return (
    <Container className="py-10 lg:py-14">
      <PageHeader eyebrow="Companies" title="Profiles and financial statements.">
        Listed companies: exchange profile, market data and the latest audited statements, parsed from the filing and
        checked with accounting identities (each figure is marked verified, inconsistent or unchecked). NGX and NSE Kenya
        statements come from the exchanges&apos; own filings; other listings from Yahoo Finance, cross-checked against SEC
        filings when a CIK is given. Private companies: funding rounds, valuations and investors from the deals database.
      </PageHeader>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_auto]">
        <Field label="Company">
          <input required value={form.name} onChange={set("name")} placeholder="Dangote Cement" className="field" />
        </Field>
        <Field label="Ticker (optional)">
          <input value={form.ticker} onChange={(e) => setForm({ ...form, ticker: e.target.value.toUpperCase() })} placeholder="DANGCEM.LG" className="field kbd" />
        </Field>
        <Field label="Country (optional)">
          <input value={form.country} onChange={set("country")} maxLength={3} placeholder="NG" className="field kbd uppercase" />
        </Field>
        <Field label="SEC CIK (optional)">
          <input value={form.cik} onChange={set("cik")} inputMode="numeric" placeholder="1756708" className="field kbd" />
        </Field>
        <div className="flex items-end">
          <button type="submit" disabled={busy} className="btn btn-primary w-full">
            {busy ? "Building..." : "Profile"}
          </button>
        </div>
      </form>
      <p className="mt-3 text-[0.8125rem] text-[color:var(--dim)]">
        Examples: Dangote Cement (DANGCEM.LG), Safaricom (SCOM.NR), Naspers (NPN.JO), Jumia (JMIA, CIK 1756708), Moniepoint (private).
      </p>
      {error && <ErrorNote message={error} />}
      {busy && <Loading label="Reading filings and statements. Large PDFs take up to 30 seconds." />}

      {p && (
        <div className="mt-10 space-y-10">
          <section>
            <h2 className="h2 text-[1.5rem]">{p.name}</h2>
            <p className="mt-1 text-[0.875rem] text-[color:var(--muted)]">
              {[p.ticker, p.exchange, p.country_name, (p.identity?.sector as string) ?? null].filter(Boolean).join(" · ")}
            </p>
            <p className="mt-1 text-[0.75rem] text-[color:var(--dim)]">Sources: {p.sources.join(", ") || "none found"}</p>
            {p.identity?.business && <p className="mt-4 max-w-3xl text-[0.875rem] leading-relaxed text-[color:var(--muted)]">{String(p.identity.business).slice(0, 700)}</p>}
            {p.identity?.board && p.identity.board.length > 0 && (
              <p className="mt-3 text-[0.8125rem] text-[color:var(--muted)]">Board: {p.identity.board.join(", ")}</p>
            )}
            {typeof p.identity?.auditor === "string" && <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">Auditor: {p.identity.auditor}</p>}
          </section>

          {p.market && (
            <section>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Stat label="Price" value={p.market.price != null ? `${num(p.market.price as number, 2)} ${p.market.currency ?? ""}` : "n/a"}
                  note={<>
                    <span className={toneOf(p.market.change_pct)}>{pctText(p.market.change_pct, 2)}</span>
                    {p.market.delayed && p.market.quote_time
                      ? ` · delayed quote, ${String(p.market.quote_time).slice(11, 16)} UTC`
                      : ` · ${p.market.as_at ? `as of ${String(p.market.as_at).slice(0, 10)}` : "date not reported"}`}
                    {p.market.stale ? <span className="text-risk"> · stale ({String(p.market.age_days)} days)</span> : null}
                  </>} />
                <Stat label="Market cap" value={p.market.market_cap_usd ? usd(p.market.market_cap_usd as number) : p.market.market_cap ? compact(p.market.market_cap as number) : "n/a"}
                  note={p.market.market_cap ? `${compact(p.market.market_cap as number)} ${p.market.currency ?? ""}${p.market.shares_outstanding ? ` · ${compact(p.market.shares_outstanding as number)} shares` : ""}` : "Not published for this listing"} />
                <Stat label="Year to date" value={<span className={toneOf(p.market.ytd_usd_pct ?? p.market.ytd_pct)}>{pctText(p.market.ytd_usd_pct ?? p.market.ytd_pct)}</span>}
                  note={p.market.ytd_note ? String(p.market.ytd_note) : p.market.ytd_usd_pct != null ? `In USD · ${pctText(p.market.ytd_pct)} in ${p.market.currency ?? "local currency"}` : p.market.ytd_pct != null ? "Local currency" : undefined} />
                <Stat label="Latest private valuation mark" value={usd(p.valuation.latest_mark?.valuation_usd)} note={p.valuation.latest_mark ? `${p.valuation.latest_mark.basis}, ${p.valuation.latest_mark.announced}` : undefined} />
              </div>
              <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">
                {String(p.market.source ?? "")}
                {p.market.low_52w != null ? ` · 52-week range ${num(p.market.low_52w as number, 2)} to ${num(p.market.high_52w as number, 2)}` : ""}
                {p.listing?.secondary_of ? ` · secondary listing; primary on ${p.listing.secondary_of.toUpperCase()}` : ""}
                {p.listing ? <> · <Link className="hover:underline" href={`/app/markets/screener?exchange=${p.listing.exchange}${p.listing.sector ? `&sector=${encodeURIComponent(p.listing.sector)}` : ""}`}>peers on {p.listing.exchange_name}</Link></> : null}
              </p>
            </section>
          )}

          {fin ? (
            <section>
              <div className="flex flex-wrap items-center gap-3">
                <h3 className="eyebrow">Financial statements</h3>
                <Pill value={financialsStatus} title="Accounting identity checks" />
              </div>
              <p className="mt-2 text-[0.8125rem] text-[color:var(--muted)]">
                {fin.source_url ? (
                  <a href={fin.source_url} target="_blank" rel="noreferrer" className="hover:underline">
                    {fin.source}
                  </a>
                ) : (
                  fin.source
                )}
                {fin.period ? ` · period ended ${fin.period.end}${fin.period.months ? ` (${fin.period.months} months)` : ""}` : ""}
                {fin.currency ? ` · ${fin.currency}` : ""}
                {fin.basis ? ` · ${fin.basis}` : ""}
              </p>
              <div className="mt-4">
                <Table head={["Line item", "Current", "Prior", "Check"]} minWidth="32rem">
                  {ORDER.filter((k) => fin.items[k]).map((k) => (
                    <tr key={k}>
                      <Td>{words(k)}</Td>
                      <Td className="kbd">{compact(fin.items[k].current)}</Td>
                      <Td className="kbd text-[color:var(--muted)]">{fin.items[k].prior != null ? compact(fin.items[k].prior!) : ""}</Td>
                      <Td>
                        <Pill value={fin.status?.[k] ?? "unchecked"} />
                      </Td>
                    </tr>
                  ))}
                </Table>
              </div>
              {fin.checks.length > 0 && (
                <ul className="mt-4 space-y-1 text-[0.8125rem]">
                  {fin.checks.map((c) => (
                    <li key={c.check} className={c.passed ? "text-verified" : "text-risk"}>
                      {c.passed ? "✓" : "✗"} {c.check}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : (
            p.financials_note && <p className="text-[0.875rem] text-[color:var(--muted)]">{p.financials_note}</p>
          )}

          {p.sec_cross_check && p.sec_cross_check.length > 0 && (
            <section>
              <h3 className="eyebrow">Cross-check against SEC filings</h3>
              <div className="mt-3">
                <Table head={["Period", "Field", "Yahoo", "SEC filing", "Match"]} minWidth="32rem">
                  {p.sec_cross_check.map((r) => (
                    <tr key={r.period + r.field}>
                      <Td className="kbd">{r.period}</Td>
                      <Td>{words(r.field)}</Td>
                      <Td className="kbd">{compact(r.yahoo)}</Td>
                      <Td className="kbd">{compact(r.sec_filing)}</Td>
                      <Td>
                        <Pill value={r.match ? "verified" : "inconsistent"} />
                      </Td>
                    </tr>
                  ))}
                </Table>
              </div>
            </section>
          )}

          {p.multiples_withheld && <p className="text-[0.875rem] text-[color:var(--muted)]">Trading multiples withheld: {p.multiples_withheld}</p>}
          {p.multiples && Object.keys(p.multiples).length > 0 && (
            <section>
              <h3 className="eyebrow">Trading multiples</h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-4">
                {Object.entries(p.multiples).map(([k, v]) => (
                  <Stat key={k} label={MULTIPLES[k] ?? k} value={k === "dividendYield" ? `${num(v * 100, 2)}%` : num(v, 2)} />
                ))}
              </div>
            </section>
          )}

          <section>
            <h3 className="eyebrow">Private markets and transactions</h3>
            <div className="mt-3 grid gap-3 sm:grid-cols-4">
              <Stat label="Deals involving the company" value={p.private_markets.deal_count} />
              <Stat label="Equity raised" value={usd(p.private_markets.equity_raised_usd)} />
              <Stat label="Debt raised" value={usd(p.private_markets.debt_raised_usd)} />
              <Stat label="Last round" value={p.private_markets.last_round ? words(p.private_markets.last_round) : "n/a"} />
            </div>
            {p.private_markets.investors_and_lenders.length > 0 && (
              <p className="mt-4 text-[0.875rem] text-[color:var(--muted)]">
                Investors and lenders:{" "}
                {p.private_markets.investors_and_lenders.map((n, i) => (
                  <span key={n}>
                    {i > 0 && ", "}
                    <Link href={`/app/investors/${encodeURIComponent(n)}`} className="hover:underline">
                      {n}
                    </Link>
                  </span>
                ))}
              </p>
            )}
            {p.private_markets.deals.length > 0 && (
              <div className="mt-4">
                <DealRows deals={p.private_markets.deals} />
              </div>
            )}
          </section>

          {p.valuation.public_bridge && (() => {
            const b = p.valuation.public_bridge;
            return (
              <section>
                <h3 className="eyebrow">Private mark against listed peers</h3>
                <p className="mt-2 max-w-3xl text-[0.875rem] leading-relaxed text-[color:var(--muted)]">
                  The latest mark of {usd(b.valuation_usd)}{b.announced ? ` (${b.announced})` : ""} would be larger than {b.larger_than} of {b.peers} listed {b.sector.toLowerCase()} companies
                  {b.scope === "country" ? ` in ${p.country_name ?? b.country}` : " across Africa"} (median listed cap {usd(b.peer_median_cap_usd)}).
                  {b.peer_ytd_usd != null ? ` Those listed peers are ${b.peer_ytd_usd >= 0 ? "up" : "down"} ${Math.abs(b.peer_ytd_usd * 100).toFixed(1)}% in dollars this year.` : ""}
                </p>
                <div className="mt-3 grid gap-2 sm:grid-cols-5">
                  {b.largest_peers.map((r) => (
                    <Link key={`${r.exchange}:${r.symbol}`} href={`/app/companies?${new URLSearchParams({ name: r.name, exchange: r.exchange, symbol: r.symbol })}`} className="rounded-lg border hairline p-3 text-[0.8125rem] hover:bg-white/[0.03]">
                      <span className="block truncate">{r.name}</span>
                      <span className="kbd text-[color:var(--muted)]">{usd(r.mcap_usd)}</span>
                    </Link>
                  ))}
                </div>
                <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">{b.note}</p>
              </section>
            );
          })()}

          {p.valuation.comparables.deals.length > 0 && (
            <section>
              <h3 className="eyebrow">Comparable deals</h3>
              <p className="mt-2 text-[0.8125rem] text-[color:var(--dim)]">{p.valuation.comparables.method}</p>
              <div className="mt-4">
                <DealRows deals={p.valuation.comparables.deals} showWhy />
              </div>
            </section>
          )}

          {events && events.length > 0 && (
            <section>
              <h3 className="eyebrow">Corporate events, last 12 months</h3>
              <ul className="mt-3 space-y-2">
                {events.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-baseline gap-2 text-[0.8125rem]">
                    <span className="kbd text-[0.75rem] text-[color:var(--dim)]">{e.day}</span>
                    <Pill value={e.signal_type ?? "event"} />
                    {e.url ? <a href={e.url} target="_blank" rel="noreferrer" className="hover:underline">{e.headline_en || e.headline}</a> : <span>{e.headline_en || e.headline}</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {p.filings && p.filings.length > 0 && (
            <section>
              <h3 className="eyebrow">Filed documents</h3>
              <ul className="mt-3 space-y-1.5 text-[0.8125rem]">
                {p.filings.map((f) => (
                  <li key={f.url}>
                    <span className="kbd mr-2 text-[0.75rem] text-[color:var(--dim)]">{f.filed}</span>
                    <a href={f.url} target="_blank" rel="noreferrer" className="hover:underline">
                      {f.title}
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </Container>
  );
}
