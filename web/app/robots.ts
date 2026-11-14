import type { MetadataRoute } from "next";
import { SITE } from "../lib/site";

export default function robots(): MetadataRoute.Robots {
  const base = (SITE.url ?? "https://deal-intelligence.app").replace(/\/$/, "");
  return { rules: [{ userAgent: "*", allow: "/", disallow: ["/admin", "/account", "/api", "/api-keys", "/companies", "/countries", "/investors", "/research", "/watchlists", "/elections", "/evaluation", "/briefs", "/market-briefs", "/markets/screener", "/markets/investments", "/markets/compare", "/markets/valuation", "/markets/portfolio", "/markets/monitoring"] }], sitemap: `${base}/sitemap.xml` };
}
