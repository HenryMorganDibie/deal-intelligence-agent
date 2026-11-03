import type { Metadata } from "next";
import { Example } from "../../components/Example";
import { PublicPage } from "../../components/PublicPage";
import type { Showcase } from "../../lib/pulse";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Example brief | Deal Intelligence",
  description: "Inspect an example company brief with evidence, source details and human-review flags.",
};

export default async function ExamplePage() {
  // Regenerated at most hourly (the showcase refreshes once a day), so visits are served as static HTML.
  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ||
    "https://deal-intelligence-api.vercel.app";
  let showcase: Showcase | null = null;
  try {
    const response = await fetch(`${apiUrl}/api/showcase`, { next: { revalidate: 3600 } });
    if (response.ok) showcase = (await response.json()) as Showcase;
  } catch {
    // Example renders its explicit fallback only when the API is actually unavailable.
  }
  return <PublicPage><Example brief={showcase?.example ?? showcase?.hero ?? null} /></PublicPage>;
}
