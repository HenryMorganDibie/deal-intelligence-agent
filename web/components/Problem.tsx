import { Container, Heading, Reveal, Section } from "./primitives";

const ROWS = [
  ["Who decides a signal exists", "The model", "115 deterministic patterns. Zero candidates means zero signals."],
  ["Severity", "The model's opinion", "Rule-strength bands; CRITICAL needs two independent sources"],
  ["Confidence", "An opaque float", "The measured hit rate of past flags like it, with its sample size"],
  ["Evidence", "Whatever the model recalls", "A source document, a publication date and a credited publisher"],
  ["Wrong company", "Silently attributed", "Must be named in the same clause as the event, or it is dropped"],
  ["Audit", "None", "SHA-256 hash-chained log that detects edited and deleted entries"],
];

export function Problem({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <Section id="problem" labelledBy="problem-title" className="py-14 sm:py-16">
        <Container className="grid gap-6 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <p className="eyebrow">The problem</p>
            <h2 id="problem-title" className="h2 mt-3 max-w-3xl">
              Finding a deal is easy. Verifying what happened is the hard part.
            </h2>
            <p className="mt-4 max-w-3xl text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
              Reports can disagree, key terms may be undisclosed, and a company mentioned in a headline is not always the company the event is about. Deal Intelligence connects records to their sources and makes uncertainty visible.
            </p>
          </div>
          <a href="/how-it-works" className="btn btn-ghost whitespace-nowrap">See how it works <span aria-hidden>→</span></a>
        </Container>
      </Section>
    );
  }
  return (
    <Section id="problem" labelledBy="problem-title">
      <Container>
        <Heading
          index="01"
          eyebrow="The problem"
          id="problem-title"
          title={
            <>
              Most AI finance tools let the model decide.{" "}
              <span className="text-[color:var(--muted)]">That is the part you cannot audit.</span>
            </>
          }
          lede="When a language model both finds and explains a signal, a confident paragraph is indistinguishable from a correct one. Here the jobs are separated: rules find, calibration weighs, the LLM only explains."
        />

        <Reveal delay={120} className="mt-14">
          <div className="panel overflow-hidden">
            <div className="hidden grid-cols-[1fr_1fr_1.4fr] border-b hairline px-6 py-3 sm:grid">
              <span className="eyebrow">Dimension</span>
              <span className="eyebrow">Typical AI tool</span>
              <span className="eyebrow text-verified">Deal Intelligence</span>
            </div>
            <ul>
              {ROWS.map(([dim, typical, ours], i) => (
                <li
                  key={dim}
                  className={`grid gap-1 px-6 py-4 sm:grid-cols-[1fr_1fr_1.4fr] sm:gap-4 ${i ? "border-t hairline" : ""}`}
                >
                  <span className="text-[0.9375rem] font-medium">{dim}</span>
                  <span className="text-[0.9375rem] text-[color:var(--dim)] line-through decoration-white/15 sm:no-underline">
                    {typical}
                  </span>
                  <span className="text-[0.9375rem] text-[color:var(--text)]">
                    <span aria-hidden className="mr-2 text-verified">✓</span>
                    {ours}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
