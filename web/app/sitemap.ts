import type { MetadataRoute } from "next";
import { apiHeaders, apiUrl } from "../lib/api-base";
import { SITE } from "../lib/site";

// The public pages plus the public page of each recent deal, rebuilt at most daily.
export const revalidate = 86400;

const PAGES = ["", "/platform", "/how-it-works", "/attribution", "/coverage", "/example", "/limits", "/methodology",
  "/contact", "/developers"];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = (SITE.url ?? "https://deal-intelligence.app").replace(/\/$/, "");
  const out: MetadataRoute.Sitemap = PAGES.map((p) => ({ url: `${base}${p}`, changeFrequency: "weekly", priority: p ? 0.6 : 1 }));
  try {
    for (let offset = 0; offset < 1000; offset += 100) {
      const r = await fetch(apiUrl(`/api/deals?limit=100&offset=${offset}`), { headers: apiHeaders(), next: { revalidate: 86400 } });
      if (!r.ok) break;
      const page = (await r.json()) as { deals: { id: string; announced: string | null }[] };
      for (const d of page.deals) {
        out.push({ url: `${base}/deals/${d.id}`, lastModified: d.announced ?? undefined, changeFrequency: "monthly", priority: 0.5 });
      }
      if (page.deals.length < 100) break;
    }
  } catch {
    // The static pages are still listed when the API is unreachable.
  }
  return out;
}
