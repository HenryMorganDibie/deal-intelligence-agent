import type { Metadata } from "next";
import Link from "next/link";
import { PublicPage } from "../../components/PublicPage";
import { Container } from "../../components/primitives";
import { usd, words } from "../../components/app/ui";
import { apiHeaders, apiUrl } from "../../lib/api-base";
import type { Deal } from "../../lib/market";

/**
 * The latest deals, public: what a link in a roundup post opens to, readable without an account, with each deal
 * linking to its own public page. Search, filters, investors and alerts stay in the app.
 */
export const revalidate = 1800;

export const metadata: Metadata = {
  title: "Latest African deals | Deal Intelligence",
  description: "The newest private-market deals across Africa: funding rounds, debt, acquisitions, exits and fund closes, each with its sources.",
  alternates: { canonical: "/deals" },
  openGraph: { title: "Latest African deals", url: "/deals", type: "website", siteName: "Deal Intelligence",
    description: "The newest private-market deals across Africa: funding rounds, debt, acquisitions, exits and fund closes, each with its sources." },
  twitter: { card: "summary_large_image", title: "Latest African deals",
    description: "The newest private-market deals across Africa: funding rounds, debt, acquisitions, exits and fund closes, each with its sources." },
};

async function latest(): Promise<Deal[]> {
  try {
    const r = await fetch(apiUrl("/api/deals?limit=60"), { headers: apiHeaders(), next: { revalidate } });
    return r.ok ? (((await r.json()) as { deals?: Deal[] }).deals ?? []) : [];
  } catch {
    return [];
  }
}

function country(code: string | null): string | null {
  if (!code) return null;
  if (code === "CD") return "DR Congo";
  if (code === "CG") return "Republic of the Congo";
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

function line(d: Deal): string {
  const amount = d.amount_usd ? usd(d.amount_usd) : null;
  const who = d.investors.slice(0, 2).join(", ");
  switch (d.deal_type) {
    case "equity_funding":
      return `raised ${amount ?? "new funding"}${who ? ` from ${who}` : ""}`;
    case "debt_financing":
      return `secured ${amount ? `${amount} in ` : ""}debt financing${who ? ` from ${who}` : ""}`;
    case "acquisition":
      return `acquired${d.buyer ? ` by ${d.buyer}` : ""}${amount ? ` for ${amount}` : ""}`;
    case "exit":
      return `sold${d.seller ? ` by ${d.seller}` : ""}${amount ? ` for ${amount}` : ""}`;
    case "fund_raise":
      return `closed ${amount ? `${amount} ` : ""}in commitments`;
    case "ipo":
      return `listing${amount ? `, raising ${amount}` : ""}`;
    default:
      return words(d.deal_type).toLowerCase();
  }
}

export default async function LatestDeals() {
  const deals = (await latest()).filter((d) => d.target);
  return (
    <PublicPage>
      <Container className="max-w-4xl pb-16 pt-28">
        <p className="eyebrow">Deals</p>
        <h1 className="h2 mt-3 text-[2rem] sm:text-[2.5rem]">Latest African deals</h1>
        <p className="mt-4 text-[1rem] leading-relaxed text-[color:var(--muted)]">
          Funding rounds, debt, acquisitions, exits and fund closes across all 54 countries, newest first. Each links to its sources.
        </p>
        <ul className="mt-8 divide-y divide-white/[0.06] border-y hairline">
          {deals.map((d) => (
            <li key={d.id}>
              <Link href={`/deals/${d.id}`} className="flex items-baseline justify-between gap-4 py-4 hover:bg-white/[0.02]">
                <span>
                  <span className="font-medium">{d.target}</span>{" "}
                  <span className="text-[color:var(--muted)]">{line(d)}</span>
                  <span className="block text-xs text-[color:var(--dim)]">
                    {[words(d.deal_type), country(d.country), d.announced].filter(Boolean).join(" · ")}
                  </span>
                </span>
                {d.amount_usd ? <span className="shrink-0 font-display text-lg">{usd(d.amount_usd)}</span> : null}
              </Link>
            </li>
          ))}
        </ul>
        <p className="mt-8 text-sm text-[color:var(--muted)]">
          Search every deal, follow investors and set alerts in the app.{" "}
          <Link href="/account?next=%2Fdeals" className="text-verified hover:underline">Open the deal database</Link>
        </p>
      </Container>
    </PublicPage>
  );
}
