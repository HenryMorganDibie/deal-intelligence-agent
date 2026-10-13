import { LINKS } from "../lib/site";
import { ArrowRight, Container, Heading, Reveal, Section } from "./primitives";

const LIMITS = [
  {
    title: "JSE history is current-day only",
    body: "Free SENS access covers today's announcements, and the JSE site blocks automated access. Older JSE events come from news.",
  },
  {
    title: "Attribution is a heuristic",
    body: "The clause rule trades some recall for precision: “Shares of Acme jump after it beats estimates” is missed. Other coverage usually catches the same event.",
  },
  {
    title: "Backtests need outcomes",
    body: "Precision and hit rate are only as good as the outcomes you record. Results need 50+ confirmed outcomes per signal type to mean much.",
  },
  {
    title: "African calibration is thinner",
    body: "Base rates come mostly from US and global research. Treat early severities on African companies with extra caution until feedback accumulates.",
  },
  {
    title: "Severity means strength, not bad news",
    body: "A widely reported earnings beat can be CRITICAL. Direction is shown separately as an expected move up or down.",
  },
  {
    title: "Regex, not a language model, finds signals",
    body: "That is the point: it is reproducible and auditable. It can miss novel phrasings and non-English disclosures.",
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
