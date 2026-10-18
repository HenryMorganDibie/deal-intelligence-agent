import type { Metadata } from "next";
import { Platform } from "../../components/Platform";
import { PublicPage } from "../../components/PublicPage";
import { getPulse } from "../../lib/pulse";

export const metadata: Metadata = {
  title: "Platform | Deal Intelligence",
  description: "Explore deal discovery, company financials, investor research, market context and evidence-linked intelligence.",
};

export default async function PlatformPage() {
  const pulse = await getPulse();
  return <PublicPage><Platform pulse={pulse} /></PublicPage>;
}
