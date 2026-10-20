"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Container } from "../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Table, Td, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { apiUrl, get } from "../../../lib/market";

type CI = { value: number; low: number | null; high: number | null; k?: number; n: number; median?: number } | null;
type Market = "all" | "us" | "africa";

type TypeRow = {
  predictions: number;
  event_confirmation: {
    labelled: number;
    confirmed: number;
    precision: CI;
    precision_official_only: CI;
    base_rate: { value: number | null; hits: number | null; company_months: number | null };
    lift: { value: number; low: number; high: number } | null;
    recall: CI;
  } | null;
  market_reaction: { moves_n: number; direction_hit_rate: CI; mean_move_in_predicted_direction_pct: CI };
};

type SignalReport = {
  generated_at?: string;
  refresh?: { schedule: string; next: string };
  design: {
    start: string;
    end: string;
    as_of_dates: number;
    companies: { us: number; africa: number };
    company_months: { us: number; africa: number };
    lookback_days: number;
    horizon_days: number;
    reproduce: string;
    universe_size?: number | null;
    uncovered_companies?: Record<string, number> | null;
    not_yet_run?: number | null;
  };
  funnel: Record<string, number | string>;
  by_type: Record<string, { price_only: boolean } & Record<Market, TypeRow>>;
  pooled_confirmable: Record<Market, TypeRow>;
  alpha: {
    what_it_is: string;
    reading: string;
    spearman_alpha_vs_confirmed: number | null;
    bands: Record<"low" | "middle" | "high", {
      alpha_range: [number, number] | null;
      event_confirmation: CI;
      direction_hit_rate: CI;
      mean_move_in_predicted_direction_pct: CI;
    }>;
    by_type: Record<string, { labelled: number; precision: Record<"low" | "middle" | "high", number | null>; spearman: number | null }> | null;
  };
  rules: { name: string; rule: string }[];
};

type Slice = Record<string, CI | { n: number; precision: CI; recall: CI } | null>;
type Extraction = {
  items: number;
  gold_transactions: number;
  sample: string;
  note_on_recall: string;
  detection: { all: { n: number; precision: CI; recall: CI }; by_language: Slice; by_country: Slice; by_publisher: Slice };
  fields: { n_records: number; all: Record<string, CI>; fully_correct_record: CI; by_deal_type: Slice; by_country: Slice; by_language: Slice };
};
type DataQuality = {
  extraction: Extraction;
  heldout_extraction: Extraction | null;
  dedup: { pairs: number; sample: string; merge_precision: CI; missed_duplicates_among_lookalikes: CI };
  identity: { pairs: number; sample: string; join_precision: CI; join_recall: CI; malformed_names_caught: CI; valid_names_kept: CI };
  heldout_names: { names: number; malformed_names_caught: CI; valid_names_resolved_to_the_right_organisation: CI } | null;
  labels: string;
};
type AttrStats = {
  items: number;
  items_with_an_event: number;
  exactly_right: CI;
  precision: CI;
  recall: CI;
  false_alarm_rate_on_no_event_items: CI;
};
type AttrSet = { overall: AttrStats; high_confidence_labels: AttrStats; by_market?: Record<string, AttrStats>; by_category?: Record<string, AttrStats> };
type Attribution = { natural: AttrSet | null; hard: AttrSet | null; sets: Record<string, string>; labels: string };
type ReturnForecastSlice = {
  holdout_n: number;
  holdout_dates?: number;
  candidate_mae_pct?: number;
  zero_return_baseline_mae_pct?: number;
  mae_improvement_pct?: number;
  direction_n?: number;
  direction_accuracy?: number | null;
  qualified: boolean;
  reason: string;
};
type ReturnForecastValidation = {
  horizon: string;
  candidate: string;
  train_through?: string;
  holdout_from?: string;
  holdout_through?: string;
  latest_labelled_as_of?: string;
  data_age_days?: number;
  freshness_max_age_days?: number;
  freshness_passed?: boolean;
  qualified: boolean;
  reason: string;
  overall: ReturnForecastSlice;
  by_market: Record<"us" | "africa", ReturnForecastSlice>;
};

type Review2026 = {
  name: string;
  seed: number;
  drawn: string;
  items: number;
  pairs: number;
  strata: Record<string, number>;
  pair_strata: Record<string, number>;
  note?: string;
  status: string;
  progress: { labels_a: number; labels_b: number; pair_labels_a: number; pair_labels_b: number; adjudicated: number };
};

type Evaluation = {
  review_2026?: Review2026 | null;
  signal_report: SignalReport | null;
  data_quality: DataQuality | null;
  data_quality_baseline: DataQuality | null;
  attribution: Attribution | null;
  attribution_before: Attribution | null;
  return_forecast_validation: ReturnForecastValidation | null;
  live_outcomes: Record<string, { confirmed: number; refuted: number }> | null;
  measured_now?: { backtest_observations: number; live_observations: number };
};

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "n/a" : `${Math.round(v * 100)}%`);

