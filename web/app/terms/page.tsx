import type { Metadata } from "next";
import { Address, LegalPage, Section } from "../../components/LegalPage";
import { BUSINESS, MINIMUM_AGE } from "../../lib/legal";

export const metadata: Metadata = {
  title: "Terms of Use | Deal Intelligence",
  description: "The terms for using Deal Intelligence: who may use it, subscriptions and renewal, acceptable use and limits of liability.",
};

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Use"
      intro={<p>These terms apply when you use Deal Intelligence, its website, app, alerts and API. By creating an account or using the
        service you agree to them. If you use it for an organisation, you agree for that organisation.</p>}
    >
      <Section title="1. Who may use it">
        <p>You must be at least {MINIMUM_AGE} years old to create an account or use the service. We do not knowingly collect information from
          anyone under {MINIMUM_AGE}; if we learn an account belongs to someone younger, we close it and delete its data.</p>
      </Section>
      <Section title="2. Research, not advice">
        <p>Deal Intelligence is research and data software. It does not give investment, legal or tax advice, execute trades or hold funds.
          Figures come from public sources and automated processing and can be incomplete, late or wrong. Check anything you rely on against the
          original source, which we link wherever we have one.</p>
      </Section>
      <Section title="3. Your account">
        <p>Keep your password and two-factor device safe; you are responsible for activity on your account. Tell us at {BUSINESS.email} if you
          think someone else has used it. Information you add about a company must be true and yours to share.</p>
      </Section>
      <Section title="4. Subscriptions, renewal and cancellation">
        <p>Paid plans are billed in advance through Paystack, monthly or yearly as you choose. <strong className="text-[color:var(--text)]">A
          subscription renews automatically at the end of each period, at the price shown when you subscribed, until you cancel.</strong> You
          can cancel any time in Plan and billing; cancelling stops the next renewal and you keep access until the end of the period you paid
          for. We tell you before any price change applies to your subscription.</p>
      </Section>
      <Section title="5. Acceptable use">
        <p>Do not resell or republish the data in bulk, scrape the service, get around plan limits or security, share an account or API key
          outside your organisation, or use the service to break the law or harass anyone. API use is governed by your plan&apos;s quota.</p>
      </Section>
      <Section title="6. Content and copyright">
        <p>We show short headlines and facts with links to their sources. Third-party content belongs to its owners. To report material you
          believe infringes your copyright, see <a className="underline underline-offset-4" href="/copyright">Copyright and DMCA</a>.</p>
      </Section>
      <Section title="7. Availability and liability">
        <p>We work to keep the service running and accurate but provide it as is, without warranties to the extent the law allows. To the
          extent the law allows, we are not liable for indirect or consequential losses, or for decisions made using the service, and our total
          liability is limited to what you paid us in the 12 months before the claim.</p>
      </Section>
      <Section title="8. Ending and changes">
        <p>You can close your account at any time. We may suspend accounts that break these terms. If we change these terms materially we tell
          account holders by email before the change applies.</p>
      </Section>
      <Section title="9. Contact">
        <p>{BUSINESS.name}, {BUSINESS.email}. Postal address: <Address value={BUSINESS.postalAddress} />.</p>
      </Section>
    </LegalPage>
  );
}
