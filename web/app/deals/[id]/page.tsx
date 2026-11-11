import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PublicPage } from "../../../components/PublicPage";
import { Container } from "../../../components/primitives";
import { Stat, usd, words } from "../../../components/app/ui";
import { apiHeaders, apiUrl } from "../../../lib/api-base";
import type { Deal, Verification } from "../../../lib/market";

/**
 * Public, read-only view of one deal: the facts and their sources, readable without an account, so links shared
 * on LinkedIn or X open to the deal instead of a sign-in form, and search engines can index it. Comparables,
 * investor histories and alerts stay in the app behind sign-in.
 */
export const revalidate = 3600;

type DealResponse = { deal: Deal; parties: { name: string; role: string }[]; verification?: Verification };

async function load(id: string): Promise<DealResponse | null> {
  try {
    const r = await fetch(apiUrl(`/api/deals/${encodeURIComponent(id)}`), { headers: apiHeaders(), next: { revalidate: 3600 } });
    return r.ok ? ((await r.json()) as DealResponse) : null;
  } catch {
    return null;
  }
}

function country(code: string | null): string | null {
  if (!code) return null;
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

/** One plain sentence, from the stored fields only. */
function sentence(d: Deal): string {
  const amount = d.amount_usd ? usd(d.amount_usd) : null;
  const who = d.investors.slice(0, 3).join(", ");
  switch (d.deal_type) {
    case "equity_funding":
      return `${d.target} raised ${amount ?? "new funding"}${d.round ? ` (${words(d.round)})` : ""}${who ? ` from ${who}` : ""}.`;
    case "debt_financing":
      return `${d.target} secured ${amount ? `${amount} in ` : ""}debt financing${who ? ` from ${who}` : ""}.`;
    case "acquisition":
      return `${d.buyer ?? "A buyer"} acquired ${d.stake_pct && d.stake_pct < 100 ? `a ${d.stake_pct}% stake in ` : ""}${d.target}${amount ? ` for ${amount}` : ""}.`;
    case "exit":
      return `${d.seller ?? "A seller"} sold its stake in ${d.target}${d.buyer ? ` to ${d.buyer}` : ""}${amount ? ` for ${amount}` : ""}.`;
    default:
      return d.headline;
  }
}

export async function generateMetadata({ params }: { params: { id: string } }): Promise<Metadata> {
  const data = await load(params.id);
  if (!data) return { title: "Deal not found | Deal Intelligence", robots: { index: false } };
  const d = data.deal;
  const where = country(d.country);
  const title = `${d.target ?? d.headline}${d.amount_usd ? `: ${usd(d.amount_usd)}` : ""} ${words(d.deal_type).toLowerCase()} | Deal Intelligence`;
  const description = `${sentence(d)}${where ? ` ${where}.` : ""} Reported ${d.announced ?? ""}, with ${d.sources.length} source${d.sources.length === 1 ? "" : "s"}.`;
  return {
    title,
    description,
    alternates: { canonical: `/deals/${d.id}` },
    openGraph: { title, description, type: "article", url: `/deals/${d.id}` },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function PublicDealPage({ params }: { params: { id: string } }) {
  const data = await load(params.id);
  if (!data) notFound();
  const { deal: d, parties, verification: v } = data;
  const where = country(d.country);
  const tier = v?.tier ?? d.verification ?? ((d.independent_stories ?? 0) >= 2 ? "corroborated" : "single source");
  const stories = v?.independent_stories ?? d.independent_stories;
  const next = encodeURIComponent(`/app/deals/${d.id}`);
  const sources = [...d.sources].sort((a, b) => (a.date ?? "").localeCompare(b.date ?? ""));
  return (
    <PublicPage>
      <Container className="max-w-4xl pb-20 pt-28 sm:pt-32">
        <p className="eyebrow">
          {words(d.deal_type)}
          {where ? ` · ${where}` : ""}
          {d.sector ? ` · ${words(d.sector)}` : ""}
        </p>
        <h1 className="h2 mt-3">{d.target ?? d.headline}</h1>
        <p className="lede mt-4 max-w-2xl">{sentence(d)}</p>

        <div className="mt-8 grid gap-3 sm:grid-cols-4">
          <Stat label="Amount" value={usd(d.amount_usd)} note={d.amount && d.currency && d.currency !== "USD" ? `${d.amount.toLocaleString()} ${d.currency}` : undefined} />
          <Stat label="Round or stake" value={d.round ? words(d.round) : d.stake_pct ? `${d.stake_pct}%` : "n/a"} />
          <Stat label="First reported" value={d.announced ?? "n/a"} />
          <Stat
            label="Verification"
            value={tier === "official" ? "Official" : tier === "corroborated" ? "Corroborated" : "Single source"}
            note={tier === "official" ? "From an official filing or announcement"
              : tier === "corroborated" ? `${stories ?? "Several"} independent reports`
              : "One report so far; treat figures with care"}
          />
        </div>

        {parties.length > 0 && (
          <>
            <h2 className="eyebrow mt-10">Parties</h2>
            <ul className="mt-3 flex flex-wrap gap-2">
              {parties.map((p) => (
                <li key={p.name + p.role} className="inline-flex rounded-full border hairline px-3 py-1.5 text-[0.8125rem]">
                  {p.name} <span className="ml-2 text-[color:var(--dim)]">{p.role}</span>
                </li>
              ))}
            </ul>
          </>
        )}

        <h2 className="eyebrow mt-10">Sources ({sources.length})</h2>
        <ul className="mt-3 space-y-2 text-[0.875rem]">
          {sources.map((s, i) => (
            <li key={i}>
              <a href={s.url} target="_blank" rel="noopener noreferrer nofollow" className="hover:underline">
                {s.title || s.publisher || "Source"}
              </a>
              <span className="text-[color:var(--dim)]">
                {" "}
                · {s.publisher || "Publisher n/a"}
                {s.date ? ` · ${s.date}` : ""}
              </span>
            </li>
          ))}
        </ul>

        <div className="panel mt-12 p-6">
          <p className="font-display text-lg font-semibold tracking-tight">See the full picture</p>
          <p className="mt-2 max-w-2xl text-[0.9375rem] text-[color:var(--muted)]">
            Comparable deals and valuations, every investor&apos;s track record, the company&apos;s history and alerts when
            something changes, across all 54 African countries. Free to start.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Link href={`/account?mode=sign-up&next=${next}`} className="btn btn-primary">
              Create a free account
            </Link>
            <Link href={`/account?next=${next}`} className="btn btn-ghost">
              Sign in
            </Link>
          </div>
        </div>
        <p className="mt-6 text-[0.75rem] text-[color:var(--dim)]">
          Built from public reports. Figures are as reported and may be revised; report a correction to info@deal-intelligence.app.
        </p>
      </Container>
    </PublicPage>
  );
}
