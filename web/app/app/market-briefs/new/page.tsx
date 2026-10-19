"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Container } from "../../../../components/primitives";
import { ApiError } from "../../../../lib/api";
import { DEAL_TYPES, SECTORS, post } from "../../../../lib/market";

type Created = { id: string; title: string; transaction_count: number; period_start: string; period_end: string };
const label = (value: string) => value.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());

export default function NewMarketBriefPage() {
  const router = useRouter();
  const [lookback, setLookback] = useState("30");
  const [country, setCountry] = useState("");
  const [sector, setSector] = useState("");
  const [dealType, setDealType] = useState("");
  const [audience, setAudience] = useState("Investment banking analyst");
  const [researchQuestion, setResearchQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await post<Created>("/api/market-briefs", {
        lookback_days: Number(lookback),
        ...(country.trim() ? { country: country.trim().toUpperCase() } : {}),
        ...(sector ? { sector } : {}),
        ...(dealType ? { deal_type: dealType } : {}),
        audience,
        ...(researchQuestion.trim() ? { research_question: researchQuestion.trim() } : {}),
      });
      router.push("/app/market-briefs/" + encodeURIComponent(result.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate the market brief. Please try again.");
      setLoading(false);
    }
  }

  return (
    <Container className="max-w-3xl py-10 lg:py-14">
      <Link href="/app" className="text-sm text-[color:var(--muted)] hover:text-[color:var(--text)]">← All briefs</Link>
      <p className="eyebrow mt-8">New market brief</p>
      <h1 className="h2 mt-3 text-[2rem] sm:text-[2.5rem]">Deals &amp; M&amp;A intelligence</h1>
      <p className="mt-3 max-w-2xl text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
        Build an analyst-ready brief from Deal Intelligence records plus live web research. The LLM synthesizes numbered evidence,
        links sources, and separates reported facts from interpretation. Company analysis remains available separately.
      </p>

      {loading ? (
        <div className="panel mt-8 p-5" role="status" aria-live="polite">
          <p className="font-medium">Building your market brief…</p>
          <p className="mt-2 text-sm text-[color:var(--muted)]">Filtering stored transactions, searching live news and web sources, synthesizing evidence with the configured LLM, checking citations, and assembling comparable activity.
        </div>
      ) : (
        <form onSubmit={submit} className="panel mt-8 space-y-5 p-5 sm:p-6">
          <label className="block">
            <span className="mb-1.5 block text-sm text-[color:var(--muted)]">Geography</span>
            <input value={country} onChange={(e) => setCountry(e.target.value.toUpperCase())} maxLength={3} placeholder="Africa (all countries) · or ISO code, e.g. NG" className="field" />
            <span className="mt-1.5 block text-xs text-[color:var(--dim)]">Leave blank for Africa-wide coverage. Enter a country ISO code to narrow the brief.</span>
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-sm text-[color:var(--muted)]">Period</span>
              <select value={lookback} onChange={(e) => setLookback(e.target.value)} className="field">
                <option value="30">Last 30 days</option>
                <option value="90">Last 90 days</option>
                <option value="180">Last 180 days</option>
                <option value="365">Last 12 months</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm text-[color:var(--muted)]">Audience</span>
              <select value={audience} onChange={(e) => setAudience(e.target.value)} className="field">
                <option>Investment banking analyst</option>
                <option>Private equity investor</option>
                <option>Venture capital investor</option>
                <option>Corporate strategy team</option>
                <option>Market research analyst</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm text-[color:var(--muted)]">Sector</span>
              <select value={sector} onChange={(e) => setSector(e.target.value)} className="field">
                <option value="">All sectors</option>
                {SECTORS.map((s) => <option key={s} value={s}>{label(s)}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm text-[color:var(--muted)]">Transaction type</span>
              <select value={dealType} onChange={(e) => setDealType(e.target.value)} className="field">
                <option value="">All transaction types</option>
                {DEAL_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
              </select>
            </label>
          </div>
          <label className="block">
            <span className="mb-1.5 block text-sm text-[color:var(--muted)]">Research focus (optional)</span>
            <textarea
              value={researchQuestion}
              onChange={(e) => setResearchQuestion(e.target.value)}
              maxLength={500}
              rows={4}
              placeholder="e.g. Which recent fintech transactions suggest consolidation, who are the active buyers, and what should an investment banking analyst investigate next?"
              className="field min-h-24 w-full resize-y"
            />
            <span className="mt-1.5 block text-xs text-[color:var(--dim)]">The LLM uses this to guide hybrid research across stored deals and live web/news results. Specific questions usually produce more useful briefs.</span>
          </label>
          <div className="rounded-lg border hairline p-4">
            <p className="text-sm font-medium">What the report includes</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-[color:var(--muted)]">
              <li>Transaction counts and disclosed values, with sample limitations stated</li>
              <li>Key transactions, source links and single-source/corroborated labels</li>
              <li>Descriptive activity patterns and comparable transactions</li>
              <li>LLM-written analysis informed by hybrid database and live web/news search</li>
              <li>Numbered evidence with clickable source links and citation checks</li>
              <li>Methodology, period and data-coverage caveats</li>
            </ul>
          </div>
          {error && <p className="text-sm text-risk" role="alert">{error}</p>}
          <button type="submit" className="btn btn-primary w-full sm:w-auto">Generate market brief</button>
        </form>
      )}
    </Container>
  );
}
