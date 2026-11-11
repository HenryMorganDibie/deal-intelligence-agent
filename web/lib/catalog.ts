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

export type NairaRate = { perUsd: number; asOf: string | null };

const FIVE_MINUTES = 300;

/** Live USD/NGN market quote, updated through the trading day. */
async function liveQuote(): Promise<NairaRate | null> {
  const r = await fetch("https://query1.finance.yahoo.com/v8/finance/chart/NGN=X?interval=1m&range=1d", {
    headers: { "User-Agent": "Mozilla/5.0 (compatible; DealIntelligence/1.0)" }, next: { revalidate: FIVE_MINUTES } });
  if (!r.ok) return null;
  const meta = (await r.json())?.chart?.result?.[0]?.meta;
  const rate = Number(meta?.regularMarketPrice);
  return rate > 0 ? { perUsd: rate, asOf: meta?.regularMarketTime ? new Date(meta.regularMarketTime * 1000).toISOString() : null } : null;
}

/** Fallback: the published daily reference rate. */
async function referenceRate(): Promise<NairaRate | null> {
  const r = await fetch("https://open.er-api.com/v6/latest/USD", { next: { revalidate: FIVE_MINUTES } });
  if (!r.ok) return null;
  const d = await r.json();
  const rate = Number(d?.rates?.NGN);
  return rate > 0 ? { perUsd: rate, asOf: d?.time_last_update_unix ? new Date(d.time_last_update_unix * 1000).toISOString() : null } : null;
}

/** Last resort: the platform's own daily market snapshot. */
async function snapshotRate(): Promise<NairaRate | null> {
  const r = await fetch(apiUrl("/api/markets/overview"), { headers: apiHeaders(), next: { revalidate: FIVE_MINUTES } });
  if (!r.ok) return null;
  const d = (await r.json()) as { currencies?: { currency: string; per_usd: number | null }[]; fx_as_of?: string };
  const rate = d.currencies?.find((c) => c.currency === "NGN")?.per_usd;
  return rate && rate > 0 ? { perUsd: rate, asOf: d.fx_as_of ? new Date(d.fx_as_of).toISOString() : null } : null;
}

/** Naira per US dollar, following the market: refreshed every five minutes; null when no source answers. */
export async function loadNairaRate(): Promise<NairaRate | null> {
  for (const source of [liveQuote, referenceRate, snapshotRate]) {
    try {
      const rate = await source();
      if (rate) return rate;
    } catch {
      /* try the next source */
    }
  }
  return null;
}
