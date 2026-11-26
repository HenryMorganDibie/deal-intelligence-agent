import type { Metadata } from "next";
import { PublicPage } from "../../../components/PublicPage";
import CompareCompanies from "../../app/markets/compare/page";

const previewTitle = "GTCO vs First HoldCo vs Zenith Bank | Deal Intelligence";
const previewDescription =
  "Compare three leading Nigerian banks side by side with market data, financials and research-backed company insights.";

export const metadata: Metadata = {
  title: previewTitle,
  description: previewDescription,
  alternates: { canonical: "/markets/compare" },
  openGraph: {
    title: previewTitle,
    description: previewDescription,
    url: "/markets/compare",
    type: "website",
    siteName: "Deal Intelligence",
    images: [
      {
        url: "/markets/compare/opengraph-image",
        width: 1200,
        height: 630,
        alt: "GTCO, First HoldCo and Zenith Bank compared by Deal Intelligence",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: previewTitle,
    description: previewDescription,
    images: ["/markets/compare/opengraph-image"],
  },
};

export default function PublicMarketsComparePage() {
  return (
    <PublicPage>
      <CompareCompanies publicPreview />
    </PublicPage>
  );
}
