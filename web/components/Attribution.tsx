"use client";

import { useState } from "react";
import { Container, Heading, Reveal, Section } from "./primitives";

/**
 * Headlines from live runs (13 Oct 2026). Each is split the way the engine
 * splits it; `who` is the company name, `trigger` the phrase a rule matched.
 */
type Part = { text: string; who?: boolean; trigger?: boolean };
type Example = {
  company: string;
  clauses: Part[][];
  separators: string[];
  signal: string;
  verdict: "attributed" | "dropped";
  reason: string;
};

const EXAMPLES: Example[] = [
  {
    company: "Safaricom",
    clauses: [
      [{ text: "Earnings call transcript" }],
      [{ text: "Vodacom " }, { text: "lifts outlook", trigger: true }, { text: " in Q1 2026" }],
      [{ text: "Safaricom", who: true }, { text: " deal reshapes growth" }],
    ],
    separators: [":", "as"],
    signal: "Earnings surprise",
    verdict: "dropped",
    reason: "The outlook clause is about Vodacom. Safaricom is named in a different clause.",
  },
  {
    company: "Intel",
    clauses: [
      [
        { text: "SoftBank Group Q1 profit " },
        { text: "beats expectations", trigger: true },
        { text: " on " },
        { text: "Intel", who: true },
        { text: " windfall" },
      ],
    ],
    separators: [],
    signal: "Earnings surprise",
    verdict: "dropped",
    reason: "Earnings belong to the subject. Intel is named only after the trigger, so the beat is SoftBank's.",
  },
  {
    company: "Naspers",
    clauses: [
      [
        { text: "EU Commission clears " },
        { text: "acquisition", trigger: true },
        { text: " of eMAG by " },
        { text: "Naspers", who: true },
      ],
    ],
    separators: [],
    signal: "M&A activity",
    verdict: "attributed",
    reason: "Both parties to a deal are relevant, and Naspers is named in the same clause as the acquisition.",
  },
  {
    company: "Intel",
    clauses: [
      [{ text: "Intel", who: true }, { text: " forecast " }, { text: "crushes estimates", trigger: true }],
      [{ text: "AI boom boosts chip demand" }],
    ],
    separators: ["as"],
    signal: "Earnings surprise · positive",
    verdict: "attributed",
    reason: "Intel is the subject and is named before the trigger, in the same clause.",
  },
];

export function Attribution() {
  const [active, setActive] = useState(0);
  const ex = EXAMPLES[active];
  const ok = ex.verdict === "attributed";

  return (
    <Section id="attribution" labelledBy="attribution-title">
      <Container>
        <Heading
          index="03"
          eyebrow="Subject attribution"
          id="attribution-title"
          title={
            <>
              Named in the story is not the same as{" "}
              <span className="text-[color:var(--muted)]">the story being about you.</span>
            </>
          }
          lede="A headline about a rival that mentions your company in passing used to become your signal. Now the engine splits each headline into clauses, and a trigger only counts when the company is named in the same clause. For events that belong to the subject, like earnings and executive changes, the company must come first."
        />

        <div className="mt-14 grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal className="min-w-0">
            <div role="tablist" aria-label="Attribution examples" className="flex flex-col gap-2">
              {EXAMPLES.map((e, i) => {
                const selected = i === active;
                return (
                  <button
                    key={i}
                    role="tab"
                    type="button"
                    aria-selected={selected}
                    aria-controls="attribution-panel"
                    onClick={() => setActive(i)}
                    className={`rounded-[12px] border px-4 py-3.5 text-left transition-colors ${
                      selected ? "border-white/15 bg-white/[0.04]" : "hairline hover:bg-white/[0.02]"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-3">
                      <span className="text-[0.9375rem] font-medium">{e.company}</span>
                      <span className={`kbd text-[0.6875rem] uppercase tracking-[0.12em] ${e.verdict === "attributed" ? "text-verified" : "text-risk"}`}>
                        {e.verdict === "attributed" ? "Attributed" : "Dropped"}
                      </span>
                    </span>
                    <span className="mt-1 block truncate text-[0.8125rem] text-[color:var(--muted)]">
                      {e.clauses.map((c) => c.map((p) => p.text).join("")).join(" … ")}
                    </span>
                  </button>
                );
              })}
            </div>
          </Reveal>

          <Reveal delay={100} className="min-w-0">
            <div id="attribution-panel" role="tabpanel" className="panel h-full p-6 sm:p-8" aria-live="polite">
              <div className="flex flex-wrap items-center gap-3">
                <span className="eyebrow">Analysing</span>
                <span className="rounded-full border hairline px-2.5 py-0.5 text-[0.8125rem]">{ex.company}</span>
                <span className="eyebrow ml-auto">Live headline</span>
              </div>

              <div className="mt-7 flex flex-wrap items-center gap-2">
                {ex.clauses.map((clause, ci) => (
                  <span key={ci} className="contents">
                    <span
                      className={`rounded-[10px] border px-3 py-2 text-[1.0625rem] leading-relaxed ${
                        clause.some((p) => p.trigger) ? "border-white/15 bg-white/[0.035]" : "border-dashed border-white/10"
                      }`}
                    >
                      {clause.map((p, pi) =>
                        p.who ? (
                          <mark key={pi} className="rounded bg-verified/15 px-1 text-verified">
                            {p.text}
                          </mark>
                        ) : p.trigger ? (
                          <mark key={pi} className="rounded bg-white/10 px-1 text-[color:var(--text)] underline decoration-white/40 underline-offset-4">
                            {p.text}
                          </mark>
                        ) : (
                          <span key={pi} className="text-[color:var(--muted)]">
                            {p.text}
                          </span>
                        )
                      )}
                    </span>
                    {ci < ex.separators.length && (
                      <span className="kbd rounded-full border border-dashed border-white/15 px-2 py-0.5 text-[0.6875rem] text-[color:var(--dim)]">
                        split at “{ex.separators[ci]}”
                      </span>
                    )}
                  </span>
                ))}
              </div>

              <div className="mt-7 flex flex-wrap gap-x-6 gap-y-2 text-[0.8125rem] text-[color:var(--muted)]">
                <span className="flex items-center gap-2">
                  <span aria-hidden className="h-2.5 w-2.5 rounded-sm bg-verified/40" /> Company named
                </span>
                <span className="flex items-center gap-2">
                  <span aria-hidden className="h-2.5 w-2.5 rounded-sm bg-white/25" /> Rule trigger
                </span>
                <span className="flex items-center gap-2">
                  <span aria-hidden className="h-2.5 w-2.5 rounded-sm border border-dashed border-white/25" /> Clause without the trigger
                </span>
              </div>

              <div className={`mt-8 rounded-[12px] border p-4 ${ok ? "border-verified/25 bg-verified/[0.05]" : "border-risk/25 bg-risk/[0.05]"}`}>
                <p className={`kbd text-[0.75rem] uppercase tracking-[0.12em] ${ok ? "text-verified" : "text-risk"}`}>
                  {ok ? "✓ Attributed" : "✕ Not attributed"} · {ex.signal}
                </p>
                <p className="mt-2 text-[0.9375rem] leading-relaxed">{ex.reason}</p>
              </div>

              <p className="mt-6 text-[0.8125rem] leading-relaxed text-[color:var(--muted)]">
                <span className="text-explain">With an LLM configured,</span> the explanation step also judges whether the
                evidence is about the company. It cannot delete a signal: a “no” is shown as an attribution doubt and the
                brief requires human review.
              </p>
            </div>
          </Reveal>
        </div>
      </Container>
    </Section>
  );
}
