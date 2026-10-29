import { count, type Pulse, type ShowcaseBrief } from "../lib/pulse";
import { LINKS } from "../lib/site";
import { HeroBrief } from "./HeroBrief";
import { ArrowRight, Container, Reveal } from "./primitives";

function facts(pulse: Pulse | null) {
  return [
    { k: "54", v: "African countries, in their own languages" },
    pulse?.deals.total
      ? { k: count(pulse.deals.total), v: `deals: PE, VC, debt and M&A, ${pulse.deals.recent} in the last ${pulse.deals.window_days} days` }
      : { k: "1,700+", v: "deals: PE, VC, debt and M&A" },
    { k: "8", v: "signal types, 17 compound-event rules" },
    pulse?.measured.backtest_observations
      ? {
          k: count(pulse.measured.backtest_observations + pulse.measured.live_observations),
          v: "past signals behind every confidence figure",
        }
      : { k: "546", v: "automated tests behind every release" },
  ];
}

export function Hero({ pulse = null, brief = null }: { pulse?: Pulse | null; brief?: ShowcaseBrief | null }) {
  const FACTS = facts(pulse);
  return (
    <section id="top" aria-labelledby="hero-title" className="noise relative overflow-hidden pb-20 pt-32 sm:pb-28 sm:pt-40">
      <div aria-hidden className="grid-bg absolute inset-0" />
      <div
        aria-hidden
        className="absolute left-1/2 top-[-18rem] h-[36rem] w-[60rem] -translate-x-1/2 rounded-full opacity-60 blur-3xl"
        style={{ background: "radial-gradient(closest-side, rgba(110,231,200,0.14), rgba(185,163,255,0.06) 55%, transparent)" }}
      />

      <Container className="relative grid items-center gap-14 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16">
        <div className="min-w-0">
          <Reveal>
            <a
              href="#platform"
              className="inline-flex items-center gap-2 rounded-full border hairline bg-white/[0.03] py-1 pl-1 pr-3 text-[0.8125rem] text-[color:var(--muted)] transition-colors hover:text-[color:var(--text)]"
            >
              <span className="rounded-full bg-verified/15 px-2 py-0.5 kbd text-[0.6875rem] text-verified">New</span>
              Deals, investors, financials and risk for all 54 African countries
              <ArrowRight />
            </a>
          </Reveal>

          <Reveal delay={60}>
            <h1 id="hero-title" className="h1 mt-7 text-gradient">
              Deal signals you can audit.
            </h1>
          </Reveal>

          <Reveal delay={120}>
            <p className="lede mt-7 max-w-xl">
              Company signals, private-market deals, investors, financial statements and country risk across all 54
              African countries and the US. Screen listed shares, compare companies, analyse DCF/DDM valuations and
              portfolios, and explore supported ETFs, Treasury bills, bonds and listed property. Track watchlists and
              corporate events, and generate research briefs with source-linked evidence. Rules find the facts; an LLM
              explains them and is never allowed to invent one. Every number traces back to a source.
            </p>
          </Reveal>

          <Reveal delay={180}>
            <div className="mt-9 flex flex-wrap gap-3">
              <a href="/app" className="btn btn-primary">
                Run your first brief
                <ArrowRight />
              </a>
              <a href={LINKS.methodology} className="btn btn-ghost">
                Read the methodology
              </a>
            </div>
          </Reveal>

          <Reveal delay={240}>
            <dl className="mt-12 grid grid-cols-2 gap-x-6 gap-y-5 border-t hairline pt-6 sm:grid-cols-4">
              {FACTS.map((f) => (
                <div key={f.v}>
                  <dt className="sr-only">{f.v}</dt>
                  <dd>
                    <span className="block font-display text-xl font-semibold tracking-tight">{f.k}</span>
                    <span className="mt-1 block text-[0.8125rem] leading-snug text-[color:var(--muted)]">{f.v}</span>
                  </dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </div>

        <Reveal delay={200} className="relative min-w-0">
          <div
            aria-hidden
            className="absolute -inset-6 -z-10 rounded-[28px] opacity-70 blur-2xl"
            style={{ background: "radial-gradient(closest-side, rgba(110,231,200,0.10), transparent)" }}
          />
          <HeroBrief brief={brief} />
        </Reveal>
      </Container>
    </section>
  );
}
