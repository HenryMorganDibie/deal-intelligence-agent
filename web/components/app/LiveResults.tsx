"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { ProBadge } from "./PlanLinks";
import { ErrorNote, Field, PageHeader } from "./ui";
import { Container } from "../primitives";
import { ApiError } from "../../lib/api";
import { del, get, post } from "../../lib/market";

type Ranked = { candidate: string; party: string | null; votes: number; share: number; [k: string]: string | number | null };
type Spread = Record<string, { states_at_25: number; needed: number; met: boolean; fct_at_25: boolean | null }>;
type Summary = {
  reported: number; units: number; complete: boolean; declared: number; valid: number; rejected: number; votes_cast: number;
  registered: number | null; turnout: number | null; results: Ranked[]; units_won: Record<string, number>;
  leader: string | null; margin: number | null; register_reported?: number; spread?: Spread;
};
type Area = Summary & { area: string; region: string; pending: string[] };
type Unit = {
  unit: string; area: string; status: "pending" | "provisional" | "declared"; results: Ranked[];
  votes_cast: number | null; rejected: number | null; registered: number | null; turnout: number | null; winner: string | null;
  source: string | null; updated_at: string | null;
};
type Data = {
  label: string; polling_day: string; body: string; unit_word: string; units_word: string; area_word: string;
  candidates: string[]; national: Summary; areas: Area[]; units: Unit[]; notes: string; baseline_year: number | null;
  operator: boolean; plan: string; rejected_ballots: boolean; ballot: { name: string; party: string | null }[];
};
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

// One steady colour per candidate, in ballot order, so a candidate reads the same in every table.
const COLOURS = ["#6ee7c8", "#f5b955", "#8fb4ff", "#f28b82", "#c3a6ff", "#9ad18b", "#f0a6ca", "#a3a3a3"];
const pct = (x: number | null | undefined) => (x == null ? "–" : `${(x * 100).toFixed(1)}%`);
const num = (x: number | null | undefined) => (x == null ? "–" : x.toLocaleString("en-GB"));

