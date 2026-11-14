import type { ReactNode } from "react";

type Officer = { name: string; title: string; year_born?: number };
type BoardMember = { name: string; role?: string; nationality?: string; page: number };
export type Governance = {
  rc_number?: string; registered_office?: string; company_secretary?: string; auditor?: string; registrar?: string;
  holding_company?: string;
  board?: BoardMember[];
  committees?: { name: string; members: string[]; page: number }[];
  shareholders?: { name: string; percent?: number; page: number }[];
  subsidiaries?: { name: string; country?: string; percent?: number; page: number }[];
  source: string; source_url: string; filed?: string | null; pages_read: number[]; method: string;
};
export type Identity = Record<string, unknown> & {
  board?: string[]; officers?: Officer[]; address?: string; website?: string; phone?: string; auditor?: string;
  company_secretary?: string; incorporated?: string; listed?: string; employees?: number; isin?: string;
  symbol?: string; market_classification?: string; source?: string;
};

const str = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : null);
const pct = (v?: number) => (v == null ? "–" : `${v % 1 === 0 ? v.toFixed(0) : v.toFixed(2)}%`);

function Section({ title, note, children }: { title: string; note?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <h3 className="eyebrow">{title}</h3>
      <div className="mt-3">{children}</div>
      {note && <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">{note}</p>}
    </section>
  );
}

function PageRef({ g, page }: { g: Governance; page: number }) {
  return <a href={`${g.source_url}#page=${page}`} target="_blank" rel="noreferrer" className="kbd text-[0.75rem] text-[color:var(--dim)] hover:underline">p{page}</a>;
}

/** Corporate facts, people, ownership and subsidiaries, each from a named source; absent facts are not shown. */
export function CompanyGovernance({ identity, governance: g, country }: { identity?: Identity; governance?: Governance; country: string | null }) {
  const id = identity ?? {};
  const website = str(id.website);
  const facts: [string, ReactNode][] = ([
    ["Registered office", str(g?.registered_office) ?? str(id.address)],
    ["RC number", g?.rc_number ? `RC ${g.rc_number}` : null],
    ["Incorporated", str(id.incorporated)],
    ["Listed", str(id.listed)],
    ["ISIN", str(id.isin)],
    ["Holding company", str(g?.holding_company)],
    ["Auditor", str(g?.auditor) ?? str(id.auditor)],
    ["Company secretary", str(g?.company_secretary) ?? str(id.company_secretary)],
    ["Registrar", str(g?.registrar)],
    ["Employees", typeof id.employees === "number" ? id.employees.toLocaleString("en-GB") : null],
    ["Phone", str(id.phone)],
    ["Website", website ? <a href={website.startsWith("http") ? website : `https://${website}`} target="_blank" rel="noreferrer" className="hover:underline">{website.replace(/^https?:\/\//, "")}</a> : null],
    ["Market classification", str(id.market_classification)],
  ] as [string, ReactNode][]).filter(([, v]) => v != null && v !== "");

  const board = g?.board?.length ? g.board : (id.board ?? []).map((name) => ({ name, page: 0 } as BoardMember));
  const officers = id.officers ?? [];
  const nigeria = country === "NG";
  const sourceNote = g ? (
    <>read from <a href={g.source_url} target="_blank" rel="noreferrer" className="hover:underline">{g.source.replace(/^Annual financial statements filed with the exchange: /, "")}</a>
      {g.filed ? `, filed ${g.filed}` : ""}. Each fact appears on the page shown, as printed; anything that could not be confirmed is left out.</>
  ) : null;

  if (!facts.length && !board.length && !officers.length && !g) return null;
  return (
    <div className="space-y-8">
      {facts.length > 0 && (
        <Section title="Company facts" note={[id.source && `Profile: ${id.source}`, g && "corporate details from the filed statements"].filter(Boolean).join(" · ") || undefined}>
          <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
            {facts.map(([k, v]) => (
              <div key={k} className="min-w-0">
                <dt className="text-[0.75rem] text-[color:var(--dim)]">{k}</dt>
                <dd className="mt-0.5 text-[0.875rem] text-[color:var(--text)]">{v}</dd>
              </div>
            ))}
          </dl>
          {nigeria && (
            <p className="mt-3 text-[0.75rem] text-[color:var(--dim)]">
              Check the registry: <a href="https://search.cac.gov.ng/home" target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">CAC company search</a>
              {" · "}<a href="https://bor.cac.gov.ng/search" target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">beneficial ownership register</a>
            </p>
          )}
        </Section>
      )}

      {(board.length > 0 || officers.length > 0) && (
        <div className="grid gap-8 lg:grid-cols-2">
          {board.length > 0 && (
            <Section title={`Board of directors · ${board.length}`} note={!g?.board?.length && id.source ? `Names: ${id.source}` : undefined}>
              <table className="w-full text-left text-[0.8125rem]">
                <tbody className="divide-y divide-white/[0.07] border-y hairline">
                  {board.map((b) => (
                    <tr key={b.name}>
                      <td className="py-2 pr-3 text-[color:var(--text)]">{b.name}</td>
                      <td className="py-2 pr-3 text-[color:var(--muted)]">{b.role ?? ""}{b.nationality ? <span className="text-[color:var(--dim)]"> · {b.nationality}</span> : null}</td>
                      <td className="py-2 text-right">{g && b.page ? <PageRef g={g} page={b.page} /> : null}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          )}
          {officers.length > 0 && (
            <Section title="Executives" note={id.source ? `Source: ${id.source}` : undefined}>
              <table className="w-full text-left text-[0.8125rem]">
                <tbody className="divide-y divide-white/[0.07] border-y hairline">
                  {officers.map((o) => (
                    <tr key={o.name + o.title}>
                      <td className="py-2 pr-3 text-[color:var(--text)]">{o.name}</td>
                      <td className="py-2 text-[color:var(--muted)]">{o.title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          )}
        </div>
      )}

      {g?.committees && g.committees.length > 0 && (
        <Section title="Board committees">
          <ul className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
            {g.committees.map((c) => (
              <li key={c.name} className="text-[0.8125rem]">
                <span className="text-[color:var(--text)]">{c.name}</span> <PageRef g={g} page={c.page} />
                <p className="mt-0.5 text-[color:var(--muted)]">{c.members.join(", ")}</p>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {g && ((g.shareholders?.length ?? 0) > 0 || (g.subsidiaries?.length ?? 0) > 0) && (
        <div className="grid gap-8 lg:grid-cols-2">
          {g.shareholders && g.shareholders.length > 0 && (
            <Section title="Substantial shareholders (5% or more)">
              <table className="w-full text-left text-[0.8125rem]">
                <tbody className="divide-y divide-white/[0.07] border-y hairline">
                  {g.shareholders.map((s) => (
                    <tr key={s.name}>
                      <td className="py-2 pr-3 text-[color:var(--text)]">{s.name}</td>
                      <td className="kbd py-2 pr-3 text-right">{pct(s.percent)}</td>
                      <td className="py-2 text-right"><PageRef g={g} page={s.page} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          )}
          {g.subsidiaries && g.subsidiaries.length > 0 && (
            <Section title={`Subsidiaries · ${g.subsidiaries.length}`}>
              <table className="w-full text-left text-[0.8125rem]">
                <tbody className="divide-y divide-white/[0.07] border-y hairline">
                  {g.subsidiaries.map((s) => (
                    <tr key={s.name}>
                      <td className="py-2 pr-3 text-[color:var(--text)]">{s.name}</td>
                      <td className="py-2 pr-3 text-[color:var(--muted)]">{s.country ?? ""}</td>
                      <td className="kbd py-2 pr-3 text-right">{pct(s.percent)}</td>
                      <td className="py-2 text-right"><PageRef g={g} page={s.page} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          )}
        </div>
      )}

      {sourceNote && <p className="border-t hairline pt-3 text-[0.75rem] text-[color:var(--dim)]">Board, committees, shareholders, subsidiaries and corporate details: {sourceNote}</p>}
    </div>
  );
}
