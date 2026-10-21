"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Container } from "../../../../components/primitives";
import { ApiError } from "../../../../lib/api";
import { get, post } from "../../../../lib/market";
import { trackProductAction } from "../../../../lib/tracking";

type MarketReport = {
  parent_brief_id?: string | null;
  brief_type: string; title: string; audience: string; period_start: string; period_end: string; generated_at: string;
  scope_label: string; metrics: { transaction_count: number; disclosed_value_count: number; disclosed_value_usd_label: string; countries_represented: number };
  key_transactions: Array<Record<string, any>>; comparables: Array<Record<string, any>>; observed_patterns: string[];
  newsletter_selected_evidence?: Array<{ n?: number; kind?: string; title: string; text?: string; url: string | null; date?: string | null; source?: string | null; source_quality?: string; source_quality_note?: string }>;
  advisory_signals: Array<{ title: string; rationale: string; evidence_count: number; evidence: Array<{ headline: string; url: string | null }> }>;
  methodology: string; coverage_note: string; markdown: string;
  research_question?: string;
  web_research?: {
    question?: string; answer?: string; mode?: "llm" | "deterministic" | "unavailable"; model?: string | null;
    evidence?: Array<{ n: number; kind: string; title: string; text: string; url: string | null; date: string | null; source: string | null; source_quality?: string; source_quality_note?: string }>;
    validation?: { grounded_share?: number; invalid_citations_removed?: number; uncited_sentences?: string[] };
  };
};
type Result = { id: string; title: string; report: MarketReport; markdown: string; created_at: string };

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}
const readable = (v: unknown) => String(v ?? "Not disclosed").replace(/_/g, " ");

function distribution(items: Array<Record<string, any>>, field: string) {
  const counts = new Map<string, number>();
  for (const item of items) {
    const raw = field === "country"
      ? (item.country || item.countries?.[0])
      : item[field];
    const label = String(raw || "Unclassified").replace(/_/g, " ");
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 5);
}

function DistributionChart({ title, values }: { title: string; values: Array<[string, number]> }) {
  const max = Math.max(1, ...values.map(([, count]) => count));
  return (
    <section className="panel p-4 sm:p-5">
      <h3 className="text-sm font-semibold">{title}</h3>
      {values.length ? <div className="mt-4 space-y-3">
        {values.map(([label, count]) => (
          <div key={label}>
            <div className="mb-1 flex items-center justify-between gap-3 text-xs">
              <span className="min-w-0 truncate">{label}</span>
              <span className="shrink-0 text-[color:var(--muted)]">{count}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/10" role="img" aria-label={label + ": " + count}>
              <div className="h-full rounded-full bg-[color:var(--verified)]" style={{ width: (count / max * 100) + "%" }} />
            </div>
          </div>
        ))}
      </div> : <p className="mt-3 text-sm text-[color:var(--muted)]">No classified items available.</p>}
    </section>
  );
}

