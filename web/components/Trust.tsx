import { Container, Heading, Reveal, Section } from "./primitives";

const ITEMS = [
  {
    title: "Hash-chained audit log",
    body: "Every pipeline step is written to an append-only log. Each entry hashes all of its stored fields and links to the previous one, so edited and deleted entries are detected.",
    code: "python main.py audit --verify",
  },
  {
    title: "Compliance mode",
    body: "Suppresses low-confidence signals before the LLM sees them, counts what was suppressed, and stamps the brief as AI-generated and unverified.",
    code: "analyse --compliance",
  },
  {
    title: "Deterministic replay",
    body: "Re-runs a stored analysis as of its original date through the same rules, calibration and compound-event logic, and records the feedback data it calibrated with.",
    code: "replay --company Intel --date 2026-08-01",
  },
  {
    title: "Alerts on change, not on schedule",
    body: "Monitoring alerts on a new event or an escalation, records whether the webhook was delivered, and never re-counts an event it has already seen.",
    code: "monitor --run --interval 3600",
  },
  {
    title: "Backtests against real outcomes",
    body: "Each prediction is scored once against recorded market outcomes. Hit rate follows the predicted direction. Recall is not reported, because it needs a ground truth this system does not have.",
    code: "backtest --run",
  },
  {
    title: "Portfolio risk that adds up",
    body: "Fractional weights are normalised, holdings without a risk profile are reported as coverage rather than counted as zero risk, and contagion pairs are surfaced.",
    code: "portfolio --name fund --risk",
  },
];

export function Trust() {
  return (
    <Section id="trust" labelledBy="trust-title">
      <Container>
        <Heading
          index="08"
          eyebrow="Built for review"
          id="trust-title"
          title="Made for teams that have to defend the call."
          lede="Compliance, risk and investment committees ask the same question: how do you know? Every part of the system is designed to answer it."
        />
        <div className="mt-14 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ITEMS.map((it, i) => (
            <Reveal key={it.title} delay={(i % 3) * 70}>
              <article className="spotlight panel flex h-full flex-col p-6">
                <h3 className="h3">{it.title}</h3>
                <p className="mt-3 flex-1 text-[0.875rem] leading-relaxed text-[color:var(--muted)]">{it.body}</p>
                <code className="kbd mt-5 block truncate rounded-md border hairline bg-black/30 px-3 py-2 text-[0.75rem] text-[color:var(--muted)]">
                  <span className="text-verified">$</span> {it.code}
                </code>
              </article>
            </Reveal>
          ))}
        </div>
      </Container>
    </Section>
  );
}
