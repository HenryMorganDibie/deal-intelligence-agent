"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { Container } from "../../../components/primitives";
import { ErrorNote, PageHeader, Pill, words } from "../../../components/app/ui";
import { ResultFeedback } from "../../../components/app/ResultFeedback";
import { ApiError } from "../../../lib/api";
import { post, type ResearchResult } from "../../../lib/market";

const EXAMPLES = [
  "Which fintech companies in Nigeria raised money in the last 6 months, and from whom?",
  "What acquisitions happened in Kenyan banking this year?",
  "How risky is Ghana for a private equity investor right now?",
  "Which development finance institutions are most active in West Africa?",
];

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
        show each source's classification, and should distinguish reported facts from derived analysis. Citation checks
        confirm that a cited item exists; they do not prove that it supports every claim. When evidence is missing,
        conflicting, stale or secondary, treat the answer as provisional and verify the underlying documents.
      </PageHeader>

      <form onSubmit={ask} className="space-y-3">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          rows={3}
          placeholder="Which fintech companies in Nigeria raised money in the last 6 months?"
          className="field min-h-[5.5rem] resize-y"
        />
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={busy} className="btn btn-primary">
            {busy ? "Researching..." : "Ask"}
          </button>
          <span className="text-[0.8125rem] text-[color:var(--dim)]">Counts toward the 1,000 free requests per visitor each day.</span>
        </div>
      </form>
      <div className="mt-5 flex flex-wrap gap-2">
        {EXAMPLES.map((q) => (
          <button
            key={q}
            type="button"
            disabled={busy}
            onClick={() => {
              setQuestion(q);
              ask(undefined, q);
            }}
            className="rounded-full border hairline px-3 py-1.5 text-left text-[0.8125rem] text-[color:var(--muted)] hover:text-[color:var(--text)] disabled:opacity-40"
          >
            {q}
          </button>
        ))}
      </div>
      {error && <ErrorNote message={error} />}

      {result && (
        <section className="mt-10" aria-label="Answer">
          <div className="flex flex-wrap items-center gap-2 text-[0.75rem] text-[color:var(--dim)]">
            <Pill value={result.mode === "llm" ? "LLM-written" : "deterministic"} title="Answer mode" />
            <span>{result.mode === "llm" ? `Written by ${result.model ?? "the LLM"} from the evidence below` : "Deterministic summary (no LLM configured)"}</span>
            {v && <span>· {Math.round(v.grounded_share * 100)}% of factual sentences have a citation (not a claim-accuracy score)</span>}
            {v && v.invalid_citations_removed.length > 0 && <span>· {v.invalid_citations_removed.length} invalid citation(s) removed</span>}
          </div>
          {v && (v.uncited_sentences.length > 0 || v.grounded_share < 1) && (
            <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
              <strong>Evidence review needed.</strong> Some factual statements do not have citations. Citation presence
              alone is not proof of correctness; verify material claims against the linked source documents before relying on them.
            </div>
          )}
          <FormattedAnswer text={result.answer} />
          <section className="mt-4 rounded-xl border hairline p-4" aria-label="Evidence coverage">
            <h2 className="text-sm font-semibold">Evidence retrieved for this question</h2>
            {result.evidence_coverage.length ? (
              <ul className="mt-2 flex flex-wrap gap-2">
                {result.evidence_coverage.map((source) => (
                  <li key={source.kind} className="rounded-full border hairline px-3 py-1 text-[0.75rem] text-[color:var(--muted)]">
                    {words(source.kind)}: {source.items}
                    {source.latest_source_date ? ` · latest dated ${source.latest_source_date}` : ""}
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
