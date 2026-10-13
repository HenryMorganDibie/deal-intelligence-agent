import { Container, Heading, Reveal, Section } from "./primitives";

type Node = {
  n: string;
  name: string;
  kind: "verified" | "explain";
  body: string;
  out: string;
};

const NODES: Node[] = [
  {
    n: "01",
    name: "Collect",
    kind: "verified",
    body: "SEC EDGAR, NGX, NSE Kenya and JSE SENS disclosures, African and global news, in parallel. Each source fails on its own without blocking the run.",
    out: "filings + news inside the lookback window",
  },
  {
    n: "02",
    name: "Detect",
    kind: "verified",
    body: "115 patterns across 8 signal types. A source must name the company, and the event must be in the same clause as the name.",
    out: "signal candidates, or none",
  },
  {
    n: "03",
    name: "Calibrate",
    kind: "verified",
    body: "Raw scores map to severity bands from historical base rates. CRITICAL needs two independent sources. Analyst feedback adjusts the bands once 10 labelled outcomes exist.",
    out: "severity + materialisation probability",
  },
  {
    n: "04",
    name: "Explain",
    kind: "explain",
    body: "The LLM writes the headline, evidence list and reasoning for each confirmed candidate. It cannot add, remove, retype or re-grade a signal; it can only flag doubt.",
    out: "analyst-language explanation",
  },
  {
    n: "05",
    name: "Score",
    kind: "verified",
    body: "Alpha score from severity, source credibility, corroboration, recency and liquidity, plus an expected move and an evidence-quality breakdown.",
    out: "0–100 alpha, direction, review flags",
  },
  {
    n: "06",
    name: "Interact",
    kind: "verified",
    body: "14 compound-event rules: credit risk followed by distress escalates; M&A next to distress contradicts. Boosts re-check the human-review threshold.",
    out: "compound events, systemic risk level",
  },
  {
    n: "07",
    name: "Synthesise",
    kind: "explain",
    body: "The LLM drafts the executive summary. It cannot rate the brief below its most severe signal. If the LLM is down, the brief is built from the findings and flagged.",
    out: "the brief",
  },
  {
    n: "08",
    name: "Remember",
    kind: "verified",
    body: "Warehouse, company risk memory, entity graph and the hash-chained audit log. Re-runs do not recount the same event.",
    out: "history for backtests, replay and monitoring",
  },
];

export function Pipeline() {
  return (
    <Section id="pipeline" labelledBy="pipeline-title">
      <Container>
        <Heading
          index="02"
          eyebrow="How it works"
          id="pipeline-title"
          title="Eight steps. Two of them use an LLM, and neither can change the facts."
          lede={
            <>
              <span className="text-verified">Mint</span> marks work done by rules you can read.{" "}
              <span className="text-explain">Violet</span> marks text written by the model. The model only ever sees
              candidates the engine has already confirmed.
            </>
          }
        />

        <ol className="relative mt-16 grid gap-px overflow-hidden rounded-[14px] border hairline bg-[color:var(--line)] sm:grid-cols-2 lg:grid-cols-4">
          {NODES.map((node, i) => {
            const accent = node.kind === "verified" ? "text-verified" : "text-explain";
            const bar = node.kind === "verified" ? "bg-verified" : "bg-explain";
            return (
              <li key={node.n} className="spotlight relative bg-[color:var(--bg)] p-6">
                <Reveal delay={(i % 4) * 70}>
                  <div className="flex items-center justify-between">
                    <span className="kbd text-[0.75rem] text-[color:var(--dim)]">{node.n}</span>
                    <span className={`kbd text-[0.625rem] uppercase tracking-[0.14em] ${accent}`}>
                      {node.kind === "verified" ? "Deterministic" : "LLM · explain only"}
                    </span>
                  </div>
                  <div className="mt-6 h-px w-full bg-white/5">
                    <div data-grow className={`h-px ${bar}`} style={{ width: "100%", ["--reveal-delay" as string]: `${i * 90}ms` }} />
                  </div>
                  <h3 className="h3 mt-6">{node.name}</h3>
                  <p className="mt-3 text-[0.875rem] leading-relaxed text-[color:var(--muted)]">{node.body}</p>
                  <p className="kbd mt-5 text-[0.6875rem] text-[color:var(--dim)]">
                    <span aria-hidden className={accent}>→ </span>
                    {node.out}
                  </p>
                </Reveal>
              </li>
            );
          })}
        </ol>
      </Container>
    </Section>
  );
}
