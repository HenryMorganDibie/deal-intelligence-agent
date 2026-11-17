import type { ReactNode } from "react";
import { LEGAL_UPDATED } from "../lib/legal";
import { PublicPage } from "./PublicPage";
import { Container } from "./primitives";

/** A plain, readable legal document: title, last-updated date, then numbered sections. */
export function LegalPage({ title, intro, children }: { title: string; intro: ReactNode; children: ReactNode }) {
  return (
    <PublicPage>
      <Container className="max-w-3xl pb-20 pt-28 sm:pt-32">
        <p className="eyebrow">Legal</p>
        <h1 className="h2 mt-3">{title}</h1>
        <p className="mt-2 text-sm text-[color:var(--dim)]">Last updated {LEGAL_UPDATED}</p>
        <div className="mt-6 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">{intro}</div>
        <div className="legal mt-10 space-y-8 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">{children}</div>
      </Container>
    </PublicPage>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="font-display text-lg font-semibold text-[color:var(--text)]">{title}</h2>
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

export function Address({ value }: { value?: string }) {
  return value ? <>{value}</> : <>available on request from the email address above</>;
}
