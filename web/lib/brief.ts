/** Shapes of the stored brief (a JSON dump of the Python AnalystBrief model). */

export type Severity = "low" | "medium" | "high" | "critical";

export type AlphaScore = {
  score: number;
  learned_confirmation_probability?: number | null;
  expected_direction?: "positive" | "negative" | "mixed" | "neutral" | null;
  expected_magnitude_pct_low?: number | null;
  expected_magnitude_pct_high?: number | null;
  expected_median_pct?: number | null;
  comparable_events_n?: number;
  move_confidence?: string;
  move_basis?: string | null;
  compound_adjusted_score?: number | null;
  liquidity_tier?: string;
};

export type Signal = {
  signal_type: string;
  severity: Severity;
  headline: string;
  evidence: string[];
  source_urls: string[];
  filing_references: string[];
  confidence: number;
  reasoning: string;
  corroboration_count: number;
  alpha_score?: AlphaScore | null;
  attribution_doubt?: string | null;
};

export type CompoundSignal = {
  compound_id: string;
  component_signal_types: string[];
  interaction_type: string;
  escalation_score: number;
  systemic_risk_level: string;
  reasoning_chain: string;
};

export type RiskFactor = { factor: string; impact: string; likelihood: Severity; mitigation?: string | null };
export type KeyMetric = { name: string; value: string; period: string; interpretation: string };

export type Brief = {
  company_name: string;
  ticker?: string | null;
  brief_date: string;
  analyst_model: string;
  executive_summary: string;
  overall_severity: Severity;
  recommendation: string;
  confidence_score: number;
  detected_signals: Signal[];
  key_metrics?: KeyMetric[];
  competitive_context?: string | null;
  signal_candidates_count: number;
  top_alpha_score?: number | null;
  requires_human_review: boolean;
  human_review_reasons: string[];
  risk_factors: RiskFactor[];
  recent_developments?: string[];
  filings_reviewed: { form_type: string; filing_date: string; document_url: string; description?: string | null }[];
  news_reviewed: { title: string; source: string; published_date: string; url: string }[];
  total_sources: number;
  compliance_mode: boolean;
  compliance_flags: string[];
  low_confidence_signals_suppressed: number;
  compound_signals: CompoundSignal[];
  systemic_risk_level: string;
  processing_time_seconds?: number | null;
};

export type BriefRow = {
  id: string;
  company: string;
  ticker: string | null;
  severity: Severity | null;
  signal_count: number;
  llm_used: boolean;
  created_at: string;
};

export const SEVERITY_STYLE: Record<Severity, string> = {
  low: "text-[color:var(--muted)] border-white/15",
  medium: "text-bone border-white/25",
  high: "text-risk border-risk/40",
  critical: "text-risk border-risk/70 bg-risk/10",
};

export function label(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Measured move after similar flags: "↓ -2.8% to +1.3% (median -1.3%, n=53)". */
export function expectedMove(a?: AlphaScore | null): string | null {
  if (!a || a.expected_magnitude_pct_low == null || a.expected_magnitude_pct_high == null) return null;
  let lo = a.expected_magnitude_pct_low;
  let hi = a.expected_magnitude_pct_high;
  // Briefs stored before measured moves held unsigned magnitudes with a separate direction.
  if (a.expected_direction === "negative" && lo >= 0 && hi >= 0) [lo, hi] = [-hi, -lo];
  const sign = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  // An arrow only when the stated direction agrees with what similar flags measured.
  const m = a.expected_median_pct;
  const agrees = m == null || (a.expected_direction === "positive" && m > 0) || (a.expected_direction === "negative" && m < 0);
  const arrow = !agrees ? "" : a.expected_direction === "positive" ? "↑ " : a.expected_direction === "negative" ? "↓ " : "";
  const median = a.expected_median_pct != null ? `, median ${sign(a.expected_median_pct)}` : "";
  const n = a.comparable_events_n ? `, n=${a.comparable_events_n}` : "";
  return `${arrow}${sign(lo)} to ${sign(hi)}${median}${n}`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
