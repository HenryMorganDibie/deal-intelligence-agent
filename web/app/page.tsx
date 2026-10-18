import { FinalCta, SiteFooter } from "../components/Closing";
import { Example } from "../components/Example";
import { Hero } from "../components/Hero";
import { MarketPulse } from "../components/MarketPulse";
import { Problem } from "../components/Problem";
import { SiteNav } from "../components/SiteNav";
import { SourceMarquee } from "../components/SourceMarquee";
import { getPulse, getShowcase, usd } from "../lib/pulse";
import corporateOfWeekArchive from "../data/corporate-of-week.json";
import { ArrowRight, Container, Reveal } from "../components/primitives";

export const revalidate = 60;

type CorporateSource = { publisher: string; title: string; url: string; date: string | null; kind: string };
type CorporateSelection = {
  company: string; company_url: string; headline: string; deal_type: string; amount_usd: number | null;
  country: string | null; sector: string | null; announced: string | null; score: number;
  independent_stories: number; transaction_records: number; related_events: number; reasons: string[];
  sources: CorporateSource[]; method: string; period_start: string; period_end: string; selected_at: string;
  runner_ups: { company: string; score: number; reasons: string[] }[];
};
const corporateSelection = (corporateOfWeekArchive as { current: CorporateSelection | null }).current;
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
    title: "Understand markets",
    body: "Compare country context, investor activity and risk while keeping data coverage and gaps visible.",
    href: "/app/countries",
    label: "Explore country coverage",
  },
];

export default async function LandingPage() {
  const [pulse, showcase] = await Promise.all([getPulse(), getShowcase()]);
  return (
    <div className="relative">
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
        <section aria-labelledby="corporate-week-title" className="border-t hairline py-14 sm:py-16">
          <Container>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="eyebrow">Evidence-led editorial selection</p>
                <h2 id="corporate-week-title" className="h2 mt-3">Corporate of the Week</h2>
                <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[color:var(--muted)]">
                  One company selected from the previous seven days of reported transactions, ranked using disclosed deal
                  significance, independent reporting, recency, and matching corporate-event evidence.
                </p>
              </div>
              {corporateSelection && <p className="eyebrow">Week ending {displayDate(corporateSelection.period_end)}</p>}
            </div>
            {corporateSelection ? (
              <div className="panel mt-6 overflow-hidden">
                <div className="grid gap-6 p-6 sm:p-8 lg:grid-cols-[1.2fr_0.8fr]">
                  <div>
                    <p className="eyebrow">
                      {corporateSelection.country || "Market not specified"}
                      {corporateSelection.sector ? " · " + corporateSelection.sector.replace(/_/g, " ") : ""}
                      {corporateSelection.announced ? " · Reported " + displayDate(corporateSelection.announced) : ""}
                    </p>
                    <h3 className="h2 mt-3">{corporateSelection.company}</h3>
                    <p className="mt-4 text-base leading-relaxed">{corporateSelection.headline}</p>
                    <div className="mt-5 flex flex-wrap gap-2 text-sm text-[color:var(--muted)]">
                      <span className="kbd">{corporateSelection.deal_type.replace(/_/g, " ")}</span>
                      {corporateSelection.amount_usd != null && <span className="kbd">{usd(corporateSelection.amount_usd)} disclosed</span>}
                      <span className="kbd">{corporateSelection.independent_stories} independent {corporateSelection.independent_stories === 1 ? "story" : "stories"}</span>
                      {corporateSelection.related_events > 0 && <span className="kbd">{corporateSelection.related_events} related event signals</span>}
                    </div>
                    <div className="mt-6 flex flex-wrap gap-3">
                      <a href={corporateSelection.company_url} className="btn btn-primary">Explore company <ArrowRight /></a>
                      {corporateSelection.sources[0] && (
                        <a href={corporateSelection.sources[0].url} target="_blank" rel="noopener noreferrer" className="btn btn-ghost">
                          Read original source <ArrowRight />
                        </a>
                      )}
                    </div>
                  </div>
                  <div className="border-t hairline pt-5 lg:border-l lg:border-t-0 lg:pl-7 lg:pt-0">
                    <h4 className="h3">Why it was selected</h4>
                    <ul className="mt-4 space-y-3">
                      {corporateSelection.reasons.map((reason) => (
                        <li key={reason} className="flex gap-2 text-sm leading-relaxed text-[color:var(--muted)]">
                          <span aria-hidden="true" className="text-verified">•</span><span>{reason}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-5 border-t hairline pt-4 text-xs leading-relaxed text-[color:var(--dim)]">
                      Ranking score: {corporateSelection.score.toFixed(2)}. This is a relative selection score, not a
                      probability, company rating, or investment recommendation.
                    </p>
                  </div>
                </div>
                <div className="border-t hairline px-6 py-5 sm:px-8">
                  <h4 className="h3">Evidence trail ({corporateSelection.sources.length} source links)</h4>
                  <ul className="mt-3 grid gap-3 md:grid-cols-2">
                    {corporateSelection.sources.slice(0, 4).map((source) => (
                      <li key={source.url} className="min-w-0">
                        <a href={source.url} target="_blank" rel="noopener noreferrer" className="text-sm hover:text-verified hover:underline">
                          {source.title}
                        </a>
                        <p className="mt-1 text-xs text-[color:var(--muted)]">
                          {source.publisher}{source.date ? " · " + displayDate(source.date) : ""}
                          {" · "}{source.kind === "related_company_coverage" ? "Related company coverage" : source.kind === "corporate_event" ? "Corporate event" : "Transaction report"}
                        </p>
                      </li>
                    ))}
                  </ul>
                  {corporateSelection.runner_ups.length > 0 && (
                    <details className="mt-5 border-t hairline pt-4">
                      <summary className="cursor-pointer text-sm hover:text-verified">Other companies considered</summary>
                      <ul className="mt-3 grid gap-3 sm:grid-cols-3">
                        {corporateSelection.runner_ups.map((candidate) => (
                          <li key={candidate.company} className="rounded-lg border hairline p-3">
                            <p className="text-sm font-medium">{candidate.company}</p>
                            <p className="mt-1 text-xs text-[color:var(--muted)]">Score {candidate.score.toFixed(2)}</p>
                            <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">{candidate.reasons[0]}</p>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                  <p className="mt-4 text-xs leading-relaxed text-[color:var(--dim)]">{corporateSelection.method}</p>
                </div>
              </div>
            ) : (
              <div className="panel mt-6 p-6 sm:p-8">
                <h3 className="h3">The weekly selection is being prepared.</h3>
                <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[color:var(--muted)]">
                  This section only features a company when a dated transaction and inspectable source evidence meet the
                  selection rules. If the evidence is insufficient, it will not invent a winner.
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
            <div className="mt-10 grid gap-3 md:grid-cols-3">
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
