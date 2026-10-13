import { expectedMove, formatDate, label, SEVERITY_STYLE, type Brief, type Severity, type Signal } from "../../lib/brief";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`kbd inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[0.6875rem] uppercase tracking-[0.1em] ${SEVERITY_STYLE[severity]}`}
    >
      {severity}
    </span>
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function SignalCard({ s }: { s: Signal }) {
  const move = expectedMove(s.alpha_score);
  return (
    <article className="panel p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-verified">{label(s.signal_type)}</span>
        <SeverityBadge severity={s.severity} />
        <span className="kbd text-[0.75rem] text-[color:var(--muted)]">{Math.round(s.confidence * 100)}% confidence</span>
        {s.alpha_score && (
          <span className="kbd text-[0.75rem] text-[color:var(--muted)]">alpha {s.alpha_score.score.toFixed(0)}</span>
        )}
        {move && (
          <span
            className={`kbd ml-auto text-[0.8125rem] ${s.alpha_score?.expected_direction === "negative" ? "text-risk" : "text-verified"}`}
          >
            {move}
          </span>
        )}
      </div>
      <h3 className="mt-3 text-[1.0625rem] font-medium leading-snug">{s.headline}</h3>
      <p className="mt-2 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
        <span className="kbd mr-2 text-[0.6875rem] uppercase tracking-[0.12em] text-explain">Why</span>
        {s.reasoning}
      </p>

      {s.attribution_doubt && (
        <p className="mt-3 rounded-[10px] border border-risk/30 bg-risk/5 p-3 text-[0.875rem] text-risk">
          Attribution check: {s.attribution_doubt}
        </p>
      )}

      {s.evidence.length > 0 && (
        <ul className="mt-4 space-y-1.5 border-l border-white/10 pl-4">
          {s.evidence.slice(0, 4).map((e, i) => (
            <li key={i} className="text-[0.875rem] leading-relaxed text-[color:var(--muted)]">
              {e}
            </li>
          ))}
        </ul>
      )}

      {s.source_urls.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {s.source_urls.slice(0, 6).map((u) => (
            <a
              key={u}
              href={u}
              target="_blank"
              rel="noreferrer noopener"
              className="kbd rounded-full border hairline px-2.5 py-1 text-[0.6875rem] text-[color:var(--muted)] transition-colors hover:text-[color:var(--text)]"
            >
              {hostOf(u)} ↗
            </a>
          ))}
        </div>
      )}
    </article>
  );
}

