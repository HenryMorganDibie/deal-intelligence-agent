import type { Metadata } from "next";
import type { ReactNode } from "react";
import { SiteFooter } from "../../components/Closing";
import { SiteNav } from "../../components/SiteNav";
import { Container } from "../../components/primitives";
import { ciText, count, getPulse, getQuality, shortDate, type Pulse } from "../../lib/pulse";

// Figures in "Current state" follow the live data (see lib/pulse.ts).
export const revalidate = 1800;

export const metadata: Metadata = {
  title: "Methodology | Deal Intelligence",
  description: "How every score, rate and figure in Deal Intelligence is computed, which numbers are measured, and which are design choices.",
};

function Part({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-24 border-t hairline py-10">
      <h2 id={`${id}-title`} className="h3 text-[1.375rem]">
        {title}
      </h2>
      <div className="mt-4 space-y-4 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">{children}</div>
    </section>
  );
}

function Label({ kind }: { kind: "measured" | "design" }) {
  return (
    <span
      className={`ml-2 rounded-full border px-2 py-0.5 align-middle text-[0.6875rem] ${
        kind === "measured" ? "border-[rgba(110,231,200,0.35)] text-verified" : "border-[color:var(--line)] text-[color:var(--dim)]"
      }`}
    >
      {kind === "measured" ? "Measured" : "Design choice"}
    </span>
  );
}

const Code = ({ children }: { children: ReactNode }) => (
  <code className="kbd block overflow-x-auto rounded-lg border hairline bg-white/[0.02] px-4 py-3 text-[0.8125rem] text-[color:var(--text)]">
    {children}
  </code>
);

const pct = (x: number | null | undefined) => (x == null ? "n/a" : `${Math.round(x * 100)}%`);

function CurrentState({ pulse }: { pulse: Pulse }) {
  const m = pulse.measured;
  const bands = m.alpha_validation?.bands;
  const rows: [string, string][] = [
    ["Observations behind confidence and moves", `${count(m.backtest_observations)} backtest + ${count(m.live_observations)} live`],
    [
      "Flags later confirmed, all types",
      m.overall_confirmation?.rate != null
        ? `${pct(m.overall_confirmation.rate)} (${m.overall_confirmation.confirmed} of ${m.overall_confirmation.labelled})`
        : "n/a",
    ],
  ];
  if (bands) rows.push(["Confirmed, by alpha third (low / middle / high)", `${pct(bands.low.precision)} / ${pct(bands.middle.precision)} / ${pct(bands.high.precision)}`]);
  rows.push(
    ["Deals stored", `${count(pulse.deals.total)} in ${pulse.deals.countries} countries`],
    [`Deals in the last ${pulse.deals.window_days} days`, `${count(pulse.deals.recent)} in ${pulse.deals.recent_countries} countries`],
  );
  return (
    <section aria-labelledby="state-title" className="panel mt-8 p-6">
      <h2 id="state-title" className="eyebrow">Current state · {shortDate(pulse.as_of)}</h2>
      <dl className="mt-4 grid gap-x-6 gap-y-3 text-[0.875rem] sm:grid-cols-[1fr_auto]">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-[color:var(--muted)]">{k}</dt>
            <dd className="kbd text-[color:var(--text)] sm:text-right">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-[0.75rem] text-[color:var(--dim)]">
        Recomputed from the live data every 30 minutes; live outcomes are added as hosted briefs are labelled each day.
      </p>
    </section>
  );
}

