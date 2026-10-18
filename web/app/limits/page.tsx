import type { Metadata } from "next";
import { Faq } from "../../components/Faq";
import { Limits } from "../../components/Limits";
import { PublicPage } from "../../components/PublicPage";
import { getQuality } from "../../lib/pulse";

export const metadata: Metadata = {
  title: "Limits and FAQ | Deal Intelligence",
  description: "Understand data gaps, evaluation limits, coverage differences and common questions before relying on the platform.",
};

export default async function LimitsPage() {
  const quality = await getQuality();
  return <PublicPage><Limits quality={quality} /><Faq /></PublicPage>;
}
