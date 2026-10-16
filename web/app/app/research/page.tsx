"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { Container } from "../../../components/primitives";
import { ErrorNote, PageHeader, Pill, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { post, type ResearchResult } from "../../../lib/market";

const EXAMPLES = [
  "Which fintech companies in Nigeria raised money in the last 6 months, and from whom?",
  "What acquisitions happened in Kenyan banking this year?",
  "How risky is Ghana for a private equity investor right now?",
  "Which development finance institutions are most active in West Africa?",
];

/** Renders an answer with [n] citations as links to the evidence list. */
function Cited({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  const re = /\[(\d{1,3})\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    parts.push(text.slice(last, m.index));
    parts.push(
      <a key={m.index} href={`#ev-${m[1]}`} className="mx-0.5 align-super text-[0.6875rem] text-verified hover:underline">
        {m[1]}
      </a>,
    );
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
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
      <PageHeader eyebrow="Research" title="Ask about African companies, deals and risk.">
        Answers are written only from numbered evidence: the deals database, corporate events, country and currency
        risk, investor activity and a live news search. Citation numbers are checked against the evidence list; this
        confirms a source is present, not that it fully supports the claim.
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
            {v && <span>· {Math.round(v.grounded_share * 100)}% of factual sentences have valid citations</span>}
            {v && v.invalid_citations_removed.length > 0 && <span>· {v.invalid_citations_removed.length} invalid citation(s) removed</span>}
          </div>
          <div className="panel mt-3 whitespace-pre-wrap p-5 text-[0.9375rem] leading-relaxed">
            <Cited text={result.answer} />
          </div>
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
              </li>
            ))}
          </ol>
        </section>
      )}
    </Container>
  );
}
