import { count, type Pulse } from "../lib/pulse";
import { ArrowRight, Container, Heading, Reveal, Section } from "./primitives";

const modules = (pulse: Pulse | null) => [
  {
    title: "Companies and financial statements",
    body: "NGX and NSE Kenya audited statements parsed from the filing and checked with accounting identities, figure by figure. Yahoo Finance and SEC cross-checks for other listings.",
    href: "/app/companies",
  },
  {
    title: "PE, VC, debt and M&A transactions",
    body: pulse?.deals.total
      ? `${count(pulse.deals.total)} deals in ${pulse.deals.countries} countries, ${pulse.deals.recent} of them in the last ${pulse.deals.window_days} days, extracted daily in English, French and Portuguese, every source linked.`
      : "1,700+ deals over two years in 48 countries, extracted daily in English, French and Portuguese, every source linked.",
    href: "/app/deals",
  },
  {
    title: "Investors, funds, LPs and GPs",
    body: "Who invested, lent, bought, sold, committed as an LP or closed a fund, with DFIs, PE and VC firms matched across their name variants.",
    href: "/app/investors",
  },
  {
    title: "Valuations and comparable deals",
    body: "Reported and stake-implied valuations, comparables scored on sector, type, country and size, listed multiples.",
    href: "/app/deals",
  },
  {
    title: "Country, currency and sector risk",
    body: "All 54 African countries scored from World Bank data with every formula shown; 42 currencies by regime and depreciation; sector event balance.",
    href: "/app/countries",
  },
  {
    title: "Source-grounded AI research",
    body: "Answers written only from numbered evidence, with citations checked and uncited sentences flagged. Country and sector reports.",
    href: "/app/research",
  },
  {
    title: "Event monitoring and alerts",
    body: "A daily feed of corporate events and deals across 54 countries. Watchlists by company, country and event type, with RSS and webhooks.",
    href: "/app/watchlists",
  },
  {
    title: "Historical outcomes and evaluation",
    body: "A walk-forward backtest with precision against base rates, recall and price hit rates. Weak results are published as they are.",
    href: "/app/evaluation",
  },
  {
    title: "Coverage and verification by country",
    body: "For each country: what is read, which languages, which regulators, and how far a signal there can be verified.",
    href: "/app/coverage",
  },
];

export function Platform({ pulse = null }: { pulse?: Pulse | null }) {
  const MODULES = modules(pulse);
  return (
    <Section id="platform" labelledBy="platform-title">
      <Container>
        <Heading
          index="00"
          eyebrow="The platform"
          id="platform-title"
          title={
            <>
              Intelligence on African companies and private markets.{" "}
              <span className="text-[color:var(--muted)]">All 54 countries, every number sourced.</span>
            </>
          }
          lede="Signal briefs are one part. The same deterministic, auditable approach runs the deals database, investor profiles, company financials, risk scores, research and alerts."
        />
        <div className="mt-14 grid gap-px overflow-hidden rounded-[14px] border hairline bg-[color:var(--line)] sm:grid-cols-2 lg:grid-cols-3">
          {MODULES.map((m, i) => (
            <Reveal key={m.title} delay={(i % 3) * 60} className="bg-[color:var(--bg)]">
              <a href={m.href} className="group block h-full p-6 transition-colors hover:bg-white/[0.02]">
                <h3 className="h3 flex items-center justify-between gap-3">
                  {m.title}
                  <ArrowRight className="shrink-0 text-[color:var(--dim)] transition-colors group-hover:text-verified" />
                </h3>
                <p className="mt-3 text-[0.875rem] leading-relaxed text-[color:var(--muted)]">{m.body}</p>
              </a>
            </Reveal>
          ))}
        </div>
      </Container>
    </Section>
  );
}
