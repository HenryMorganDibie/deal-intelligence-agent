import type { Metadata } from "next";
import { Example } from "../../components/Example";
import { PublicPage } from "../../components/PublicPage";
import type { Showcase } from "../../lib/pulse";

export const dynamic = "force-dynamic";
export const revalidate = 60;

export const metadata: Metadata = {
  title: "Example brief | Deal Intelligence",
  description: "Inspect an example company brief with evidence, source details and human-review flags.",
};

export default async function ExamplePage() {
  // Do not prerender the static fallback into production HTML. The API has its own
  // short edge cache, so this request stays current without bypassing that cache.
  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ||
    "https://deal-intelligence-api.vercel.app";
  let showcase: Showcase | null = null;
  try {
    const response = await fetch(`${apiUrl}/api/showcase`, { next: { revalidate: 60 } });
    if (response.ok) showcase = (await response.json()) as Showcase;
  } catch {
    // Example renders its explicit fallback only when the API is actually unavailable.
  }
  return <PublicPage><Example brief={showcase?.example ?? showcase?.hero ?? null} /></PublicPage>;
}
