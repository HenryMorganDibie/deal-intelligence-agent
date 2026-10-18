import type { Metadata } from "next";
import { Pipeline } from "../../components/Pipeline";
import { Scoring } from "../../components/Scoring";
import { Trust } from "../../components/Trust";
import { PublicPage } from "../../components/PublicPage";
import { getPulse } from "../../lib/pulse";

export const metadata: Metadata = {
  title: "How it works | Deal Intelligence",
  description: "See how source collection, deterministic detection, calibration, scoring and AI explanation fit together.",
};

export default async function HowItWorksPage() {
  const pulse = await getPulse();
  return <PublicPage><Pipeline /><Scoring pulse={pulse} /><Trust /></PublicPage>;
}
