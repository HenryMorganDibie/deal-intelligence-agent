"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { ProBadge } from "./PlanLinks";
import { ErrorNote, Field } from "./ui";
import { Container } from "../primitives";
import { ApiError } from "../../lib/api";
import { del, get, post } from "../../lib/market";
import { Segmented } from "./Chip";
import { PastResults } from "./PastResults";
import { PollsPanel } from "./PollsPanel";
import { SheetImport } from "./SheetImport";
import { StateTileMap } from "./StateTileMap";
import { partyColour } from "../../lib/parties";

type Ranked = { candidate: string; party: string | null; votes: number; share: number; [k: string]: string | number | null };
type Spread = Record<string, { states_at_25: number; needed: number; met: boolean; fct_at_25: boolean | null; of?: number }>;
type Previous = { year: number; results: { name: string; party: string; share: number | null; won: boolean }[] };
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
  operator: boolean; plan: string; rejected_ballots: boolean; ballot: { name: string; party: string | null; running_mate?: string | null }[];
  baseline_winners: Record<string, string>; state?: string | null; previous?: Previous | null; rule?: string | null;
};
// Names off the ballot (a 2023 winner not standing in 2027) get these, in order of first appearance.
const EXTRA = ["#b0a089", "#7f9cb5", "#c99f6e"];
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
// How the press names a candidate in short: usually the surname, but some go by their first name.
const FIRST_NAME = new Set(["Atiku Abubakar"]);
const short = (n: string) => (FIRST_NAME.has(n) ? n.split(" ")[0] : n.split(" ").slice(-1)[0]);

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

type PollAvg = { polls_used: number; pollsters?: string[]; window_days: number; shares: { candidate: string; share: number }[] };
type Tab = "overview" | "units" | "polls" | "past" | "import";

function daysTo(day: string): number {
  const today = new Date(new Date().toISOString().slice(0, 10) + "T00:00:00Z").getTime();
  return Math.round((Date.parse(`${day}T00:00:00Z`) - today) / 86_400_000);
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[0.75rem] text-[color:var(--dim)]">{label}</p>
      <p className="kbd mt-0.5 truncate text-[1.125rem] text-[color:var(--text)]">{value}</p>
      {sub && <p className="truncate text-[0.75rem] text-[color:var(--muted)]">{sub}</p>}
    </div>
  );
}

