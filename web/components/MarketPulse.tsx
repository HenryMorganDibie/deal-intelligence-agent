import { DEAL_TYPE, SIGNAL_TYPE, count, label, shortDate, usd, type Pulse } from "../lib/pulse";
import { ArrowRight, Container, Heading, Reveal, Section } from "./primitives";

/** The current month of African deal flow and this week's corporate events, re-rendered from the live feed. */
export function MarketPulse({ pulse, compact = false }: { pulse: Pulse | null; compact?: boolean }) {
  if (!pulse || !pulse.deals.total) return null;
  const { deals, events } = pulse;
  if (compact) {
    const stats = [
      { value: count(deals.total), label: "reported deals indexed" },
      { value: count(deals.recent), label: `deals in the last ${deals.window_days} days` },
      { value: String(deals.recent_countries), label: "countries with recent deal activity" },
    ];
    return (
      <Section id="pulse" labelledBy="pulse-title" className="py-14 sm:py-16">
        <Container>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="max-w-2xl">
              <p className="eyebrow">Market pulse · Daily feed</p>
              <h2 id="pulse-title" className="h2 mt-3">Recent deal activity, from reported records.</h2>
              <p className="mt-3 text-sm leading-relaxed text-[color:var(--muted)]">
                Counts reflect records currently stored, not every transaction that occurred. The latest record is dated {shortDate(pulse.latest_record) || "not available"}.
              </p>
            </div>
            <a href="/app/deals" className="btn btn-ghost">Browse all deals <ArrowRight /></a>
          </div>
          <dl className="mt-7 grid grid-cols-1 gap-px overflow-hidden rounded-[14px] border hairline bg-[color:var(--line)] sm:grid-cols-3">
            {stats.map((s) => (
              <div key={s.label} className="bg-[color:var(--bg)] p-5">
                <dt className="sr-only">{s.label}</dt>
                <dd>
                  <span className="block font-display text-2xl font-semibold tracking-tight">{s.value}</span>
                  <span className="mt-1 block text-[0.8125rem] leading-snug text-[color:var(--muted)]">{s.label}</span>
                </dd>
              </div>
            ))}
          </dl>
          <div className="panel mt-3 overflow-hidden">
            <div className="flex items-center justify-between border-b hairline px-5 py-3">
              <h3 className="h3">Latest reported deals</h3>
              <a href="/app/deals" className="eyebrow inline-flex items-center gap-2 hover:text-verified">Full feed <ArrowRight /></a>
            </div>
            <ul>
              {deals.latest.slice(0, 4).map((d, i) => (
                <li key={d.id} className={i ? "border-t hairline" : ""}>
                  <a href={`/app/deals/${d.id}`} className="grid gap-2 px-5 py-4 transition-colors hover:bg-white/[0.02] sm:grid-cols-[1fr_auto] sm:items-center sm:gap-6">
                    <div className="min-w-0">
                      <p className="text-[0.9375rem] font-medium">{d.headline}</p>
                      <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">
                        {label(DEAL_TYPE, d.deal_type)}{d.country ? ` · ${d.country.name}` : ""}{d.publisher ? ` · ${d.publisher}` : ""}{d.announced ? ` · ${shortDate(d.announced)}` : ""}
                      </p>
                    </div>
                    <span className="kbd text-[0.8125rem] text-verified">{usd(d.amount_usd)}</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </Container>
      </Section>
    );
  }
  const types = Object.entries(deals.by_type);
  const maxType = Math.max(1, ...types.map(([, n]) => n));
  const stats = [
    { k: count(deals.recent), v: `deals in the last ${deals.window_days} days` },
    { k: usd(deals.recent_disclosed_usd), v: `disclosed, across ${deals.recent_disclosed_n} deals with a stated size` },
    { k: String(deals.recent_countries), v: "countries with a deal this month" },
    { k: count(events.recent), v: `corporate events in the last ${events.window_days} days` },
  ];
  return (
    <Section id="pulse" labelledBy="pulse-title">
      <Container>
        <Heading
          index="Live"
          eyebrow="Market pulse"
          id="pulse-title"
          title={
            <>
              This month in African private markets.{" "}
              <span className="text-[color:var(--muted)]">Recomputed from the daily feed.</span>
            </>
          }
          lede={`Counts and sums over stored records only: nothing on this panel is estimated. Latest record ${shortDate(
            pulse.latest_record,
          )}; the page refreshes every 30 minutes and the feed is read every morning.`}
        />

        <Reveal>
          <dl className="mt-14 grid grid-cols-2 gap-px overflow-hidden rounded-[14px] border hairline bg-[color:var(--line)] lg:grid-cols-4">
            {stats.map((s) => (
              <div key={s.v} className="bg-[color:var(--bg)] p-6">
                <dt className="sr-only">{s.v}</dt>
                <dd>
                  <span className="block font-display text-2xl font-semibold tracking-tight">{s.k}</span>
                  <span className="mt-1 block text-[0.8125rem] leading-snug text-[color:var(--muted)]">{s.v}</span>
                </dd>
              </div>
            ))}
          </dl>
        </Reveal>

        <div className="mt-4 grid gap-4 lg:grid-cols-[1.35fr_1fr]">
          <Reveal>
            <div className="panel h-full overflow-hidden">
              <div className="flex items-center justify-between border-b hairline px-6 py-4">
                <h3 className="h3">Latest deals</h3>
                <a href="/app/deals" className="eyebrow inline-flex items-center gap-2 hover:text-verified">
                  All {count(deals.total)} <ArrowRight />
                </a>
              </div>
              <ul>
                {deals.latest.map((d, i) => (
                  <li key={d.id} className={i ? "border-t hairline" : ""}>
                    <a href={`/app/deals/${d.id}`} className="grid gap-1 px-6 py-4 transition-colors hover:bg-white/[0.02] sm:grid-cols-[1fr_auto] sm:gap-6">
                      <div className="min-w-0">
                        <p className="truncate text-[0.9375rem] font-medium">{d.headline}</p>
                        <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">
                          {label(DEAL_TYPE, d.deal_type)}
                          {d.country ? ` · ${d.country.name}` : ""}
                          {d.publisher ? ` · ${d.publisher}` : ""} · {shortDate(d.announced)}
                        </p>
                      </div>
                      <span className="kbd self-start text-[0.8125rem] text-verified">{usd(d.amount_usd)}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>

          <div className="grid gap-4">
            <Reveal delay={80}>
              <div className="panel p-6">
                <h3 className="h3">Deal mix, last {deals.window_days} days</h3>
                <ul className="mt-5 space-y-3">
                  {types.map(([t, n]) => (
                    <li key={t}>
                      <div className="mb-1.5 flex items-baseline justify-between text-[0.8125rem]">
                        <span>{label(DEAL_TYPE, t)}</span>
                        <span className="kbd text-[color:var(--muted)]">{n}</span>
                      </div>
                      <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
                        <div className="h-full rounded-full bg-verified/80" style={{ width: `${(n / maxType) * 100}%` }} />
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </Reveal>
            <Reveal delay={140}>
              <div className="panel p-6">
                <h3 className="h3">Most active</h3>
                <div className="mt-4 grid gap-6 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
                  <div>
                    <p className="eyebrow">Countries</p>
                    <ul className="mt-3 space-y-2 text-[0.875rem]">
                      {deals.top_countries.map((c) => (
                        <li key={c.code} className="flex justify-between gap-3">
                          <a href={`/app/countries/${c.code}`} className="hover:text-verified">{c.name}</a>
                          <span className="kbd text-[color:var(--muted)]">{c.deals}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="eyebrow">Investors</p>
                    <ul className="mt-3 space-y-2 text-[0.875rem]">
                      {deals.active_investors.map((v) => (
                        <li key={v.name} className="flex justify-between gap-3">
                          <a href={`/app/investors/${encodeURIComponent(v.name)}`} className="truncate hover:text-verified">
                            {v.name}
                          </a>
                          <span className="kbd text-[color:var(--muted)]">{v.deals}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </div>

        {events.latest.length > 0 && (
          <Reveal>
            <div className="panel mt-4 overflow-hidden">
              <div className="flex items-center justify-between border-b hairline px-6 py-4">
                <h3 className="h3">Corporate events this week</h3>
                <a href="/app/watchlists" className="eyebrow inline-flex items-center gap-2 hover:text-verified">
                  Watch a market <ArrowRight />
                </a>
              </div>
              <ul className="grid lg:grid-cols-2">
                {events.latest.map((e, i) => (
                  <li key={e.id ?? i} className={`border-t hairline px-6 py-4 ${i < 2 ? "lg:border-t-0" : ""} ${i === 0 ? "border-t-0" : ""}`}>
                    <p className="text-[0.75rem] uppercase tracking-[0.12em] text-[color:var(--dim)]">
                      {label(SIGNAL_TYPE, e.signal_type)}
                      {e.country ? ` · ${e.country.name}` : ""} · {shortDate(e.day)}
                    </p>
                    {e.url ? (
                      <a href={e.url} rel="noopener noreferrer" target="_blank" className="mt-1 block text-[0.9375rem] hover:text-verified">
                        {e.headline}
                      </a>
                    ) : (
                      <p className="mt-1 text-[0.9375rem]">{e.headline}</p>
                    )}
                    {e.publisher && <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">{e.publisher}</p>}
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        )}
      </Container>
    </Section>
  );
}
