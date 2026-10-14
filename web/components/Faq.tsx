import { Container, Heading, Reveal, Section } from "./primitives";

const FAQ = [
  {
    q: "Does it need an LLM?",
    a: "No. Detection, calibration, scoring, attribution and compound events are deterministic. Without a key the brief is built from those findings, labelled as such and flagged for human review. With Claude or Groq you also get analyst-language headlines, reasoning, an executive summary and an attribution check.",
  },
  {
    q: "Can the LLM change a signal?",
    a: "No. It only sees candidates the rule engine has already confirmed. It cannot add, remove, retype or re-grade them, and it cannot rate the brief below its most severe signal. If it omits a signal, the deterministic version is used. If it doubts attribution, that is shown and review is required.",
  },
  {
    q: "Which model does it use?",
    a: "Claude and Groq, with no lock-in to either. Every provider with a key is used in order, Claude first, then Groq (gpt-oss-120b, with Qwen behind it); if one fails, the next answers. Set DEAL_INTEL_PROVIDER to pin one. Each brief and the audit log record which model actually wrote it.",
  },
  {
    q: "Is this investment advice?",
    a: "No. It is research tooling. Briefs are AI-assisted and unverified, and anything above the review threshold says so in the brief itself.",
  },
  {
    q: "How do I know it is not hallucinating sources?",
    a: "Every signal links to the filing or article it came from, with its publication date and publisher. Sources outside your lookback window are rejected, and the pipeline trace counts what was skipped and why.",
  },
  {
    q: "Is the hosted app free?",
    a: "Yes, and there is no account to create. Click Run your first brief and go: up to 10 analyses a day per visitor. Each brief gets its own link you can share, and your list of briefs is kept in your browser.",
  },
  {
    q: "Is it open source?",
    a: "Yes. The full system, its 373 tests and an architecture document with its known limits are on GitHub.",
  },
];

export function Faq() {
  return (
    <Section id="faq" labelledBy="faq-title">
      <Container className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr]">
        <Heading index="11" eyebrow="Questions" id="faq-title" title="Asked before you have to." />
        <Reveal delay={100} className="min-w-0">
          <div className="border-t hairline">
            {FAQ.map((f) => (
              <details key={f.q} className="group border-b hairline">
                <summary className="flex cursor-pointer items-center justify-between gap-6 py-5 text-[1rem] font-medium">
                  {f.q}
                  <span aria-hidden className="faq-icon kbd text-lg text-[color:var(--muted)] transition-transform duration-200">
                    +
                  </span>
                </summary>
                <p className="pb-6 pr-10 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">{f.a}</p>
              </details>
            ))}
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
