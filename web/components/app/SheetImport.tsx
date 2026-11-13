"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError } from "../../lib/api";
import { get, post } from "../../lib/market";
import { Field } from "./ui";

type Queue = { by_status: Record<string, number>; failed: { pu_code: string; error: string | null }[]; daily_reads: number };
type Result = { queued: number; duplicates: number; refused: { row: number; reason: string }[]; refused_total: number };

const ELECTIONS: [string, string][] = [
  ["presidential-2027", "Presidential"], ["senate-2027", "Senate"], ["reps-2027", "House of Representatives"],
  ["governorship-2027", "Governorship"], ["state-assembly-2027", "State House of Assembly"],
];

/** Parse pasted lines: "code, link" or "code, link, priority" (commas or tabs, a header line is skipped). */
function parse(text: string): { pu_code: string; image_url: string; priority?: number }[] {
  return text.split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !/^pu[_ ]?code/i.test(l)).map((l) => {
    const [code, url, prio] = l.split(/[\t,]\s*/);
    return { pu_code: (code ?? "").trim(), image_url: (url ?? "").trim(), ...(prio ? { priority: Number(prio) } : {}) };
  });
}

/** Bulk import of polling-unit result sheets (IReV downloads or your own collection) into the reading queue. */
export function SheetImport() {
  const [election, setElection] = useState("presidential-2027");
  const [text, setText] = useState("");
  const [queue, setQueue] = useState<Queue | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setQueue(await get<Queue>("/api/elections/results/queue", { election })); }
    catch (e) { setError(e instanceof ApiError ? e.message : "The queue could not be loaded."); }
  }, [election]);
  useEffect(() => { void load(); }, [load]);
  const rows = parse(text);

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null); setResult(null);
    try { setResult(await post<Result>("/api/elections/results/import", { election, sheets: rows })); setText(""); await load(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "The sheets could not be queued."); }
    finally { setBusy(false); }
  }

  const s = queue?.by_status ?? {};
  return (
    <section id="sheet-import">
      <h2 className="h3">Import result sheets</h2>
      <p className="mt-1 max-w-3xl text-[0.8125rem] text-[color:var(--dim)]">
        Paste polling-unit sheet links, from IReV downloads or your own collection, one per line: the polling-unit code,
        the https link to the image and, optionally, a priority (higher is read first). Up to 2,000 at a time. They are
        read every hour, up to {queue?.daily_reads ?? 400} a day, through the same reading and checks as a single upload,
        and count in your results totals. Sheets are kept to your account.
      </p>
      {queue && (
        <p className="kbd mt-3 text-[0.8125rem] text-[color:var(--muted)]">
          Queued {s.queued ?? 0} · reading {s.reading ?? 0} · read {s.read ?? 0} · failed {s.failed ?? 0}
        </p>
      )}
      <form onSubmit={submit} className="panel mt-3 space-y-3 p-5">
        <Field label="Election">
          <select value={election} onChange={(e) => setElection(e.target.value)} className="field">
            {ELECTIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </Field>
        <Field label="Sheets (code, link, priority)">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} className="field kbd min-h-[9rem]"
                    placeholder={"24/11/01/001, https://example.org/sheets/24-11-01-001.jpg, 5\n24/11/01/002, https://example.org/sheets/24-11-01-002.jpg"} />
        </Field>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={busy || rows.length === 0 || rows.length > 2000} className="btn btn-primary">
            {busy ? "Queuing…" : `Queue ${rows.length || ""} sheet${rows.length === 1 ? "" : "s"}`}
          </button>
          {rows.length > 2000 && <span className="text-[0.8125rem] text-risk">At most 2,000 at a time.</span>}
        </div>
        {result && (
          <p role="status" className="text-[0.8125rem] text-verified">
            {result.queued} queued{result.duplicates ? `, ${result.duplicates} already in the queue` : ""}{result.refused_total ? `, ${result.refused_total} refused` : ""}.
          </p>
        )}
        {result?.refused.length ? (
          <ul className="text-[0.75rem] text-risk">{result.refused.slice(0, 8).map((r) => <li key={r.row}>Line {r.row + 1}: {r.reason}</li>)}</ul>
        ) : null}
        {error && <p role="alert" className="text-[0.8125rem] text-risk">{error}</p>}
      </form>
      {queue?.failed.length ? (
        <div className="mt-3">
          <p className="text-[0.8125rem] text-[color:var(--muted)]">Latest failures</p>
          <ul className="mt-1 text-[0.75rem] text-[color:var(--dim)]">{queue.failed.slice(0, 10).map((f, i) => <li key={i}><span className="kbd">{f.pu_code}</span>: {f.error}</li>)}</ul>
        </div>
      ) : null}
    </section>
  );
}