/** The live results page for one election (The Gambia, Nigeria): tallies, areas, units and, for operators, entry. */
export function LiveResults({ election, title, intro }: { election: string; title: string; intro: string }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<{ status?: number; text: string } | null>(null);
  const [area, setArea] = useState("all");
  const [pickedState, setPickedState] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [polls, setPolls] = useState<PollAvg | null>(null);

  const load = useCallback(async () => {
    try { setData(await get<Data>("/api/elections/live", { election })); setError(null); }
    catch (e) { setError(e instanceof ApiError ? { status: e.status, text: e.message } : { text: "Live results could not be loaded." }); }
  }, [election]);
  useEffect(() => {
    void load();
    const t = setInterval(() => { if (document.visibilityState === "visible") void load(); }, 30_000);
    return () => clearInterval(t);
  }, [load]);
  useEffect(() => {
    if (election !== "ng-2027") return;
    get<{ average: PollAvg }>("/api/elections/polls", { election }).then((r) => setPolls(r.average)).catch(() => setPolls(null));
  }, [election]);

  const colour = useMemo(() => {
    if (data?.rule === "ng_gov_spread") {
      const party = Object.fromEntries(data.ballot.map((c) => [c.name, c.party]));
      return (n: string) => partyColour(party[n]);
    }
    const order = data?.candidates ?? [];
    const extra = Array.from(new Set(Object.values(data?.baseline_winners ?? {}).filter((n) => !order.includes(n))));
    return (n: string) => order.includes(n) ? COLOURS[order.indexOf(n) % COLOURS.length] : EXTRA[Math.max(0, extra.indexOf(n)) % EXTRA.length];
  }, [data]);

  const nat = data?.national;
  const by = data?.baseline_year;
  const nigeria = election === "ng-2027";
  const gov = data?.rule === "ng_gov_spread";
  // INEC lists governorship candidates surname first, so a one-word short name would mislead there.
  const nm = (n: string) => (gov ? n : short(n));
  const shown = (data?.units ?? []).filter((c) => area === "all" || c.area === area);
  const days = data ? daysTo(data.polling_day) : 0;
  const counting = !!nat && nat.reported > 0;
  const status = !nat ? "" : nat.complete ? "Complete" : counting ? `Counting · ${nat.reported} of ${nat.units} in` : days > 0 ? "Before the vote" : "Awaiting results";
  const shortDate = (d: string) => new Date(`${d}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  const tabs: [Tab, string][] = [["overview", "Overview"], ["units", cap(data?.units_word ?? "results")],
    ...(nigeria ? [["polls", "Polls"], ["past", "Past results"]] as [Tab, string][] : []),
    ...(nigeria && data?.plan === "institutional" ? [["import", "Import sheets"]] as [Tab, string][] : [])];
  const top2023 = (nat?.results ?? []).filter((r) => by && r[`votes_${by}`]).sort((a, b) => (b[`votes_${by}`] as number) - (a[`votes_${by}`] as number));

  return (
    <Container className="max-w-6xl py-10">
      <header>
        <p className="text-[0.8125rem] text-[color:var(--dim)]">
          {election.startsWith("ng-2027-gov-")
            ? <Link href="/app/elections/nigeria/governorship" className="underline-offset-2 hover:text-[color:var(--text)] hover:underline">Governorship elections</Link>
            : "Live results"}
        </p>
        <h1 className="h2 mt-1 text-[1.75rem] sm:text-[2rem]">{title.split(":")[0]}<span className="text-[color:var(--muted)]"> · {cap(title.split(":")[1]?.split(",")[0]?.trim() ?? "")}</span></h1>
        {data && (
          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.875rem] text-[color:var(--muted)]">
            <span>{shortDate(data.polling_day)}</span>
            {days > 0 && !counting && <span className="text-[color:var(--dim)]">· {days} day{days === 1 ? "" : "s"} to go</span>}
            <span className="inline-flex items-center gap-1.5 rounded-full border hairline px-2.5 py-0.5 text-[0.75rem]">
              <span className={`h-1.5 w-1.5 rounded-full ${counting && !nat?.complete ? "animate-pulse bg-[color:var(--verified,#6ee7c8)]" : "bg-[color:var(--dim)]"}`} />{status}
            </span>
            <Link href="/app/watchlists#elections" className="text-[color:var(--muted)] underline-offset-2 hover:text-[color:var(--text)] hover:underline">Alerts</Link>
            {nigeria && <Link href="/app/elections/nigeria/governorship" className="text-[color:var(--muted)] underline-offset-2 hover:text-[color:var(--text)] hover:underline">Governorship races</Link>}
          </p>
        )}
        <p className="mt-2 max-w-3xl text-[0.8125rem] text-[color:var(--dim)]">{intro}</p>
      </header>

      {error?.status === 403 ? (
        <p className="mt-8 inline-flex flex-wrap items-center gap-1 text-sm text-[color:var(--muted)]">Live results come with the Pro plan and above<ProBadge source="live_results" /></p>
      ) : error ? <div className="mt-8"><ErrorNote message={error.text} /></div> : !data || !nat ? (
        <p className="mt-8 text-sm text-[color:var(--dim)]" role="status">Loading…</p>
      ) : (
        <>
          <div role="tablist" aria-label="Sections" className="mb-8 mt-6 flex gap-6 overflow-x-auto border-b hairline">
            {tabs.map(([k, label]) => (
              <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                      className={`-mb-px shrink-0 border-b-2 pb-2.5 text-[0.9375rem] transition-colors ${
                        tab === k ? "border-[color:var(--text)] text-[color:var(--text)]" : "border-transparent text-[color:var(--muted)] hover:text-[color:var(--text)]"}`}>
                {label}
              </button>
            ))}
          </div>

          {tab === "overview" && (
            <>
              {counting && (
                <div className="mb-6 grid grid-cols-2 gap-4 border-y hairline py-4 sm:grid-cols-5">
                  <Stat label="Leader" value={nat.leader ? nm(nat.leader) : "–"} sub={nat.results[0]?.party ?? undefined} />
                  <Stat label="Margin" value={num(nat.margin)} />
                  <Stat label={`${cap(data.units_word)} in`} value={`${nat.reported}/${nat.units}`} sub={`${nat.declared} declared`} />
                  <Stat label="Valid votes" value={num(nat.valid)} sub={data.rejected_ballots ? `${num(nat.rejected)} rejected` : undefined} />
                  <Stat label="Turnout" value={pct(nat.turnout)} sub={nat.turnout == null ? "when complete" : undefined} />
                </div>
              )}

              <div className={`grid gap-8 ${data.unit_word === "state" ? "lg:grid-cols-[minmax(0,26rem)_1fr]" : ""}`}>
                {data.unit_word === "state" && (
                  <div>
                    <StateTileMap winners={Object.fromEntries(data.units.map((u) => [u.unit, u.winner]))} baseline={data.baseline_winners ?? {}}
                                  baselineYear={data.baseline_year} colour={colour}
                                  onPick={(st) => { setPickedState(st); if (nigeria) setTab("past"); }} />
                    {nigeria && <p className="mt-1 text-[0.75rem] text-[color:var(--dim)]">Click a state for its past results.</p>}
                  </div>
                )}

                <div className="min-w-0 space-y-8">
                  {counting ? (
                    <section>
                      <h2 className="text-[0.9375rem] text-[color:var(--text)]">{gov ? `${data.state}, all LGAs in so far` : "National"}</h2>
                      <div className="mt-3"><Bars results={nat.results.slice(0, 6)} colour={colour} /></div>
                      {Object.keys(nat.units_won).length > 0 && (
                        <p className="mt-3 text-[0.8125rem] text-[color:var(--muted)]">
                          {cap(data.units_word)} won: {Object.entries(nat.units_won).map(([n, w]) => `${nm(n)} ${w}`).join(" · ")}
                        </p>
                      )}
                    </section>
                  ) : (
                    <section>
                      <h2 className="text-[0.9375rem] text-[color:var(--text)]">Before the vote</h2>
                      <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">
                        {data.body} declares results {data.unit_word} by {data.unit_word} after polls close. This page fills in as it does, with an alert for each.
                      </p>
                      {polls && polls.polls_used > 0 && (
                        <div className="mt-5">
                          <p className="text-[0.8125rem] text-[color:var(--muted)]">Polling average <span className="text-[color:var(--dim)]">· {polls.polls_used} pollster{polls.polls_used === 1 ? "" : "s"}, last {polls.window_days} days</span></p>
                          <ul className="mt-2 space-y-2">
                            {polls.shares.slice(0, 4).map((x) => (
                              <li key={x.candidate}>
                                <div className="flex justify-between text-[0.875rem]"><span>{x.candidate}</span><span className="kbd text-[color:var(--muted)]">{x.share.toFixed(1)}%</span></div>
                                <div className="mt-1 h-1.5 rounded-full bg-white/[0.06]"><div className="h-1.5 rounded-full" style={{ width: `${x.share}%`, background: colour(x.candidate) }} /></div>
                              </li>
                            ))}
                          </ul>
                          <button type="button" onClick={() => setTab("polls")} className="mt-2 text-[0.75rem] text-[color:var(--muted)] underline-offset-2 hover:underline">All polls</button>
                        </div>
                      )}
                      {gov && data.previous && data.previous.results.length > 0 && (
                        <div className="mt-5">
                          <p className="text-[0.8125rem] text-[color:var(--muted)]">{data.previous.year} governorship result</p>
                          <ul className="mt-2 space-y-1 text-[0.875rem]">
                            {data.previous.results.map((r) => (
                              <li key={r.name} className="flex justify-between gap-2">
                                <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: partyColour(r.party) }} />
                                  {r.name}<span className="text-[color:var(--dim)]"> · {r.party}{r.won ? " · won" : ""}</span></span>
                                <span className="kbd text-[color:var(--muted)]">{r.share == null ? "–" : `${r.share.toFixed(1)}%`}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {gov && (
                        <div className="mt-5">
                          <p className="text-[0.8125rem] text-[color:var(--muted)]">On the ballot <span className="text-[color:var(--dim)]">· {data.ballot.length} tickets, INEC&apos;s final list</span></p>
                          <table className="mt-2 w-full text-left text-[0.8125rem]">
                            <tbody className="divide-y divide-white/[0.07] border-y hairline">
                              {data.ballot.map((c) => (
                                <tr key={c.name}>
                                  <td className="py-1.5 pr-3"><span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: colour(c.name) }} />{c.party}</td>
                                  <td className="py-1.5 pr-3 text-[color:var(--text)]">{c.name}</td>
                                  <td className="py-1.5 text-[color:var(--dim)]">{c.running_mate ? `with ${c.running_mate}` : ""}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                      {top2023.length > 0 && (
                        <div className="mt-5">
                          <p className="text-[0.8125rem] text-[color:var(--muted)]">{by} result</p>
                          <ul className="mt-2 space-y-1 text-[0.875rem]">
                            {top2023.map((r) => (
                              <li key={r.candidate} className="flex justify-between gap-2">
                                <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: colour(r.candidate) }} />{r.candidate}</span>
                                <span className="kbd text-[color:var(--muted)]">{num(r[`votes_${by}`] as number)}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </section>
                  )}

                  {nat.spread && (
                    <section>
                      <h2 className="text-[0.9375rem] text-[color:var(--text)]">The 25% rule</h2>
                      <p className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">
                        {gov
                          ? `To win, a candidate needs the most votes and at least 25% in two-thirds of ${data.state}'s ${nat.units} LGAs (${Math.ceil((nat.units * 2) / 3)}).`
                          : "To win, a candidate needs the most votes and at least 25% in 24 of the 36 states. The FCT's place in the rule was disputed in 2023, so it's shown separately."}
                      </p>
                      {Object.keys(nat.spread).length > 0 && (
                        <table className="mt-3 w-full text-left text-[0.8125rem]">
                          <tbody className="divide-y divide-white/[0.07] border-y hairline">
                            {Object.entries(nat.spread).slice(0, 5).map(([n, v]) => (
                              <tr key={n}>
                                <td className="py-2 pr-3">{n}</td>
                                <td className="kbd py-2 pr-3 text-[color:var(--muted)]">{v.states_at_25}/{v.of ?? 36}</td>
                                <td className={`py-2 pr-3 ${v.met ? "text-verified" : "text-[color:var(--dim)]"}`}>{v.met ? "Met" : `${v.needed - v.states_at_25} to go`}</td>
                                {!gov && <td className="py-2 text-right text-[color:var(--dim)]">FCT {v.fct_at_25 == null ? "–" : v.fct_at_25 ? "yes" : "no"}</td>}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </section>
                  )}

                  {counting && !gov && (
                    <section>
                      <h2 className="text-[0.9375rem] text-[color:var(--text)]">By {data.area_word}</h2>
                      <table className="mt-3 w-full text-left text-[0.8125rem]">
                        <tbody className="divide-y divide-white/[0.07] border-y hairline">
                          {data.areas.map((a) => (
                            <tr key={a.area}>
                              <td className="py-2 pr-3">{a.area}</td>
                              <td className="kbd py-2 pr-3 text-[color:var(--muted)]">{a.reported}/{a.units}</td>
                              <td className="py-2 pr-3">{a.leader ? <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: colour(a.leader) }} />{a.leader}</span> : <span className="text-[color:var(--dim)]">–</span>}</td>
                              <td className="kbd py-2 text-right text-[color:var(--muted)]">{a.margin ? `+${num(a.margin)}` : ""}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </section>
                  )}
                </div>
              </div>
            </>
          )}

          {tab === "units" && (
            <section>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-[0.875rem] text-[color:var(--muted)]">{nat.reported} of {nat.units} {data.units_word} in</p>
                <Segmented label={cap(data.area_word)} value={area} onChange={setArea}
                           options={[["all", "All"], ...data.areas.map((a) => [a.area, a.area] as [string, string])]} />
              </div>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[40rem] text-left text-[0.8125rem]">
                  <thead className="text-[color:var(--dim)]">
                    <tr><th className="py-2 pr-3 font-normal">{cap(data.unit_word)}</th><th className="py-2 pr-3 font-normal">{cap(data.area_word)}</th><th className="py-2 pr-3 font-normal">Leader</th><th className="py-2 pr-3 font-normal">Share</th><th className="py-2 pr-3 font-normal">Margin</th><th className="py-2 pr-3 font-normal">Turnout</th>{by && <th className="py-2 font-normal">{by}</th>}</tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.07] border-t hairline">
                    {shown.map((u) => {
                      const [a, b] = u.results;
                      const prior = data.baseline_winners?.[u.unit];
                      return (
                        <Fragment key={u.unit}>
                          <tr className={u.results.length ? "cursor-pointer hover:bg-white/[0.02]" : ""} onClick={() => u.results.length && setOpen(open === u.unit ? null : u.unit)}>
                            <td className="py-2 pr-3 text-[color:var(--text)]">{u.unit}{u.status === "provisional" && <span className="ml-1.5 text-[0.6875rem] text-[color:var(--dim)]">provisional</span>}</td>
                            <td className="py-2 pr-3 text-[color:var(--muted)]">{u.area}</td>
                            <td className="py-2 pr-3">{a?.votes ? <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: colour(a.candidate) }} />{a.candidate}</span> : <span className="text-[color:var(--dim)]">Pending</span>}</td>
                            <td className="kbd py-2 pr-3 text-[color:var(--muted)]">{a?.votes ? pct(a.share) : ""}</td>
                            <td className="kbd py-2 pr-3 text-[color:var(--muted)]">{a?.votes && b ? num(a.votes - b.votes) : ""}</td>
                            <td className="kbd py-2 pr-3 text-[color:var(--muted)]">{u.turnout != null ? pct(u.turnout) : ""}</td>
                            {by && <td className="py-2 text-[color:var(--dim)]">{prior ? short(prior) : ""}</td>}
                          </tr>
                          {open === u.unit && (
                            <tr>
                              <td colSpan={by ? 7 : 6} className="bg-white/[0.02] px-3 py-3">
                                <ul className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
                                  {u.results.slice(0, 8).map((r) => (
                                    <li key={r.candidate} className="flex justify-between gap-2"><span>{r.candidate} <span className="text-[color:var(--dim)]">{r.party}</span></span>
                                      <span className="kbd text-[color:var(--muted)]">{num(r.votes)} · {pct(r.share)}{by && r[`share_${by}`] != null ? <span className="text-[color:var(--dim)]"> ({by} {pct(r[`share_${by}`] as number)})</span> : null}</span></li>
                                  ))}
                                </ul>
                                <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">
                                  {num(u.votes_cast)} votes cast{u.rejected ? ` · ${num(u.rejected)} rejected` : ""}{u.registered ? ` · ${num(u.registered)} registered` : ""}
                                  {u.source ? <> · <a href={u.source} target="_blank" rel="noopener noreferrer" className="underline">source</a></> : null}
                                  {nigeria ? <> · <button type="button" className="underline" onClick={() => { setPickedState(u.unit); setTab("past"); }}>past results</button></> : null}
                                </p>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {tab === "polls" && nigeria && <PollsPanel election={election} ballot={data.ballot} colour={colour} />}
          {tab === "past" && nigeria && <PastResults selected={pickedState} />}
          {tab === "import" && nigeria && <SheetImport />}

          {data.operator && tab !== "past" && tab !== "import" && <EntryForm data={data} election={election} onSaved={load} />}
          <p className="mt-10 text-[0.75rem] text-[color:var(--dim)]">{data.notes} Refreshes every 30 seconds.</p>
        </>
      )}
    </Container>
  );
}
