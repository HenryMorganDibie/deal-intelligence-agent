/**
 * Live market summary for the public pages. Fetched on the server and re-rendered every
 * REVALIDATE seconds (incremental static regeneration), so the landing and methodology
 * pages follow the daily deal and event feed and the hourly live-outcome refresh.
 * Returns null when the API is unreachable; callers fall back to static copy.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";
export const REVALIDATE = 1800;

export type PulseCountry = { code: string; name: string };

export type PulseDeal = {
  id: string;
  deal_type: string | null;
  target: string | null;
  buyer: string | null;
  investors: string[];
  amount_usd: number | null;
  country: PulseCountry | null;
  sector: string | null;
  announced: string | null;
  headline: string;
  publisher: string | null;
};

export type PulseEvent = {
  id: string | null;
  signal_type: string | null;
  direction: string | null;
  country: PulseCountry | null;
  day: string | null;
  headline: string;
  publisher: string | null;
  url: string | null;
};

export type AlphaBand = { n: number; alpha_range: [number, number]; precision: number | null };

export type Pulse = {
  as_of: string;
  latest_record: string | null;
  deals: {
    total: number;
    countries: number;
    since: string;
    window_days: number;
    recent: number;
    recent_countries: number;
    recent_disclosed_usd: number;
    recent_disclosed_n: number;
    by_type: Record<string, number>;
    top_countries: (PulseCountry & { deals: number })[];
    largest: PulseDeal | null;
    latest: PulseDeal[];
    active_investors: { name: string; type: string | null; deals: number }[];
  };
  events: {
    total: number;
    window_days: number;
    recent: number;
    by_type: Record<string, number>;
    latest: PulseEvent[];
  };
  measured: {
    period?: string | null;
    overall_confirmation?: { labelled: number; confirmed: number; rate: number | null } | null;
    backtest_observations: number;
    live_observations: number;
    live_updated_at?: string | null;
    alpha_validation?: {
      labelled: number;
      bands: Record<"low" | "middle" | "high", AlphaBand>;
      spearman_alpha_vs_confirmed: number | null;
      verdict?: string;
    } | null;
  };
};

export async function getPulse(): Promise<Pulse | null> {
  if (!API_URL) return null;
  try {
    const resp = await fetch(`${API_URL}/api/pulse`, { next: { revalidate: REVALIDATE } });
    if (!resp.ok) return null;
    return (await resp.json()) as Pulse;
  } catch {
    return null;
  }
}

export function usd(n: number | null | undefined): string {
  if (n == null) return "undisclosed";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1)}bn`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(n >= 1e8 ? 0 : 1)}m`;
  if (n >= 1e3) return `$${Math.round(n / 1e3)}k`;
  return `$${Math.round(n)}`;
}

/** 1735 -> "1,735". */
export function count(n: number): string {
  return n.toLocaleString("en-US");
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export const DEAL_TYPE: Record<string, string> = {
  equity_funding: "Equity funding",
  merger: "Merger",
  joint_venture: "Joint venture",
  acquisition: "Acquisition",
  debt_financing: "Debt financing",
  fund_raise: "Fund raise",
  exit: "Exit",
  ipo: "IPO",
  other: "Other",
};

export const SIGNAL_TYPE: Record<string, string> = {
  m_and_a_activity: "M&A",
  credit_risk: "Credit risk",
  distressed_asset: "Distress",
  earnings_surprise: "Earnings",
  insider_activity: "Insider",
  leadership_change: "Leadership",
  regulatory_action: "Regulatory",
  debt_restructuring: "Restructuring",
};

export function label(map: Record<string, string>, key: string | null | undefined): string {
  if (!key) return "Other";
  return map[key] ?? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
