import { ApiError } from "./api";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";

export async function get<T>(path: string, params?: Record<string, string | number | undefined | null>): Promise<T> {
  return request<T>(path + query(params));
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export async function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export function apiUrl(path: string): string {
  return `${API_URL}${path}`;
}

function query(params?: Record<string, string | number | undefined | null>): string {
  if (!params) return "";
  const q = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return q.length ? "?" + new URLSearchParams(q.map(([k, v]) => [k, String(v)])).toString() : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_URL) throw new ApiError("The API is not configured.", 503);
  let resp: Response;
  try {
    resp = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError("Could not reach the service. Check your connection and try again.", 0);
  }
  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : "Something went wrong. Try again in a minute.";
    throw new ApiError(detail, resp.status);
  }
  return body as T;
}

export type Source = { publisher?: string; url?: string; date?: string; title?: string; stage?: string | null };

export type Interval = { value: number; low: number; high: number; k: number; n: number } | null;

export type FieldCheck = {
  field: string;
  value: string | number | null;
  status: "corroborated" | "reported" | "derived" | "classified" | "uncertain" | "not disclosed";
  basis: string;
  independent_stories?: number;
};

export type Verification = {
  tier: "official" | "corroborated" | "single source";
  tier_label: string;
  sources: number;
  independent_stories: number;
  syndicated_copies: number;
  dates: { first_reported: string | null; announced_or_rumoured: string | null; completed_reported: string | null; note: string };
  fields: FieldCheck[];
  story_groups: { publisher: string | null; date: string | null; title: string | null; url: string | null }[][];
};

export type FieldAccuracy = {
  set: string;
  fields: Record<string, Interval>;
  fully_correct_record: Interval;
  detection: { precision: Interval; recall: Interval } | null;
} | null;

export type Deal = {
  id: string;
  deal_type: string;
  stage: string | null;
  round: string | null;
  target: string | null;
  buyer: string | null;
  seller: string | null;
  investors: string[];
  amount: number | null;
  currency: string | null;
  amount_usd: number | null;
  stake_pct: number | null;
  implied_valuation_usd: number | null;
  reported_valuation_usd: number | null;
  sector: string | null;
  country: string | null;
  countries: string[];
  announced: string | null;
  headline: string;
  sources: Source[];
  similarity?: number;
  why?: string[];
  independent_stories?: number;
  verification?: "corroborated" | "single source";
};

export type Stats = { n: number; min: number; p25: number; median: number; p75: number; max: number } | null;

export type Comparables = {
  deals: Deal[];
  size_usd: Stats;
  implied_valuation_usd: Stats;
  method: string;
};

export type RiskComponent = { name: string; weight: number; risk: number | null; formula?: string };

export type CountryRisk = {
  country: string;
  iso2: string;
  score: number | null;
  tier: string | null;
  coverage: number;
  components: RiskComponent[];
  indicators: Record<string, { value: number; year: number; label: string }>;
  spot_usd_rate: number | null;
  data_as_of: string | null;
  method: string;
};

export type CurrencyRisk = {
  currency: string;
  countries: string[];
  regime: string;
  regime_note: string;
  spot_per_usd: number | null;
  official_per_usd: { value: number; year: number } | null;
  spot_vs_official_pct: number | null;
  last_year_depreciation_pct: number | null;
  five_year_annualised_depreciation_pct: number | null;
  volatility_pct: number | null;
  score: number | null;
  tier: string | null;
  method: string;
};

export type CoverageRow = {
  iso2: string;
  country: string;
  region: string;
  exchange: string | null;
  currency: string;
  prices: string | null;
  statements: string | null;
  filings: string | null;
  news: { edition: string; national_edition: boolean; languages: string[] };
  regulators: string[];
  regulator_acronyms: string[];
  country_risk: { score: number | null; tier: string | null; coverage: number };
  deals: number;
  deal_value_usd: number;
  events: number;
  tier: "A" | "B" | "C";
};

export type Event = {
  id: string;
  day: string | null;
  headline: string;
  publisher: string;
  url: string;
  signal_type: string;
  direction: string | null;
  country: string | null;
  sector: string | null;
};

export type InvestorRow = {
  name: string;
  type: string | null;
  hq: string | null;
  deal_count: number;
  roles: Record<string, number>;
  disclosed_usd: number;
  countries: Record<string, number>;
  last_seen: string | null;
};

export type EvidenceItem = {
  n: number;
  kind: string;
  title: string;
  text: string;
  url: string | null;
  date: string | null;
  source: string | null;
};

export type ResearchResult = {
  question: string;
  answer: string;
  mode: "llm" | "deterministic";
  model: string | null;
  evidence: EvidenceItem[];
  validation: { grounded_share: number; uncited_sentences: string[]; invalid_citations_removed: number[]; cited_items: number[] };
};

export const SECTORS = [
  "fintech", "banking", "insurance", "energy", "oil_gas", "mining", "telecom", "agriculture", "healthcare", "logistics",
  "mobility", "ecommerce_retail", "real_estate", "infrastructure", "education", "media_tech", "manufacturing", "hospitality",
];

export const DEAL_TYPES = ["acquisition", "merger", "equity_funding", "debt_financing", "fund_raise", "exit", "ipo", "joint_venture"];

export const SIGNAL_TYPES = [
  "m_and_a_activity", "credit_risk", "distressed_asset", "earnings_surprise", "leadership_change",
  "regulatory_action", "debt_restructuring", "insider_activity",
];
