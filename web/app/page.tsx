import { FinalCta, SiteFooter } from "../components/Closing";
import { Example } from "../components/Example";
import { Hero } from "../components/Hero";
import { MarketPulse } from "../components/MarketPulse";
import { Problem } from "../components/Problem";
import { SiteNav } from "../components/SiteNav";
import { SourceMarquee } from "../components/SourceMarquee";
import { getMarkets, getPulse, getShowcase } from "../lib/pulse";
import { MarketsToday } from "../components/MarketsToday";
import corporateOfWeekArchive from "../data/corporate-of-week.json";
import { ArrowRight, Container, Reveal } from "../components/primitives";

export const revalidate = 60;

type CorporateSource = { publisher: string; title: string; url: string; date: string | null; kind: string };
type CorporateSelection = {
  company: string; company_url: string; headline: string; deal_type: string; amount_usd: number | null;
  country: string | null; sector: string | null; announced: string | null; score: number;
  independent_stories: number; transaction_records: number; related_events: number; reasons: string[];
  sources: CorporateSource[]; method: string; period_start: string; period_end: string; selected_at: string;
  runner_ups?: { company: string; score: number; reasons: string[] }[];
  companies?: CorporateSelection[];
};
const corporateSelection = (corporateOfWeekArchive as { current: CorporateSelection | null }).current;
const corporateCompanies = (corporateSelection?.companies?.length ? corporateSelection.companies : corporateSelection ? [corporateSelection] : [])
  .filter((company) => company.sources.some((source) => source.kind === "corporate_event"))
  .filter((company) => !["ma_activity", "m_and_a_activity", "m&a", "merger", "acquisition"].includes(company.deal_type.toLowerCase()));
