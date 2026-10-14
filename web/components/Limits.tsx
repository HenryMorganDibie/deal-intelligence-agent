import { ciText, type Quality } from "../lib/pulse";
import { LINKS } from "../lib/site";
import { ArrowRight, Container, Heading, Reveal, Section } from "./primitives";

const limits = (q: Quality | null) => [
  {
    title: "Deals are what gets reported",
    body: q?.dealComplete
      ? `Extracted from public reporting: undisclosed deals cannot appear. On a held-out test set, ${ciText(q.dealPrecision)} of extracted records are genuine transactions and ${ciText(q.dealComplete)} have every field right. Each deal page shows which of its fields are corroborated, single-source or uncertain.`
      : "Extracted from public reporting: undisclosed deals cannot appear. Each deal page shows which of its fields are corroborated, single-source or uncertain, and the evaluation page measures accuracy by field.",
  },
  {
    title: "Coverage is uneven by country",
    body: "Machine-readable filings and prices exist for NGX and NSE Kenya, vendor data for JSE, EGX and Casablanca. The other 49 countries are covered through news, deals and risk data.",
  },
  {
    title: "Statements are parsed, then checked",
    body: "PDF layouts vary, so each figure is checked against accounting identities and marked verified, inconsistent or unchecked. Interim statements are linked, not parsed.",
  },
  {
    title: "Some signals beat chance, some do not",
    body: "In the backtest only leadership-change flags clearly beat their base rate; regulatory and distress flags look better than chance but on samples too small to be sure, and M&A and credit flags do not. Confirming an event is not the same as a profitable price move, which is measured separately.",
  },
  {
    title: "Country risk uses public data",
    body: "World Bank indicators are annual and often a year old; sovereign ratings and bond spreads are licensed and not included.",
  },
  {
    title: "Patterns, not a trained model",
    body: q?.attributionRecall
      ? `Reproducible and auditable in English, French, Portuguese and Arabic, but phrasings the rules do not cover are missed: on held-out adversarial news headlines the engine found ${ciText(q.attributionRecall)} of real events, with false alarms on ${ciText(q.attributionFalseAlarm)} of no-event headlines.`
      : "Reproducible and auditable in English, French, Portuguese and Arabic, but phrasings the rules do not cover are missed.",
  },
];

export function Limits({ quality = null }: { quality?: Quality | null }) {
  const LIMITS = limits(quality);
  return (
    <Section id="limits" labelledBy="limits-title">
      <Container>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <Heading
            index="09"
            eyebrow="Honest limits"
            id="limits-title"
            title="What it does not do yet."
            lede="Written down up front, not discovered in production."
          />
          <Reveal>
            <a href={LINKS.limitations} className="btn btn-ghost">
              Full list in the methodology
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
