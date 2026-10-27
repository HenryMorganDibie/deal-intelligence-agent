import { expectedMove, formatDate, label, SEVERITY_STYLE, type Brief, type Severity, type Signal, type TrackRecord } from "../../lib/brief";
import { ResultFeedback } from "./ResultFeedback";

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

const TRACK_STYLE: Record<TrackRecord["grade"], string> = {
  proven: "border-[color:var(--verified)] text-verified",
  indicative: "border-[color:var(--line)] text-[color:var(--text)]",
  insufficient: "border-[color:var(--line)] text-[color:var(--muted)]",
  chance: "border-[color:var(--line)] text-[color:var(--dim)]",
};

// How flags like this one have performed against how often the event happens anyway (walk-forward backtest
// pooled with live outcomes). The basis is in the tooltip.
function TrackRecordBadge({ record }: { record: TrackRecord }) {
  return (
    <span
      className={`kbd inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[0.6875rem] ${TRACK_STYLE[record.grade]}`}
      title={`Track record. ${record.basis}`}
    >
      {record.label}
    </span>
  );
}

function SignalCard({ s }: { s: Signal }) {
  const move = expectedMove(s.alpha_score);
  return (
    <article className="panel p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-verified">{label(s.signal_type)}</span>
        <SeverityBadge severity={s.severity} />
        {s.track_record && <TrackRecordBadge record={s.track_record} />}
        <span
          className="kbd text-[0.75rem] text-[color:var(--muted)]"
          title="Calibrated probability that this signal's event materialises"
        >
          {Math.round(s.confidence * 100)}% event probability
        </span>
        {s.alpha_score && (
          <span
            className="kbd text-[0.75rem] text-[color:var(--muted)]"
            title={
              s.alpha_score.compound_adjusted_score != null
                ? `Compound-adjusted ${s.alpha_score.compound_adjusted_score.toFixed(0)} (untested multiplier, not included)`
                : "Composite of severity, credibility, corroboration, recency and liquidity"
            }
          >
            alpha {s.alpha_score.score.toFixed(0)}
          </span>
        )}
        {s.alpha_score?.learned_confirmation_probability != null && (
          <span
            className="kbd text-[0.75rem] text-[color:var(--muted)]"
            title="Experimental learned probability of historical event confirmation. Separate from alpha; not a buy/sell recommendation."
          >
            learned confirmation {Math.round(s.alpha_score.learned_confirmation_probability * 100)}%
          </span>
        )}
        {move && (
          <span
            title={s.alpha_score?.move_basis ?? "Measured market-adjusted 10-day move after similar flags"}
            className={`kbd ml-auto text-[0.8125rem] ${move.startsWith("↓") ? "text-risk" : move.startsWith("↑") ? "text-verified" : "text-[color:var(--muted)]"}`}
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

const VERIFICATION_STEPS: Record<string, string> = {
  m_and_a_activity: "Confirm the transaction parties, announcement date, and whether it is proposed or completed in the original announcement.",
  credit_risk: "Check the latest financial statements, debt maturities, liquidity position, and any rating-agency update.",
  distressed_asset: "Verify the legal or restructuring status and distinguish a filing from a report or market rumour.",
  earnings_surprise: "Compare the reported figures with the original results release and the prior-period basis.",
  leadership_change: "Confirm the named executive, role, effective date, and whether the departure is confirmed.",
  regulatory_action: "Read the regulator's notice and verify whether it is an investigation, proposed action, or final decision.",
  debt_restructuring: "Check the original lender or court notice for affected debt, terms, and current status.",
  insider_activity: "Verify the original insider disclosure, transaction date, and whether the trade was a purchase or sale.",
};

export function BriefView({ brief, resultId }: { brief: Brief; resultId?: string }) {
  const signals = brief.detected_signals ?? [];
  const keyMetrics = brief.key_metrics ?? [];
  const recentDevelopments = brief.recent_developments ?? [];
  const filings = brief.filings_reviewed ?? [];
  const news = brief.news_reviewed ?? [];
  const latestFiling = filings.map((filing) => filing.filing_date).filter(Boolean).sort().at(-1);
  const latestNews = news.map((item) => item.published_date).filter(Boolean).sort().at(-1);
  const verificationSteps = [...new Set(signals.map((signal) => VERIFICATION_STEPS[signal.signal_type]).filter(Boolean))];
  const deterministicOnly = /LLM unavailable/i.test(brief.analyst_model ?? "");
  return (
    <div className="space-y-10">
      <header>
        <div className="flex flex-wrap items-center gap-3">
          <SeverityBadge severity={brief.overall_severity} />
          {signals.length > 0 && (
            <span
              className="kbd text-[0.75rem] text-[color:var(--muted)]"
              title="Mean calibrated probability that the confirmed signal events materialise"
            >
              {Math.round(brief.confidence_score * 100)}% mean event probability
            </span>
          )}
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

      {keyMetrics.length > 0 && (
        <section aria-labelledby="metrics-title">
          <h2 id="metrics-title" className="eyebrow">Key metrics</h2>
          <ul className="mt-3 divide-y divide-white/[0.07] border-y hairline">
            {keyMetrics.map((metric, i) => (
              <li key={`${metric.name}-${i}`} className="grid gap-1 py-3 sm:grid-cols-[minmax(8rem,0.6fr)_minmax(0,1.4fr)]">
                <div>
                  <p className="font-medium">{metric.name}</p>
                  <p className="kbd text-[0.75rem] text-[color:var(--dim)]">{metric.value}{metric.period ? ` · ${metric.period}` : ""}</p>
                </div>
                <p className="text-[0.875rem] leading-relaxed text-[color:var(--muted)]">{metric.interpretation}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {(brief.competitive_context || recentDevelopments.length > 0) && (
        <section aria-labelledby="context-title" className="space-y-5">
          <h2 id="context-title" className="eyebrow">Company context</h2>
          {brief.competitive_context && <p className="text-[0.9375rem] leading-relaxed">{brief.competitive_context}</p>}
          {recentDevelopments.length > 0 && (
            <ul className="list-disc space-y-1.5 pl-5 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">
              {recentDevelopments.map((development, i) => <li key={`${development}-${i}`}>{development}</li>)}
            </ul>
          )}
        </section>
      )}

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

      <section aria-labelledby="verify-next-title" className="rounded-xl border hairline p-5">
        <h2 id="verify-next-title" className="eyebrow">What to verify next</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-[0.875rem] leading-relaxed text-[color:var(--muted)]">
          {(verificationSteps.length ? verificationSteps : [
            "No signal was found in the sources retrieved for this run. Check the lookback period and available filings/news before concluding that no relevant event occurred.",
          ]).map((step) => <li key={step}>{step}</li>)}
        </ul>
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
        <p className="mt-2 text-[0.8125rem] text-[color:var(--dim)]">
          Retrieved {filings.length} filing(s) and {news.length} news item(s).
          {latestFiling ? ` Latest filing date: ${latestFiling}.` : " No filing date is available."}
          {latestNews ? ` Latest news publication date: ${latestNews}.` : " No news publication date is available."}
          {" "}These are source dates, not source refresh timestamps or proof that all sources were available.
        </p>
        <div className="mt-3 grid gap-6 md:grid-cols-2">
          <div className="min-w-0">
            <p className="text-[0.8125rem] text-[color:var(--dim)]">Filings ({filings.length})</p>
            <ul className="mt-2 space-y-1.5">
              {filings.slice(0, 25).map((f, i) => (
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
            <p className="text-[0.8125rem] text-[color:var(--dim)]">News ({news.length})</p>
            <ul className="mt-2 space-y-1.5">
              {news.slice(0, 25).map((n, i) => (
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
      {resultId && <ResultFeedback resultType="brief" resultId={resultId} />}
    </div>
  );
}
