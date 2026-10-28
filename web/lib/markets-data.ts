// Types and formatting for the daily market snapshot (/api/markets/*).

export type Quote = {
  exchange: string;
  exchange_name: string;
  symbol: string;
  name: string;
  sector: string | null;
  country: string;
  currency: string;
  price: number;
  chg_1d: number | null;
  ytd: number | null;
  ytd_usd: number | null;
  mcap: number | null;
  mcap_usd: number | null;
  shares: number | null;
  volume: number | null;
  value_traded: number | null;
  value_traded_usd: number | null;
  date: string | null;
  age_days: number | null;
  stale: boolean;
  ytd_suspect?: boolean;
  secondary_of?: string;
  cap_note?: string;
  match?: number;
};

export type ExchangeTile = {
  exchange: string;
  name: string;
  country: string;
  currency: string;
  index: { name: string; level: number; chg_1d: number | null; date: string | null } | null;
  listed: number;
  priced_today: number;
  advancers: number;
  decliners: number;
  mcap_usd: number | null;
  mcap_coverage: number;
  ytd_local: number | null;
  ytd_usd: number | null;
  ytd_median_local: number | null;
  ytd_median_usd: number | null;
  currency_ytd_vs_usd: number | null;
  as_of: string | null;
  stale: boolean;
};

export type Mover = Pick<Quote, "exchange" | "symbol" | "name" | "sector" | "price" | "currency" | "chg_1d" | "ytd" |
  "ytd_usd" | "mcap_usd" | "volume" | "value_traded" | "date"> & { value_traded_usd?: number | null };

export type SectorMove = { sector: string; shares: number; mcap_usd: number | null; chg_1d: number | null; ytd_usd: number | null };
export type CurrencyMove = { currency: string; per_usd: number; jan1_per_usd: number | null; ytd_vs_usd: number | null };

export type Overview = {
  exchanges: ExchangeTile[];
  gainers: Mover[];
  losers: Mover[];
  most_traded: Mover[];
  sectors: SectorMove[];
  currencies: CurrencyMove[];
  coverage: { exchanges: number; shares: number; priced_today: number; with_market_cap: number };
  fx_as_of: string | null;
  captured_at: string | null;
  method: string;
};

export type Screener = { total: number; rows: Quote[]; sectors: string[] };

export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  const s = (v * 100).toFixed(digits);
  return `${v > 0 ? "+" : ""}${s}%`;
}

export function tone(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v) || v === 0) return "text-[color:var(--muted)]";
  return v > 0 ? "text-verified" : "text-risk";
}

export function price(v: number | null | undefined, currency?: string | null): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  const digits = v >= 1000 ? 0 : v >= 10 ? 2 : v >= 1 ? 2 : 4;
  return `${v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}${currency ? ` ${currency}` : ""}`;
}

export function compact(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  const a = Math.abs(v);
  const [div, unit] = a >= 1e9 ? [1e9, "bn"] : a >= 1e6 ? [1e6, "m"] : a >= 1e3 ? [1e3, "k"] : [1, ""];
  return `${(v / div).toFixed(a >= 1e3 ? 1 : 0).replace(/\.0$/, "")}${unit}`;
}

// Background for a heatmap cell: green for gains, red for losses, deeper with size (capped at ±5% a day,
// ±50% year to date).
export function heat(v: number | null | undefined, cap: number): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "rgba(255,255,255,0.04)";
  const a = Math.min(1, Math.abs(v) / cap) * 0.55 + 0.06;
  return v >= 0 ? `rgba(110,231,200,${a.toFixed(3)})` : `rgba(255,143,112,${a.toFixed(3)})`;
}

export function companyHref(q: Pick<Quote, "exchange" | "symbol" | "name">): string {
  const p = new URLSearchParams({ name: q.name, exchange: q.exchange, symbol: q.symbol });
  return `/app/companies?${p}`;
}

export function asOf(day: string | null | undefined): string {
  if (!day) return "date not reported";
  const d = new Date(day);
  return Number.isNaN(d.getTime()) ? day : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}
