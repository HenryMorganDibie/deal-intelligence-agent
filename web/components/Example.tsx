import { SIGNAL_TYPE, label, shortDate, type ShowcaseBrief } from "../lib/pulse";
import { Container, Heading, Reveal, Section } from "./primitives";

const words = (v: string | null | undefined) => (v ? v.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : "n/a");

/** An excerpt of a real brief: the latest showcase run when there is one, else a Boeing run of 13 Oct 2026. */
export function Example({ brief = null }: { brief?: ShowcaseBrief | null }) {
  const live = brief && brief.signal_count ? brief : null;
  const sig = live?.signals[0];
  const facts: [string, string][] = live
    ? [
        ["Company", live.company],
        ["Ticker", [live.ticker, live.market].filter(Boolean).join(" · ") || "n/a"],
        ["Severity", (live.severity ?? "n/a").toUpperCase()],
        ["Top alpha", live.top_alpha != null ? `${live.top_alpha.toFixed(1)} / 100` : "n/a"],
        ["Liquidity", words(live.liquidity)],
        ["Systemic risk", words(live.systemic_risk)],
        ["Sources reviewed", String(live.total_sources ?? live.filings + live.news)],
        [`Skipped, not about ${live.company}`, String(live.off_target ?? "n/a")],
      ]
    : [
        ["Company", "Boeing"],
        ["Ticker", "BA"],
        ["Severity", "MEDIUM"],
        ["Top alpha", "65.1 / 100"],
        ["Liquidity", "Large cap"],
        ["Systemic risk", "Isolated"],
        ["Sources reviewed", "62"],
        ["Skipped, not about Boeing", "21"],
      ];
  const file = `brief-${(live?.company ?? "Boeing").toLowerCase().replace(/[^a-z0-9]+/g, "-")}.md`;
  const date = live ? shortDate(live.created_at) : "13 Oct 2026";
  const lede = !live
    ? "An excerpt from a live run, with no LLM configured. The brief still arrives: the narrative falls back to the deterministic findings, says so, and asks for human review."
    : "An excerpt from this week's runs, regenerated every day on a fixed list of US and African companies. Every signal, source and review flag below was decided by the rule engine; the full brief adds the model-written narrative.";
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
          lede={lede}
        />

        <Reveal delay={100} className="mt-14">
          <div className="panel overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b hairline px-5 py-3">
              <span className="kbd text-[0.75rem] text-[color:var(--muted)]">{file}</span>
              <span className="tag">
                <span aria-hidden className="h-1 w-1 rounded-full bg-verified" />
                Live run · {date} · excerpt
              </span>
            </div>
            <div className="grid lg:grid-cols-[1fr_1.15fr]">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-4 border-b hairline p-6 lg:border-b-0 lg:border-r">
                {facts.map(([k, v]) => (
                  <div key={k}>
                    <dt className="eyebrow">{k}</dt>
                    <dd className="mt-1 text-[0.9375rem]">{v}</dd>
                  </div>
                ))}
              </dl>
              <div className="p-6">
                {live && sig ? (
                  <>
                    <p className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-verified">
                      Signal 1 · {label(SIGNAL_TYPE, sig.signal_type)} · {words(sig.severity)}
                    </p>
                    <p className="mt-3 text-[1rem] leading-relaxed">{sig.evidence}</p>
                    <p className="kbd mt-1 text-[0.75rem] text-[color:var(--dim)]">{sig.source}</p>
                    {live.signals[1] && (
                      <div className="mt-5 border-t hairline pt-4">
                        <p className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-verified">
                          Signal 2 · {label(SIGNAL_TYPE, live.signals[1].signal_type)} · {words(live.signals[1].severity)}
                        </p>
                        <p className="mt-2 text-[0.9375rem] leading-relaxed">{live.signals[1].evidence}</p>
                        <p className="kbd mt-1 text-[0.75rem] text-[color:var(--dim)]">{live.signals[1].source}</p>
                      </div>
                    )}
                    {live.requires_human_review && (
                      <div className="mt-5 rounded-[10px] border border-risk/25 bg-risk/[0.05] p-4">
                        <p className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-risk">⚑ Human review required before acting</p>
                        {(live.review_reasons ?? []).length > 0 && (
                          <ul className="mt-2 space-y-1 text-[0.875rem] text-[color:var(--muted)]">
                            {(live.review_reasons ?? []).map((r) => (
                              <li key={r}>{r}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
                    <a href={`/app/briefs/${live.id}`} className="kbd mt-5 inline-block text-[0.8125rem] text-verified hover:underline">
                      Read the full brief →
                    </a>
                  </>
                ) : (
                  <>
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
                  </>
                )}
              </div>
            </div>
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
