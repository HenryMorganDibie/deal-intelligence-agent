/** Shapes of the stored brief (a JSON dump of the Python AnalystBrief model). */

export type Severity = "low" | "medium" | "high" | "critical";

export type AlphaScore = {
  score: number;
  expected_direction?: "positive" | "negative" | "neutral" | null;
  expected_magnitude_pct_low?: number | null;
  expected_magnitude_pct_high?: number | null;
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
  signal_candidates_count: number;
  top_alpha_score?: number | null;
  requires_human_review: boolean;
  human_review_reasons: string[];
  risk_factors: RiskFactor[];
  recent_developments: string[];
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

export function expectedMove(a?: AlphaScore | null): string | null {
  if (!a || (a.expected_direction !== "positive" && a.expected_direction !== "negative")) return null;
  if (a.expected_magnitude_pct_low == null || a.expected_magnitude_pct_high == null) return null;
  const arrow = a.expected_direction === "positive" ? "↑" : "↓";
  return `${arrow} ${a.expected_magnitude_pct_low.toFixed(0)}–${a.expected_magnitude_pct_high.toFixed(0)}%`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
