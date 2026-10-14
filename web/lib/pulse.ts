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

/** A showcase brief: the pipeline run daily on a fixed company list (never visitors' searches). */
export type ShowcaseSignal = {
  signal_type: string | null;
  severity: string | null;
  headline: string | null;
  evidence: string;
  source: string;
  alpha: number | null;
  move_low: number | null;
  move_high: number | null;
  move_median: number | null;
  move_n: number | null;
  confidence: number | null;
};

export type ShowcaseBrief = {
  id: string;
  created_at: string;
  company: string;
  ticker: string | null;
  market: string | null;
  severity: string | null;
  top_alpha: number | null;
  systemic_risk: string | null;
  liquidity: string | null;
  requires_human_review: boolean | null;
  llm_used: boolean;
  executive_summary: string | null;
  filings: number;
  news: number;
  total_sources: number | null;
  candidates: number;
  off_target: number | null;
  unattributed: number | null;
  unattributed_title: string | null;
  review_reasons?: string[];
  signal_count: number;
  signals: ShowcaseSignal[];
};

export type Showcase = { hero: ShowcaseBrief | null; example: ShowcaseBrief | null };

export async function getShowcase(): Promise<Showcase | null> {
  if (!API_URL) return null;
  try {
    const resp = await fetch(`${API_URL}/api/showcase`, { next: { revalidate: REVALIDATE } });
    if (!resp.ok) return null;
    return (await resp.json()) as Showcase;
  } catch {
    return null;
  }
}

/** "-2.6% to +1.4%" from a measured interquartile range. */
export function moveRange(lo: number | null, hi: number | null): string | null {
  if (lo == null || hi == null) return null;
  const f = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  return `${f(lo)} to ${f(hi)}`;
}

/** Headline accuracy figures from the held-out evaluation sets, for copy that quotes them. */
export type QualityCI = { value: number; low: number; high: number; n: number } | null;
export type Quality = {
  dealPrecision: QualityCI;
  dealRecall: QualityCI;
  dealComplete: QualityCI;
  attributionPrecision: QualityCI;
  attributionRecall: QualityCI;
  attributionFalseAlarm: QualityCI;
};

export async function getQuality(): Promise<Quality | null> {
  if (!API_URL) return null;
  try {
    const resp = await fetch(`${API_URL}/api/evaluation`, { next: { revalidate: REVALIDATE } });
    if (!resp.ok) return null;
    const e = await resp.json();
    const ho = e?.data_quality?.heldout_extraction;
    const at = e?.attribution?.natural?.overall;
    return {
      dealPrecision: ho?.detection?.all?.precision ?? null,
      dealRecall: ho?.detection?.all?.recall ?? null,
      dealComplete: ho?.fields?.fully_correct_record ?? null,
      attributionPrecision: at?.precision ?? null,
      attributionRecall: at?.recall ?? null,
      attributionFalseAlarm: at?.false_alarm_rate_on_no_event_items ?? null,
    };
  } catch {
    return null;
  }
}

/** "71% (95% CI 61–79%, n=99)". */
export function ciText(x: QualityCI): string {
  if (!x) return "n/a";
  const p = (v: number) => Math.round(v * 100);
  return `${p(x.value)}% (95% CI ${p(x.low)}–${p(x.high)}%, n=${x.n})`;
}
