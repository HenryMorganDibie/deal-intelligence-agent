import Link from "next/link";
import data from "../../data/investment_ideas.json";

type InvestmentIdea = {
  asset: string;
  risk: string;
  suitable_for: string;
  benefits: string[];
  disadvantages: string[];
  example: string;
};

type PipelineStage = {
  id: string;
  name: string;
  status: string;
  notes: string;
  labels_collected?: number;
  labels_target?: number;
  observations_collected?: number;
  new_observations_today?: number;
  relationships?: number;
  entities?: number;
  eligible_backtest_rows?: number;
  promoted?: boolean;
  holdout_metrics?: {
    learned_ranker?: { precision_at_20pct?: number; n?: number };
    alpha_baseline?: { precision_at_20pct?: number };
  };
};

type PageData = {
  updated_at?: string;
  stages?: PipelineStage[];
  ideas?: InvestmentIdea[];
};

const pageData = data as PageData;
const ideas = pageData.ideas ?? [];
const stages = pageData.stages ?? [];

export default function InvestingPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-20 text-[color:var(--text)]">
      <div className="mb-8">
        <p className="eyebrow">Investing, made clearer</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">Understand the choices before investing</h1>
        <p className="mt-4 max-w-3xl text-base leading-relaxed text-[color:var(--muted)]">
          Learn how stocks, money market funds, bonds and diversified funds differ. Compare their purpose,
          risks, costs and drawbacks before deciding what fits your goals and time horizon.
        </p>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-[color:var(--dim)]">
          This is educational information, not a personalized recommendation or a promise of returns. Products,
          regulation, fees, taxes and investor protections differ by country.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {ideas.map((idea) => (
          <article key={idea.asset} className="rounded-2xl border border-white/10 bg-[rgba(17,21,31,0.7)] p-5 shadow-lg shadow-black/10">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-xl font-semibold">{idea.asset}</h2>
              <span className="rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[0.7rem] font-medium uppercase tracking-[0.08em] text-emerald-200">
                {idea.risk}
              </span>
            </div>

            <p className="mb-4 text-sm text-[color:var(--muted)]">
              <span className="font-medium text-[color:var(--text)]">Best for:</span> {idea.suitable_for}
            </p>

            <div className="space-y-4 text-sm">
              <div>
                <h3 className="mb-2 font-medium text-[color:var(--text)]">Benefits</h3>
                <ul className="space-y-1.5 text-[color:var(--muted)]">
                  {idea.benefits.map((benefit) => (
                    <li key={benefit}>✓ {benefit}</li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="mb-2 font-medium text-[color:var(--text)]">Drawbacks</h3>
                <ul className="space-y-1.5 text-[color:var(--muted)]">
                  {idea.disadvantages.map((item) => (
                    <li key={item}>• {item}</li>
                  ))}
                </ul>
              </div>
            </div>

            <p className="mt-4 border-t border-white/10 pt-4 text-xs text-[color:var(--dim)]">
              Example: {idea.example}
            </p>
          </article>
        ))}
      </div>

      <section className="mt-12 rounded-2xl border border-white/10 bg-[rgba(14,17,24,0.8)] p-6">
        <h2 className="text-2xl font-semibold">A beginner&apos;s checklist</h2>
        <div className="mt-4 grid gap-5 md:grid-cols-3">
          <div>
            <p className="text-sm uppercase tracking-[0.08em] text-[color:var(--dim)]">1. Start with your goal</p>
            <p className="mt-2 text-[color:var(--muted)]">Separate emergency savings and near-term expenses from money you can leave invested for years.</p>
          </div>
          <div>
            <p className="text-sm uppercase tracking-[0.08em] text-[color:var(--dim)]">2. Check the product</p>
            <p className="mt-2 text-[color:var(--muted)]">Verify the provider and fund with your local regulator. Read fees, holdings, redemption rules and audited performance.</p>
          </div>
          <div>
            <p className="text-sm uppercase tracking-[0.08em] text-[color:var(--dim)]">3. Know the downside</p>
            <p className="mt-2 text-[color:var(--muted)]">Consider what happens if prices fall, rates change, the issuer defaults, or your currency weakens. Avoid investing borrowed or essential money.</p>
          </div>
        </div>
      </section>

      <section className="mt-12" aria-labelledby="pipeline-title">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow">Daily research pipeline</p>
            <h2 id="pipeline-title" className="mt-2 text-2xl font-semibold">How the intelligence improves</h2>
          </div>
          {pageData.updated_at && (
            <p className="text-xs text-[color:var(--dim)]">
              Data refreshed {new Date(pageData.updated_at).toLocaleString("en", { timeZone: "UTC" })} UTC
            </p>
          )}
        </div>
        {stages.length ? (
          <ol className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {stages.map((stage) => (
              <li key={stage.id} className="rounded-xl border border-white/10 bg-[rgba(17,21,31,0.55)] p-4">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-medium">{stage.name}</h3>
                  <span className="rounded-full border border-white/10 px-2 py-1 text-[0.65rem] uppercase tracking-wide text-[color:var(--muted)]">
                    {stage.status.replaceAll("_", " ")}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">{stage.notes}</p>
                {(stage.labels_collected != null || stage.observations_collected != null ||
                  stage.relationships != null || stage.eligible_backtest_rows != null) && (
                  <p className="mt-3 border-t border-white/10 pt-3 text-xs text-[color:var(--dim)]">
                    {stage.labels_collected != null &&
                      `${stage.labels_collected.toLocaleString()} reviewed labels${stage.labels_target != null ? ` / ${stage.labels_target.toLocaleString()} target` : ""}`}
                    {stage.observations_collected != null &&
                      `${stage.observations_collected.toLocaleString()} financial observations${stage.new_observations_today != null ? ` · ${stage.new_observations_today} new today` : ""}`}
                    {stage.relationships != null &&
                      `${stage.relationships.toLocaleString()} sourced relationships · ${(stage.entities ?? 0).toLocaleString()} entities`}
                    {stage.eligible_backtest_rows != null &&
                      `${stage.eligible_backtest_rows.toLocaleString()} eligible backtest examples`}
                  </p>
                )}
                {stage.holdout_metrics?.learned_ranker?.precision_at_20pct != null && (
                  <p className="mt-3 border-t border-white/10 pt-3 text-xs text-[color:var(--dim)]">
                    Held-out top-20% precision: {Math.round(stage.holdout_metrics.learned_ranker.precision_at_20pct * 100)}%
                    {stage.holdout_metrics.alpha_baseline?.precision_at_20pct != null &&
                      ` vs ${Math.round(stage.holdout_metrics.alpha_baseline.precision_at_20pct * 100)}% alpha baseline`}
                    {stage.holdout_metrics.learned_ranker.n != null &&
                      ` · ${stage.holdout_metrics.learned_ranker.n.toLocaleString()} examples`}
                  </p>
                )}
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-4 text-sm text-[color:var(--muted)]">
            Daily collection and model evaluation results will appear here after the scheduled workflow publishes its first run.
          </p>
        )}
      </section>

      <div className="mt-8 text-sm text-[color:var(--muted)]">
        <Link href="/" className="inline-flex items-center gap-2 text-emerald-300 hover:text-emerald-200">
          ← Back to the main site
        </Link>
      </div>
    </main>
  );
}
