import type { Metadata } from "next";
import { SiteFooter } from "../../components/Closing";
import { SiteNav } from "../../components/SiteNav";
import { ArrowRight, Container } from "../../components/primitives";
import { CONTACT_EMAIL, REQUESTS, mailto } from "../../lib/site";

export const metadata: Metadata = {
  title: "Contact | Deal Intelligence",
  description: "Request a demonstration, discuss a pilot, or ask about the methodology and evaluation data.",
};

export default function ContactPage() {
  return (
    <>
      <SiteNav />
      <main id="main" className="pb-16 pt-28">
        <Container className="max-w-3xl">
          <p className="eyebrow">Contact</p>
          <h1 className="h2 mt-3 text-[2rem] sm:text-[2.5rem]">Talk to the person who built it.</h1>
          <p className="mt-4 text-[1rem] leading-relaxed text-[color:var(--muted)]">
            Every request goes to Henry Dibie directly, at{" "}
            <a href={`mailto:${CONTACT_EMAIL}`} className="text-verified hover:underline">
              {CONTACT_EMAIL}
            </a>
            . Each option below opens an email with a short template, so the first reply can be specific.
          </p>
          <div className="mt-10 grid gap-4">
            {REQUESTS.map((r) => (
              <a
                key={r.key}
                href={mailto(r.subject, r.template)}
                className="panel group block p-6 transition-colors hover:bg-white/[0.02]"
              >
                <h2 className="h3 flex items-center justify-between gap-3">
                  {r.title}
                  <ArrowRight className="shrink-0 text-[color:var(--dim)] transition-colors group-hover:text-verified" />
                </h2>
                <p className="mt-2 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">{r.body}</p>
              </a>
            ))}
          </div>
          <section aria-labelledby="pilot-title" className="mt-12 border-t hairline pt-8">
            <h2 id="pilot-title" className="h3">What a pilot looks like</h2>
            <ol className="mt-4 list-decimal space-y-2 pl-5 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
              <li>Agree the coverage universe: countries, sectors, companies and deal types that matter to you.</li>
              <li>Fix the success measures before starting: for example recall against deals you already track, field accuracy, and time to first report.</li>
              <li>Run for four to eight weeks with daily briefs, the deal feed and watchlists on your universe.</li>
              <li>Close with an evaluation report on your own reference data, using the same method as the public evaluation pages.</li>
            </ol>
          </section>
        </Container>
      </main>
      <SiteFooter />
    </>
  );
}
