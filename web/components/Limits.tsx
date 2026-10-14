import { LINKS } from "../lib/site";
import { ArrowRight, Container, Heading, Reveal, Section } from "./primitives";

const LIMITS = [
  {
    title: "JSE history is current-day only",
    body: "Free SENS access covers today's announcements, and the JSE site blocks automated access. Older JSE events come from news.",
  },
  {
    title: "Backtests are still filling up",
    body: "Outcomes are now labelled automatically, against a market benchmark and SEC filings, with recall. The numbers need about 50 outcomes per signal type, so they firm up over the first months.",
  },
  {
    title: "Africa has no filing-based ground truth",
    body: "US signals are confirmed by later SEC filings. African ones are judged on price reaction only, and calibrate on African outcomes once 10 per signal type exist.",
  },
  {
    title: "Severity means strength, not bad news",
    body: "A widely reported earnings beat can be CRITICAL. Direction is shown separately as an expected move up or down.",
  },
  {
    title: "Patterns, in English and French",
    body: "Reproducible and auditable by design. Francophone disclosures are now covered; Arabic and Portuguese are not, and novel phrasings can still be missed.",
  },
  {
    title: "Unlisted companies have no prices",
    body: "Private, OTC and thinly traded names often return no market data, so their outcomes stay unlabelled unless a filing confirms them.",
  },
];

export function Limits() {
  return (
    <Section id="limits" labelledBy="limits-title">
      <Container>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <Heading
            index="09"
            eyebrow="Honest limits"
            id="limits-title"
            title="What it does not do yet."
            lede="Written down in the repository, not discovered in production."
          />
          <Reveal>
            <a href={LINKS.limitations} className="btn btn-ghost" target="_blank" rel="noreferrer">
              Full list in ARCHITECTURE.md
              <ArrowRight />
            </a>
          </Reveal>
        </div>
        <div className="mt-14 grid gap-px overflow-hidden rounded-[14px] border hairline bg-[color:var(--line)] sm:grid-cols-2 lg:grid-cols-3">
          {LIMITS.map((l, i) => (
            <Reveal key={l.title} delay={(i % 3) * 60} className="bg-[color:var(--bg)] p-6">
              <p className="kbd text-[0.6875rem] text-[color:var(--dim)]">{String(i + 1).padStart(2, "0")}</p>
              <h3 className="h3 mt-4">{l.title}</h3>
              <p className="mt-3 text-[0.875rem] leading-relaxed text-[color:var(--muted)]">{l.body}</p>
            </Reveal>
          ))}
        </div>
      </Container>
    </Section>
  );
}
