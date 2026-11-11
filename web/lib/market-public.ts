import { API_CONFIGURED, apiHeaders, apiUrl } from "./api-base";

/** The public markets snapshot: the shapes /api/markets/overview and /api/markets/instruments return. */
export type ExchangeTile = {
  exchange: string; name: string; country: string; mcap_usd: number | null; ytd_usd: number | null;
  advancers: number | null; decliners: number | null; as_of: string | null; stale?: boolean;
};
export type SectorRow = { sector: string; shares: number; mcap_usd: number | null; ytd_usd: number | null; chg_1d: number | null };
export type CurrencyRow = { currency: string; per_usd: number | null; ytd_vs_usd: number | null };
export type Overview = { exchanges?: ExchangeTile[]; sectors?: SectorRow[]; currencies?: CurrencyRow[]; captured_at?: string };
export type BillRow = { tenor_label?: string; tenor_days?: number; rate?: number; true_yield?: number; auction_date?: string };
export type BillBlock = { country?: string; country_name?: string; rows?: BillRow[] };
export type PolicyRate = { country?: string; country_name?: string; rate?: number; date?: string; confirmed_by?: string | null };
export type Instruments = { tbills?: BillBlock[]; policy_rates?: PolicyRate[] };

export async function loadMarkets(timeoutMs?: number): Promise<{ overview: Overview | null; instruments: Instruments | null }> {
  if (!API_CONFIGURED) return { overview: null, instruments: null };
  const get = async <T,>(path: string): Promise<T | null> => {
    try {
      const r = await fetch(apiUrl(path), {
        headers: apiHeaders(), next: { revalidate: 3600 }, ...(timeoutMs ? { signal: AbortSignal.timeout(timeoutMs) } : {}),
      });
      return r.ok ? ((await r.json()) as T) : null;
    } catch {
      return null;
    }
  };
  const [overview, instruments] = await Promise.all([get<Overview>("/api/markets/overview"), get<Instruments>("/api/markets/instruments")]);
  return { overview, instruments };
}

export const billYield = (r: BillRow): number | null => r.true_yield ?? r.rate ?? null;

/** Latest auction per country, newest first, shortest tenor of that auction first. */
export function latestBills(blocks: BillBlock[] | undefined): { name: string; date: string; rows: BillRow[] }[] {
  const out = [];
  for (const b of blocks ?? []) {
    const rows = (b.rows ?? []).filter((r) => billYield(r) != null && r.auction_date);
    if (!rows.length) continue;
    const date = rows.map((r) => r.auction_date!).sort().at(-1)!;
    out.push({ name: b.country_name ?? b.country ?? "", date,
      rows: rows.filter((r) => r.auction_date === date).sort((a, z) => (a.tenor_days ?? 0) - (z.tenor_days ?? 0)) });
  }
  return out.sort((a, z) => z.date.localeCompare(a.date));
}

export const pct = (v: number | null | undefined, signed = true): string =>
  v == null ? "n/a" : Math.abs(v) < 0.0005 ? "0%" : `${signed && v > 0 ? "+" : ""}${(v * 100).toFixed(1).replace(/\.0$/, "")}%`;

export function countryName(code: string | null | undefined): string | null {
  if (!code) return null;
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}
