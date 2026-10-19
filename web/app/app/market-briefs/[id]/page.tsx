"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Container } from "../../../../components/primitives";
import { ApiError } from "../../../../lib/api";
import { get } from "../../../../lib/market";

type MarketReport = {
  brief_type: string; title: string; audience: string; period_start: string; period_end: string; generated_at: string;
  scope_label: string; metrics: { transaction_count: number; disclosed_value_count: number; disclosed_value_usd_label: string; countries_represented: number };
  key_transactions: Array<Record<string, any>>; comparables: Array<Record<string, any>>; observed_patterns: string[];
  advisory_signals: Array<{ title: string; rationale: string; evidence_count: number; evidence: Array<{ headline: string; url: string | null }> }>;
  methodology: string; coverage_note: string; markdown: string;
};
type Result = { id: string; title: string; report: MarketReport; markdown: string; created_at: string };

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}
const readable = (v: unknown) => String(v ?? "Not disclosed").replace(/_/g, " ");

export default function MarketBriefPage({ params }: { params: { id: string } }) {
  const [row, setRow] = useState<Result | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    get<Result>("/api/market-briefs/" + encodeURIComponent(params.id))
      .then(setRow)
      .catch((err) => { setRow(null); setError(err instanceof ApiError ? err.message : "Could not load this market brief."); });
  }, [params.id]);

  return (
    <Container className="max-w-5xl py-10 lg:py-14">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
        <Link href="/app" className="text-sm text-[color:var(--muted)] hover:text-[color:var(--text)]">← All briefs</Link>
        {row && <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-ghost h-8 px-3 text-[0.8125rem]" onClick={async () => {
            try { await navigator.clipboard.writeText(window.location.href); setCopied(true); }
            catch { setCopied(false); }
          }}>{copied ? "Link copied" : "Share link"}</button>
          <button type="button" className="btn btn-ghost h-8 px-3 text-[0.8125rem]" onClick={() => download("africa-deals-intelligence-brief.md", row.markdown || row.report.markdown)}>Export Markdown</button>
        </div>}
      </div>
      {row === undefined ? <p className="text-sm text-[color:var(--muted)]">Loading market brief…</p> :
       row === null ? <div><h1 className="h3 text-xl">{error ? "Could not load this brief" : "Market brief not found"}</h1><p className="mt-2 text-sm text-[color:var(--muted)]">{error ?? "Check the link and try again."}</p></div> :
       <article>
        <p className="eyebrow">Market intelligence · {row.report.audience}</p>
        <h1 className="h2 mt-3 text-[2rem] sm:text-[2.75rem]">{row.title}</h1>
        <p className="mt-3 text-sm text-[color:var(--muted)]">{row.report.scope_label}</p>
        <p className="mt-1 text-xs text-[color:var(--dim)]">Announcement window {row.report.period_start} to {row.report.period_end} · Generated {new Date(row.report.generated_at).toLocaleString()}</p>

        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Dated transaction records", row.report.metrics.transaction_count.toLocaleString()],
            ["Records with disclosed value", row.report.metrics.disclosed_value_count.toLocaleString()],
            ["Disclosed value total", row.report.metrics.disclosed_value_usd_label],
            ["Countries represented", row.report.metrics.countries_represented.toLocaleString()],
          ].map(([title, value]) => <div key={title} className="panel p-4"><p className="text-xs text-[color:var(--muted)]">{title}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>)}
        </div>
        <p className="mt-3 text-xs leading-relaxed text-[color:var(--dim)]">Metrics describe records currently held by Deal Intelligence, not a complete census of all transactions. Undisclosed amounts are not estimated.</p>

        <section className="mt-10">
          <h2 className="h3 text-xl">Key transactions</h2>
          <div className="mt-4 space-y-4">
            {row.report.key_transactions.length ? row.report.key_transactions.map((d, i) => <article key={String(d.id ?? i)} className="panel p-4 sm:p-5">
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

        <section className="mt-10">
          <h2 className="h3 text-xl">Observed patterns</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-[color:var(--muted)]">{row.report.observed_patterns.map((p, i) => <li key={i}>{p}</li>)}</ul>
        </section>
        <section className="mt-10">
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
        </section>
        <section className="mt-10">
          <h2 className="h3 text-xl">Comparable activity</h2>
          <div className="mt-3 divide-y hairline border-y hairline">
            {row.report.comparables.length ? row.report.comparables.map((d, i) => <div key={String(d.id ?? i)} className="py-3">
              <p className="font-medium">{readable(d.headline || d.target)}</p>
              <p className="mt-1 text-sm text-[color:var(--muted)]">{d.announced || "Date not recorded"} · {readable(d.deal_type)} · {d.amount_usd_label || "Amount not disclosed"}</p>
              {(d.sources || []).filter((s: any) => s.url).slice(0, 1).map((s: any) => <a key={s.url} className="mt-1 inline-block text-sm underline" href={s.url} target="_blank" rel="noreferrer">{s.publisher || "Source"} ↗</a>)}
            </div>) : <p className="py-4 text-sm text-[color:var(--muted)]">No comparable records met the similarity and date criteria.</p>}
          </div>
        </section>
        <section className="mt-10 panel p-5">
          <h2 className="h3 text-xl">Methodology and limitations</h2>
          <p className="mt-3 text-sm leading-relaxed text-[color:var(--muted)]">{row.report.methodology}</p>
          <p className="mt-3 text-sm leading-relaxed text-[color:var(--muted)]">{row.report.coverage_note}</p>
        </section>
       </article>}
    </Container>
  );
}
