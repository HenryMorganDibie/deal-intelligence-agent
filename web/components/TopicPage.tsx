import Link from "next/link";
import { PublicPage } from "./PublicPage";
import { Container } from "./primitives";
import type { Topic } from "../lib/post-topics";

/** The public page a post links to: the post's figures in full, dated, with a way into the wider data. */
export function TopicPage({ topic, day, stats }: { topic: Topic; day: string | null; stats?: [string, string][] }) {
  return (
    <PublicPage>
      <Container className="max-w-3xl pb-16 pt-28">
        <p className="eyebrow">{topic.pill}{day ? ` · ${day}` : ""}</p>
        <h1 className="h2 mt-3 text-[2rem] sm:text-[2.5rem]">{topic.title}</h1>
        <p className="mt-4 text-[1rem] leading-relaxed text-[color:var(--muted)]">{topic.intro}</p>
        {stats?.length ? (
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            {stats.map(([v, k]) => (
              <div key={k} className="panel p-4">
                <div className="font-display text-2xl">{v}</div>
                <div className="text-sm text-[color:var(--muted)]">{k}</div>
              </div>
            ))}
          </div>
        ) : null}
        {topic.rows.length ? (
          <ul className="mt-8 divide-y divide-white/[0.06] border-y hairline">
            {topic.rows.map((r) => (
              <li key={`${r.name}-${r.value}`} className="flex items-baseline justify-between gap-4 py-4">
                <span>
                  <span className="font-medium">{r.name}</span>
                  {r.note ? <span className="block text-sm text-[color:var(--muted)]">{r.note}</span> : null}
                </span>
                <span className={`shrink-0 font-display text-lg ${r.tone === "up" ? "text-verified" : r.tone === "down" ? "text-[#f59e8b]" : ""}`}>
                  {r.value}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-8 text-[color:var(--muted)]">No figures for this day yet.</p>
        )}
        <p className="mt-8 text-sm">
          <Link href={topic.more.href} className="text-verified hover:underline">{topic.more.label}</Link>
        </p>
      </Container>
    </PublicPage>
  );
}