function displayDate(value: string | null | undefined): string {
  if (!value) return "Date not available";
  const parsed = new Date(value.slice(0, 10) + "T00:00:00Z");
  return Number.isNaN(parsed.getTime()) ? "Date not available" :
    parsed.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

const CAPABILITIES = [
  {
    title: "Discover deals",
    body: "Search reported PE, VC, debt and M&A transactions with source links and field-level evidence.",
    href: "/app/deals",
    label: "Explore the deal feed",
  },
  {
    title: "Track companies",
    body: "Review financial statements, company events and signals with the underlying evidence in view.",
    href: "/app/companies",
    label: "Explore company research",
  },
  {
    title: "Follow markets",
    body: "Daily prices, returns in dollars and valuations for 1,500+ listed African companies, with a valuation workspace that checks every input against evidence.",
    href: "/app/markets",
    label: "Explore markets",
  },
  {
    title: "Understand countries",
    body: "Compare country context, investor activity and risk while keeping data coverage and gaps visible.",
    href: "/app/countries",
    label: "Explore country coverage",
  },
];

export default async function LandingPage() {
  const [pulse, showcase, markets] = await Promise.all([getPulse(), getShowcase(), getMarkets()]);
  return (
    <div className="relative overflow-x-clip">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-full focus:bg-bone focus:px-4 focus:py-2 focus:text-ink"
      >
        Skip to content
      </a>
      <SiteNav />
      <main id="main">
        <Hero pulse={pulse} brief={showcase?.hero ?? null} />
        <SourceMarquee />
        <Problem compact />
        <MarketPulse pulse={pulse} compact />
        <MarketsToday data={markets} />
        <section aria-labelledby="corporate-week-title" className="border-t hairline py-14 sm:py-16">
          <Container>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="eyebrow">Evidence-led corporate shortlist</p>
                <h2 id="corporate-week-title" className="h2 mt-3">Corporate of the Week</h2>
                <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[color:var(--muted)]">
                  Up to five companies with verified, source-linked corporate events from the latest seven complete days, such as leadership changes, earnings, regulatory action or restructuring. Transaction headlines already shown in Latest Deals are excluded. The list refreshes daily; fewer companies appear when evidence is limited.
                </p>
              </div>
              {corporateSelection && (
                <div className="text-right">
                  <p className="eyebrow">Week ending {displayDate(corporateSelection.period_end)}</p>
                  <p className="mt-2 text-xs text-[color:var(--muted)]">Updated {displayDate(corporateSelection.selected_at)}</p>
                </div>
              )}
            </div>
            {corporateSelection && corporateCompanies.length ? (
              <div className="mt-6 grid gap-4">
                {corporateCompanies
                  .slice(0, 5)
                  .sort((a, b) => String(b.announced || "").localeCompare(String(a.announced || "")))
                  .map((company, index) => (
                    <article key={company.company} className="panel overflow-hidden">
                      <div className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(220px,0.35fr)]">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="kbd">#{index + 1}</span>
                            <p className="eyebrow">
                              {company.country || "Market not specified"}
                              {company.sector ? " · " + company.sector.replace(/_/g, " ") : ""}
                            </p>
                            <span className="text-xs text-[color:var(--muted)]">Announced {displayDate(company.announced)}</span>
                          </div>
                          <h3 className="h3 mt-3">{company.company}</h3>
                          <p className="mt-2 text-sm leading-relaxed">{company.headline}</p>
                          <div className="mt-4 flex flex-wrap gap-2 text-xs text-[color:var(--muted)]">
                            <span className="kbd">{company.deal_type.replace(/_/g, " ")}</span>
                            <span className="kbd">{company.independent_stories} directly matching {company.independent_stories === 1 ? "source" : "sources"}</span>
                            {company.related_events > 0 && <span className="kbd">{company.related_events} related event signals</span>}
                          </div>
                          <div className="mt-4 flex flex-wrap gap-3">
                            <a href={company.company_url} className="btn btn-primary">Explore company <ArrowRight /></a>
                            {company.sources[0] && (
                              <a href={company.sources[0].url} target="_blank" rel="noopener noreferrer" className="btn btn-ghost">
                                Read source <ArrowRight />
                              </a>
                            )}
                          </div>
                        </div>
                        <div className="border-t hairline pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
                          <h4 className="text-sm font-medium">Why it made the list</h4>
                          <ul className="mt-3 space-y-2">
                            {company.reasons.slice(0, 3).map((reason) => (
                              <li key={reason} className="flex gap-2 text-xs leading-relaxed text-[color:var(--muted)]">
                                <span aria-hidden="true" className="text-verified">•</span><span>{reason}</span>
                              </li>
                            ))}
                          </ul>
                          <p className="mt-4 border-t hairline pt-3 text-xs leading-relaxed text-[color:var(--dim)]">
                            Evidence links: {company.sources.length}. Ranking score: {company.score.toFixed(2)} (not an investment rating).
                          </p>
                        </div>
                      </div>
                      <div className="border-t hairline px-5 py-4 sm:px-6">
                        <p className="text-xs font-medium text-[color:var(--muted)]">Source trail</p>
                        <ul className="mt-2 grid gap-2 sm:grid-cols-2">
                          {company.sources.slice(0, 2).map((source) => (
                            <li key={source.url} className="min-w-0">
                              <a href={source.url} target="_blank" rel="noopener noreferrer" className="text-xs hover:text-verified hover:underline">
                                {source.title}
                              </a>
                              <p className="mt-1 text-xs text-[color:var(--dim)]">{source.publisher}{source.date ? " · " + displayDate(source.date) : ""}</p>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </article>
                  ))}
                <p className="text-xs leading-relaxed text-[color:var(--dim)]">
                  The list only includes dated, source-linked non-transaction corporate events. Companies are ordered by event date, newest first;
                  the score supports editorial context and is not a probability, company rating, or investment recommendation.
                </p>
              </div>
            ) : (
              <div className="panel mt-6 p-6 sm:p-8">
                <h3 className="h3">The corporate shortlist is being prepared.</h3>
                <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[color:var(--muted)]">
                  Companies appear only when a dated corporate event and inspectable source evidence meet the selection rules.
                  If evidence is insufficient, the page will not invent entries.
                </p>
              </div>
            )}
          </Container>
        </section>
        <section aria-labelledby="capabilities-title" className="border-t hairline py-20 sm:py-24">
          <Container>
            <Reveal>
              <p className="eyebrow">The platform</p>
              <h2 id="capabilities-title" className="h2 mt-4 max-w-3xl">
                Find the opportunity. Inspect the evidence. Make your own call.
              </h2>
              <p className="lede mt-5 max-w-2xl">
                One research workflow for African private markets and company intelligence, with the source trail and limitations visible.
              </p>
            </Reveal>
            <div className="mt-10 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {CAPABILITIES.map((item, i) => (
                <Reveal key={item.title} delay={i * 70}>
                  <article className="panel flex h-full flex-col p-6">
                    <h3 className="h3">{item.title}</h3>
                    <p className="mt-3 flex-1 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">{item.body}</p>
                    <a href={item.href} className="mt-6 inline-flex items-center gap-2 text-[0.875rem] text-verified hover:underline">
                      {item.label}<ArrowRight />
                    </a>
                  </article>
                </Reveal>
              ))}
            </div>
            <div className="mt-6">
              <a href="/platform" className="btn btn-ghost">Explore the full platform <ArrowRight /></a>
            </div>
          </Container>
        </section>
        <Example brief={showcase?.example ?? showcase?.hero ?? null} />
        <section className="border-t hairline py-16 sm:py-20">
          <Container className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
            <div>
              <p className="eyebrow">Built for scrutiny</p>
              <h2 className="h2 mt-3 max-w-2xl">Every claim has a trail. Every dataset has limits.</h2>
              <p className="mt-4 max-w-2xl text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
                See how detection works, how companies are attributed to events, what each country covers, and where the evidence is incomplete.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <a href="/how-it-works" className="btn btn-ghost">How it works</a>
              <a href="/limits" className="btn btn-ghost">Known limits</a>
            </div>
          </Container>
        </section>
        <FinalCta />
      </main>
      <SiteFooter />
    </div>
  );
}
