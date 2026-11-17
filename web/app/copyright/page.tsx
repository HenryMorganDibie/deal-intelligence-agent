import type { Metadata } from "next";
import { Address, LegalPage, Section } from "../../components/LegalPage";
import { DMCA_AGENT } from "../../lib/legal";

export const metadata: Metadata = {
  title: "Copyright and DMCA | Deal Intelligence",
  description: "How to report content on Deal Intelligence that you believe infringes your copyright, and our designated agent.",
};

export default function CopyrightPage() {
  return (
    <LegalPage
      title="Copyright and DMCA notices"
      intro={<p>We respect the rights of authors and publishers. Deal Intelligence shows short headlines and facts with a link to the original
        source, never full articles. If you believe something on the site infringes your copyright, tell our designated agent and we will act
        on it promptly.</p>}
    >
      <Section title="Designated agent">
        <p>Notices under the US Digital Millennium Copyright Act (17 U.S.C. § 512) and similar laws go to:</p>
        <address className="not-italic rounded-xl border hairline p-4 text-[color:var(--text)]">
          {DMCA_AGENT.name}<br />
          Email: <a className="underline underline-offset-4" href={`mailto:${DMCA_AGENT.email}`}>{DMCA_AGENT.email}</a><br />
          {DMCA_AGENT.phone ? <>Phone: {DMCA_AGENT.phone}<br /></> : null}
          Postal address: <Address value={DMCA_AGENT.postalAddress} />
        </address>
      </Section>
      <Section title="What a notice must include">
        <ol className="list-decimal space-y-1.5 pl-5">
          <li>Your physical or electronic signature, as the owner or someone authorised to act for the owner.</li>
          <li>The copyrighted work you believe is infringed.</li>
          <li>The material on Deal Intelligence you want removed, with its address (URL) so we can find it.</li>
          <li>Your name, postal address, telephone number and email address.</li>
          <li>A statement that you believe in good faith the use is not authorised by the owner, its agent or the law.</li>
          <li>A statement, under penalty of perjury, that the notice is accurate and that you are the owner or authorised to act for the owner.</li>
        </ol>
      </Section>
      <Section title="What we do">
        <p>When a complete notice arrives we remove or disable access to the material, and tell the person who provided it where there is one.
          Accounts that repeatedly infringe are closed.</p>
      </Section>
      <Section title="Counter-notices">
        <p>If your material was removed and you believe that was a mistake, send the agent: your signature; the material removed and where it
          appeared; a statement under penalty of perjury that you believe in good faith it was removed by mistake or misidentification; and your
          name, address and telephone number with your consent to the jurisdiction of the courts for your address (or, outside the United
          States, any district where we may be found) and to accept service from the person who sent the notice. We restore the material in 10
          to 14 business days unless that person tells us they have filed a court action.</p>
        <p>A notice or counter-notice that knowingly misrepresents facts can make the sender liable for damages.</p>
      </Section>
    </LegalPage>
  );
}
