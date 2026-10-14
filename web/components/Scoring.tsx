import type { CSSProperties } from "react";
import { Container, Heading, Reveal, Section } from "./primitives";

const ALPHA = [
  { name: "Severity", weight: 35, note: "rule-strength band" },
  { name: "Source credibility", weight: 25, note: "SEC and exchanges 1.0, Reuters 0.95" },
  { name: "Corroboration", weight: 20, note: "independent sources" },
  { name: "Recency", weight: 10, note: "14-day half-life from publication" },
  { name: "Liquidity", weight: 10, note: "live market cap in USD" },
];

// Evidence-quality breakdown of the Intel insider signal from the live run.
const QUALITY = [
  { name: "Source", v: 1.0 },
  { name: "Filing strength", v: 0.88 },
  { name: "Historical precision", v: 0.53 },
  { name: "Entities", v: 0.55 },
  { name: "Corroboration", v: 0.47 },
  { name: "Extraction", v: 0.65 },
  { name: "Recency", v: 0.35 },
];

function Bar({ value, delay, tone = "bg-verified" }: { value: number; delay: number; tone?: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
      <div
        data-grow
        className={`h-full rounded-full ${tone}`}
        style={{ width: `${Math.round(value * 100)}%`, "--reveal-delay": `${delay}ms` } as CSSProperties}
      />
    </div>
  );
}

export function Scoring() {
  return (
    <Section id="scoring" labelledBy="scoring-title">
      <Container>
        <Heading
          index="06"
          eyebrow="Scoring"
          id="scoring-title"
          title="Every score decomposes into parts you can check."
          lede="The alpha score ranks how actionable a signal is. The evidence-quality breakdown shows how well supported it is. The move shown with each signal is what actually followed similar flags, with its sample size."
        />

        <div className="mt-14 grid gap-4 lg:grid-cols-2">
          <Reveal>
            <div className="panel h-full p-6 sm:p-8">
              <div className="flex items-center justify-between">
                <h3 className="h3">Alpha score, 0 to 100</h3>
                <span className="eyebrow">Weights</span>
              </div>
              <ul className="mt-7 space-y-5">
                {ALPHA.map((a, i) => (
                  <li key={a.name}>
                    <div className="mb-2 flex items-baseline justify-between gap-4">
                      <span className="text-[0.9375rem]">{a.name}</span>
                      <span className="kbd text-[0.8125rem] text-verified">{a.weight}%</span>
                    </div>
                    <Bar value={a.weight / 35} delay={i * 90} />
                    <p className="mt-1.5 text-[0.75rem] text-[color:var(--dim)]">{a.note}</p>
                  </li>
                ))}
              </ul>
              <p className="mt-7 border-t hairline pt-5 text-[0.8125rem] leading-relaxed text-[color:var(--muted)]">
                The weights are design choices, not fitted values. The backtest tests whether a higher alpha means more
                confirmed events, and the evaluation page publishes the answer. Scores of 70 or more, and every CRITICAL
                signal, require human review.
              </p>
            </div>
          </Reveal>

          <Reveal delay={100}>
            <div className="panel h-full p-6 sm:p-8">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="h3">Evidence quality</h3>
                <span className="tag">
                  <span aria-hidden className="h-1 w-1 rounded-full bg-verified" />
                  Intel · Form 4 · live run
                </span>
              </div>
              <p className="mt-2 font-display text-5xl font-semibold tracking-tight">
                67<span className="text-2xl text-[color:var(--muted)]">%</span>
              </p>
              <ul className="mt-6 grid gap-x-8 gap-y-4 sm:grid-cols-2">
                {QUALITY.map((q, i) => (
                  <li key={q.name}>
                    <div className="mb-1.5 flex items-baseline justify-between">
                      <span className="text-[0.8125rem] text-[color:var(--muted)]">{q.name}</span>
                      <span className="kbd text-[0.75rem]">{q.v.toFixed(2)}</span>
                    </div>
                    <Bar value={q.v} delay={i * 70} tone={q.v < 0.5 ? "bg-risk/80" : "bg-verified"} />
                  </li>
                ))}
              </ul>
              <p className="mt-7 border-t hairline pt-5 text-[0.8125rem] leading-relaxed text-[color:var(--muted)]">
                Reasoning shown in the brief:{" "}
                <span className="text-[color:var(--text)]">“Confidence reduced by: single-source (1 corroboration), signal age reducing temporal relevance.”</span>
              </p>
            </div>
          </Reveal>
        </div>
      </Container>
    </Section>
  );
}
