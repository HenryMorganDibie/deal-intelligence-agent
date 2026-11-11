import type { Metadata } from "next";
import Link from "next/link";
import { PublicPage } from "../../components/PublicPage";
import { Container } from "../../components/primitives";
import { usd } from "../../components/app/ui";
import { billYield, countryName, latestBills, loadMarkets, pct } from "../../lib/market-public";

/**
 * African markets today, public: exchanges, sectors, currencies, Treasury bills and policy rates from the platform's
 * daily snapshot. What a market post links to, readable without an account. Share-level screens, quotes and
 * portfolios stay in the app.
 */
export const revalidate = 3600;

export const metadata: Metadata = {
  title: "African markets today | Deal Intelligence",
  description: "Every African stock exchange, sector returns in dollars, currencies, Treasury bill auctions and policy rates, updated daily.",
  alternates: { canonical: "/markets" },
};

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="mt-12">
      <h2 className="h3">{title}</h2>
      {note ? <p className="mt-1 text-sm text-[color:var(--muted)]">{note}</p> : null}
      <div className="mt-4 overflow-x-auto">{children}</div>
    </section>
  );
}

const th = "py-2 pr-4 text-left text-xs font-normal uppercase tracking-wide text-[color:var(--dim)]";
const td = "py-2 pr-4 text-sm";

export default async function MarketsToday() {
  const { overview, instruments } = await loadMarkets();
  const exchanges = (overview?.exchanges ?? []).filter((e) => !e.stale && e.as_of).sort((a, z) => (z.mcap_usd ?? 0) - (a.mcap_usd ?? 0));
  const sectors = (overview?.sectors ?? []).filter((s) => s.shares >= 10 && s.ytd_usd != null).sort((a, z) => (z.ytd_usd ?? 0) - (a.ytd_usd ?? 0));
  const currencies = (overview?.currencies ?? []).filter((c) => c.ytd_vs_usd != null).sort((a, z) => (z.ytd_vs_usd ?? 0) - (a.ytd_vs_usd ?? 0));
  const bills = latestBills(instruments?.tbills);
  const policy = (instruments?.policy_rates ?? []).filter((p) => p.rate != null).sort((a, z) => String(z.date).localeCompare(String(a.date)));
  const asOf = exchanges.map((e) => e.as_of!).sort().at(-1);

  return (
    <PublicPage>
      <Container className="max-w-5xl pb-16 pt-28">
        <p className="eyebrow">Markets</p>
        <h1 className="h2 mt-3 text-[2rem] sm:text-[2.5rem]">African markets today</h1>
        <p className="mt-4 text-[1rem] leading-relaxed text-[color:var(--muted)]">
          {exchanges.length} exchanges, sectors, currencies, Treasury bills and policy rates{asOf ? `, as of ${asOf}` : ""}. Returns
          are in US dollars, so currency moves are included.
        </p>

        <Section title="Exchanges" note="Largest first. Year to date in US dollars.">
          <table className="w-full">
            <thead><tr><th className={th}>Exchange</th><th className={th}>Market value</th><th className={th}>This year (US$)</th><th className={th}>Up / down</th></tr></thead>
            <tbody>
              {exchanges.map((e) => (
                <tr key={e.exchange} className="border-t hairline">
                  <td className={td}>{e.name}{e.name.includes("(") ? "" : ` (${countryName(e.country)})`}</td>
                  <td className={td}>{e.mcap_usd ? usd(e.mcap_usd) : "n/a"}</td>
                  <td className={td}>{pct(e.ytd_usd)}</td>
                  <td className={td}>{e.advancers || e.decliners ? `${e.advancers ?? 0} / ${e.decliners ?? 0}` : "no trades"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Sectors" note="Across every exchange, sectors with ten or more shares.">
          <table className="w-full">
            <thead><tr><th className={th}>Sector</th><th className={th}>This year (US$)</th><th className={th}>Last day</th><th className={th}>Market value</th></tr></thead>
            <tbody>
              {sectors.map((s) => (
                <tr key={s.sector} className="border-t hairline">
                  <td className={td}>{s.sector}</td><td className={td}>{pct(s.ytd_usd)}</td>
                  <td className={td}>{pct(s.chg_1d)}</td><td className={td}>{s.mcap_usd ? usd(s.mcap_usd) : "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Currencies" note="Against the US dollar. A positive figure means the currency strengthened.">
          <table className="w-full">
            <thead><tr><th className={th}>Currency</th><th className={th}>Per US$</th><th className={th}>This year</th></tr></thead>
            <tbody>
              {currencies.map((c) => (
                <tr key={c.currency} className="border-t hairline">
                  <td className={td}>{c.currency}</td>
                  <td className={td}>{c.per_usd?.toLocaleString("en-US", { maximumFractionDigits: 2 }) ?? "n/a"}</td>
                  <td className={td}>{pct(c.ytd_vs_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Treasury bills" note="Latest auction in each country, newest first.">
          <table className="w-full">
            <thead><tr><th className={th}>Country</th><th className={th}>Yields</th><th className={th}>Auction</th></tr></thead>
            <tbody>
              {bills.map((b) => (
                <tr key={b.name} className="border-t hairline">
                  <td className={td}>{b.name}</td>
                  <td className={td}>{b.rows.map((r) => `${r.tenor_label ?? `${r.tenor_days} days`} ${billYield(r)!.toFixed(2)}%`).join(", ")}</td>
                  <td className={td}>{b.date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Policy rates" note="Central bank rates, most recent first. Unconfirmed figures come from a third-party feed.">
          <table className="w-full">
            <thead><tr><th className={th}>Country</th><th className={th}>Rate</th><th className={th}>As of</th></tr></thead>
            <tbody>
              {policy.map((p) => (
                <tr key={`${p.country}-${p.date}`} className="border-t hairline">
                  <td className={td}>{p.country_name ?? p.country}</td><td className={td}>{p.rate}%</td>
                  <td className={td}>{p.date}{p.confirmed_by ? "" : " (unconfirmed)"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <p className="mt-12 text-sm text-[color:var(--muted)]">
          Screen 1,600+ listed shares, see quotes and track a portfolio in the app.{" "}
          <Link href="/app/markets" className="text-verified hover:underline">Open the markets dashboard</Link>
        </p>
      </Container>
    </PublicPage>
  );
}
