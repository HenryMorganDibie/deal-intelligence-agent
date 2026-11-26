import type { Metadata } from "next";
import { PublicPage } from "../../../components/PublicPage";
import CompareCompanies from "../../app/markets/compare/page";

export const metadata: Metadata = {
  title: "Compare listed and private companies | Deal Intelligence",
  description: "Compare company financials, market performance and valuation metrics side by side. Share a read-only comparison without an account.",
  alternates: { canonical: "/markets/compare" },
  openGraph: {
    title: "Compare companies | Deal Intelligence",
    description: "Compare company financials, market performance and valuation metrics side by side.",
    url: "/markets/compare",
    type: "website",
    siteName: "Deal Intelligence",
  },
  twitter: {
    card: "summary",
    title: "Compare companies | Deal Intelligence",
    description: "Compare company financials, market performance and valuation metrics side by side.",
  },
};

export default function PublicMarketsComparePage() {
  return (
    <PublicPage>
      <CompareCompanies publicPreview />
    </PublicPage>
  );
}
