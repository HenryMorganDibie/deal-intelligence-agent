import type { Metadata } from "next";
import { SiteFooter } from "../../components/Closing";
import { SiteNav } from "../../components/SiteNav";
import { Container } from "../../components/primitives";
import { ContactForm } from "../../components/ContactForm";

export const metadata: Metadata = {
  title: "Contact | Deal Intelligence",
  description:
    "Contact Deal Intelligence to request a demonstration, explore an institutional pilot, discuss a partnership, or ask about our data and methodology.",
};

export default function ContactPage() {
  return (
    <>
      <SiteNav />
      <main id="main" className="pb-16 pt-28">
        <Container className="max-w-3xl">
          <p className="eyebrow">Contact</p>
          <h1 className="h2 mt-3 text-[2rem] sm:text-[2.5rem]">
            Let's talk about better market intelligence.
          </h1>
          <p className="mt-4 text-[1rem] leading-relaxed text-[color:var(--muted)]">
            Whether you're evaluating the platform, exploring an institutional pilot, or discussing a
            strategic partnership, tell us what you're working on. Your enquiry goes directly to the
            Deal Intelligence team.
          </p>

          <ContactForm />

          <p className="mt-5 text-sm text-[color:var(--muted)]">
            Prefer email? Write to{" "}
            <a href="mailto:info@deal-intelligence.app" className="text-verified hover:underline">
              info@deal-intelligence.app
            </a>
            .
          </p>

          <section aria-labelledby="pilot-title" className="mt-12 border-t hairline pt-8">
            <h2 id="pilot-title" className="h3">What an institutional pilot looks like</h2>
            <ol className="mt-4 list-decimal space-y-2 pl-5 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
              <li>Agree the coverage universe: countries, sectors, companies and deal types that matter to your team.</li>
              <li>Set success measures before starting, such as recall against deals you already track, field accuracy, and time to first report.</li>
              <li>Run a scoped evaluation using the deal feed, company signals and watchlists relevant to your universe.</li>
              <li>Review the results against your reference data, with limitations and evidence made explicit.</li>
            </ol>
          </section>
        </Container>
      </main>
      <SiteFooter />
    </>
  );
}