export default function MarketBriefPage({ params }: { params: { id: string } }) {
  const [row, setRow] = useState<Result | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [selectedItems, setSelectedItems] = useState<string[]>([]);
  const [briefingType, setBriefingType] = useState<"deal" | "advisory" | "both">("both");
  const [newsletterAudience, setNewsletterAudience] = useState("Investment banking analyst");
  const [newsletterInstructions, setNewsletterInstructions] = useState("");
  const [generatingNewsletter, setGeneratingNewsletter] = useState(false);
  const [newsletterError, setNewsletterError] = useState<string | null>(null);
  const router = useRouter();
  useEffect(() => {
    get<Result>("/api/market-briefs/" + encodeURIComponent(params.id))
      .then((result) => { trackProductAction("market_brief_opened"); setRow(result); })
      .catch((err) => { setRow(null); setError(err instanceof ApiError ? err.message : "Could not load this market brief."); });
  }, [params.id]);

  useEffect(() => {
    if (!row) return;
    const dealItems = (row.report.key_transactions ?? []).map((_, index) => "deal:" + index);
    const webItems = (row.report.web_research?.evidence ?? []).slice(0, 25).map((item) => "web:" + item.n);
    setSelectedItems([...dealItems, ...webItems].slice(0, 40));
  }, [row?.id]);

  function toggleSelected(item: string, checked: boolean) {
    if (checked) {
      if (selectedItems.includes(item)) return;
      if (selectedItems.length >= 40) {
        setNewsletterError("A newsletter can include up to 40 selected items. Remove an item before adding another.");
        return;
      }
      setNewsletterError(null);
      setSelectedItems((current) => [...new Set([...current, item])]);
    } else {
      setSelectedItems((current) => current.filter((value) => value !== item));
      setNewsletterError(null);
    }
  }

  async function createNewsletter() {
    if (!row || generatingNewsletter || selectedItems.length === 0) return;
    setGeneratingNewsletter(true);
    setNewsletterError(null);
    try {
      const created = await post<{ id: string }>("/api/market-briefs/newsletter", {
        source_brief_id: row.id,
        briefing_type: briefingType,
        selected_items: selectedItems,
        audience: newsletterAudience,
        ...(newsletterInstructions.trim() ? { instructions: newsletterInstructions.trim() } : {}),
      });
      router.push("/app/market-briefs/" + encodeURIComponent(created.id));
    } catch (err) {
      setNewsletterError(err instanceof ApiError ? err.message : "Could not generate the newsletter. Please try again.");
      setGeneratingNewsletter(false);
    }
  }

  return (
    <Container className="max-w-5xl py-10 lg:py-14">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-3 print-hide">
        <Link href="/app" className="text-sm text-[color:var(--muted)] hover:text-[color:var(--text)]">← All briefs</Link>
        {row && <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-ghost h-8 px-3 text-[0.8125rem]" onClick={async () => {
            try { await navigator.clipboard.writeText(window.location.href); setCopied(true); }
            catch { setCopied(false); }
          }}>{copied ? "Link copied" : "Share link"}</button>
          {row.report.brief_type === "research_newsletter" && <button type="button" className="btn btn-primary h-8 px-3 text-[0.8125rem]" onClick={() => window.print()}>Export PDF / Print</button>}
          {row.report.brief_type !== "research_newsletter" && <button type="button" className="btn btn-ghost h-8 px-3 text-[0.8125rem]" onClick={() => download("africa-deals-intelligence-brief.md", row.markdown || row.report.markdown)}>Export Markdown</button>}
        </div>}
      </div>
      {row === undefined ? <p className="text-sm text-[color:var(--muted)]">Loading market brief…</p> :
       row === null ? <div><h1 className="h3 text-xl">{error ? "Could not load this brief" : "Market brief not found"}</h1><p className="mt-2 text-sm text-[color:var(--muted)]">{error ?? "Check the link and try again."}</p></div> :
       <article>
        <p className="eyebrow">{row.report.brief_type === "research_newsletter" ? "Research newsletter" : "Market intelligence"} · {row.report.audience}</p>
        <h1 className="h2 mt-3 text-[2rem] sm:text-[2.75rem]">{row.title}</h1>
        <p className="mt-3 text-sm text-[color:var(--muted)]">{row.report.scope_label}</p>
        <p className="mt-1 text-xs text-[color:var(--dim)]">Announcement window {row.report.period_start} to {row.report.period_end} · Generated {new Date(row.report.generated_at).toLocaleString()}</p>
        {row.report.parent_brief_id && <p className="mt-2 text-sm"><Link href={"/app/market-briefs/" + encodeURIComponent(row.report.parent_brief_id)} className="underline underline-offset-4">Open source research brief ↗</Link></p>}
        {row.report.brief_type === "research_newsletter" && <p className="mt-2 text-xs text-[color:var(--muted)]">Draft newsletter · verify every source and claim before external distribution.</p>}

        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Dated transaction records", row.report.metrics.transaction_count.toLocaleString()],
            ["Records with disclosed value", row.report.metrics.disclosed_value_count.toLocaleString()],
            ["Disclosed value total", row.report.metrics.disclosed_value_usd_label],
            ["Countries represented", row.report.metrics.countries_represented.toLocaleString()],
          ].map(([title, value]) => <div key={title} className="panel p-4"><p className="text-xs text-[color:var(--muted)]">{title}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>)}
        </div>
        <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">Metrics describe records currently held by Deal Intelligence, not a complete census of all transactions. Undisclosed amounts are not estimated.</p>

        {row.report.brief_type === "research_newsletter" && <>
          <section className="mt-8">
            <p className="eyebrow">Market analytics</p>
            <h2 className="h3 mt-2 text-xl">What the selected evidence shows</h2>
            <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">These charts summarize the transaction records selected for this briefing. They describe this evidence sample only, not the entire market or undisclosed activity.</p>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <DistributionChart title="Deal type" values={distribution(row.report.key_transactions ?? [], "deal_type")} />
              <DistributionChart title="Sector distribution" values={distribution(row.report.key_transactions ?? [], "sector")} />
              <DistributionChart title="Country distribution" values={distribution(row.report.key_transactions ?? [], "country")} />
            </div>
          </section>
          <section className="mt-8 panel p-5 sm:p-7 newsletter-prose">
            <p className="eyebrow">Deal Intelligence · Analyst briefing</p>
            <h2 className="h3 mt-2 text-xl">Newsletter</h2>
            <div className="mt-5 whitespace-pre-wrap text-[0.98rem] leading-8">{row.report.web_research?.answer || "Newsletter text is not available."}</div>
          </section>
        </>}

        <section className="mt-10 panel p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow">Hybrid research</p>
              <h2 className="h3 mt-2 text-xl">{row.report.brief_type === "research_newsletter" ? "Source evidence and citation trail" : "LLM analysis with live web evidence"}</h2>
              {row.report.research_question && <p className="mt-2 text-sm text-[color:var(--muted)]">Focus: {row.report.research_question}</p>}
            </div>
            <span className="kbd">{row.report.web_research?.mode === "llm" ? "LLM synthesis" : row.report.web_research?.mode === "deterministic" ? "Deterministic fallback" : "Web research unavailable"}</span>
          </div>
          {row.report.web_research?.mode !== "llm" && (
            <p className="mt-3 text-sm leading-relaxed text-[color:var(--muted)]">
              {row.report.web_research?.mode === "deterministic"
                ? "The LLM was unavailable for this run, so this section uses the research engine's deterministic fallback. Check the linked evidence before relying on an interpretation."
                : "Live web research could not be completed for this run. The database-backed transaction metrics remain available; no external findings have been inferred."}
            </p>
          )}
          {row.report.brief_type !== "research_newsletter" && row.report.web_research?.answer && (
            <div className="mt-4 whitespace-pre-wrap text-sm leading-7">{row.report.web_research.answer}</div>
          )}
          {row.report.web_research?.validation && (
            <p className="mt-3 text-xs text-[color:var(--dim)]">
              Citation validation: {Math.round((row.report.web_research.validation.grounded_share ?? 0) * 100)}% grounded sentences
              {typeof row.report.web_research.validation.invalid_citations_removed === "number"
                ? " · " + row.report.web_research.validation.invalid_citations_removed + " invalid citation(s) removed"
                : ""}.
            </p>
          )}
          <div className="mt-5 border-t hairline pt-4">
            {row.report.brief_type === "research_newsletter" && (row.report.newsletter_selected_evidence ?? []).length > 0 && <div className="mb-5">
              <h3 className="text-sm font-semibold">Analyst-selected web sources ({row.report.newsletter_selected_evidence?.length ?? 0})</h3>
              <ul className="mt-3 space-y-3">
                {(row.report.newsletter_selected_evidence ?? []).map((item, index) => <li key={String(item.n ?? index) + "-" + (item.url ?? item.title)} className="border-b hairline pb-3 last:border-0">
                  <div className="flex flex-wrap items-center gap-2">
                    {typeof item.n === "number" && <span className="kbd">[{item.n}]</span>}
                    {item.date && <span className="text-xs text-[color:var(--dim)]">{item.date}</span>}
                  </div>
                  {item.url ? <a className="mt-1 inline-block text-sm font-medium underline underline-offset-4" href={item.url} target="_blank" rel="noreferrer">{item.title} ↗</a> : <p className="mt-1 text-sm font-medium">{item.title}</p>}
                  {item.source && <p className="mt-1 text-xs text-[color:var(--muted)]">Source: {item.source}{item.source_quality ? " · " + item.source_quality : ""}</p>}
                  {item.text && <p className="mt-1 text-sm leading-relaxed text-[color:var(--muted)]">{item.text}</p>}
                  {item.source_quality_note && <p className="mt-1 text-xs text-[color:var(--dim)]">{item.source_quality_note}</p>}
                </li>)}
              </ul>
            </div>}
            <h3 className="text-sm font-semibold">Research-engine evidence ({row.report.web_research?.evidence?.length ?? 0})</h3>
            <p className="mt-1 text-xs text-[color:var(--dim)]">Search results and stored records are evidence leads, not automatic confirmation. Check the original publisher page for context.</p>
            {(row.report.web_research?.evidence ?? []).length ? (
              <ul className="mt-3 space-y-3">
                {(row.report.web_research?.evidence ?? []).map((item) => (
                  <li key={String(item.n) + "-" + (item.url ?? item.title)} className="border-b hairline pb-3 last:border-0">
                    {row.report.brief_type !== "research_newsletter" && <label className="mb-2 flex items-center gap-2 text-xs text-[color:var(--muted)]">
                      <input type="checkbox" checked={selectedItems.includes("web:" + item.n)} onChange={(e) => toggleSelected("web:" + item.n, e.target.checked)} />
                      Include this web finding in the newsletter
                    </label>}
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="kbd">[{item.n}]</span>
                      <span className="text-xs uppercase tracking-wide text-[color:var(--muted)]">{readable(item.kind)}</span>
                      {item.date && <span className="text-xs text-[color:var(--dim)]">{item.date}</span>}
                    </div>
                    {item.url ? (
                      <a className="mt-1 inline-block text-sm font-medium underline decoration-[color:var(--dim)] underline-offset-4 hover:text-[color:var(--text)]" href={item.url} target="_blank" rel="noreferrer">{item.title} ↗</a>
                    ) : <p className="mt-1 text-sm font-medium">{item.title}</p>}
                    {item.source && <p className="mt-1 text-xs text-[color:var(--muted)]">Source: {item.source}{item.source_quality ? " · " + item.source_quality : ""}</p>}
                    <p className="mt-1 text-sm leading-relaxed text-[color:var(--muted)]">{item.text}</p>
                    {item.source_quality_note && <p className="mt-1 text-xs text-[color:var(--dim)]">{item.source_quality_note}</p>}
                  </li>
                ))}
              </ul>
            ) : <p className="mt-3 text-sm text-[color:var(--muted)]">No additional live web evidence was returned for this query.</p>}
          </div>
        </section>

        <section className="mt-10">
          <h2 className="h3 text-xl">Key transactions</h2>
          <div className="mt-4 space-y-4">
            {row.report.key_transactions.length ? row.report.key_transactions.map((d, i) => <article key={String(d.id ?? i)} className="panel p-4 sm:p-5">
              {row.report.brief_type !== "research_newsletter" && <label className="mb-3 flex items-center gap-2 text-xs text-[color:var(--muted)]">
                <input type="checkbox" checked={selectedItems.includes("deal:" + i)} onChange={(e) => toggleSelected("deal:" + i, e.target.checked)} />
                Include this transaction in the newsletter
              </label>}
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-xs uppercase tracking-wide text-[color:var(--muted)]">{readable(d.deal_type)} · {readable(d.stage)}</p>
                  <h3 className="mt-1 text-base font-semibold">{readable(d.headline || d.target)}</h3>
                </div>
                <span className="rounded-full border hairline px-2.5 py-1 text-xs">{readable(d.verification)}</span>
              </div>
              <p className="mt-3 text-sm text-[color:var(--muted)]">{d.announced || "Date not recorded"} · {readable(d.sector)} · {d.amount_usd_label || "Amount not disclosed"}</p>
              <p className="mt-1 text-sm text-[color:var(--muted)]">Parties: {[d.buyer, d.target, d.seller].filter(Boolean).join(" · ") || "Not fully identified"}</p>
              {Array.isArray(d.sources) && d.sources.length > 0 && <ul className="mt-3 space-y-1.5">{d.sources.filter((s: any) => s.url).slice(0, 3).map((s: any, j: number) => <li key={s.url + j}><a className="text-sm underline decoration-[color:var(--dim)] underline-offset-4 hover:text-[color:var(--text)]" href={s.url} target="_blank" rel="noreferrer">{s.publisher || s.title || "Open source"} ↗</a>{s.date ? <span className="ml-2 text-xs text-[color:var(--dim)]">{s.date}</span> : null}</li>)}</ul>}
              <p className="mt-3 text-xs text-[color:var(--dim)]">{d.independent_stories ?? 0} independent story group(s); this is not a guarantee that every field is correct.</p>
            </article>) : <p className="text-sm text-[color:var(--muted)]">No transaction records matched the selected filters and dates.</p>}
          </div>
        </section>

        {row.report.brief_type !== "research_newsletter" && <section className="mt-10">
          <h2 className="h3 text-xl">Observed patterns</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-[color:var(--muted)]">{row.report.observed_patterns.map((p, i) => <li key={i}>{p}</li>)}</ul>
        </section>}
        {row.report.brief_type !== "research_newsletter" && <section className="mt-10">
          <h2 className="h3 text-xl">Potential advisory research leads</h2>
          <p className="mt-2 text-sm text-[color:var(--muted)]">These are evidence-based prompts for further research, not confirmed mandates or recommendations.</p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {(row.report.advisory_signals ?? []).length ? row.report.advisory_signals.map((signal, i) => <article key={signal.title + i} className="panel p-4">
              <h3 className="font-semibold">{signal.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">{signal.rationale}</p>
              <p className="mt-2 text-xs text-[color:var(--dim)]">Based on {signal.evidence_count} transaction records in this sample</p>
              <ul className="mt-2 space-y-1">{signal.evidence.filter((e) => e.url).slice(0, 3).map((e, j) => <li key={(e.url ?? "") + j}><a className="text-sm underline underline-offset-4" href={e.url ?? "#"} target="_blank" rel="noreferrer">{e.headline || "Supporting transaction"} ↗</a></li>)}</ul>
            </article>) : <p className="text-sm text-[color:var(--muted)]">The current sample does not show repeated activity strong enough to generate a research lead.</p>}
          </div>
        </section>}
        {row.report.brief_type !== "research_newsletter" && <section className="mt-10">
          <h2 className="h3 text-xl">Comparable activity</h2>
          <div className="mt-3 divide-y hairline border-y hairline">
            {row.report.comparables.length ? row.report.comparables.map((d, i) => <div key={String(d.id ?? i)} className="py-3">
              <p className="font-medium">{readable(d.headline || d.target)}</p>
              <p className="mt-1 text-sm text-[color:var(--muted)]">{d.announced || "Date not recorded"} · {readable(d.deal_type)} · {d.amount_usd_label || "Amount not disclosed"}</p>
              {(d.sources || []).filter((s: any) => s.url).slice(0, 1).map((s: any) => <a key={s.url} className="mt-1 inline-block text-sm underline" href={s.url} target="_blank" rel="noreferrer">{s.publisher || "Source"} ↗</a>)}
            </div>) : <p className="py-4 text-sm text-[color:var(--muted)]">No comparable records met the similarity and date criteria.</p>}
          </div>
        </section>}
        {row.report.brief_type !== "research_newsletter" && <section className="mt-10 panel p-5 sm:p-6 print-hide">
          <p className="eyebrow">Turn research into deliverable</p>
          <h2 className="h3 mt-2 text-xl">Create a deal or advisory newsletter</h2>
          <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">
            Select the deals and web findings that matter, choose the newsletter format, and let the LLM draft a polished, source-linked briefing.
            The generated newsletter is saved as its own shareable brief for review and PDF export.
          </p>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-sm text-[color:var(--muted)]">Briefing format</span>
              <select value={briefingType} onChange={(e) => setBriefingType(e.target.value as "deal" | "advisory" | "both")} className="field">
                <option value="both">Deal &amp; advisory newsletter</option>
                <option value="deal">Deal briefing newsletter</option>
                <option value="advisory">Advisory briefing newsletter</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm text-[color:var(--muted)]">Audience</span>
              <select value={newsletterAudience} onChange={(e) => setNewsletterAudience(e.target.value)} className="field">
                <option>Investment banking analyst</option>
                <option>Managing director / deal team</option>
                <option>Private equity investor</option>
                <option>Venture capital investor</option>
                <option>Corporate strategy team</option>
                <option>Market research analyst</option>
              </select>
            </label>
          </div>
          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm text-[color:var(--muted)]">Editorial instructions (optional)</span>
            <textarea value={newsletterInstructions} onChange={(e) => setNewsletterInstructions(e.target.value)} maxLength={1000} rows={3}
              placeholder="e.g. Lead with the three most material transactions, explain implications for Nigerian banks, and end with questions for the next client meeting."
              className="field min-h-20 w-full resize-y" />
          </label>
          <div className="mt-4 rounded-lg border hairline p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">Selected research items</h3>
              <span className="kbd">{selectedItems.length} selected</span>
            </div>
            <p className="mt-1 text-xs text-[color:var(--dim)]">Use the checkboxes beside transactions and web evidence below to refine this selection. Up to 40 items can be included.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="btn btn-ghost h-8 px-3 text-xs" onClick={() => setSelectedItems([
                ...(row.report.key_transactions ?? []).map((_, index) => "deal:" + index),
                ...(row.report.web_research?.evidence ?? []).slice(0, 25).map((item) => "web:" + item.n),
              ].slice(0, 40))}>Select all visible</button>
              <button type="button" className="btn btn-ghost h-8 px-3 text-xs" onClick={() => setSelectedItems([])}>Clear selection</button>
            </div>
          </div>
          {newsletterError && <p className="mt-3 text-sm text-risk" role="alert">{newsletterError}</p>}
          <button type="button" onClick={createNewsletter} disabled={generatingNewsletter || selectedItems.length === 0}
            className="btn btn-primary mt-4 w-full sm:w-auto">
            {generatingNewsletter ? "Drafting source-cited newsletter…" : "Generate newsletter from selected research"}
          </button>
          <p className="mt-2 text-xs leading-relaxed text-[color:var(--dim)]">Advisory opportunities are framed as evidence-backed research hypotheses, never as confirmed mandates. Review every citation before external distribution.</p>
        </section>}

        <section className="mt-10 panel p-5">
          <h2 className="h3 text-xl">Methodology and limitations</h2>
          <p className="mt-3 text-sm leading-relaxed text-[color:var(--muted)]">{row.report.methodology}</p>
          <p className="mt-3 text-sm leading-relaxed text-[color:var(--muted)]">{row.report.coverage_note}</p>
        </section>
       </article>}
    </Container>
  );
}
