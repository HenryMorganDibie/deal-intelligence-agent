"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { get } from "../../lib/market";

type Exchange = { exchange: string; name: string; currency: string; ytd_usd: number | null; ytd_local: number | null;
  ytd_median_usd: number | null; mcap_usd: number | null; listed: number; priced_today: number; advancers: number; decliners: number;
  index: { name: string; level: number; chg_1d: number | null; date: string } | null };
type Listing = { exchange: string; symbol: string; name: string; sector: string | null; price: number | null; currency: string;
  chg_1d: number | null; ytd_usd: number | null; mcap_usd: number | null };
type Dashboard = {
  market: { exchanges: Exchange[]; largest: Listing[]; mcap_usd: number | null } | null;
  rates: {
    policy_rate: { rate: number; date: string | null; date_kind?: string; source: string | null; source_url: string | null } | null;
    tbills: { date: string | null; source: string | null; source_url: string | null; rows: { tenor_days: number; rate: number; auction_date: string | null }[] } | null;
    stablecoin: { pair: string; rate: number; official_per_usd: number | null; premium: number | null; source?: string } | null;
  };
  investor_origin: { since: string; deals: number; deals_with_known_origin: number; foreign_share: number | null;
    origins: { country: string; name: string; deals: number; share: number; local: boolean }[]; note: string };
  benchmarks: { since: string; deals: number; rank: number | null; countries_ranked: number; africa_deals: number; median_size_usd: number | null;
    africa_median_size_usd: number | null; disclosed_share: number | null; africa_disclosed_share: number | null;
    sectors: { sector: string; deals: number; share: number; africa_share: number }[] };
  elections: { key: string; label: string; page: string | null; dates: { date: string; label: string; past: boolean }[] }[];
  outlook: { years: string[]; projected_from: string; source: string; source_url: string;
    rows: { indicator: string; label: string; values: Record<string, number | null> }[] } | null;
};