/** "51% [41–62] n=82": the value, its 95% interval and the sample behind it. */
function Ci({ x, unit = "%", digits = 0 }: { x: CI | undefined; unit?: "%" | "pp"; digits?: number }) {
  if (!x) return <span className="text-[color:var(--dim)]">n/a</span>;
  const f = (v: number | null) => (v === null ? "?" : unit === "%" ? (v * 100).toFixed(digits) : v.toFixed(1));
  const interval = x.low !== null && x.high !== null;
  const zeroInside = unit === "pp" && interval && (x.low as number) <= 0 && (x.high as number) >= 0;
  return (
    <span className="whitespace-nowrap">
      <span className={zeroInside ? "text-[color:var(--muted)]" : ""}>
        {unit === "pp" && x.value > 0 ? "+" : ""}
        {f(x.value)}
        {unit === "%" ? "%" : "%"}
      </span>
      {interval && (
        <span className="text-[color:var(--dim)]">
          {" "}
          [{f(x.low)} to {f(x.high)}]
        </span>
      )}
      <span className="text-[color:var(--dim)]"> n={x.n}</span>
    </span>
  );
}

function Section({ id, title, children, lede }: { id: string; title: string; lede?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-t`} className="scroll-mt-24 border-t hairline pt-10 mt-12">
      <h2 id={`${id}-t`} className="h3 text-[1.25rem]">
        {title}
      </h2>
      {lede && <div className="mt-3 max-w-3xl text-[0.875rem] leading-relaxed text-[color:var(--muted)]">{lede}</div>}
      <div className="mt-5">{children}</div>
    </section>
  );
}

function Callout({ tone = "neutral", children }: { tone?: "neutral" | "warn"; children: ReactNode }) {
  return (
    <div
      className={`rounded-[10px] border px-4 py-3 text-[0.8125rem] leading-relaxed ${
        tone === "warn" ? "border-risk/40 bg-risk/[0.05]" : "hairline bg-white/[0.02]"
      }`}
    >
      {children}
    </div>
  );
}

function liftSummary(r: SignalReport): string {
  const rows = Object.entries(r.by_type).filter(([, v]) => !v.price_only);
  const above = rows.filter(([, v]) => (v.all.event_confirmation?.lift?.low ?? 0) > 1).map(([k]) => words(k).toLowerCase());
  const unclear = rows.filter(([, v]) => {
    const l = v.all.event_confirmation?.lift;
    return !l || l.low <= 1;
  }).map(([k]) => words(k).toLowerCase());
  return `${above.length ? `Clearly above the base rate: ${above.join(", ")}.` : "No type is clearly above its base rate."} ` +
    `Not distinguishable from, or below, the base rate: ${unclear.join(", ")}.`;
}

function returnSummary(r: SignalReport): string {
  const sig = Object.entries(r.by_type).filter(([, v]) => {
    const m = v.all.market_reaction.mean_move_in_predicted_direction_pct;
    return m && m.low !== null && m.high !== null && (m.low > 0 || m.high < 0);
  });
  if (!sig.length) return "No signal type shows a mean market-adjusted move whose 95% interval excludes zero.";
  return `Mean move interval excludes zero for: ${sig
    .map(([k, v]) => `${words(k).toLowerCase()} (${(v.all.market_reaction.mean_move_in_predicted_direction_pct!.value ?? 0) > 0 ? "the predicted way" : "against the prediction"})`)
    .join(", ")}; all others are indistinguishable from no effect.`;
}

const day = (iso?: string | null) =>
  iso ? new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }) : null;

function nextRefresh(): string {
  const d = new Date();
  const n = d.getUTCDate() < 2 ? new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 2)) : new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 2));
  return n.toISOString().slice(0, 10);
}

/** How current each part of the page is, and when it next changes. */
function Freshness({ r, live }: { r: SignalReport; live: number }) {
  const total = r.design.companies.us + r.design.companies.africa;
  return (
    <div className="mb-6 grid gap-3 text-[0.8125rem] sm:grid-cols-3">
      <div className="panel p-4">
        <p className="eyebrow">Signal backtest</p>
        <p className="mt-1.5 leading-relaxed">
          {r.generated_at ? <>Last run {day(r.generated_at)}</> : <>Current run</>} over {total.toLocaleString("en-US")} companies (
          {r.design.companies.us.toLocaleString("en-US")} US, {r.design.companies.africa.toLocaleString("en-US")} African), replaying{" "}
          {day(r.design.start)} to {day(r.design.end)}.
        </p>
        {r.design.universe_size ? (
          <p className="mt-1.5 leading-relaxed">
            Universe: {r.design.universe_size.toLocaleString("en-US")} companies.
            {Object.values(r.design.uncovered_companies ?? {}).reduce((a, b) => a + b, 0) > 0 && (
              <> {Object.values(r.design.uncovered_companies ?? {}).reduce((a, b) => a + b, 0).toLocaleString("en-US")} had no usable price or news history and are excluded.</>
            )}
            {(r.design.not_yet_run ?? 0) > 0 && (
              <> {(r.design.not_yet_run ?? 0).toLocaleString("en-US")} have not been replayed yet and join in the next monthly run.</>
            )}
          </p>
        ) : null}
        <p className="mt-1.5 text-[color:var(--muted)]">Re-run monthly on the 2nd. Next: {day(r.refresh?.next ?? nextRefresh())}.</p>
      </div>
      <div className="panel p-4">
        <p className="eyebrow">Live outcomes</p>
        <p className="mt-1.5 leading-relaxed">
          {live.toLocaleString("en-US")} labelled so far from hosted briefs, added daily and pooled into the measured figures hourly.
        </p>
      </div>
      <div className="panel p-4">
        <p className="eyebrow">Labelled evaluation sets</p>
        <p className="mt-1.5 leading-relaxed">
          Deal data quality and attribution: samples labelled 14 October 2026. They change when new samples are drawn, never
          silently.
        </p>
      </div>
    </div>
  );
}

const NAV = [
  ["summary", "Summary"],
  ["populations", "What was counted"],
  ["events", "Did the event happen?"],
  ["returns", "Did the price move?"],
  ["return-forecast", "Return forecast validation"],
  ["alpha", "Alpha score"],
  ["rules", "Labelling rules"],
  ["data-quality", "Deal data quality"],
  ["attribution", "Attribution tests"],
  ["review-2026", "2026 independent review"],
  ["reproduce", "Reproduce"],
];

const STRATUM_LABEL: Record<string, string> = {
  random: "Random 2026 reports",
  "hard:cross_border": "Cross-border deals",
  "hard:french": "French-language headlines",
  "hard:large_amount": "Amounts of $1bn or more",
  "hard:duplicate_cluster": "Reports from duplicate clusters",
  negative_candidate: "Deal-like headlines that may not be deals",
  merged: "Reports the system merged",
  kept_apart: "Look-alike reports kept separate",
  hard_negative: "Same company, different amount",
};

function Progress({ label, done, total }: { label: string; done: number; total: number }) {
  const share = total ? Math.min(done / total, 1) : 0;
  return (
    <div>
      <div className="flex justify-between text-[0.8125rem]">
        <span>{label}</span>
        <span className="kbd text-[color:var(--dim)]">
          {done} / {total}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 rounded-full bg-white/[0.06]" role="progressbar" aria-valuenow={done} aria-valuemin={0} aria-valuemax={total} aria-label={label}>
        <div className="h-1.5 rounded-full bg-verified" style={{ width: `${share * 100}%` }} />
      </div>
    </div>
  );
}

function Review2026Section({ review }: { review: Review2026 }) {
  const p = review.progress;
  return (
    <Section
      id="review-2026"
      title="2026 independent review"
      lede={
        <>
          The labels above were written by an AI annotator and have not been reviewed by an independent person. To fix that, a
          fresh, blind sample of 2026 reports was drawn on {review.drawn} (fixed seed {review.seed}) for two independent human
          annotators, with a third resolving disagreements. Annotators see only the headline, publisher and date. The published
          scores do not change until both label sets and the adjudication are complete.
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-3">
        <div className="panel p-4">
          <p className="eyebrow">Status</p>
          <p className="mt-1.5 leading-relaxed capitalize">{review.status}</p>
          <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">
            {review.items} headlines and {review.pairs} report pairs
          </p>
        </div>
        <div className="panel p-4 md:col-span-2">
          <p className="eyebrow">Labelling progress</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Progress label="Headlines, annotator A" done={p.labels_a} total={review.items} />
            <Progress label="Headlines, annotator B" done={p.labels_b} total={review.items} />
            <Progress label="Pairs, annotator A" done={p.pair_labels_a} total={review.pairs} />
            <Progress label="Pairs, annotator B" done={p.pair_labels_b} total={review.pairs} />
          </div>
        </div>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {([
          ["Headlines in the sample", review.strata],
          ["Report pairs in the sample", review.pair_strata],
        ] as const).map(([title, counts]) => (
          <div key={title} className="panel p-4">
            <p className="eyebrow">{title}</p>
            <ul className="mt-2 grid gap-1 text-[0.8125rem]">
              {Object.entries(counts).map(([k, n]) => (
                <li key={k} className="flex justify-between gap-4">
                  <span>{STRATUM_LABEL[k] ?? k}</span>
                  <span className="kbd text-[color:var(--dim)]">{n}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="mt-4">
        <Callout>
          New fields measure the failures found in the October 2026 data audit: whether a figure is a deal size, a valuation or a
          market size; whether a record is in scope; and whether a country comes from the headline or from knowing the company.
          {review.note ? ` ${review.note}` : ""} The sample, blank label files and labelling guide are downloadable below.
        </Callout>
      </div>
    </Section>
  );
}

function MarketToggle({ market, set }: { market: Market; set: (m: Market) => void }) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Market">
      {(["all", "us", "africa"] as const).map((m) => (
        <button
          key={m}
          type="button"
          aria-pressed={market === m}
          onClick={() => set(m)}
          className={`rounded-full border px-3 py-1.5 text-[0.8125rem] ${
            market === m ? "border-white/30 text-[color:var(--text)]" : "hairline text-[color:var(--muted)]"
          }`}
        >
          {m === "all" ? "All markets" : m === "us" ? "US companies" : "African companies"}
        </button>
      ))}
    </div>
  );
}

function SliceTable({ title, slice, kind }: { title: string; slice: Slice; kind: "detection" | "complete" }) {
  return (
    <div>
      <p className="text-[0.8125rem] text-[color:var(--muted)]">{title}</p>
      <div className="mt-2">
        <Table head={kind === "detection" ? ["Group", "Items", "Precision", "Recall"] : ["Group", "Every field right"]} minWidth="28rem">
          {Object.entries(slice).map(([k, v]) => (
            <tr key={k}>
              <Td>{k === "other" ? "Other (smaller groups)" : k === "unknown" ? "Not identifiable" : words(k)}</Td>
              {kind === "detection" && v && "precision" in v ? (
                <>
                  <Td className="kbd">{v.n}</Td>
                  <Td className="kbd"><Ci x={v.precision} /></Td>
                  <Td className="kbd"><Ci x={v.recall} /></Td>
                </>
              ) : (
                <Td className="kbd"><Ci x={v as CI} /></Td>
              )}
            </tr>
          ))}
        </Table>
      </div>
    </div>
  );
}

export default function EvaluationPage() {
  const [e, setE] = useState<Evaluation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [market, setMarket] = useState<Market>("all");
  const [returnsMarket, setReturnsMarket] = useState<Market>("all");
  useEffect(() => {
    get<Evaluation>("/api/evaluation").then(setE).catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the evaluation."));
  }, []);

  const r = e?.signal_report;
  const dq = e?.data_quality;
  const ho = dq?.heldout_extraction;
  const attrNat = e?.attribution?.natural;
  const returnForecast = e?.return_forecast_validation;

  return (
    <Container className="py-10 lg:py-14">
      <PageHeader eyebrow="Evaluation" title="What was measured, how, and how often it was right.">
        Every figure below has its sample size and a 95% interval. Event confirmation and market returns are reported
        separately and never combined. The labelled sets and per-prediction files are downloadable at the end of the page.
      </PageHeader>
      <nav aria-label="Sections" className="mb-2 flex flex-wrap gap-2 text-[0.8125rem]">
        {NAV.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="rounded-full border hairline px-3 py-1.5 text-[color:var(--muted)] hover:text-[color:var(--text)]">
            {label}
          </a>
        ))}
      </nav>
      {e?.signal_report && <Freshness r={e.signal_report} live={e.measured_now?.live_observations ?? 0} />}
      {error && <ErrorNote message={error} />}
      {!e ? (
        <Loading />
      ) : (
        <>
          {r && (
            <Section id="summary" title="Summary">
              <ul className="grid gap-3 lg:grid-cols-2">
                <li className="panel p-4 text-[0.875rem] leading-relaxed">
                  <p className="eyebrow">Signals: did the event happen?</p>
                  <p className="mt-2">
                    Across confirmable signal types, <Ci x={r.pooled_confirmable.all.event_confirmation?.precision} /> of flags were
                    followed by the event within {r.design.horizon_days} days. {liftSummary(r)}
                  </p>
                </li>
                <li className="panel p-4 text-[0.875rem] leading-relaxed">
                  <p className="eyebrow">Signals: did the price move?</p>
                  <p className="mt-2">
                    This is a separate question. {returnSummary(r)} Nothing here is a trading result.
                  </p>
                </li>
                <li className="panel p-4 text-[0.875rem] leading-relaxed">
                  <p className="eyebrow">Deal records</p>
                  <p className="mt-2">
                    On a held-out set never used for tuning: detection precision <Ci x={ho?.detection.all.precision} />, recall{" "}
                    <Ci x={ho?.detection.all.recall} />; every field right on <Ci x={ho?.fields.fully_correct_record} /> of records.
                  </p>
                </li>
                <li className="panel p-4 text-[0.875rem] leading-relaxed">
                  <p className="eyebrow">Attribution of news to the right company</p>
                  <p className="mt-2">
                    On a random sample of real headlines naming tracked companies: precision <Ci x={attrNat?.overall.precision} />,
                    recall <Ci x={attrNat?.overall.recall} />, false alarms on headlines with no event{" "}
                    <Ci x={attrNat?.overall.false_alarm_rate_on_no_event_items} />. Filings and exchange notices are covered by
                    separate, stronger rules.
                  </p>
                </li>
              </ul>
              <p className="mt-4 text-[0.75rem] text-[color:var(--dim)]">
                Labelled sets were annotated from the source text alone, blind to the system&apos;s output, by an AI annotator.
                They are published item by item for inspection and are pending independent human review.
              </p>
            </Section>
          )}

          {r && (
            <Section
              id="populations"
              title="What was counted, and how the numbers relate"
              lede={String(r.funnel.explanation)}
            >
              <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  [r.funnel.predictions, "predictions", `every flag in the replay: ${r.design.companies.us} US and ${r.design.companies.africa} African companies × ${r.design.as_of_dates} monthly dates (${r.design.start} to ${r.design.end})`],
                  [r.funnel.confirmation_labelled, "labelled for event confirmation", `the ${r.funnel.confirmable_predictions} flags of confirmable types (M&A, credit, distress, leadership, regulatory, restructuring); ${r.funnel.confirmation_unlabelled} could not be checked`],
                  [r.funnel.confirmed, "confirmed", "of those labelled, the event was recorded within the horizon"],
                  [r.funnel.with_market_move, "with a market move", `flags of any type with prices on both dates; ${r.funnel.price_only_predictions} earnings and insider flags are judged on price only (${r.funnel.price_only_direction_labelled} with prices)`],
                ].map(([n, label, note]) => (
                  <li key={String(label)} className="panel p-4">
                    <p className="font-display text-2xl font-semibold">{n}</p>
                    <p className="text-[0.875rem]">{label}</p>
                    <p className="mt-1 text-[0.75rem] leading-snug text-[color:var(--muted)]">{note}</p>
                  </li>
                ))}
              </ol>
              <p className="mt-3 text-[0.8125rem] text-[color:var(--muted)]">
                The confidence figures shown in briefs use all {e.measured_now?.backtest_observations ?? r.funnel.predictions} backtest
                observations plus {e.measured_now?.live_observations ?? 0} live outcomes from hosted briefs, which are labelled under
                the same rules as they mature.
              </p>
            </Section>
          )}

          {r && (
            <Section
              id="events"
              title="Did the flagged event happen?"
              lede={
                <>
                  Precision is the share of labelled flags followed by the event. The base rate is the share of all
                  company-months followed by that event anyway; lift is precision divided by base rate, so a lift whose interval
                  includes 1 is no better than picking a company-month at random. Recall is the share of recorded events that a
                  flag preceded. This measures whether events happened, not whether anyone could profit from them.
                </>
              }
            >
              <MarketToggle market={market} set={setMarket} />
              <div className="mt-4">
                <Table
                  head={["Signal type", "Predictions", "Confirmed / labelled", "Precision [95% CI]", "Official sources only", "Base rate", "Lift [95% CI]", "Recall [95% CI]"]}
                  minWidth="72rem"
                >
                  {Object.entries(r.by_type)
                    .filter(([, v]) => !v.price_only)
                    .map(([st, v]) => {
                      const ec = v[market].event_confirmation;
                      const lift = ec?.lift;
                      return (
                        <tr key={st}>
                          <Td>{words(st)}</Td>
                          <Td className="kbd">{v[market].predictions}</Td>
                          <Td className="kbd">{ec ? `${ec.confirmed} / ${ec.labelled}` : "n/a"}</Td>
                          <Td className="kbd"><Ci x={ec?.precision} /></Td>
                          <Td className="kbd"><Ci x={ec?.precision_official_only} /></Td>
                          <Td className="kbd">
                            {ec?.base_rate.value != null ? (
                              <>
                                {pct(ec.base_rate.value)}
                                <span className="text-[color:var(--dim)]"> {ec.base_rate.hits}/{ec.base_rate.company_months}</span>
                              </>
                            ) : (
                              "n/a"
                            )}
                          </Td>
                          <Td className={`kbd ${lift ? (lift.low > 1 ? "text-verified" : lift.high < 1 ? "text-risk" : "") : ""}`}>
                            {lift ? `${lift.value}x [${lift.low} to ${lift.high}]` : "n/a"}
                          </Td>
                          <Td className="kbd"><Ci x={ec?.recall} /></Td>
                        </tr>
                      );
                    })}
                  <tr>
                    <Td className="font-medium">All confirmable types</Td>
                    <Td className="kbd">{r.pooled_confirmable[market].predictions}</Td>
                    <Td className="kbd">
                      {r.pooled_confirmable[market].event_confirmation?.confirmed} / {r.pooled_confirmable[market].event_confirmation?.labelled}
                    </Td>
                    <Td className="kbd"><Ci x={r.pooled_confirmable[market].event_confirmation?.precision} /></Td>
                    <Td className="kbd"><Ci x={r.pooled_confirmable[market].event_confirmation?.precision_official_only} /></Td>
                    <Td>{""}</Td>
                    <Td>{""}</Td>
                    <Td>{""}</Td>
                  </tr>
                </Table>
              </div>
              <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">
                Green lift: interval entirely above 1. Red: entirely below 1. Uncoloured: the data cannot tell it apart from the base
                rate. Earnings surprises and insider trades are not in this table: the disclosure is the event, so they are judged
                on price only (next section).
              </p>
            </Section>
          )}

          {r && (
            <Section
              id="returns"
              title="Did the share price move the predicted way?"
              lede={
                <>
                  A different outcome from the one above. For every flag with prices, the market-adjusted move over 10 calendar
                  days, signed so that a positive number means it went the predicted way. No trading costs, sizing, slippage or
                  portfolio construction are applied, so these are not returns anyone earned. Intervals that include zero (grey)
                  mean the data cannot distinguish the move from no effect.
                </>
              }
            >
              <MarketToggle market={returnsMarket} set={setReturnsMarket} />
              <div className="mt-4">
                <Table head={["Signal type", "Flags with prices", "Went the predicted way [95% CI]", "Mean move in predicted direction [95% CI]", "Median"]} minWidth="56rem">
                  {Object.entries(r.by_type).map(([st, v]) => {
                    const m = v[returnsMarket].market_reaction;
                    return (
                      <tr key={st}>
                        <Td>{words(st)}</Td>
                        <Td className="kbd">{m.moves_n}</Td>
                        <Td className="kbd"><Ci x={m.direction_hit_rate} /></Td>
                        <Td className="kbd"><Ci x={m.mean_move_in_predicted_direction_pct} unit="pp" digits={1} /></Td>
                        <Td className="kbd">
                          {m.mean_move_in_predicted_direction_pct?.median != null ? `${m.mean_move_in_predicted_direction_pct.median}%` : "n/a"}
                        </Td>
                      </tr>
                    );
                  })}
                </Table>
              </div>
            </Section>
          )}

          {r && (
            <Section id="alpha" title="The alpha score is a ranking, not a return forecast" lede={r.alpha.what_it_is}>
              <Table head={["Alpha third", "Alpha range", "Event confirmed [95% CI]", "Price went the predicted way [95% CI]", "Mean move in predicted direction [95% CI]"]} minWidth="60rem">
                {(["low", "middle", "high"] as const).map((k) => {
                  const b = r.alpha.bands[k];
                  return (
                    <tr key={k}>
                      <Td>{words(k)}</Td>
                      <Td className="kbd">{b.alpha_range ? `${b.alpha_range[0]} to ${b.alpha_range[1]}` : "n/a"}</Td>
                      <Td className="kbd"><Ci x={b.event_confirmation} /></Td>
                      <Td className="kbd"><Ci x={b.direction_hit_rate} /></Td>
                      <Td className="kbd"><Ci x={b.mean_move_in_predicted_direction_pct} unit="pp" digits={1} /></Td>
                    </tr>
                  );
                })}
              </Table>
              <div className="mt-4">
                <Callout tone="warn">
                  {r.alpha.reading} Rank correlation between alpha and confirmation: {r.alpha.spearman_alpha_vs_confirmed}.
                </Callout>
              </div>
              {r.alpha.by_type && Object.keys(r.alpha.by_type).length > 0 && (
                <div className="mt-6">
                  <p className="text-[0.8125rem] text-[color:var(--muted)]">
                    Within signal types with 30 or more labelled flags, so the result is not only a mix of types:
                  </p>
                  <div className="mt-2">
                    <Table head={["Signal type", "Labelled", "Low third", "Middle third", "High third", "Rank correlation"]} minWidth="40rem">
                      {Object.entries(r.alpha.by_type).map(([st, x]) => (
                        <tr key={st}>
                          <Td>{words(st)}</Td>
                          <Td className="kbd">{x.labelled}</Td>
                          <Td className="kbd">{pct(x.precision.low)}</Td>
                          <Td className="kbd">{pct(x.precision.middle)}</Td>
                          <Td className="kbd">{pct(x.precision.high)}</Td>
                          <Td className="kbd">{x.spearman ?? "n/a"}</Td>
                        </tr>
                      ))}
                    </Table>
                  </div>
                </div>
              )}
            </Section>
          )}

          <Section
            id="return-forecast"
            title="Return forecast validation"
            lede="This is a separate evaluation from alpha and event confirmation. A return estimate is eligible for use only after it beats a zero-return baseline on a recent chronological holdout, with enough data overall and in each market."
          >
            {!returnForecast ? (
              <Callout tone="warn">
                No return-forecast validation report has been published yet. The monthly backtest CI generates this report;
                until then, the system does not issue a return forecast.
              </Callout>
            ) : (
              <div className="space-y-4">
                <Callout tone={returnForecast.qualified ? "neutral" : "warn"}>
                  <strong>{returnForecast.qualified ? "Validation gates passed." : "No validated return forecast."}</strong>{" "}
                  {returnForecast.reason} Historical move ranges elsewhere on this page are descriptive, not forecasts
                  for an individual company or trading recommendations.
                </Callout>
                <div className="overflow-x-auto">
                  <Table
                    head={["Holdout", "Outcomes", "Candidate MAE", "Zero-return MAE", "MAE improvement", "Direction accuracy", "Status"]}
                    minWidth="58rem"
                  >
                    {(["overall", "us", "africa"] as const).map((key) => {
                      const slice = key === "overall" ? returnForecast.overall : returnForecast.by_market[key];
                      if (!slice) return null;
                      return (
                        <tr key={key}>
                          <Td>{words(key)}</Td>
                          <Td className="kbd">{slice.holdout_n}</Td>
                          <Td className="kbd">{slice.candidate_mae_pct == null ? "n/a" : `${slice.candidate_mae_pct.toFixed(3)}%`}</Td>
                          <Td className="kbd">{slice.zero_return_baseline_mae_pct == null ? "n/a" : `${slice.zero_return_baseline_mae_pct.toFixed(3)}%`}</Td>
                          <Td className="kbd">{slice.mae_improvement_pct == null ? "n/a" : `${slice.mae_improvement_pct.toFixed(3)}%`}</Td>
                          <Td className="kbd">{slice.direction_accuracy == null ? "n/a" : `${(slice.direction_accuracy * 100).toFixed(1)}% (n=${slice.direction_n ?? 0})`}</Td>
                          <Td>{slice.qualified ? "Passed" : "Not passed"}</Td>
                        </tr>
                      );
                    })}
                  </Table>
                </div>
                <p className="text-[0.75rem] leading-relaxed text-[color:var(--dim)]">
                  Horizon: {returnForecast.horizon}. Training through {day(returnForecast.train_through) ?? "n/a"};
                  holdout {day(returnForecast.holdout_from) ?? "n/a"} to {day(returnForecast.holdout_through) ?? "n/a"}.
                  Latest labelled date: {day(returnForecast.latest_labelled_as_of) ?? "n/a"}
                  {returnForecast.data_age_days != null ? ` (${returnForecast.data_age_days} days old)` : ""}.
                  Freshness gate: at most {returnForecast.freshness_max_age_days ?? "n/a"} days.
                  Even if these retrospective gates pass, individual live return estimates are not issued yet.
                </p>
              </div>
            )}
          </Section>

          {r && (
            <Section id="rules" title="Labelling rules and time windows" lede="The same rules apply to the backtest and to hosted briefs; the differing day counts are buffers, explained below.">
              <dl className="grid gap-3">
                {r.rules.map((x) => (
                  <div key={x.name} className="panel p-4">
                    <dt className="text-[0.875rem] font-medium">{x.name}</dt>
                    <dd className="mt-1 text-[0.8125rem] leading-relaxed text-[color:var(--muted)]">{x.rule}</dd>
                  </div>
                ))}
              </dl>
            </Section>
          )}

          {dq && (
            <Section
              id="data-quality"
              title="Deal data quality"
              lede={
                <>
                  The pipeline from raw headline to deal record, scored against labels made from the headline text alone. The
                  development set was used to find and fix errors, so its post-fix numbers are optimistic. The held-out set was drawn
                  afterwards and never used for tuning: its numbers are the ones to rely on.
                </>
              }
            >
              <Table head={["Measure", "Development set, before fixes", "Development set, after fixes", "Held-out set"]} minWidth="56rem">
                {[
                  ["Detection precision (is it a real transaction?)", (d: DataQuality | null | undefined) => d?.extraction.detection.all.precision, ho?.detection.all.precision],
                  ["Detection recall (deal-like headlines caught)", (d: DataQuality | null | undefined) => d?.extraction.detection.all.recall, ho?.detection.all.recall],
                  ["Every field right", (d: DataQuality | null | undefined) => d?.extraction.fields.fully_correct_record, ho?.fields.fully_correct_record],
                ].map(([label, f, h]) => (
                  <tr key={String(label)}>
                    <Td>{String(label)}</Td>
                    <Td className="kbd"><Ci x={(f as (d: DataQuality | null | undefined) => CI)(e.data_quality_baseline)} /></Td>
                    <Td className="kbd"><Ci x={(f as (d: DataQuality | null | undefined) => CI)(dq)} /></Td>
                    <Td className="kbd"><Ci x={h as CI} /></Td>
                  </tr>
                ))}
              </Table>

              <h3 className="eyebrow mt-8">By field, on records that are real transactions</h3>
              <div className="mt-3">
                <Table head={["Field", "Development (after fixes)", "Held-out"]} minWidth="44rem">
                  {Object.keys(dq.extraction.fields.all).map((f) => (
                    <tr key={f}>
                      <Td>{f.replace(/_/g, " ")}</Td>
                      <Td className="kbd"><Ci x={dq.extraction.fields.all[f]} /></Td>
                      <Td className="kbd"><Ci x={ho?.fields.all[f]} /></Td>
                    </tr>
                  ))}
                </Table>
              </div>

              {ho && (
                <div className="mt-8 grid gap-6 lg:grid-cols-2">
                  <SliceTable title="Held-out detection by country" slice={ho.detection.by_country} kind="detection" />
                  <SliceTable title="Held-out detection by source" slice={ho.detection.by_publisher} kind="detection" />
                  <SliceTable title="Held-out detection by language" slice={ho.detection.by_language} kind="detection" />
                  <SliceTable title="Held-out records fully correct, by deal type" slice={ho.fields.by_deal_type} kind="complete" />
                </div>
              )}
              <p className="mt-3 text-[0.75rem] text-[color:var(--dim)]">
                {ho?.note_on_recall} Small groups have wide intervals; groups under about 20 items are indicative only.
              </p>

              <h3 className="eyebrow mt-8">Deduplication and identity</h3>
              <div className="mt-3">
                <Table head={["Measure", "Result", "Sample"]} minWidth="48rem">
                  <tr>
                    <Td>Merged reports that really are one deal</Td>
                    <Td className="kbd"><Ci x={dq.dedup.merge_precision} /></Td>
                    <Td className="text-[0.75rem] text-[color:var(--muted)]">Pairs of reports merged into one record</Td>
                  </tr>
                  <tr>
                    <Td>Separate records that are actually one deal (missed duplicates)</Td>
                    <Td className="kbd text-risk"><Ci x={dq.dedup.missed_duplicates_among_lookalikes} /></Td>
                    <Td className="text-[0.75rem] text-[color:var(--muted)]">Look-alike pairs: same distinctive name or amount within two months</Td>
                  </tr>
                  <tr>
                    <Td>Name pairs the resolver joins that are one entity (development)</Td>
                    <Td className="kbd"><Ci x={dq.identity.join_precision} /></Td>
                    <Td className="text-[0.75rem] text-[color:var(--muted)]">{dq.identity.sample}</Td>
                  </tr>
                  <tr>
                    <Td>Valid names resolved to the right organisation (held-out)</Td>
                    <Td className="kbd"><Ci x={dq.heldout_names?.valid_names_resolved_to_the_right_organisation} /></Td>
                    <Td className="text-[0.75rem] text-[color:var(--muted)]">Random stored party names</Td>
                  </tr>
                  <tr>
                    <Td>Malformed names caught: fragments, combinations (held-out)</Td>
                    <Td className="kbd"><Ci x={dq.heldout_names?.malformed_names_caught} /></Td>
                    <Td className="text-[0.75rem] text-[color:var(--muted)]">Same sample; malformed names are not credited to anyone</Td>
                  </tr>
                </Table>
              </div>
              <p className="mt-3 text-[0.8125rem] text-[color:var(--muted)]">
                Every deal page shows these checks for that record: which fields are corroborated by independent stories, which are
                single-source, derived or uncertain, with the measured accuracy of each field next to it.
              </p>
            </Section>
          )}

          {e.attribution?.natural && (
            <Section
              id="attribution"
              title="Attribution: is the event about this company?"
              lede={
                <>
                  Real headlines only, each with its publisher, date and link, labelled with the events it reports about a target
                  company. {e.attribution.sets.natural} {e.attribution.labels}
                </>
              }
            >
              <h3 className="eyebrow">Random sample: the rates to quote</h3>
              <div className="mt-3">
                <Table head={["Companies", "Headlines", "With an event", "Exactly right", "Precision", "Recall", "False alarms on no-event headlines"]} minWidth="66rem">
                  {[["All", e.attribution.natural.overall] as const, ...Object.entries(e.attribution.natural.by_market ?? {})].map(([k, v]) => (
                    <tr key={k}>
                      <Td className={k === "All" ? "font-medium" : ""}>{k === "us" ? "US companies" : k === "africa" ? "African companies" : k}</Td>
                      <Td className="kbd">{v.items}</Td>
                      <Td className="kbd">{v.items_with_an_event}</Td>
                      <Td className="kbd"><Ci x={v.exactly_right} /></Td>
                      <Td className="kbd"><Ci x={v.precision} /></Td>
                      <Td className="kbd"><Ci x={v.recall} /></Td>
                      <Td className="kbd"><Ci x={v.false_alarm_rate_on_no_event_items} /></Td>
                    </tr>
                  ))}
                </Table>
              </div>

              {e.attribution.hard && (
                <>
                  <h3 className="eyebrow mt-8">Hard cases, by failure mode</h3>
                  <p className="mt-2 max-w-3xl text-[0.8125rem] text-[color:var(--muted)]">{e.attribution.sets.hard}</p>
                  <div className="mt-3">
                    <Table head={["Failure mode", "Headlines", "With an event", "Exactly right", "Precision", "Recall", "False alarms on no-event headlines"]} minWidth="66rem">
                      {Object.entries(e.attribution.hard.by_category ?? {}).map(([k, v]) => (
                        <tr key={k}>
                          <Td>{words(k)}</Td>
                          <Td className="kbd">{v.items}</Td>
                          <Td className="kbd">{v.items_with_an_event}</Td>
                          <Td className="kbd"><Ci x={v.exactly_right} /></Td>
                          <Td className="kbd"><Ci x={v.precision} /></Td>
                          <Td className="kbd"><Ci x={v.recall} /></Td>
                          <Td className="kbd"><Ci x={v.false_alarm_rate_on_no_event_items} /></Td>
                        </tr>
                      ))}
                    </Table>
                  </div>
                </>
              )}

              {e.attribution_before?.natural && (
                <>
                  <h3 className="eyebrow mt-8">Before and after the 14 October rule changes, same headlines</h3>
                  <div className="mt-3">
                    <Table head={["Set", "Measure", "Before", "After"]} minWidth="40rem">
                      {(["natural", "hard"] as const).flatMap((set) =>
                        (["precision", "recall", "false_alarm_rate_on_no_event_items"] as const).map((m) => (
                          <tr key={set + m}>
                            <Td>{set === "natural" ? "Random sample" : "Hard cases"}</Td>
                            <Td>{m === "false_alarm_rate_on_no_event_items" ? "False alarms" : words(m)}</Td>
                            <Td className="kbd"><Ci x={e.attribution_before?.[set]?.overall[m]} /></Td>
                            <Td className="kbd"><Ci x={e.attribution?.[set]?.overall[m]} /></Td>
                          </tr>
                        )),
                      )}
                    </Table>
                  </div>
                </>
              )}
              <div className="mt-4">
                <Callout>
                  These headlines were labelled after the rule changes and were not used to make them, so both columns are honest
                  measures. Corroboration counts independent stories only: syndicated copies of one wire story, and near-identical
                  headlines, count once. Every error is listed in the downloadable error file with its source link.
                </Callout>
              </div>
            </Section>
          )}

          {e.review_2026 && <Review2026Section review={e.review_2026} />}

          <Section
            id="reproduce"
            title="Reproduce it"
            lede={
              <>
                {r?.design.reproduce} Every labelled item carries its reasoning; disagreements are welcome through the{" "}
                <a href="/contact" className="text-verified hover:underline">contact page</a>.
              </>
            }
          >
            <ul className="grid gap-2 text-[0.8125rem] sm:grid-cols-2">
              {[
                ["backtest_predictions.csv", "Every backtest prediction with its outcome labels"],
                ["deal_extraction_items.jsonl", "Development headlines"],
                ["deal_extraction_labels.jsonl", "Development labels"],
                ["deal_heldout_items.jsonl", "Held-out headlines"],
                ["deal_heldout_labels.jsonl", "Held-out labels"],
                ["deal_errors.jsonl", "Every extraction, dedup and identity error"],
                ["dedup_items.jsonl", "Deduplication pairs"],
                ["dedup_labels.jsonl", "Deduplication labels"],
                ["identity_items.jsonl", "Name pairs"],
                ["identity_labels.jsonl", "Name pair labels"],
                ["names_heldout_items.jsonl", "Held-out names"],
                ["names_heldout_labels.jsonl", "Held-out name labels"],
                ["attribution_natural_items.jsonl", "Attribution: random real headlines"],
                ["attribution_natural_labels.jsonl", "Attribution: random sample labels"],
                ["attribution_hard_items.jsonl", "Attribution: hard-case real headlines"],
                ["attribution_hard_labels.jsonl", "Attribution: hard-case labels"],
                ["attribution_errors.jsonl", "Attribution: every error, with source links"],
                ["review_2026_items.jsonl", "2026 review: headlines to label"],
                ["review_2026_pairs.jsonl", "2026 review: report pairs to label"],
                ["review_2026_labels_template.jsonl", "2026 review: blank headline labels"],
                ["review_2026_pair_labels_template.jsonl", "2026 review: blank pair labels"],
                ["review_2026_guidelines.md", "2026 review: labelling guide"],
              ].map(([f, label]) => (
                <li key={f}>
                  <a href={apiUrl(`/api/evaluation/files/${f}`)} className="text-verified hover:underline">
                    {label}
                  </a>{" "}
                  <span className="kbd text-[0.6875rem] text-[color:var(--dim)]">{f}</span>
                </li>
              ))}
            </ul>
            {e.live_outcomes && (
              <p className="mt-4 text-[0.8125rem] text-[color:var(--muted)]">
                Live outcomes so far:{" "}
                {Object.values(e.live_outcomes).reduce((a, x) => a + x.confirmed + x.refuted, 0)} labelled across{" "}
                {Object.keys(e.live_outcomes).length} signal-type and market groups.
              </p>
            )}
          </Section>
        </>
      )}
    </Container>
  );
}
