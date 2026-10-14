import { LINKS } from "../lib/site";
import { ArrowRight, Container, LogoMark, Reveal } from "./primitives";

export function FinalCta() {
  return (
    <section aria-labelledby="cta-title" className="noise relative overflow-hidden border-t hairline py-28 sm:py-36">
      <div aria-hidden className="grid-bg absolute inset-0 opacity-70" />
      <div
        aria-hidden
        className="absolute bottom-[-20rem] left-1/2 h-[34rem] w-[56rem] -translate-x-1/2 rounded-full blur-3xl"
        style={{ background: "radial-gradient(closest-side, rgba(110,231,200,0.12), rgba(185,163,255,0.05) 55%, transparent)" }}
      />
      <Container className="relative text-center">
        <Reveal>
          <h2 id="cta-title" className="h1 mx-auto max-w-4xl text-gradient">
            Show your work.
          </h2>
        </Reveal>
        <Reveal delay={80}>
          <p className="lede mx-auto mt-6 max-w-xl">
            Run a brief on a company you know well, then check every line of it against the sources. That is the test.
          </p>
        </Reveal>
        <Reveal delay={160}>
          <div className="mt-10 flex flex-wrap justify-center gap-3">
            <a href="/app" className="btn btn-primary">
              Run your first brief
              <ArrowRight />
            </a>
            <a href={LINKS.evaluation} className="btn btn-ghost">
              See how often it was right
            </a>
          </div>
        </Reveal>
      </Container>
    </section>
  );
}

export function SiteFooter() {
  const cols = [
    {
      title: "Product",
      links: [
        { label: "How it works", href: "/#pipeline" },
        { label: "Attribution", href: "/#attribution" },
        { label: "Coverage", href: "/#coverage" },
        { label: "Open the app", href: "/app" },
      ],
    },
    {
      title: "Evidence",
      links: [
        { label: "Methodology", href: LINKS.methodology },
        { label: "Evaluation", href: LINKS.evaluation },
        { label: "Coverage by country", href: "/app/coverage" },
        { label: "Known limits", href: LINKS.limitations },
      ],
    },
    {
      title: "Contact",
      links: [{ label: "Get in touch", href: LINKS.contact }],
    },
  ];

  return (
    <footer className="border-t hairline py-14">
      <div className="mx-auto grid w-full max-w-page gap-10 px-4 sm:px-6 md:grid-cols-[1.4fr_repeat(3,1fr)] lg:px-8">
        <div>
          <a href="/#top" className="flex items-center gap-2.5 text-[0.9375rem] font-medium">
            <LogoMark />
            Deal Intelligence
          </a>
          <p className="mt-4 max-w-xs text-[0.8125rem] leading-relaxed text-[color:var(--muted)]">
            Deal intelligence for African and US markets. Research tooling, not investment advice.
          </p>
        </div>
        {cols.map((c) => (
          <nav key={c.title} aria-label={c.title}>
            <p className="eyebrow">{c.title}</p>
            <ul className="mt-4 space-y-2.5">
              {c.links.map((l) => (
                <li key={l.label}>
                  {l.href ? (
                    <a
                      href={l.href}
                      {...(l.href.startsWith("http") ? { target: "_blank", rel: "noreferrer" } : {})}
                      className="text-[0.875rem] text-[color:var(--muted)] transition-colors hover:text-[color:var(--text)]"
                    >
                      {l.label}
                    </a>
                  ) : (
                    <span className="text-[0.875rem] text-[color:var(--dim)]">
                      {l.label} <span className="kbd ml-1 text-[0.6875rem] uppercase tracking-[0.12em]">Soon</span>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="mx-auto mt-12 flex w-full max-w-page flex-wrap justify-between gap-3 px-4 text-[0.75rem] text-[color:var(--dim)] sm:px-6 lg:px-8">
        <span>© {new Date().getFullYear()} Henry Dibie</span>
        <span className="kbd">Briefs are AI-assisted and unverified.</span>
      </div>
    </footer>
  );
}
