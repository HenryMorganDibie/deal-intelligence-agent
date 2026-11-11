import { apiHeaders, apiUrl } from "./api-base";
import { FALLBACK_CATALOG, type CatalogPlan } from "./pricing";

/** The plans and prices from the database (billing_catalog, public), refreshed at most every five minutes. */
export async function loadCatalog(): Promise<CatalogPlan[]> {
  const url = (process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/+$/, "");
  const key = process.env.SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || "";
  if (!url || !key) return FALLBACK_CATALOG;
  try {
    const r = await fetch(`${url}/rest/v1/rpc/billing_catalog`, {
      method: "POST", headers: { apikey: key, "Content-Type": "application/json" }, body: "{}", next: { revalidate: 300 },
    });
    const data = r.ok ? ((await r.json()) as CatalogPlan[] | null) : null;
    return data && data.length ? data : FALLBACK_CATALOG;
  } catch {
    return FALLBACK_CATALOG;
  }
}

/** Naira per US dollar from the daily market snapshot, refreshed hourly; null when unavailable. */
export async function loadNairaPerDollar(): Promise<number | null> {
  try {
    const r = await fetch(apiUrl("/api/markets/overview"), { headers: apiHeaders(), next: { revalidate: 3600 } });
    if (!r.ok) return null;
    const data = (await r.json()) as { currencies?: { currency: string; per_usd: number | null }[] };
    const rate = data.currencies?.find((c) => c.currency === "NGN")?.per_usd;
    return rate && rate > 0 ? rate : null;
  } catch {
    return null;
  }
}
