"use client";

import { Container } from "../../../components/primitives";
import { PageHeader } from "../../../components/app/ui";

const plannedCapabilities = [
  {
    title: "Understand valuation",
    body: "See whether a listed company appears undervalued, fairly valued or overvalued, with the assumptions and uncertainty made clear.",
  },
  {
    title: "Look beyond the price",
    body: "Bring company financials, business performance and relevant market context together to support a more informed assessment.",
  },
  {
    title: "See the risks and evidence",
    body: "Review the factors that strengthen or weaken an investment case, with source-linked evidence rather than unexplained conclusions.",
  },
  {
    title: "Compare opportunities",
    body: "Compare companies on relevant fundamentals, valuation context and risks instead of relying on a headline number alone.",
  },
];

export default function MarketsComingSoonPage() {
  return (
    <Container className="py-10 lg:py-14">
      <div className="mb-5 inline-flex items-center gap-2 rounded-full border hairline bg-white/[0.03] px-3 py-1.5 text-xs text-[color:var(--muted)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--dim)]" aria-hidden="true" />
        Coming soon
      </div>

      <PageHeader
        eyebrow="Markets"
        title="Explore Investments"
      >
        A clearer way to assess public-market opportunities. Markets is planned to help you understand what a company may be worth, what could go wrong, and how strong the evidence is before drawing a conclusion.
      </PageHeader>

      <section className="panel mt-8 p-5 sm:p-7" aria-labelledby="planned-title">
        <p className="eyebrow">What we're building</p>
        <h2 id="planned-title" className="h3 mt-2 text-xl">Investment analysis that calls it plainly.</h2>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-[color:var(--muted)]">
          The aim is not to tell you what you want to hear. If the available evidence suggests a stock is overvalued, the analysis should say so and show why, including the assumptions and limitations behind that view. Markets is not live yet, and these capabilities are planned rather than available today.
        </p>

        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {plannedCapabilities.map((item) => (
            <article key={item.title} className="rounded-xl border hairline bg-white/[0.02] p-4">
              <h3 className="text-sm font-medium">{item.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">{item.body}</p>
            </article>
          ))}
        </div>
      </section>
    </Container>
  );
}