export default async function MethodologyPage() {
  const [pulse, quality] = await Promise.all([getPulse(), getQuality()]);
  return (
    <>
      <SiteNav />
      <main id="main" className="pb-16 pt-28">
        <Container className="max-w-3xl">
          <p className="eyebrow">Methodology</p>
          <h1 className="h2 mt-3 text-[2rem] sm:text-[2.5rem]">How every number is made.</h1>
          <p className="mt-4 text-[1rem] leading-relaxed text-[color:var(--muted)]">
            Each figure in the product is either <strong className="text-[color:var(--text)]">measured</strong> from
            outcomes or a stated <strong className="text-[color:var(--text)]">design choice</strong>. Nothing is presented
            as data that is not. Results, including weak ones, are on the{" "}
            <a href="/app/evaluation" className="text-verified hover:underline">evaluation page</a>.
          </p>
          {pulse && <CurrentState pulse={pulse} />}
          <nav aria-label="Sections" className="mt-8 flex flex-wrap gap-2 text-[0.8125rem]">
            {[
              ["detection", "Detection"], ["calibration", "Confidence"], ["alpha", "Alpha score"], ["moves", "Expected moves"],
              ["quality", "Evidence quality"], ["deals", "Deals"], ["financials", "Financial statements"], ["risk", "Risk scores"],
              ["research", "Research"], ["evaluation", "Evaluation"], ["coverage", "Coverage"], ["limits", "Limits"],
            ].map(([id, label]) => (
              <a key={id} href={`#${id}`} className="rounded-full border hairline px-3 py-1.5 text-[color:var(--muted)] hover:text-[color:var(--text)]">
                {label}
              </a>
            ))}
          </nav>

          <Part id="detection" title="Detection">
            <p>
              A deterministic rule engine reads SEC filings, exchange disclosures (NGX, NSE Kenya, JSE SENS) and the
              financial press in English, French, Portuguese and Arabic, and fires on patterns for eight signal types: M&amp;A,
              credit risk, distress, earnings surprise, leadership change, regulatory action, debt restructuring and insider
              activity. A source must name the company, and the triggering phrase must be in a clause about it. The language
              model never creates, removes, retypes or re-grades a signal; it only explains confirmed ones.
            </p>
          </Part>

          <Part id="calibration" title="Severity and confidence">
            <p>
              Severity <Label kind="design" />: the rule score, raised by independent corroborating sources, falls into a
              band for its signal type (for M&amp;A: 0.85 and above is CRITICAL, 0.70 HIGH, 0.50 MEDIUM). CRITICAL needs at
              least two independent sources.
            </p>
            <p>
              Confidence <Label kind="measured" />: the share of past flags of the same type and severity that were followed
              within 90 days by a confirming filing, exchange disclosure or credible report, from a walk-forward backtest.
              For earnings and insider signals, where the disclosure is the event, it is the share whose market-adjusted move
              went the expected way. Small samples are smoothed toward the type-level rate:
            </p>
            <Code>rate = (confirmed + 5 × parent_rate) / (labelled + 5)</Code>
            <p>
              The tables are not frozen at the backtest. Every hosted brief is labelled against what followed (price reaction
              after 12 days, confirmation after 95), and each hour the service pools those live outcomes with the backtest
              observations and recomputes every rate and move range. Once a signal type has 10 live outcomes in a market (US
              or Africa), the observed live rate for that market is used directly.
            </p>
          </Part>

          <Part id="alpha" title="Alpha score">
            <p>
              A 0 to 100 ranking of how actionable a signal is. The weights <Label kind="design" /> are stated, not fitted:
            </p>
            <Code>alpha = 100 × (0.35 severity + 0.25 source credibility + 0.20 corroboration + 0.10 recency + 0.10 liquidity)</Code>
            <p>
              Severity weights are 1.00, 0.78, 0.52 and 0.28 from CRITICAL to LOW. Source credibility ranges from 1.0 for SEC and
              exchange filings to lower values for less established outlets. Corroboration is 1 − 1/(1 + 0.8n) for n sources.
              Recency halves every 14 days with a floor of 0.30. Liquidity comes from live market capitalisation in US dollars.
            </p>
            <p>
              Whether the weights are useful is tested <Label kind="measured" />: the backtest splits predictions into thirds by
              alpha and reports each third&apos;s confirmation rate, with the rank correlation. The evaluation page shows the
              result. A rising confirmation rate shows the score orders flags by how often the event happened; it does not show
              that high-alpha flags earn returns, which the evaluation page measures separately and finds indistinguishable from
              zero at the current sample size. Alpha is not a recommendation to buy or sell.
            </p>
          </Part>

          <Part id="moves" title="Expected moves">
            <p>
              The move shown with a signal <Label kind="measured" /> is the distribution of market-adjusted returns over 10
              calendar days after the same kind of flag in the backtest (close on the first trading day on or after day 10,
              against the first close on or after the flag; about 7 trading days) (benchmarks: S&amp;P 500, Satrix 40, NGX ASI, NSE NASI). It
              is shown as the interquartile range with the median and the number of observations. With fewer than 10
              observations the product says &quot;insufficient history&quot; rather than show a range. The direction is the
              source&apos;s own when it states one (an earnings beat, an insider purchase), else the measured majority.
            </p>
          </Part>

          <Part id="quality" title="Evidence quality">
            <p>
              A rubric of seven graded components <Label kind="design" />: source reliability, corroboration, filing strength,
              historical precision, entity matches, recency and extraction, weighted 22, 20, 18, 15, 10, 10 and 5 percent. It
              describes how well a signal is supported, not the probability it materialises. Its historical precision
              component is measured.
            </p>
          </Part>

          <Part id="deals" title="Deals database">
            <p>
              Transactions are extracted by rules from headlines in African business and private-capital publications and from
              searches in every one of the 54 countries&apos; news editions and languages, every day. Each record has its type,
              parties, amount, stake, round, stage, sector and country, with every source linked. Amounts are as reported and
              converted to US dollars at the deal year&apos;s average official rate <Label kind="measured" />. Implied valuations
              are amount ÷ stake. Reports of one transaction merge by company and month.
            </p>
            <p>
              Each record shows its own verification <Label kind="measured" />. Every source keeps its headline, sources are
              grouped into independent stories (syndicated copies of one wire story and near-identical headlines count once),
              and each field is marked corroborated (stated by two or more independent stories), single source, derived
              (currency conversion, stake-implied valuation), classified (sector, by keyword rules), uncertain (sources disagree,
              a malformed party name, or a present-tense acquisition headline that does not confirm completion) or not disclosed.
              The first-reported date, the date a source first reported the deal as announced, and the date one first reported
              it completed are shown separately; none is a legal signing or closing date.
            </p>
            <p>
              Accuracy is measured on labelled samples of raw headlines, with a held-out set drawn after all fixes and never used
              for tuning{quality?.dealComplete ? `: ${ciText(quality.dealPrecision)} of extracted records are genuine transactions, ${ciText(quality.dealRecall)} of deal-like headlines are caught, and ${ciText(quality.dealComplete)} of records have every field right` : ""}.
              Field-by-field results, by country, source, language and deal type, are on the{" "}
              <a href="/app/evaluation#data-quality" className="text-verified hover:underline">evaluation page</a>.
            </p>
            <p>
              Comparables are scored <Label kind="design" />: 3 points for the same sector, 2 for the same type, 2 for the same
              country (1 for the same region), 2 for a size within 3× (1 within 10×); deals scoring 3 or more are shown with
              size and valuation quartiles.
            </p>
          </Part>

          <Part id="financials" title="Financial statements">
            <p>
              NGX and NSE Kenya statements are parsed from the audited annual statements the companies file with the exchanges.
              Each figure is checked against accounting identities (gross profit = revenue − cost of sales; profit after tax =
              profit before tax − tax; assets = liabilities + equity) and marked verified, inconsistent or unchecked. Other
              listings use Yahoo Finance; for SEC filers they are cross-checked against the SEC&apos;s XBRL data.
            </p>
          </Part>

          <Part id="risk" title="Country, currency and sector risk">
            <p>
              Country risk <Label kind="measured" /> uses World Bank Worldwide Governance and Development Indicators; each
              component maps to 0 to 100 with a fixed formula <Label kind="design" />, for example inflation ÷ 40% and (2.5 −
              political stability estimate) ÷ 5. The score is the weighted mean over the components with data, and the share
              available is shown. Currency risk combines last-year and five-year depreciation against the dollar and their
              volatility, reduced for pegged regimes. Sector risk is the smoothed share of adverse corporate events (credit,
              distress, restructuring, regulatory) against deal flow and other events over 90 days.
            </p>
          </Part>

          <Part id="research" title="Research answers">
            <p>
              The question is parsed for countries, sectors, deal and investor types, companies and dates. Evidence is
              retrieved and numbered, and the language model answers only from it, citing each claim. Citations are checked
              afterwards: references to items that do not exist are removed, and sentences without a citation are listed with
              the answer.
            </p>
          </Part>

          <Part id="evaluation" title="Evaluation">
            <p>
              A walk-forward replay: on each monthly date the engine sees only what was published in the previous 30 days, and
              each prediction is judged on the following 90 days. Lift is precision divided by the base rate, the chance that
              a random company-month had the event anyway. Hosted briefs are also labelled daily against later filings,
              credible news and abnormal price moves.
            </p>
            <p>
              Two outcomes are kept apart throughout. <strong className="text-[color:var(--text)]">Event confirmation</strong>{" "}
              asks whether the flagged event happened within 90 calendar days. <strong className="text-[color:var(--text)]">Market
              reaction</strong> asks whether the market-adjusted share price moved the predicted way over 10 calendar days. A
              confirmed event can come with no price move, and neither is a trading result: no costs, sizing or portfolio
              construction are applied.
            </p>
            <p>
              Time windows, reconciled: the backtest judges confirmation over 90 calendar days and price over 10 calendar days.
              Hosted briefs use the same windows but are labelled later, at 12 days for price (so the day-10 close exists even
              across a weekend or holiday) and at 95 days for confirmation (the 90-day window plus 5 days for filings and reports
              inside it to be indexed). Intervals are 95% Wilson intervals; the full labelling rules and every prediction are
              downloadable from the evaluation page.
            </p>
            <p>
              Attribution, whether a news item&apos;s event belongs to the target company, is tested on real headlines only, each
              with its publisher, date and link: a random sample naming tracked companies, and a hard-case sample of denials,
              references back to the company, subsidiaries, several companies, rumours, history and short names
              {quality?.attributionRecall ? `. On the random sample the engine found ${ciText(quality.attributionRecall)} of real events with precision ${ciText(quality.attributionPrecision)}` : ""}.
              Corroboration counts independent stories, not articles.
            </p>
          </Part>

          <Part id="coverage" title="Coverage">
            <p>
              Every country gets news search in its own languages, deal and event extraction, regulator detection and country
              risk. Machine-readable filings and prices exist for NGX and NSE Kenya (tier A); vendor data for JSE, EGX and
              Casablanca (tier B); the other countries are covered through news, deals and risk data (tier C). The{" "}
              <a href="/app/coverage" className="text-verified hover:underline">coverage page</a> states this for each country.
            </p>
          </Part>

          <Part id="limits" title="Known limits">
            <ul className="list-disc space-y-2 pl-5">
              <li>
                Measured rates rest on a backtest of 46 companies over 18 months
                {pulse ? `, plus ${count(pulse.measured.live_observations)} live outcomes so far` : ""}; several signal types
                have small samples, shown with every figure.
              </li>
              <li>Only leadership-change flags clearly beat their base rate in the backtest; M&amp;A and credit flags do not, and other types have samples too small to tell. The evaluation page shows each with its interval.</li>
              <li>
                Deals come from public reporting: undisclosed private deals cannot appear.
                {quality?.dealComplete ? ` On the held-out set ${ciText(quality.dealComplete)} of records have every field right, so individual fields marked single-source or uncertain should be checked against the linked sources.` : " Fields marked single-source or uncertain should be checked against the linked sources."}
              </li>
              <li>Statement layouts vary, so a figure is only marked verified when an accounting identity confirms it; interim statements are linked, not parsed.</li>
              <li>World Bank data are annual and often a year old; sovereign ratings and bond spreads are licensed and not included.</li>
              <li>Detection is pattern-based: auditable and reproducible, but phrasings the rules do not cover are missed, and on news headlines most are. Filings and exchange notices are covered by stronger, item-code rules.</li>
            </ul>
          </Part>
        </Container>
      </main>
      <SiteFooter />
    </>
  );
}
