import { Container, Heading, Reveal, Section } from "./primitives";

const SIGNALS = [
  { name: "M&A activity", examples: ["definitive merger agreement", "tender offer", "8-K Item 2.01 · 5.01"], span: "lg:col-span-2" },
  { name: "Credit risk", examples: ["going concern", "covenant breach", "8-K Item 2.04"], span: "" },
  { name: "Distressed asset", examples: ["chapter 11 filing", "business rescue", "8-K Item 1.03"], span: "" },
  { name: "Earnings surprise", examples: ["profit warning", "crushes estimates", "8-K Item 4.02 restatement"], direction: "Beat or miss: direction read from the text", span: "" },
  { name: "Insider activity", examples: ["Form 4 open-market purchase", "Schedule 13D", "activist stake"], direction: "Purchase up, discretionary sale down", span: "lg:col-span-2" },
  { name: "Leadership change", examples: ["CEO resigns", "abrupt departure", "8-K Item 5.02"], span: "" },
  { name: "Regulatory action", examples: ["SEC investigation", "licence revoked", "consent order"], span: "" },
  { name: "Debt restructuring", examples: ["forbearance agreement", "debt-for-equity swap", "maturity extension"], span: "lg:col-span-2" },
];

export function Signals() {
  return (
    <Section id="signals" labelledBy="signals-title">
      <Container>
        <Heading
          index="04"
          eyebrow="What it detects"
          id="signals-title"
          title="Eight signal types, each defined by rules you can read."
          lede="Patterns live in one table in the engine; the signal registry is derived from it, so documentation and detection cannot drift. Routine filings like quarterly results releases, option grants and tax withholding produce nothing."
        />

        <div className="mt-14 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {SIGNALS.map((s, i) => (
            <Reveal key={s.name} delay={(i % 4) * 60} className={s.span}>
              <article className="spotlight panel h-full p-5">
                <h3 className="h3">{s.name}</h3>
                <ul className="mt-4 flex flex-wrap gap-1.5">
                  {s.examples.map((e) => (
                    <li key={e} className="kbd rounded-md border hairline bg-white/[0.02] px-2 py-1 text-[0.6875rem] text-[color:var(--muted)]">
                      {e}
                    </li>
                  ))}
                </ul>
                {s.direction && (
                  <p className="mt-4 flex items-center gap-2 text-[0.8125rem] text-[color:var(--muted)]">
                    <span aria-hidden className="kbd text-verified">↑</span>
                    <span aria-hidden className="kbd text-risk">↓</span>
                    {s.direction}
                  </p>
                )}
              </article>
            </Reveal>
          ))}
        </div>
      </Container>
    </Section>
  );
}
