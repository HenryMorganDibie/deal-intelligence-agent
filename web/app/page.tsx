import { FinalCta, SiteFooter } from "../components/Closing";
import { Example } from "../components/Example";
import { Hero } from "../components/Hero";
import { MarketPulse } from "../components/MarketPulse";
import { Problem } from "../components/Problem";
import { SiteNav } from "../components/SiteNav";
import { SourceMarquee } from "../components/SourceMarquee";
import { getPulse, getShowcase } from "../lib/pulse";
import { ArrowRight, Container, Reveal } from "../components/primitives";

export const revalidate = 60;

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
        {pulse?.events.latest[0] && (
          <section aria-labelledby="corporate-week-title" className="border-t hairline py-14 sm:py-16">
            <Container>
              <div className="panel overflow-hidden">
                <div className="grid gap-6 p-6 sm:p-8 md:grid-cols-[0.7fr_1.3fr] md:items-center">
                  <div>
                    <p className="eyebrow">Corporate of the Week</p>
                    <h2 id="corporate-week-title" className="h2 mt-3">A company story worth your attention.</h2>
                    <p className="mt-3 text-sm leading-relaxed text-[color:var(--muted)]">
                      A current corporate development surfaced by the event feed, with its source available to inspect.
                    </p>
                  </div>
                  <div className="border-t hairline pt-5 md:border-l md:border-t-0 md:pl-7 md:pt-0">
                    <p className="eyebrow">
                      {pulse.events.latest[0].country?.name ?? "Corporate event"}
                      {pulse.events.latest[0].day ? ` · ${pulse.events.latest[0].day}` : ""}
                    </p>
                    <h3 className="h3 mt-3">{pulse.events.latest[0].headline}</h3>
                    {pulse.events.latest[0].publisher && (
                      <p className="mt-2 text-sm text-[color:var(--muted)]">{pulse.events.latest[0].publisher}</p>
                    )}
                    <div className="mt-5 flex flex-wrap gap-3">
                      {pulse.events.latest[0].url && (
                        <a href={pulse.events.latest[0].url} target="_blank" rel="noopener noreferrer" className="btn btn-primary">
                          Read source <ArrowRight />
                        </a>
                      )}
                      <a href="/app/watchlists" className="btn btn-ghost">Track corporate events <ArrowRight /></a>
                    </div>
                  </div>
                </div>
              </div>
            </Container>
          </section>
        )}
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