function Bars({ results, colour }: { results: Ranked[]; colour: (n: string) => string }) {
  return (
    <ul className="space-y-2">
      {results.map((r) => (
        <li key={r.candidate}>
          <div className="flex items-baseline justify-between gap-3 text-[0.875rem]">
            <span className="text-[color:var(--text)]">{r.candidate}{r.party ? <span className="text-[color:var(--dim)]"> · {r.party}</span> : null}</span>
            <span className="kbd shrink-0 text-[color:var(--muted)]">{num(r.votes)} · {pct(r.share)}</span>
          </div>
          <div className="mt-1 h-2 rounded-full bg-white/[0.06]">
            <div className="h-2 rounded-full" style={{ width: `${Math.max(r.share * 100, r.votes ? 1 : 0)}%`, background: colour(r.candidate) }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function EntryForm({ data, election, onSaved }: { data: Data; election: string; onSaved: () => void }) {
  const [con, setCon] = useState("");
  const [votes, setVotes] = useState<Record<string, string>>({});
  const [registered, setRegistered] = useState("");
  const [rejected, setRejected] = useState("");
  const [accredited, setAccredited] = useState("");
  const [status, setStatus] = useState<"declared" | "provisional">("declared");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const total = data.ballot.reduce((s, c) => s + (Number(votes[c.name]) || 0), 0);

  function pick(name: string) {
    setCon(name);
    const existing = data.units.find((c) => c.unit === name);
    setVotes(Object.fromEntries((existing?.results ?? []).map((r) => [r.candidate, String(r.votes)])));
    setRegistered(existing?.registered ? String(existing.registered) : "");
    setRejected(existing?.rejected ? String(existing.rejected) : "");
    setSource(existing?.source ?? "");
    setNote(null);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setNote(null);
    try {
      const r = await post<{ warnings: string[]; alerts: { sent?: number } | null }>(`/api/elections/live?election=${election}`, {
        unit: con, status, source: source.trim() || null,
        registered: registered ? Number(registered) : null,
        rejected: data.rejected_ballots && rejected ? Number(rejected) : null,
        accredited: data.rejected_ballots && accredited ? Number(accredited) : null,
        votes: Object.fromEntries(data.ballot.map((c) => [c.name, Number(votes[c.name]) || 0])),
      });
      setNote({ ok: true, text: `${con} saved${r.alerts?.sent ? `, ${r.alerts.sent} alert${r.alerts.sent === 1 ? "" : "s"} sent` : ""}.${r.warnings.length ? ` ${r.warnings.join(" ")}` : ""}` });
      onSaved();
    } catch (err) {
      setNote({ ok: false, text: err instanceof ApiError ? err.message : "The result could not be saved." });
    } finally { setBusy(false); }
  }

  async function remove() {
    if (!con || !window.confirm(`Remove ${con}'s result? Its earlier versions stay in the record.`)) return;
    try { await del(`/api/elections/live/${encodeURIComponent(con)}?election=${election}`); setNote({ ok: true, text: `${con} removed.` }); onSaved(); }
    catch (err) { setNote({ ok: false, text: err instanceof ApiError ? err.message : "The result could not be removed." }); }
  }

  return (
    <form onSubmit={submit} className="panel mt-8 space-y-4 p-5">
      <h2 className="h3">Enter a result (operators)</h2>
      <p className="text-[0.8125rem] text-[color:var(--dim)]">As {data.body} declares it. Saving again corrects it; earlier versions are kept. Declared results are pushed to results alerts. Leave a candidate blank for zero.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={cap(data.unit_word)}>
          <select value={con} onChange={(e) => pick(e.target.value)} required className="field">
            <option value="">Choose…</option>
            {data.areas.map((a) => (
              <optgroup key={a.area} label={`${a.area} (${a.region})`}>
                {data.units.filter((c) => c.area === a.area).map((c) => (
                  <option key={c.unit} value={c.unit}>{c.unit}{c.status !== "pending" ? ` · ${c.status}` : ""}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <select value={status} onChange={(e) => setStatus(e.target.value as "declared" | "provisional")} className="field">
            <option value="declared">Declared by {data.body}</option>
            <option value="provisional">Provisional (not pushed to alerts)</option>
          </select>
        </Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {data.ballot.map((c) => (
          <Field key={c.name} label={`${c.name}${c.party ? ` (${c.party})` : ""}`}>
            <input inputMode="numeric" pattern="[0-9]*" value={votes[c.name] ?? ""} placeholder="0"
                   onChange={(e) => setVotes({ ...votes, [c.name]: e.target.value.replace(/\D/g, "") })} className="field kbd" />
          </Field>
        ))}
        <Field label="Registered voters (if announced)">
          <input inputMode="numeric" value={registered} onChange={(e) => setRegistered(e.target.value.replace(/\D/g, ""))} className="field kbd" />
        </Field>
        {data.rejected_ballots && (
          <>
            <Field label="Rejected ballots">
              <input inputMode="numeric" value={rejected} onChange={(e) => setRejected(e.target.value.replace(/\D/g, ""))} className="field kbd" />
            </Field>
            <Field label="Accredited voters (if announced)">
              <input inputMode="numeric" value={accredited} onChange={(e) => setAccredited(e.target.value.replace(/\D/g, ""))} className="field kbd" />
            </Field>
          </>
        )}
      </div>
      <Field label="Source link (optional)">
        <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="https://" className="field" />
      </Field>
      <p className="kbd text-[0.8125rem] text-[color:var(--muted)]">Valid votes: {num(total)}{rejected ? ` · votes cast ${num(total + Number(rejected))}` : ""}{registered ? ` · turnout ${pct((total + (Number(rejected) || 0)) / Number(registered))}` : ""}</p>
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy || !con} className="btn btn-primary">{busy ? "Saving…" : "Save result"}</button>
        {con && data.units.find((c) => c.unit === con)?.status !== "pending" && (
          <button type="button" onClick={remove} className="btn btn-ghost">Remove</button>
        )}
      </div>
      {note && <p role="status" className={`text-[0.8125rem] ${note.ok ? "text-verified" : "text-risk"}`}>{note.text}</p>}
    </form>
  );
}

/** The live results page for one election (The Gambia, Nigeria): tallies, areas, units and, for operators, entry. */
export function LiveResults({ election, title, intro }: { election: string; title: string; intro: string }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<{ status?: number; text: string } | null>(null);
  const [area, setArea] = useState("all");

  const load = useCallback(async () => {
    try { setData(await get<Data>("/api/elections/live", { election })); setError(null); }
    catch (e) { setError(e instanceof ApiError ? { status: e.status, text: e.message } : { text: "Live results could not be loaded." }); }
  }, [election]);
  useEffect(() => {
    void load();
    const t = setInterval(() => { if (document.visibilityState === "visible") void load(); }, 30_000);
    return () => clearInterval(t);
  }, [load]);

  const colour = useMemo(() => {
    const order = data?.candidates ?? [];
    return (n: string) => COLOURS[Math.max(0, order.indexOf(n)) % COLOURS.length];
  }, [data]);

  const nat = data?.national;
  const shown = (data?.units ?? []).filter((c) => area === "all" || c.area === area);
  const by = data?.baseline_year;

  return (
    <Container className="py-10">
      <PageHeader eyebrow="Live results" title={title}>
        {intro} Refreshes every 30 seconds. <Link href="/app/watchlists#election-alerts-title" className="underline">Get each result by alert</Link>.
      </PageHeader>

      {error?.status === 403 ? (
        <p className="inline-flex flex-wrap items-center gap-1 text-sm text-[color:var(--muted)]">Live results come with the Pro plan and above<ProBadge source="live_results" /></p>
      ) : error ? <ErrorNote message={error.text} /> : !data || !nat ? (
        <p className="text-sm text-[color:var(--dim)]" role="status">Loading live results…</p>
      ) : (
        <>
          <section className="grid gap-4 lg:grid-cols-[2fr_1fr]">
            <div className="panel p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="h3">National</h2>
                <span className="text-[0.8125rem] text-[color:var(--muted)]">{nat.reported} of {nat.units} {data.units_word} in · {nat.declared} declared</span>
              </div>
              <div className="mt-4">
                {nat.reported ? <Bars results={nat.results} colour={colour} /> : (
                  <p className="text-[0.875rem] text-[color:var(--muted)]">No results yet. {data.body} declares them {data.unit_word} by {data.unit_word} after polls close on {new Date(`${data.polling_day}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "long", timeZone: "UTC" })}.</p>
                )}
              </div>
            </div>
            <div className="panel space-y-3 p-5 text-[0.875rem]">
              <p className="flex justify-between"><span className="text-[color:var(--muted)]">Leader</span><span>{nat.leader ?? "–"}</span></p>
              <p className="flex justify-between"><span className="text-[color:var(--muted)]">Margin</span><span className="kbd">{num(nat.margin)}</span></p>
              <p className="flex justify-between"><span className="text-[color:var(--muted)]">Valid votes</span><span className="kbd">{num(nat.valid)}</span></p>
              {data.rejected_ballots && <p className="flex justify-between"><span className="text-[color:var(--muted)]">Rejected</span><span className="kbd">{num(nat.rejected)}</span></p>}
              {nat.register_reported != null && <p className="flex justify-between"><span className="text-[color:var(--muted)]">Register fully reported</span><span className="kbd">{pct(nat.register_reported)}</span></p>}
              <p className="flex justify-between"><span className="text-[color:var(--muted)]">Registered voters</span><span className="kbd">{num(nat.registered)}</span></p>
              {Object.keys(nat.units_won).length > 0 && (
                <div className="border-t hairline pt-3">
                  <p className="text-[color:var(--muted)]">{cap(data.units_word)} won</p>
                  <ul className="mt-1 space-y-1">
                    {Object.entries(nat.units_won).map(([n, w]) => (
                      <li key={n} className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: colour(n) }} />{n}</span>
                        <span className="kbd">{w}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {by && nat.results.some((r) => r[`votes_${by}`]) && (
                <p className="border-t hairline pt-3 text-[0.75rem] text-[color:var(--dim)]">
                  {by}: {nat.results.filter((r) => r[`votes_${by}`]).map((r) => `${r.candidate.split(" ").slice(-1)[0]} ${num(r[`votes_${by}`] as number)}`).join(" · ")}
                </p>
              )}
            </div>
          </section>

          {nat.spread && Object.keys(nat.spread).length > 0 && (
            <section className="mt-8">
              <h2 className="h3">25% in two-thirds of the states</h2>
              <p className="mt-1 text-[0.8125rem] text-[color:var(--dim)]">The winner needs the most votes and at least 25% in 24 of the 36 states. Whether the FCT is also required was disputed in 2023, so it is shown on its own.</p>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[28rem] text-left text-[0.8125rem]">
                  <thead className="text-[color:var(--dim)]"><tr><th className="py-2 pr-3 font-normal">Candidate</th><th className="py-2 pr-3 font-normal">States at 25%</th><th className="py-2 pr-3 font-normal">Test</th><th className="py-2 font-normal">FCT at 25%</th></tr></thead>
                  <tbody className="divide-y divide-white/[0.07] border-t hairline">
                    {Object.entries(nat.spread).map(([n, v]) => (
                      <tr key={n}>
                        <td className="py-2 pr-3">{n}</td>
                        <td className="kbd py-2 pr-3">{v.states_at_25} of 36</td>
                        <td className={`py-2 pr-3 ${v.met ? "text-verified" : "text-[color:var(--muted)]"}`}>{v.met ? "Met" : `${v.needed - v.states_at_25} more needed`}</td>
                        <td className="py-2">{v.fct_at_25 == null ? "–" : v.fct_at_25 ? "Yes" : "No"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="mt-8">
            <h2 className="h3">By {data.area_word}</h2>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[36rem] text-left text-[0.8125rem]">
                <thead className="text-[color:var(--dim)]">
                  <tr><th className="py-2 pr-3 font-normal">{cap(data.area_word)}</th><th className="py-2 pr-3 font-normal">In</th><th className="py-2 pr-3 font-normal">Leader</th><th className="py-2 pr-3 font-normal">Margin</th><th className="py-2 pr-3 font-normal">Turnout</th><th className="py-2 font-normal">Registered</th></tr>
                </thead>
                <tbody className="divide-y divide-white/[0.07] border-t hairline">
                  {data.areas.map((a) => (
                    <tr key={a.area}>
                      <td className="py-2 pr-3"><button type="button" onClick={() => setArea(a.area)} className="underline-offset-2 hover:underline">{a.area}</button>{a.region !== a.area && <span className="text-[color:var(--dim)]"> {a.region}</span>}</td>
                      <td className="kbd py-2 pr-3">{a.reported}/{a.units}</td>
                      <td className="py-2 pr-3">{a.leader ? <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: colour(a.leader) }} />{a.leader}</span> : "–"}</td>
                      <td className="kbd py-2 pr-3">{num(a.margin)}</td>
                      <td className="kbd py-2 pr-3">{pct(a.turnout)}</td>
                      <td className="kbd py-2">{num(a.registered)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="mt-8">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="h3">{cap(data.units_word)}</h2>
              <select value={area} onChange={(e) => setArea(e.target.value)} className="field w-auto" aria-label={cap(data.area_word)}>
                <option value="all">All {data.units.length}</option>
                {data.areas.map((a) => <option key={a.area} value={a.area}>{a.area}{a.region !== a.area ? ` (${a.region})` : ""}</option>)}
              </select>
            </div>
            <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {shown.map((c) => (
                <li key={c.unit} className="panel p-4" style={c.winner ? { borderLeft: `3px solid ${colour(c.winner)}` } : undefined}>
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="text-[0.875rem] text-[color:var(--text)]">{c.unit}</p>
                    <span className={`text-[0.75rem] ${c.status === "declared" ? "text-verified" : "text-[color:var(--dim)]"}`}>{c.status}</span>
                  </div>
                  <p className="text-[0.75rem] text-[color:var(--dim)]">{c.area}</p>
                  {c.results.length > 0 && (
                    <ul className="mt-2 space-y-0.5 text-[0.8125rem]">
                      {c.results.slice(0, 3).map((r) => (
                        <li key={r.candidate} className="flex justify-between gap-2"><span>{r.candidate}</span><span className="kbd text-[color:var(--muted)]">{num(r.votes)} · {pct(r.share)}{by && r[`share_${by}`] != null ? <span className="text-[color:var(--dim)]"> ({by}: {pct(r[`share_${by}`] as number)})</span> : null}</span></li>
                      ))}
                      <li className="text-[0.75rem] text-[color:var(--dim)]">
                        {num(c.votes_cast)} votes{c.turnout != null ? ` · turnout ${pct(c.turnout)}` : ""}
                        {c.source ? <> · <a href={c.source} target="_blank" rel="noopener noreferrer" className="underline">source</a></> : null}
                      </li>
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </section>

          <p className="mt-6 text-[0.75rem] text-[color:var(--dim)]">{data.notes}</p>
          {data.operator && <EntryForm data={data} election={election} onSaved={load} />}
        </>
      )}
    </Container>
  );
}
