import { Container, Heading, Reveal, Section } from "./primitives";

const ROWS = [
  ["Who decides a signal exists", "The model", "115 deterministic patterns. Zero candidates means zero signals."],
  ["Severity", "The model's opinion", "Calibrated against historical base rates, adjusted by analyst feedback"],
  ["Confidence", "An opaque float", "A materialisation probability plus a 7-part evidence-quality breakdown"],
  ["Evidence", "Whatever the model recalls", "A source document, a publication date and a credited publisher"],
  ["Wrong company", "Silently attributed", "Must be named in the same clause as the event, or it is dropped"],
  ["Audit", "None", "SHA-256 hash-chained log that detects edited and deleted entries"],
];

export function Problem() {
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
