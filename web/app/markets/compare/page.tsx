import type { Metadata } from "next";
import { PublicPage } from "../../../components/PublicPage";
import CompareCompanies from "../../app/markets/compare/page";
import { decodeEntries, encodeEntries } from "../../../lib/compare";
import { SITE } from "../../../lib/site";

type Props = { searchParams: Promise<{ c?: string | string[] }> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const params = await searchParams;
  const raw = Array.isArray(params.c) ? params.c[0] : params.c;
  const refs = decodeEntries(raw ?? null);
  const comparison = refs.length > 0;
  const names = refs.map((r) => r.name);
  const title = comparison
    ? `${names.slice(0, 2).join(" vs ")}${names.length > 2 ? ` + ${names.length - 2} more` : ""} | Deal Intelligence`
    : "Compare companies | Deal Intelligence";
  const description = comparison
    ? `Compare ${names.join(", ")} using sourced financial statements, market prices and valuation metrics on Deal Intelligence.`
    : "Compare listed and private companies using sourced financial statements, market prices and valuation metrics.";
  const canonical = comparison ? `/markets/compare?c=${encodeURIComponent(encodeEntries(refs))}` : "/markets/compare";
  const image = comparison
    ? `/markets/compare/og?c=${encodeURIComponent(encodeEntries(refs))}`
    : "/markets/compare/og";
  const base = SITE.url?.replace(/\/$/, "") ?? "";
  const absolute = (path: string) => base ? `${base}${path}` : path;

  return {
    title,
    description,
    alternates: { canonical },
    openGraph: {
      title,
      description,
      url: absolute(canonical),
      type: "website",
      siteName: "Deal Intelligence",
      images: [{ url: absolute(image), width: 1200, height: 630, alt: comparison ? title : "Compare companies on Deal Intelligence" }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [absolute(image)],
    },
  };
}

export default function PublicMarketsComparePage() {
  return (
    <PublicPage>
      <CompareCompanies publicPreview />
    </PublicPage>
  );
}
