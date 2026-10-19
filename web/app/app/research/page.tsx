"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Container } from "../../../components/primitives";
import { ErrorNote, PageHeader, Pill, words } from "../../../components/app/ui";
import { ResultFeedback } from "../../../components/app/ResultFeedback";
import { ApiError } from "../../../lib/api";
import { get, post, type Event as MarketEvent, type ResearchResult } from "../../../lib/market";

type ResearchSuggestion = {
  title: string;
  description: string;
  question: string;
  category: string;
  context?: string;
};

const FALLBACK_EXAMPLES: ResearchSuggestion[] = [
  {
    title: "Track a new funding round",
    description: "Identify the investors, amount, stage and what is actually confirmed.",
    question: "Find recently announced funding rounds in African private markets. For each, identify the company, investors, amount, round stage, announcement date and primary evidence. Mark unreported fields as unknown.",
    category: "Funding",
  },
  {
    title: "Map a sector shift",
    description: "See what recent deals reveal about where capital is moving.",
    question: "Which African sectors have seen notable private-market investment activity in the last 90 days? Compare disclosed deal counts and values where available, name the underlying transactions, and distinguish observed evidence from interpretation.",
    category: "Market trends",
  },
  {
    title: "Check a company's deal history",
    description: "Build a sourced timeline of raises, acquisitions and exits.",
    question: "Build a sourced transaction timeline for a company relevant to African private markets, including funding rounds, acquisitions, debt financing and exits. Link each event to evidence and flag conflicts or gaps.",
    category: "Company research",
  },
  {
    title: "Understand a regulatory change",
    description: "Connect a policy decision to the businesses and investors it may affect.",
    question: "Identify recent regulatory or central-bank changes affecting African businesses or investors. Explain the effective date, affected markets and sectors, and likely implications, separating the official rule from analysis.",
    category: "Policy & risk",
  },
];

function promptsFromEvents(events: MarketEvent[]): ResearchSuggestion[] {
  const seen = new Set<string>();
  return events
    .filter((event) => event.headline?.trim())
    .filter((event) => {
      const key = event.headline.trim().toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 4)
    .map((event) => {
      const headline = event.headline.trim();
      const context = [event.country, event.sector].filter(Boolean).join(" · ");
      return {
        title: headline.length > 86 ? `${headline.slice(0, 83).trimEnd()}…` : headline,
        description: context ? `Recent signal in ${context}. Open a sourced brief and separate facts from implications.` : "Explore the reported event, verify the key details and assess what it could mean.",
        question: `Investigate this recent market event: "${headline}". Summarize what happened, identify the companies and investors involved, extract dates and disclosed amounts, assess market implications, and separate confirmed facts from inference and unknowns. Cite supporting evidence.`,
        category: event.sector || "Latest event",
        ...(context ? { context } : {}),
      };
    });
}

/** Renders common Markdown inline formatting and links citations to the evidence list. */
function AnswerText({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  const re = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\[(\d{1,3})\]|(\*\*[^*]+\*\*|__[^_]+__)|(\*[^*\n]+\*|_[^_\n]+_)|`([^`\n]+)`|(https?:\/\/[^\s)]+)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    parts.push(text.slice(last, m.index));
    if (m[1] && m[2]) {
      parts.push(<a key={m.index} href={m[2]} target="_blank" rel="noreferrer noopener" className="text-verified hover:underline">{m[1]}</a>);
    } else if (m[3]) {
      parts.push(
        <a key={m.index} href={`#ev-${m[3]}`} className="mx-0.5 align-super text-[0.6875rem] text-verified hover:underline">
          {m[3]}
        </a>,
      );
    } else if (m[4]) {
      parts.push(<strong key={m.index}>{m[4].slice(2, -2)}</strong>);
    } else if (m[5]) {
      parts.push(<em key={m.index}>{m[5].slice(1, -1)}</em>);
    } else if (m[6]) {
      parts.push(<code key={m.index} className="rounded bg-white/5 px-1 py-0.5 text-[0.875em]">{m[6]}</code>);
    } else if (m[7]) {
      const url = m[7].replace(/[.,;:!?]+$/, "");
      parts.push(<a key={m.index} href={url} target="_blank" rel="noreferrer noopener" className="break-all text-verified hover:underline">{url}</a>);
      parts.push(m[7].slice(url.length));
    }
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

