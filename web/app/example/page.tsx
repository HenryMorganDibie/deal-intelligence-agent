import type { Metadata } from "next";
import { Example } from "../../components/Example";
import { PublicPage } from "../../components/PublicPage";
import { getShowcase } from "../../lib/pulse";

export const metadata: Metadata = {
  title: "Example brief | Deal Intelligence",
  description: "Inspect an example company brief with evidence, source details and human-review flags.",
};

export default async function ExamplePage() {
  const showcase = await getShowcase();
  return <PublicPage><Example brief={showcase?.example ?? showcase?.hero ?? null} /></PublicPage>;
}
