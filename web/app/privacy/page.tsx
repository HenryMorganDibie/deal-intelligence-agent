import type { Metadata } from "next";
import { Address, LegalPage, Section } from "../../components/LegalPage";
import { BUSINESS, MINIMUM_AGE } from "../../lib/legal";

export const metadata: Metadata = {
  title: "Privacy | Deal Intelligence",
  description: "What Deal Intelligence collects, why, who processes it, and how to see or delete your data.",
};

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy notice"
      intro={<p>This notice explains what we collect when you use Deal Intelligence, why, and the choices you have. We do not sell personal
        data, show advertising, or record your sessions.</p>}
    >
      <Section title="What we collect">
        <ul className="list-disc space-y-1.5 pl-5">
          <li><span className="text-[color:var(--text)]">Account:</span> email address, username, nickname, password (stored only as a hash),
            two-factor settings, and confirmation that you are {MINIMUM_AGE} or older.</li>
          <li><span className="text-[color:var(--text)]">Billing:</span> plan, billing period and payment status. Card details go to Paystack and
            never reach us.</li>
          <li><span className="text-[color:var(--text)]">What you save:</span> watchlists, alerts, portfolios, API keys and any company details you
            submit.</li>
          <li><span className="text-[color:var(--text)]">Usage:</span> which pages and features are used, the referring site&apos;s name and campaign
            tags, tied to a random identifier kept in your browser&apos;s storage. Vercel Web Analytics counts page views without cookies.</li>
          <li><span className="text-[color:var(--text)]">Messages:</span> what you send through the contact form.</li>
        </ul>
      </Section>
      <Section title="Why">
        <p>To run your account and plan, send the alerts you turn on, keep the service secure, and understand which features are used so we can
          improve them.</p>
      </Section>
      <Section title="Who processes it">
        <p>Supabase (database and sign-in), Vercel (hosting and page-view counts), Paystack (payments) and SendByte (email delivery). Each handles
          data only to provide its service to us.</p>
      </Section>
      <Section title="Cookies and storage">
        <p>We use cookies only to keep you signed in. Your browser&apos;s storage also holds your theme, saved briefs and the random usage
          identifier; clearing site data removes them.</p>
      </Section>
      <Section title="Emails">
        <p>Account emails (confirmation, password reset, security notices) are part of the service. Alert emails go only to people who turn them
          on, and every one carries a one-click link to stop it.</p>
      </Section>
      <Section title="Your choices">
        <p>You can see and change your account details in the app, and ask us at {BUSINESS.email} for a copy of your data or for it to be deleted.
          We keep data while your account is open and delete it after the account is closed, except billing records the law requires us to keep.</p>
      </Section>
      <Section title="Children">
        <p>The service is for people aged {MINIMUM_AGE} and over. We do not knowingly collect data from anyone younger.</p>
      </Section>
      <Section title="Contact">
        <p>{BUSINESS.name}, {BUSINESS.email}. Postal address: <Address value={BUSINESS.postalAddress} />.</p>
      </Section>
    </LegalPage>
  );
}
