import type { Metadata } from "next";
import { PricingTable } from "../../components/billing/PricingTable";
import { PublicPage } from "../../components/PublicPage";
import { Container } from "../../components/primitives";
import { loadCatalog, loadNairaRate } from "../../lib/catalog";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Pricing | Deal Intelligence",
  description: "Plans for African private-market deals, investors, companies and country data, in naira or dollars. Start free.",
};

export default async function PricingPage() {
  const [catalog, rate] = await Promise.all([loadCatalog(), loadNairaRate()]);
  return (
    <PublicPage>
      <Container className="pb-20 pt-28 sm:pt-32">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">Pricing</p>
          <h1 className="h2 mt-3">Start free. Upgrade when you need more.</h1>
          <p className="lede mt-4">
            Paid securely through Paystack, with cards from anywhere. Cancel any time; you keep access until the end of the period
            you paid for.
          </p>
        </div>
        <div className="mt-12">
          <PricingTable catalog={catalog} rate={rate} />
        </div>
        <div className="mx-auto mt-10 max-w-2xl text-center text-sm text-[color:var(--muted)]">
          <p>
            <span className="font-medium text-[color:var(--text)]">Founding price.</span> Subscribe now and keep this price for as
            long as your subscription stays active, even if prices rise later.
          </p>
          <p className="mt-3 text-xs text-[color:var(--dim)]">
            Deal Intelligence is research and data software. It does not give investment advice, execute trades or hold funds.
          </p>
        </div>
      </Container>
    </PublicPage>
  );
}
