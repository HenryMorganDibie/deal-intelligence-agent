import type { MetadataRoute } from "next";
import { SITE } from "../lib/site";

export default function robots(): MetadataRoute.Robots {
  const base = (SITE.url ?? "https://deal-intelligence.app").replace(/\/$/, "");
  return { rules: [{ userAgent: "*", allow: "/", disallow: ["/admin", "/app", "/account", "/api"] }], sitemap: `${base}/sitemap.xml` };
}