const pct = (v: number | null | undefined, digits = 1) => (v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(digits)}%`);
const usd = (v: number | null | undefined) => {
  if (!v) return "n/a";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}bn`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}m`;
  return `$${Math.round(v).toLocaleString("en-US")}`;
};

function Block({ title, children, note }: { title: string; children: React.ReactNode; note?: React.ReactNode }) {
  return (
    <section className="panel p-5">
      <h3 className="font-medium">{title}</h3>
      <div className="mt-3">{children}</div>
      {note && <p className="mt-3 text-[0.75rem] leading-relaxed text-[color:var(--dim)]">{note}</p>}
    </section>
  );
}

/** The country's live blocks beside its deal history: market, rates and currency, who invests, benchmarks against
 * Africa, elections and the IMF outlook. Each block hides itself when its data is missing. */
export function CountryDashboard({ code, name }: { code: string; name: string }) {
  const [d, setD] = useState<Dashboard | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    get<Dashboard>(`/api/countries/${encodeURIComponent(code)}/dashboard`).then(setD).catch(() => setFailed(true));
  }, [code]);

  if (failed) return null;
  if (!d) return <p className="mt-8 text-sm text-[color:var(--muted)]">Loading markets, rates and investors…</p>;
  const { market, rates, investor_origin: origin, benchmarks: b, elections, outlook } = d;

  return (
    <div className="mt-10 space-y-4">
      <h2 className="eyebrow">{name} today</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        {market && (
          <Block title="Stock market" note="Dollar returns are cap-weighted where market values are published, from the daily close.">
            {market.exchanges.map((x) => (
              <div key={x.exchange} className="grid grid-cols-3 gap-3 text-sm">
                <div><p className="text-[0.75rem] text-[color:var(--muted)]">{x.name}</p><p className="font-semibold">{usd(x.mcap_usd)}</p></div>
                <div><p className="text-[0.75rem] text-[color:var(--muted)]">This year, in dollars</p><p className="font-semibold">{pct(x.ytd_usd ?? x.ytd_median_usd)}</p></div>
                <div><p className="text-[0.75rem] text-[color:var(--muted)]">Today</p><p className="font-semibold">{x.advancers} up · {x.decliners} down</p></div>
              </div>
            ))}
            {market.largest.length > 0 && (
              <table className="mt-4 w-full text-left text-[0.8125rem]">
                <thead className="text-[color:var(--muted)]"><tr><th className="py-1 font-normal">Largest listed</th><th className="py-1 font-normal">Value</th><th className="py-1 font-normal">This year ($)</th></tr></thead>
                <tbody>
                  {market.largest.slice(0, 6).map((r) => (
                    <tr key={`${r.exchange}-${r.symbol}`} className="border-t hairline">
                      <td className="py-1.5"><Link className="hover:underline" href={`/companies?name=${encodeURIComponent(r.name)}`}>{r.name}</Link></td>
                      <td className="py-1.5">{usd(r.mcap_usd)}</td><td className="py-1.5">{pct(r.ytd_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <Link href={`/markets/screener?exchange=${market.exchanges[0]?.exchange}`} className="mt-3 inline-block text-[0.8125rem] underline underline-offset-2">Screen every listing</Link>
          </Block>
        )}

        {(rates.policy_rate || rates.tbills || rates.stablecoin) && (
          <Block title="Rates and currency" note="Each figure carries its date. The stablecoin rate is what USDT trades for locally; its premium over the official rate is a market signal, not an official rate.">
            <div className="grid grid-cols-2 gap-3 text-sm">
              {rates.policy_rate && (
                <div><p className="text-[0.75rem] text-[color:var(--muted)]">Policy rate</p>
                  <p className="font-semibold">{rates.policy_rate.rate}%</p>
                  <p className="text-[0.75rem] text-[color:var(--dim)]">{rates.policy_rate.date}{rates.policy_rate.source ? ` · ${rates.policy_rate.source}` : ""}{rates.policy_rate.date_kind === "observation" ? " · unconfirmed" : ""}</p></div>
              )}
              {rates.stablecoin && (
                <div><p className="text-[0.75rem] text-[color:var(--muted)]">Dollar: official vs stablecoin</p>
                  <p className="font-semibold">{rates.stablecoin.official_per_usd?.toLocaleString("en-US") ?? "n/a"} · {rates.stablecoin.rate.toLocaleString("en-US")}</p>
                  <p className="text-[0.75rem] text-[color:var(--dim)]">Premium {pct(rates.stablecoin.premium)} ({rates.stablecoin.pair})</p></div>
              )}
            </div>
            {rates.tbills && rates.tbills.rows.length > 0 && (
              <div className="mt-4">
                <p className="text-[0.75rem] text-[color:var(--muted)]">Treasury bills, latest auction {rates.tbills.date ?? ""}</p>
                <div className="mt-1 flex flex-wrap gap-2">
                  {rates.tbills.rows.map((r) => <span key={r.tenor_days} className="rounded-md border hairline px-2 py-1 text-[0.8125rem]">{r.tenor_days} days: <b>{r.rate}%</b></span>)}
                </div>
              </div>
            )}
          </Block>
        )}

        {origin.origins.length > 0 && (
          <Block title="Who invests here" note={`Deals since ${origin.since}: ${origin.deals_with_known_origin} of ${origin.deals} have investors whose home country is known. ${origin.note}`}>
            <p className="text-sm">{origin.foreign_share !== null ? <>Foreign investors are in <b>{pct(origin.foreign_share, 0)}</b> of known investor appearances.</> : null}</p>
            <ul className="mt-3 space-y-1.5">
              {origin.origins.slice(0, 8).map((o) => (
                <li key={o.country} className="flex items-center gap-2 text-[0.8125rem]">
                  <span className="w-32 shrink-0 truncate">{o.name}{o.local ? " (local)" : ""}</span>
                  <span className="h-2 rounded-full bg-verified/60" style={{ width: `${Math.max(4, o.share * 100)}%`, maxWidth: "60%" }} />
                  <span className="text-[color:var(--muted)]">{o.deals} deal{o.deals === 1 ? "" : "s"}</span>
                </li>
              ))}
            </ul>
            <Link href={`/market-briefs/new?country=${code}`} className="mt-3 inline-block text-[0.8125rem] underline underline-offset-2">Brief on investors in {name}</Link>
          </Block>
        )}

        <Block title={`${name} against Africa`} note={`Last 12 months, since ${b.since}. Medians use disclosed amounts only.`}>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div><p className="text-[0.75rem] text-[color:var(--muted)]">Rank by deals</p><p className="font-semibold">{b.rank ? `${b.rank} of ${b.countries_ranked}` : "n/a"}</p><p className="text-[0.75rem] text-[color:var(--dim)]">{b.deals} of {b.africa_deals ?? "n/a"} deals</p></div>
            <div><p className="text-[0.75rem] text-[color:var(--muted)]">Median deal</p><p className="font-semibold">{usd(b.median_size_usd)}</p><p className="text-[0.75rem] text-[color:var(--dim)]">Africa {usd(b.africa_median_size_usd)}</p></div>
            <div><p className="text-[0.75rem] text-[color:var(--muted)]">Amount disclosed</p><p className="font-semibold">{pct(b.disclosed_share, 0)}</p><p className="text-[0.75rem] text-[color:var(--dim)]">Africa {pct(b.africa_disclosed_share, 0)}</p></div>
          </div>
          {b.sectors.length > 0 && (
            <table className="mt-4 w-full text-left text-[0.8125rem]">
              <thead className="text-[color:var(--muted)]"><tr><th className="py-1 font-normal">Sector</th><th className="py-1 font-normal">Share here</th><th className="py-1 font-normal">Share in Africa</th></tr></thead>
              <tbody>{b.sectors.map((s) => (
                <tr key={s.sector} className="border-t hairline"><td className="py-1.5">{s.sector}</td><td className="py-1.5">{pct(s.share, 0)}</td><td className="py-1.5">{pct(s.africa_share, 0)}</td></tr>
              ))}</tbody>
            </table>
          )}
        </Block>

        {outlook && (
          <Block title="IMF outlook" note={<>Figures from {outlook.projected_from} on are IMF projections. Source: <a className="underline" href={outlook.source_url} target="_blank" rel="noreferrer">{outlook.source}</a>.</>}>
            <table className="w-full text-left text-[0.8125rem]">
              <thead className="text-[color:var(--muted)]"><tr><th className="py-1 font-normal" />{outlook.years.map((y) => <th key={y} className="py-1 font-normal">{y}{y >= outlook.projected_from ? "*" : ""}</th>)}</tr></thead>
              <tbody>{outlook.rows.map((r) => (
                <tr key={r.indicator} className="border-t hairline"><td className="py-1.5 pr-2">{r.label}</td>
                  {outlook.years.map((y) => <td key={y} className="py-1.5">{r.values[y] ?? "n/a"}</td>)}</tr>
              ))}</tbody>
            </table>
          </Block>
        )}

        {elections.length > 0 && (
          <Block title="Elections">
            {elections.map((e) => (
              <div key={e.key} className="text-sm">
                <p className="font-medium">{e.label}</p>
                <ul className="mt-1 space-y-0.5 text-[0.8125rem] text-[color:var(--muted)]">
                  {e.dates.map((x) => <li key={x.date}>{x.date}: {x.label}{x.past ? " (held)" : ""}</li>)}
                </ul>
                {e.page && <Link href={e.page} className="mt-2 inline-block text-[0.8125rem] underline underline-offset-2">Follow results and incidents</Link>}
              </div>
            ))}
          </Block>
        )}
      </div>
    </div>
  );
}