function FormattedAnswer({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let paragraph: string[] = [];
  const lines = text.split(/\r?\n/);

  const tableCells = (line: string) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
  const isTableSeparator = (line: string) => {
    const cells = tableCells(line);
    return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
  };

  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={`list-${blocks.length}`} className={`${list.ordered ? "list-decimal" : "list-disc"} space-y-1 pl-5`}>
        {list.items.map((item, i) => <li key={`${i}-${item}`}><AnswerText text={item} /></li>)}
      </Tag>,
    );
    list = null;
  };
  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(<p key={`paragraph-${blocks.length}`}><AnswerText text={paragraph.join(" ")} /></p>);
    paragraph = [];
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed.includes("|") && lines[i + 1] && isTableSeparator(lines[i + 1])) {
      flushParagraph();
      flushList();
      const headers = tableCells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().includes("|")) {
        rows.push(tableCells(lines[i]));
        i += 1;
      }
      i -= 1;
      blocks.push(
        <div key={`table-${blocks.length}`} className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-[0.8125rem]">
            <thead>
              <tr className="border-b hairline">
                {headers.map((cell, index) => <th key={`${index}-${cell}`} className="px-3 py-2 font-semibold"><AnswerText text={cell} /></th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="border-b hairline last:border-0">
                  {headers.map((_, index) => <td key={index} className="px-3 py-2 align-top"><AnswerText text={row[index] ?? ""} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    const bullet = /^\s*[-*+]\s+(.+)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      const content = <AnswerText text={heading[2]} />;
      blocks.push(heading[1].length === 1
        ? <h2 key={`heading-${blocks.length}`} className="h3 text-xl">{content}</h2>
        : <h3 key={`heading-${blocks.length}`} className="eyebrow">{content}</h3>);
    } else if (bullet || numbered) {
      flushParagraph();
      const ordered = Boolean(numbered);
      if (list && list.ordered !== ordered) flushList();
      if (!list) list = { ordered, items: [] };
      list.items.push((bullet ?? numbered)![1]);
    } else if (trimmed) {
      flushList();
      paragraph.push(trimmed);
    } else {
      flushParagraph();
      flushList();
    }
  }
  flushParagraph();
  flushList();
  return <article className="panel mt-3 space-y-4 p-5 text-[0.9375rem] leading-relaxed">{blocks}</article>;
}

export default function ResearchPage() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [marketExamples, setMarketExamples] = useState<ResearchSuggestion[]>([]);

  useEffect(() => {
    let active = true;
    const refreshMarketExamples = async () => {
      try {
        const since = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
        const response = await get<{ events: MarketEvent[] }>("/api/events", { since, limit: 20 });
        const suggestions = promptsFromEvents(response.events ?? []);
        if (active) setMarketExamples(suggestions);
      } catch {
        if (active) setMarketExamples([]);
      }
    };
    void refreshMarketExamples();
    const dailyRefresh = window.setInterval(() => void refreshMarketExamples(), 24 * 60 * 60 * 1000);
    return () => {
      active = false;
      window.clearInterval(dailyRefresh);
    };
  }, []);

  const examples: ResearchSuggestion[] = marketExamples.length ? marketExamples : FALLBACK_EXAMPLES;

  async function ask(e?: FormEvent, q = question) {
    e?.preventDefault();
    if (q.trim().length < 5 || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await post<ResearchResult>("/api/research", { question: q.trim() }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The research request failed.");
    } finally {
      setBusy(false);
    }
  }

  const v = result?.validation;
  return (
    <Container className="max-w-4xl py-10 lg:py-14">
      <PageHeader eyebrow="Research" title="Ask an analyst question.">
        Search combines the structured deals and events database with live news search. Answers cite numbered evidence,
        show each source&apos;s classification, and should distinguish reported facts from derived analysis. Citation checks
        confirm that a cited item exists; they do not prove that it supports every claim. When evidence is missing,
        conflicting, stale or secondary, treat the answer as provisional and verify the underlying documents.
      </PageHeader>

      <form onSubmit={ask} className="space-y-3">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          rows={3}
          placeholder="Ask a question about a company, transaction, market, regulation, financial metric or risk..."
          className="field min-h-[5.5rem] resize-y"
        />
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={busy} className="btn btn-primary">
            {busy ? "Researching..." : "Ask"}
          </button>
          <span className="text-[0.8125rem] text-[color:var(--dim)]">Counts toward the 1,000 free requests per visitor each day.</span>
        </div>
      </form>
      <section className="mt-8" aria-label="Research suggestions">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow">A place to start</p>
            <h2 className="mt-1 text-lg font-semibold tracking-tight">Research ideas</h2>
            <p className="mt-1 max-w-xl text-sm text-[color:var(--muted)]">
              Choose a lead to launch a sourced analyst brief, built around the latest market signals.
            </p>
          </div>
          <span className="text-[0.75rem] text-[color:var(--dim)]">
            {marketExamples.length ? "Inspired by recent market events · updates daily" : "Curated analyst starting points"}
          </span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {examples.map((suggestion, index) => (
            <button
              key={`${suggestion.title}-${index}`}
              type="button"
              disabled={busy}
              onClick={() => { setQuestion(suggestion.question); void ask(undefined, suggestion.question); }}
              className="group flex min-h-40 flex-col rounded-xl border hairline bg-[color:var(--panel)] p-4 text-left transition hover:border-[color:var(--verified)]/50 hover:bg-white/[0.025] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <div className="flex w-full items-center justify-between gap-3">
                <span className="rounded-full border hairline px-2.5 py-1 text-[0.6875rem] font-medium text-[color:var(--muted)]">
                  {suggestion.category}
                </span>
                <span aria-hidden="true" className="text-base text-[color:var(--dim)] transition group-hover:translate-x-0.5 group-hover:text-[color:var(--verified)]">↗</span>
              </div>
              <span className="mt-4 text-sm font-semibold leading-snug text-[color:var(--text)]">{suggestion.title}</span>
              <span className="mt-2 text-[0.8125rem] leading-relaxed text-[color:var(--muted)]">{suggestion.description}</span>
              {suggestion.context && (
                <span className="mt-3 text-[0.6875rem] text-[color:var(--dim)]">{suggestion.context}</span>
              )}
              <span className="mt-auto pt-4 text-[0.75rem] font-medium text-[color:var(--verified)]">
                Use this idea <span aria-hidden="true">→</span>
              </span>
            </button>
          ))}
        </div>
      </section>
      {error && <ErrorNote message={error} />}

      {result && (
        <section className="mt-10" aria-label="Answer">
          <div className="flex flex-wrap items-center gap-2 text-[0.75rem] text-[color:var(--dim)]">
            <Pill value={result.mode === "llm" ? "LLM-written" : "deterministic"} title="Answer mode" />
            <span>{result.mode === "llm" ? `Written by ${result.model ?? "the LLM"} from the evidence below` : "Deterministic summary (no LLM configured)"}</span>
            {v && <span>· {Math.round(v.grounded_share * 100)}% of factual sentences have a citation (not a claim-accuracy score)</span>}
            {v && v.invalid_citations_removed.length > 0 && <span>· {v.invalid_citations_removed.length} invalid citation(s) removed</span>}
          </div>
          {v && (v.uncited_sentences.length > 0 || v.grounded_share < 1 || (v.weakly_supported_sentences?.length ?? 0) > 0) && (
            <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
              <strong>Evidence review needed.</strong> Some factual statements are uncited or have low keyword overlap with their cited sources.
              This is a triage warning, not a semantic accuracy score. Citation presence alone is not proof of correctness; verify material claims against the linked source documents.
            </div>
          )}
          {v?.weakly_supported_sentences && v.weakly_supported_sentences.length > 0 && (
            <details className="mt-3 text-[0.8125rem] text-[color:var(--muted)]">
              <summary className="cursor-pointer">Claims whose citations may not support them ({v.weakly_supported_sentences.length})</summary>
              <ul className="mt-2 list-disc space-y-2 pl-5">
                {v.weakly_supported_sentences.map((item, index) => (
                  <li key={`${item.sentence}-${index}`}>
                    <p>{item.sentence}</p>
                    <p className="text-[0.75rem] text-[color:var(--dim)]">Cited evidence: {item.cited_items.map((n) => `[${n}]`).join(", ")} · keyword overlap {Math.round(item.overlap * 100)}%</p>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {v?.claim_audit && v.claim_audit.length > 0 && (
            <details className="mt-3 rounded-xl border hairline p-4">
              <summary className="cursor-pointer text-sm font-semibold">Claim-to-source audit ({v.claim_audit.length} statements)</summary>
              <p className="mt-1 text-xs text-[color:var(--dim)]">
                This maps each factual sentence to its citations and source metadata. Status and keyword overlap are triage signals, not proof that a claim is true.
              </p>
              <ol className="mt-3 space-y-3">
                {v.claim_audit.map((entry, index) => (
                  <li key={index} className="border-b hairline pb-3">
                    <p className="text-sm">{String(entry.sentence ?? "")}</p>
                    <p className="mt-1 text-xs text-[color:var(--muted)]">
                      Status: {String(entry.status ?? "needs review")}
                      {typeof entry.lexical_overlap === "number" ? ` · keyword overlap ${Math.round(entry.lexical_overlap * 100)}%` : ""}
                    </p>
                    {Array.isArray(entry.sources) && entry.sources.length > 0 ? (
                      <ul className="mt-2 space-y-1 text-xs">
                        {entry.sources.map((rawSource, sourceIndex) => {
                          const source = rawSource as Record<string, unknown>;
                          const title = String(source.title ?? source.source ?? "Evidence source");
                          return (
                            <li key={sourceIndex}>
                              {typeof source.url === "string" ? (
                                <a href={source.url} target="_blank" rel="noreferrer" className="hover:underline">
                                  [{String(source.n ?? "?")}] {title}
                                </a>
                              ) : (
                                <span>[{String(source.n ?? "?")}] {title}</span>
                              )}
                              {source.date ? ` · ${String(source.date)}` : ""}
                              {source.source_quality ? ` · ${String(source.source_quality)}` : ""}
                            </li>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className="mt-1 text-xs text-[color:var(--dim)]">No valid source citation was mapped to this statement.</p>
                    )}
                  </li>
                ))}
              </ol>
            </details>
          )}
          <FormattedAnswer text={result.answer} />
          {result.conflicts && result.conflicts.length > 0 && (
            <section className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4" aria-label="Evidence disagreements">
              <h2 className="text-sm font-semibold">Evidence disagreements to review</h2>
              <p className="mt-1 text-xs text-[color:var(--muted)]">Automated flags for human review, not a determination that any source is wrong.</p>
              <ul className="mt-3 space-y-3">
                {result.conflicts.map((conflict, index) => (
                  <li key={index} className="text-sm">
                    <p>{conflict.message}</p>
                    <ul className="mt-1 list-disc pl-5 text-xs text-[color:var(--muted)]">
                      {conflict.values.map((entry, entryIndex) => (
                        <li key={entryIndex}>
                          {new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(entry.value)} {conflict.currency} · evidence {entry.evidence.map((n) => "[" + n + "]").join(", ")}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {result.limitations && result.limitations.length > 0 && (
            <details className="mt-4 rounded-xl border hairline p-4">
              <summary className="cursor-pointer text-sm font-semibold">Research scope and limitations ({result.limitations.length})</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-[color:var(--muted)]">
                {result.limitations.map((note, index) => <li key={index}>{note}</li>)}
              </ul>
            </details>
          )}
          {result.query_execution && (
            <p className="mt-3 text-xs text-[color:var(--muted)]">
              Search execution: {result.query_execution.successful_queries}/{result.query_execution.planned_queries} queries succeeded, {result.query_execution.unique_results_before_filters} unique results before filters.
            </p>
          )}
          {result.query_plan && result.query_plan.length > 0 && (
            <details className="mt-4 rounded-xl border hairline p-4">
              <summary className="cursor-pointer text-sm font-semibold">Search strategy ({result.query_plan.length} query variants)</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-[color:var(--muted)]">
                {result.query_plan.map((query, index) => <li key={index}>{query}</li>)}
              </ul>
            </details>
          )}
          <section className="mt-4 rounded-xl border hairline p-4" aria-label="Evidence coverage">
            <h2 className="text-sm font-semibold">Evidence retrieved for this question</h2>
            {result.evidence_coverage.length ? (
              <ul className="mt-2 flex flex-wrap gap-2">
                {result.evidence_coverage.map((source) => (
                  <li key={source.kind} className="rounded-full border hairline px-3 py-1 text-[0.75rem] text-[color:var(--muted)]">
                    {words(source.kind)}: {source.items}
                    {source.latest_source_date ? ` · latest dated ${source.latest_source_date}` : ""}
                    {source.distinct_source_domains ? ` · ${source.distinct_source_domains} source domains` : ""}
                    {source.direct_article_text_items ? ` · ${source.direct_article_text_items} full-text retrieved` : ""}
                    {source.snippet_only_items ? ` · ${source.snippet_only_items} snippets only` : ""}
                    {source.distinct_headlines ? ` · ${source.distinct_headlines} distinct headlines` : ""}
                    {source.likely_syndicated_items ? ` · ${source.likely_syndicated_items} likely syndicated items` : ""}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-[color:var(--muted)]">No evidence items were retrieved for this question.</p>
            )}
            <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">
              Counts describe the evidence shown below, not all information available in the market. Dates are source dates, not refresh timestamps.
            </p>
          </section>
          {v && v.uncited_sentences.length > 0 && (
            <details className="mt-3 text-[0.8125rem] text-[color:var(--muted)]">
              <summary className="cursor-pointer">Sentences without a citation ({v.uncited_sentences.length})</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {v.uncited_sentences.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </details>
          )}

          <h2 className="eyebrow mt-10">Evidence ({result.evidence.length})</h2>
          <ol className="mt-3 space-y-3">
            {result.evidence.map((i) => (
              <li key={i.n} id={`ev-${i.n}`} className="border-b hairline pb-3 text-[0.8125rem]">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="kbd text-verified">[{i.n}]</span>
                  <span className="text-[0.75rem] text-[color:var(--dim)]">
                    {words(i.kind)}
                    {i.source ? ` · ${i.source}` : ""}
                    {i.date ? ` · ${i.date}` : ""}
                    {i.source_quality ? ` · ${i.source_quality}` : ""}
                    {i.content_status === "article_text_retrieved" ? " · publisher article text retrieved (not independently verified)" : ""}
                    {i.content_status === "snippet_only" ? " · snippet only" : ""}
                    {i.content_status === "injected_search_snippet" ? " · search snippet only" : ""}
                    {i.syndication_group_size && i.syndication_group_size > 1 ? ` · possible syndication (${i.syndication_group_size} matching headlines)` : ""}
                  </span>
                </div>
                <p className="mt-1">
                  {i.url ? (
                    <a href={i.url} target="_blank" rel="noreferrer" className="hover:underline">
                      {i.title}
                    </a>
                  ) : (
                    i.title
                  )}
                </p>
                {i.text !== i.title && <p className="mt-1 text-[color:var(--muted)]">{i.text}</p>}
                {i.content_url && i.content_url !== i.url && (
                  <p className="mt-1 text-xs text-[color:var(--dim)]">
                    Retrieved article text from{" "}
                    <a href={i.content_url} target="_blank" rel="noreferrer" className="hover:underline">
                      final publisher URL
                    </a>
                    . Original source link is retained above.
                  </p>
                )}
                {i.source_quality_note && <p className="mt-1 text-[0.75rem] text-[color:var(--dim)]">{i.source_quality_note}</p>}
              </li>
            ))}
          </ol>
          <ResultFeedback resultType="research" resultId={result.result_id} />
        </section>
      )}
    </Container>
  );
}
