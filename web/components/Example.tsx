import { Container, Heading, Reveal, Section } from "./primitives";

/** Excerpt of the Markdown brief from a live run (Boeing, 13 Oct 2026, LLM step not configured). */
export function Example() {
  return (
    <Section id="example" labelledBy="example-title">
      <Container>
        <Heading
          index="07"
          eyebrow="An actual brief"
          id="example-title"
          title={
            <>
              This is what lands on your desk.{" "}
              <span className="text-[color:var(--muted)]">Terminal, Markdown or JSON.</span>
            </>
          }
          lede="An excerpt from a live run, with no LLM configured. The brief still arrives: the narrative falls back to the deterministic findings, says so, and asks for human review."
        />

        <Reveal delay={100} className="mt-14">
          <div className="panel overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b hairline px-5 py-3">
              <span className="kbd text-[0.75rem] text-[color:var(--muted)]">brief-boeing.md</span>
              <span className="tag">
                <span aria-hidden className="h-1 w-1 rounded-full bg-verified" />
                Live run · 13 Oct 2026 · excerpt
              </span>
            </div>
            <div className="grid lg:grid-cols-[1fr_1.15fr]">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-4 border-b hairline p-6 lg:border-b-0 lg:border-r">
                {[
                  ["Company", "Boeing"],
                  ["Ticker", "BA"],
                  ["Severity", "MEDIUM"],
                  ["Top alpha", "65.1 / 100"],
                  ["Liquidity", "Large cap"],
                  ["Systemic risk", "Isolated"],
                  ["Sources reviewed", "62"],
                  ["Skipped, not about Boeing", "21"],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt className="eyebrow">{k}</dt>
                    <dd className="mt-1 text-[0.9375rem]">{v}</dd>
                  </div>
                ))}
              </dl>
              <div className="p-6">
                <p className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-verified">Signal 1 · Leadership change · Medium</p>
                <p className="mt-3 text-[1rem] leading-relaxed">
                  Item 5.02: Departure or Appointment of Directors or Certain Officers
                </p>
                <p className="kbd mt-1 text-[0.75rem] text-[color:var(--dim)]">SEC EDGAR · Form 8-K · credibility 1.00</p>
                <div className="mt-5 rounded-[10px] border border-risk/25 bg-risk/[0.05] p-4">
                  <p className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-risk">⚑ Human review required before acting</p>
                  <p className="mt-2 text-[0.875rem] text-[color:var(--muted)]">
                    LLM narrative synthesis unavailable. 1 signal was confirmed by the deterministic engine and is listed below.
                  </p>
                </div>
                <p className="mt-5 text-[0.8125rem] leading-relaxed text-[color:var(--muted)]">
                  An earlier version of the engine scored a routine Boeing loan agreement as M&amp;A with an alpha of 100.
                  “Material Definitive Agreement” boilerplate no longer counts as a deal.
                </p>
              </div>
            </div>
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
