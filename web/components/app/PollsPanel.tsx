"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError } from "../../lib/api";
import { get, post } from "../../lib/market";
import { Field } from "./ui";

type Poll = { id: string; pollster: string; fieldwork_start: string; fieldwork_end: string; sample: number; method: string | null;
  shares: Record<string, number>; undecided: number | null; source: string };
type Data = {
  polls: Poll[]; operator: boolean; method: string;
  average: { polls_used: number; pollsters?: string[]; window_days: number; shares: { candidate: string; share: number; polls: number }[] };
  recent_poll_stories: { title: string; url: string | null; day: string | null; outlets: string[] | null }[];
};

/** Published polls for an election: the average, the polls, poll stories from the news, and entry for operators. */
export function PollsPanel({ election, ballot, colour }: {
  election: string; ballot: { name: string; party: string | null }[]; colour: (n: string) => string;
}) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setData(await get<Data>("/api/elections/polls", { election })); setError(null); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Polls could not be loaded."); }
  }, [election]);
  useEffect(() => { void load(); }, [load]);

  if (error) return <p className="mt-3 text-sm text-[color:var(--muted)]">{error}</p>;
  if (!data) return null;
  const avg = data.average;
  return (
    <section className="mt-8">
      <h2 className="h3">Opinion polls</h2>
      <p className="mt-1 text-[0.8125rem] text-[color:var(--dim)]">{data.method}</p>
      {avg.polls_used ? (
        <div className="panel mt-3 p-5">
          <p className="text-[0.8125rem] text-[color:var(--muted)]">Average of {avg.polls_used} pollster{avg.polls_used === 1 ? "" : "s"} ({avg.pollsters?.join(", ")}), last {avg.window_days} days</p>
          <ul className="mt-3 space-y-2">
            {avg.shares.map((s) => (
              <li key={s.candidate}>
                <div className="flex justify-between text-[0.875rem]"><span>{s.candidate}</span><span className="kbd">{s.share.toFixed(1)}%</span></div>
                <div className="mt-1 h-2 rounded-full bg-white/[0.06]"><div className="h-2 rounded-full" style={{ width: `${s.share}%`, background: colour(s.candidate) }} /></div>
              </li>
            ))}
          </ul>
        </div>
      ) : <p className="mt-3 text-[0.875rem] text-[color:var(--muted)]">No polls entered in the last {avg.window_days} days.</p>}
      {data.polls.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-[0.8125rem]">
            <thead className="text-[color:var(--dim)]"><tr><th className="py-2 pr-3 font-normal">Pollster</th><th className="py-2 pr-3 font-normal">Fieldwork</th><th className="py-2 pr-3 font-normal">Sample</th><th className="py-2 font-normal">Shares</th></tr></thead>
            <tbody className="divide-y divide-white/[0.07] border-t hairline">
              {data.polls.map((p) => (
                <tr key={p.id}>
                  <td className="py-2 pr-3"><a href={p.source} target="_blank" rel="noopener noreferrer" className="underline">{p.pollster}</a>{p.method ? <span className="text-[color:var(--dim)]"> · {p.method}</span> : null}</td>
                  <td className="kbd py-2 pr-3">{p.fieldwork_start} to {p.fieldwork_end}</td>
                  <td className="kbd py-2 pr-3">{p.sample.toLocaleString("en-GB")}</td>
                  <td className="py-2">{Object.entries(p.shares).sort((a, b) => b[1] - a[1]).map(([n, v]) => `${n.split(" ").slice(-1)[0]} ${v}%`).join(" · ")}{p.undecided ? ` · undecided ${p.undecided}%` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.recent_poll_stories.length > 0 && (
        <div className="mt-4">
          <p className="text-[0.8125rem] text-[color:var(--muted)]">Poll stories in the news, last 30 days</p>
          <ul className="mt-1 space-y-1 text-[0.8125rem]">
            {data.recent_poll_stories.slice(0, 8).map((s) => (
              <li key={s.url ?? s.title}>{s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="underline">{s.title}</a> : s.title}
                <span className="text-[color:var(--dim)]"> · {(s.outlets ?? []).join(", ")} · {s.day}</span></li>
            ))}
          </ul>
        </div>
      )}
      {data.operator && <PollForm election={election} ballot={ballot} onSaved={load} />}
    </section>
  );
}

function PollForm({ election, ballot, onSaved }: { election: string; ballot: { name: string; party: string | null }[]; onSaved: () => void }) {
  const [f, setF] = useState({ pollster: "", fieldwork_start: "", fieldwork_end: "", sample: "", method: "", source: "", undecided: "" });
  const [shares, setShares] = useState<Record<string, string>>({});
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const top = ballot.slice(0, 6);

  async function submit(e: FormEvent) {
    e.preventDefault(); setNote(null);
    try {
      await post(`/api/elections/polls?election=${election}`, {
        ...f, sample: Number(f.sample), method: f.method || null, undecided: f.undecided ? Number(f.undecided) : null,
        shares: Object.fromEntries(Object.entries(shares).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)])),
      });
      setNote({ ok: true, text: "Poll saved." }); onSaved();
    } catch (err) { setNote({ ok: false, text: err instanceof ApiError ? err.message : "The poll could not be saved." }); }
  }
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <form onSubmit={submit} className="panel mt-6 space-y-3 p-5">
      <h3 className="h3">Enter a poll (operators)</h3>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Pollster"><input value={f.pollster} onChange={set("pollster")} required className="field" /></Field>
        <Field label="Fieldwork start"><input type="date" value={f.fieldwork_start} onChange={set("fieldwork_start")} required className="field" /></Field>
        <Field label="Fieldwork end"><input type="date" value={f.fieldwork_end} onChange={set("fieldwork_end")} required className="field" /></Field>
        <Field label="Sample"><input inputMode="numeric" value={f.sample} onChange={set("sample")} required className="field kbd" /></Field>
        <Field label="Method (optional)"><input value={f.method} onChange={set("method")} placeholder="Phone, face to face…" className="field" /></Field>
        <Field label="Undecided % (optional)"><input inputMode="decimal" value={f.undecided} onChange={set("undecided")} className="field kbd" /></Field>
        {top.map((c) => (
          <Field key={c.name} label={`${c.name} %`}>
            <input inputMode="decimal" value={shares[c.name] ?? ""} onChange={(e) => setShares({ ...shares, [c.name]: e.target.value })} className="field kbd" />
          </Field>
        ))}
      </div>
      <Field label="Source link"><input value={f.source} onChange={set("source")} required placeholder="https://" className="field" /></Field>
      <button type="submit" className="btn btn-primary">Save poll</button>
      {note && <p role="status" className={`text-[0.8125rem] ${note.ok ? "text-verified" : "text-risk"}`}>{note.text}</p>}
    </form>
  );
}
