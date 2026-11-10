import type { Metadata } from "next";
import { Coverage } from "../../components/Coverage";
import { PublicPage } from "../../components/PublicPage";

export const metadata: Metadata = {
  title: "Coverage | Deal Intelligence",
  description: "Review the source feeds and data coverage supporting African market intelligence, with SEC filings for companies listed or reporting in the US.",
};

export default function CoveragePage() {
  return <PublicPage><Coverage /></PublicPage>;
}
