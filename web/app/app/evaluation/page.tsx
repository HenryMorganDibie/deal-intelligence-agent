"use client";

import { useEffect, useState } from "react";
import { Container } from "../../../components/primitives";
import { ErrorNote, Loading, PageHeader, Table, Td, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { get } from "../../../lib/market";

type Metric = {
  predictions: number; labelled: number; precision: number | null; precision_official_filings: number | null; official_labelled: number;
  events: number; recall: number | null; base_rate: number | null; lift: number | null; hit_rate: number | null; directional_n: number;
  mean_abnormal_return_10d_pct: number | null; price_only?: boolean;
};
type Evaluation = {
  historical_backtest: {
    start: string; end: string; companies: number; as_of_dates: number; lookback_days: number; horizon_days: number;
    metrics: Record<string, Record<"all" | "us" | "africa", Metric>>;
    by_severity?: Record<string, Record<"medium_plus" | "low", { labelled: number; precision: number | null }>>;
    alpha_validation?: {
      labelled: number;
      bands?: Record<"low" | "middle" | "high", { n: number; alpha_range: [number, number]; precision: number | null; mean_abs_move_10d_pct: number | null; moves_n: number }>;
      spearman_alpha_vs_confirmed?: number | null;
      verdict?: string;
      by_type?: Record<string, { labelled: number; precision: Record<"low" | "middle" | "high", number | null>; spearman: number | null }>;
    };
  } | null;
  live_outcomes: unknown;
  method: string;
};

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "n/a" : `${Math.round(v * 100)}%`);