export function BriefView({ brief }: { brief: Brief }) {
  const signals = brief.detected_signals ?? [];
  const deterministicOnly = /LLM unavailable/i.test(brief.analyst_model ?? "");
  return (
    <div className="space-y-10">
      <header>
        <div className="flex flex-wrap items-center gap-3">
          <SeverityBadge severity={brief.overall_severity} />
          <span className="kbd text-[0.75rem] text-[color:var(--muted)]">
            {Math.round(brief.confidence_score * 100)}% confidence
          </span>
          <span className="kbd text-[0.75rem] text-[color:var(--dim)]">{formatDate(brief.brief_date)}</span>
          {brief.compliance_mode && <span className="tag">Compliance mode</span>}
        </div>
        <h1 className="h2 mt-4 text-[2.25rem] sm:text-[3rem]">
          {brief.company_name}
          {brief.ticker && <span className="kbd ml-3 align-middle text-[1rem] text-[color:var(--dim)]">{brief.ticker}</span>}
        </h1>
      </header>

      {brief.requires_human_review && (
        <section className="rounded-[14px] border border-risk/30 bg-risk/[0.06] p-5" aria-labelledby="review-title">
          <h2 id="review-title" className="kbd text-[0.75rem] uppercase tracking-[0.12em] text-risk">
            Human review required
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[0.9375rem] text-[color:var(--text)]">
            {brief.human_review_reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="summary-title" className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <h2 id="summary-title" className="eyebrow">
            Executive summary
          </h2>
          <p className="mt-3 whitespace-pre-line text-[1.0625rem] leading-relaxed">{brief.executive_summary}</p>
        </div>
        <div className="panel p-5">
          <h2 className="eyebrow">Recommendation</h2>
          <p className="mt-3 text-[0.9375rem] leading-relaxed">{brief.recommendation}</p>
        </div>
      </section>

      <section aria-labelledby="signals-title">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="signals-title" className="eyebrow">
            Signals ({signals.length})
          </h2>
          <span className="kbd text-[0.75rem] text-[color:var(--dim)]">
            {brief.signal_candidates_count} candidates · {brief.total_sources} sources
            {brief.low_confidence_signals_suppressed > 0 && ` · ${brief.low_confidence_signals_suppressed} suppressed`}
          </span>
        </div>
        {signals.length === 0 ? (
          <p className="panel mt-3 p-5 text-[0.9375rem] text-[color:var(--muted)]">
            No deal signals were found in the lookback window. The rule engine only reports what it can tie to a filing or
            article about this company.
          </p>
        ) : (
          <div className="mt-3 space-y-3">
            {signals.map((s, i) => (
              <SignalCard key={`${s.signal_type}-${i}`} s={s} />
            ))}
          </div>
        )}
      </section>

      {brief.compound_signals?.length > 0 && (
        <section aria-labelledby="compound-title">
          <h2 id="compound-title" className="eyebrow">
            Compound events · systemic risk {label(brief.systemic_risk_level)}
          </h2>
          <div className="mt-3 space-y-3">
            {brief.compound_signals.map((c) => (
              <div key={c.compound_id} className="panel p-5">
                <p className="kbd text-[0.75rem] text-[color:var(--muted)]">
                  {c.component_signal_types.map(label).join(" + ")} · {label(c.interaction_type)} · escalation{" "}
                  {c.escalation_score.toFixed(2)}
                </p>
                {c.reasoning_chain && <p className="mt-2 text-[0.9375rem] leading-relaxed">{c.reasoning_chain}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {brief.risk_factors?.length > 0 && (
        <section aria-labelledby="risk-title">
          <h2 id="risk-title" className="eyebrow">
            Risk factors
          </h2>
          <ul className="mt-3 divide-y divide-white/[0.07] border-y hairline">
            {brief.risk_factors.map((r) => (
              <li key={r.factor} className="flex flex-col gap-1 py-3 sm:flex-row sm:items-start sm:gap-4">
                <SeverityBadge severity={r.likelihood} />
                <div>
                  <p className="font-medium">{r.factor}</p>
                  <p className="text-[0.875rem] text-[color:var(--muted)]">{r.impact}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {brief.compliance_flags?.length > 0 && (
        <section aria-labelledby="compliance-title">
          <h2 id="compliance-title" className="eyebrow">
            Compliance flags
          </h2>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-[0.9375rem] text-[color:var(--muted)]">
            {brief.compliance_flags.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="sources-title">
        <h2 id="sources-title" className="eyebrow">
          Sources reviewed
        </h2>
        <div className="mt-3 grid gap-6 md:grid-cols-2">
          <div className="min-w-0">
            <p className="text-[0.8125rem] text-[color:var(--dim)]">Filings ({brief.filings_reviewed.length})</p>
            <ul className="mt-2 space-y-1.5">
              {brief.filings_reviewed.slice(0, 25).map((f, i) => (
                <li key={`${f.document_url}-${i}`} className="truncate text-[0.875rem]">
                  <a href={f.document_url} target="_blank" rel="noreferrer noopener" className="hover:underline">
                    <span className="kbd text-[0.75rem] text-verified">{f.form_type}</span>{" "}
                    <span className="text-[color:var(--muted)]">{f.filing_date}</span> {f.description}
                  </a>
                </li>
              ))}
            </ul>
          </div>
          <div className="min-w-0">
            <p className="text-[0.8125rem] text-[color:var(--dim)]">News ({brief.news_reviewed.length})</p>
            <ul className="mt-2 space-y-1.5">
              {brief.news_reviewed.slice(0, 25).map((n, i) => (
                <li key={`${n.url}-${i}`} className="truncate text-[0.875rem]">
                  <a href={n.url} target="_blank" rel="noreferrer noopener" className="hover:underline">
                    <span className="text-[color:var(--muted)]">{n.source}</span> {n.title}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <footer className="border-t hairline pt-5 text-[0.8125rem] leading-relaxed text-[color:var(--dim)]">
        Generated by {deterministicOnly ? "the deterministic engine only (no LLM narrative)" : brief.analyst_model}
        {brief.processing_time_seconds != null && ` in ${brief.processing_time_seconds}s`}. Research tooling, not
        investment advice. Verify every signal against its source before acting on it.
      </footer>
    </div>
  );
}