export default function EvaluationPage() {
  const [e, setE] = useState<Evaluation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [market, setMarket] = useState<"all" | "us" | "africa">("all");
  useEffect(() => {
    get<Evaluation>("/api/evaluation").then(setE).catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the evaluation."));
  }, []);
  const b = e?.historical_backtest;
  return (
    <Container className="py-10 lg:py-14">
      <PageHeader eyebrow="Historical outcomes and signal evaluation" title="How often the signals were right.">
        A walk-forward replay: on each monthly date the engine sees only what was published in the previous 30 days, and
        each prediction is judged on the 90 days that followed against SEC filings, exchange disclosures, credible news and
        abnormal price moves. Lift compares precision with the base rate, the chance a random company-month had that event
        anyway. Weak results are shown as they are.
      </PageHeader>
      {error && <ErrorNote message={error} />}
      {!e ? (
        <Loading />
      ) : !b ? (
        <p className="text-sm text-[color:var(--muted)]">No backtest summary is published yet.</p>
      ) : (
        <>
          <p className="text-[0.875rem] text-[color:var(--muted)]">
            {b.start} to {b.end}: {b.companies} companies (US, JSE, NGX, NSE Kenya) x {b.as_of_dates} monthly dates.
          </p>
          <div className="mt-4 flex gap-2">
            {(["all", "us", "africa"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMarket(m)}
                className={`rounded-full border hairline px-3 py-1.5 text-[0.8125rem] ${market === m ? "text-[color:var(--text)]" : "text-[color:var(--muted)]"}`}
              >
                {m === "all" ? "All markets" : m === "us" ? "United States" : "Africa"}
              </button>
            ))}
          </div>
          <div className="mt-6">
            <Table head={["Signal type", "Predictions", "Precision", "Official filings only", "Base rate", "Lift", "Recall", "Price hit rate", "Abnormal return 10d"]} minWidth="60rem">
              {Object.entries(b.metrics).map(([st, by]) => {
                const a = by[market];
                return (
                  <tr key={st}>
                    <Td>{words(st)}</Td>
                    <Td className="kbd">{a.predictions}</Td>
                    <Td className="kbd">{a.price_only ? "Price only" : `${pct(a.precision)} (${a.labelled})`}</Td>
                    <Td className="kbd">{a.price_only ? "" : `${pct(a.precision_official_filings)} (${a.official_labelled})`}</Td>
                    <Td className="kbd">{pct(a.base_rate)}</Td>
                    <Td className={`kbd ${a.lift && a.lift > 1 ? "text-verified" : a.lift !== null ? "text-risk" : ""}`}>{a.lift !== null ? `${a.lift}x` : "n/a"}</Td>
                    <Td className="kbd">{pct(a.recall)} ({a.events})</Td>
                    <Td className="kbd">{pct(a.hit_rate)} ({a.directional_n})</Td>
                    <Td className="kbd">{a.mean_abnormal_return_10d_pct !== null ? `${a.mean_abnormal_return_10d_pct}%` : "n/a"}</Td>
                  </tr>
                );
              })}
            </Table>
          </div>
          <p className="mt-3 text-[0.75rem] text-[color:var(--dim)]">Counts in brackets are the sample behind each figure. {e.method}</p>

          {b.alpha_validation?.bands && (
            <>
              <h2 className="eyebrow mt-12">Does the alpha score rank signals?</h2>
              <p className="mt-2 max-w-3xl text-[0.8125rem] leading-relaxed text-[color:var(--muted)]">
                The alpha weights are design choices, so they are tested: confirmable predictions are split into thirds by
                their alpha as of the replay date. If the score is useful, the confirmation rate should rise from the low third
                to the high third. Verdict: {b.alpha_validation.verdict} (rank correlation{" "}
                {b.alpha_validation.spearman_alpha_vs_confirmed}).
              </p>
              <div className="mt-4">
                <Table head={["Alpha third", "Alpha range", "Predictions", "Confirmed", "Mean absolute 10-day move"]} minWidth="36rem">
                  {(["low", "middle", "high"] as const).map((k) => {
                    const band = b.alpha_validation!.bands![k];
                    return (
                      <tr key={k}>
                        <Td>{words(k)}</Td>
                        <Td className="kbd">{band.alpha_range[0]} to {band.alpha_range[1]}</Td>
                        <Td className="kbd">{band.n}</Td>
                        <Td className="kbd">{pct(band.precision)}</Td>
                        <Td className="kbd">{band.mean_abs_move_10d_pct != null ? `${band.mean_abs_move_10d_pct}% (${band.moves_n})` : "n/a"}</Td>
                      </tr>
                    );
                  })}
                </Table>
              </div>
              {b.alpha_validation.by_type && Object.keys(b.alpha_validation.by_type).length > 0 && (
                <div className="mt-6">
                  <p className="text-[0.8125rem] text-[color:var(--muted)]">Within signal types with 30 or more labelled predictions, so the result is not only signal-type mix:</p>
                  <div className="mt-3">
                    <Table head={["Signal type", "Labelled", "Low third", "Middle third", "High third", "Rank correlation"]} minWidth="40rem">
                      {Object.entries(b.alpha_validation.by_type).map(([st, r]) => (
                        <tr key={st}>
                          <Td>{words(st)}</Td>
                          <Td className="kbd">{r.labelled}</Td>
                          <Td className="kbd">{pct(r.precision.low)}</Td>
                          <Td className="kbd">{pct(r.precision.middle)}</Td>
                          <Td className="kbd">{pct(r.precision.high)}</Td>
                          <Td className="kbd">{r.spearman ?? "n/a"}</Td>
                        </tr>
                      ))}
                    </Table>
                  </div>
                </div>
              )}
            </>
          )}

          {b.by_severity && (
            <>
              <h2 className="eyebrow mt-12">By severity</h2>
              <p className="mt-2 text-[0.8125rem] text-[color:var(--muted)]">Low-severity flags are the noisy tail; medium and above is the operating point for action.</p>
              <div className="mt-4">
                <Table head={["Signal type", "Precision, medium and above", "Precision, low"]} minWidth="32rem">
                  {Object.entries(b.by_severity).map(([st, r]) => (
                    <tr key={st}>
                      <Td>{words(st)}</Td>
                      <Td className="kbd">{pct(r.medium_plus.precision)} ({r.medium_plus.labelled})</Td>
                      <Td className="kbd">{pct(r.low.precision)} ({r.low.labelled})</Td>
                    </tr>
                  ))}
                </Table>
              </div>
            </>
          )}
        </>
      )}
    </Container>
  );
}
