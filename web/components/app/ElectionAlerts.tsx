"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError } from "../../lib/api";
import { INCIDENT_TYPES, NG_STATES } from "../../lib/elections";
import { del, get, post } from "../../lib/market";
import { DESTINATION_LABEL, webhookDestination } from "../../lib/webhooks";
import { Chip, Segmented } from "./Chip";
import { ProBadge } from "./PlanLinks";
import { ErrorNote, Field } from "./ui";

type Alert = { id: string; name: string; filters: Record<string, unknown>; destination: string; webhook: string | null; email?: boolean; active?: boolean; sent?: number; created_at?: string };
type ElectionInfo = { key: string; country: string; label: string; dates: { date: string; name: string }[]; body: string; region_word: string; regions: string[]; coverage: string[] };
type State = { alerts: Alert[]; allowance: number; plan: string; full_features: boolean; elections: Record<string, string>; election_details?: ElectionInfo[] };
type TestResult = { delivered: boolean; destination?: string; error?: string | null };

// Elections with live results (src/data/live_elections.py SPECS).
const LIVE_RESULTS = ["gm-2026", "ng-2027"];

const NIGERIA: ElectionInfo = {
  key: "ng-2027", country: "Nigeria", label: "Nigeria: 2027 general elections", dates: [], body: "INEC",
  region_word: "State", regions: NG_STATES, coverage: [],
};

function regionWord(e: ElectionInfo, plural = false): string {
  const w = e.region_word.toLowerCase();
  return plural ? (w.endsWith("y") ? `${w.slice(0, -1)}ies` : `${w}s`) : w;
}

function nextDate(e: ElectionInfo): string | null {
  const today = new Date().toISOString().slice(0, 10);
  const d = e.dates.find((x) => x.date >= today);
  return d ? new Date(`${d.date}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : null;
}

function summary(f: Record<string, unknown>, info: (key: string) => ElectionInfo): string {
  const e = info(String(f.election ?? "ng-2027"));
  const bits: string[] = [e.country];
  bits.push(f.kind === "news" ? "All election coverage" : f.kind === "results" ? "Each result as it is declared"
    : `Incidents${f.min_severity ? `, ${f.min_severity} severity and above` : ""}`);
  const states = (f.states as string[] | undefined) ?? [];
  bits.push(states.length ? states.join(", ") : `all ${regionWord(e, true)}`);
  const types = (f.incident_types as string[] | undefined) ?? [];
  if (types.length) bits.push(types.map((t) => INCIDENT_TYPES.find(([k]) => k === t)?.[1] ?? t).join(", "));
  return bits.join(" · ");
}

/** Create, test and remove election alerts from the Alerts page (signed-in account; allowance from the plan). */
export function ElectionAlerts() {
  const [data, setData] = useState<State | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [election, setElection] = useState("ng-2027");
  const [kind, setKind] = useState<"incidents" | "news" | "results">("incidents");
  const [severity, setSeverity] = useState("medium");
  const [states, setStates] = useState<string[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [webhook, setWebhook] = useState("");
  const [starter, setStarter] = useState(false);
  const [emailMe, setEmailMe] = useState(true);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await get<State>("/api/elections/alerts"));
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Election alerts could not be loaded.");
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const details = data?.election_details ?? [];
  const info = (key: string): ElectionInfo => details.find((e) => e.key === key) ?? (key === "ng-2027" ? NIGERIA : { ...NIGERIA, key, country: data?.elections[key]?.split(":")[0] ?? key, label: data?.elections[key] ?? key, regions: [] });
  const current = info(election);
  const technologyLabel = election === "ng-2027" ? "BVAS or IReV failure" : "Election technology failure";
  const destination = webhookDestination(webhook);
  const full = !!data?.full_features;
  const atLimit = !!data && data.alerts.length >= data.allowance;

  function testText(r: TestResult): { ok: boolean; text: string } {
    return r.delivered
      ? { ok: true, text: `Test message sent to ${r.destination ?? "your webhook"}. Check the channel.` }
      : { ok: false, text: `The webhook did not accept the message${r.error ? ` (${r.error})` : ""}. Check the URL.` };
  }

  async function testNew() {
    setTesting("new"); setNote(null);
    try {
      setNote(testText(await post<TestResult>("/api/elections/alerts/test", { webhook_url: webhook.trim(), name: name.trim() || "Election alert" })));
    } catch (e) {
      setNote({ ok: false, text: e instanceof ApiError ? e.message : "The test could not be sent." });
    } finally { setTesting(null); }
  }

  async function testSaved(id: string) {
    setTesting(id); setNote(null);
    try { setNote(testText(await post<TestResult>(`/api/elections/alerts/${id}/test`))); }
    catch (e) { setNote({ ok: false, text: e instanceof ApiError ? e.message : "The test could not be sent." }); }
    finally { setTesting(null); }
  }

  async function setActive(id: string, active: boolean) {
    try { await post(`/api/elections/alerts/${id}/active`, { active }); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "The alert could not be updated."); }
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this election alert? Messages to its channel will stop.")) return;
    try { await del(`/api/elections/alerts/${id}`); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "The alert could not be deleted."); }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setNote(null);
    const filters: Record<string, unknown> = { election, kind };
    if (kind === "incidents") filters.min_severity = severity;
    if (states.length) filters.states = states;
    if (kind === "incidents" && types.length) filters.incident_types = types;
    try {
      const r = await post<Alert & { backfill?: { sent: number } }>("/api/elections/alerts", {
        name: name.trim() || "Election alert", webhook_url: webhook.trim() || null, email: emailMe, filters,
        backfill_days: starter && full ? 7 : 0,
      });
      setNote({ ok: true, text: r.backfill ? `Alert created. ${r.backfill.sent} recent incident${r.backfill.sent === 1 ? "" : "s"} sent to start.` : "Alert created. New matching incidents will arrive within the hour." });
      setName(""); setWebhook(""); setStates([]); setTypes([]); setStarter(false); setEmailMe(true); setOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The alert could not be created.");
    } finally { setBusy(false); }
  }

  if (loadError) return <p className="mt-4 text-sm text-[color:var(--muted)]">{loadError}</p>;
  if (!data) return <p className="mt-4 text-sm text-[color:var(--dim)]">Loading your election alerts…</p>;
  if (data.allowance === 0) {
    return (
      <div className="panel mt-6 flex flex-wrap items-center justify-between gap-3 p-5">
        <p className="text-[0.875rem] text-[color:var(--muted)]">Election alerts start with the Pro plan.</p>
        <ProBadge source="election_alerts" />
      </div>
    );
  }

  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const regionsLabel = current.region_word === "County" ? "Counties" : `${current.region_word}s`;
  const planName = data.plan.charAt(0).toUpperCase() + data.plan.slice(1);

  return (
    <div className="mt-6">
      {!open && (
        <div className="flex items-center justify-between gap-3">
          <p className="text-[0.875rem] text-[color:var(--muted)]">
            {data.alerts.length} of {data.allowance} in use <span className="text-[color:var(--dim)]">· {planName}</span>
          </p>
          {atLimit ? (
            <span className="inline-flex items-center gap-1 text-[0.8125rem] text-[color:var(--muted)]">All in use<ProBadge source="election_alerts_limit" /></span>
          ) : (
            <button type="button" onClick={() => { setOpen(true); setNote(null); }} className="btn btn-primary shrink-0">New election alert</button>
          )}
        </div>
      )}

      {!open && data.alerts.length === 0 && (
        <p className="mt-6 rounded-lg border border-dashed hairline p-6 text-center text-[0.875rem] text-[color:var(--muted)]">
          No election alerts yet. Pick a country, the places and the kind of incident, and where to send it.
        </p>
      )}

      {!open && data.alerts.length > 0 && (
        <ul className="mt-4 divide-y divide-white/[0.07] border-y hairline">
          {data.alerts.map((a) => (
            <li key={a.id} className="flex flex-col gap-2 py-3.5 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-[0.9375rem] text-[color:var(--text)]">
                  <span className={`h-1.5 w-1.5 rounded-full ${a.active === false ? "bg-[color:var(--dim)]" : "bg-[color:var(--verified,#6ee7c8)]"}`} />
                  {a.name}{a.active === false && <span className="text-[0.75rem] text-[color:var(--dim)]">Paused</span>}
                </p>
                <p className="mt-0.5 text-[0.8125rem] text-[color:var(--muted)]">{summary(a.filters, info)}</p>
                <p className="text-[0.75rem] text-[color:var(--dim)]">{a.destination} · {a.sent ?? 0} sent</p>
              </div>
              <div className="flex shrink-0 gap-4 text-[0.8125rem]">
                <button type="button" onClick={() => testSaved(a.id)} disabled={testing === a.id} className="text-[color:var(--muted)] hover:text-[color:var(--text)]">
                  {testing === a.id ? "Sending…" : "Send test"}
                </button>
                {a.active === false && (
                  <button type="button" onClick={() => setActive(a.id, true)} className="text-[color:var(--muted)] hover:text-[color:var(--text)]">Resume</button>
                )}
                <button type="button" onClick={() => remove(a.id)} className="text-[color:var(--muted)] hover:text-risk">Delete</button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {open && (
        <form onSubmit={submit} className="panel divide-y divide-white/[0.07]">
          <div className="flex items-center justify-between gap-3 p-5">
            <h3 className="h3">New election alert</h3>
            <button type="button" onClick={() => setOpen(false)} className="text-[0.8125rem] text-[color:var(--muted)] hover:text-[color:var(--text)]">Cancel</button>
          </div>

          <div className="grid gap-5 p-5 md:grid-cols-[13rem_1fr]">
            <div>
              <h4 className="text-[0.9375rem] text-[color:var(--text)]">What to follow</h4>
              <p className="mt-1 text-[0.8125rem] text-[color:var(--dim)]">An election, what to send, and where. Leave places and types empty for all of them.</p>
            </div>
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Election">
                  <select value={election} onChange={(e) => { setElection(e.target.value); setStates([]); if (!LIVE_RESULTS.includes(e.target.value) && kind === "results") setKind("incidents"); }} className="field">
                    {(details.length ? details : Object.keys(data.elections).map(info)).map((e) => {
                      const next = nextDate(e);
                      return <option key={e.key} value={e.key}>{e.country}{next ? ` · ${next}` : ""}</option>;
                    })}
                  </select>
                </Field>
                <Field label="Name">
                  <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder={`${current.country} incidents`} className="field" />
                </Field>
              </div>
              <div>
                <p className="mb-2 text-[0.8125rem] text-[color:var(--muted)]">Send</p>
                <Segmented label="Send" value={kind} onChange={(v) => setKind(v)}
                           options={[["incidents", "Incidents"], ...(full ? [["news", "All coverage"] as ["news", string]] : []),
                                     ...(LIVE_RESULTS.includes(election) ? [["results", "Results"] as ["results", string]] : [])]} />
                {!full && <p className="mt-1.5 text-[0.75rem] text-[color:var(--dim)]">All coverage comes with Team and above.</p>}
              </div>
              {kind === "incidents" && (
                <div>
                  <p className="mb-2 text-[0.8125rem] text-[color:var(--muted)]">Severity</p>
                  <Segmented label="Minimum severity" value={severity as "high" | "medium" | "low"} onChange={setSeverity}
                             options={[["high", "High only"], ["medium", "Medium and high"], ["low", "All"]]} />
                </div>
              )}
              <div>
                <p className="mb-2 text-[0.8125rem] text-[color:var(--muted)]">{regionsLabel}</p>
                <div className="flex max-h-44 flex-wrap gap-1.5 overflow-y-auto">
                  {current.regions.map((r) => <Chip key={r} on={states.includes(r)} onClick={() => toggle(states, setStates, r)}>{r}</Chip>)}
                </div>
              </div>
              {kind === "incidents" && (
                <div>
                  <p className="mb-2 text-[0.8125rem] text-[color:var(--muted)]">Incident types</p>
                  <div className="flex flex-wrap gap-1.5">
                    {INCIDENT_TYPES.map(([k, label]) => (
                      <Chip key={k} on={types.includes(k)} onClick={() => toggle(types, setTypes, k)}>{k === "technology_failure" ? technologyLabel : label}</Chip>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="grid gap-5 p-5 md:grid-cols-[13rem_1fr]">
            <div>
              <h4 className="text-[0.9375rem] text-[color:var(--text)]">Where to send it</h4>
              <p className="mt-1 text-[0.8125rem] text-[color:var(--dim)]">At most one email an hour, with an unsubscribe link. Channels get one message per incident.</p>
            </div>
            <div className="space-y-4">
              <label className="flex items-center gap-2.5 text-[0.875rem] text-[color:var(--muted)]">
                <input type="checkbox" checked={emailMe} onChange={(e) => setEmailMe(e.target.checked)} className="h-4 w-4 accent-verified" />
                Email me
              </label>
              <Field label="Channel webhook (optional)">
                <div className="flex flex-col gap-2 sm:flex-row">
                  <input value={webhook} onChange={(e) => { setWebhook(e.target.value); setNote(null); }} placeholder="https://hooks.slack.com/…" className="field kbd" />
                  <button type="button" onClick={testNew} disabled={!destination || testing === "new"} className="btn btn-ghost shrink-0">
                    {testing === "new" ? "Sending…" : "Send test"}
                  </button>
                </div>
                <p className="mt-1.5 text-[0.75rem] text-[color:var(--dim)]">
                  {destination
                    ? <>Formatted for <span className="text-[color:var(--text)]">{DESTINATION_LABEL[destination]}</span>.</>
                    : <Link href="/developers#chat" className="underline">How to get a webhook URL</Link>}
                </p>
              </Field>
              {full && (
                <label className="flex items-center gap-2.5 text-[0.875rem] text-[color:var(--muted)]">
                  <input type="checkbox" checked={starter} onChange={(e) => setStarter(e.target.checked)} className="h-4 w-4 accent-verified" />
                  Start with the last 7 days
                </label>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 p-5">
            <button type="submit" disabled={busy || (!destination && !emailMe) || (!!webhook.trim() && !destination)} className="btn btn-primary">{busy ? "Creating…" : "Create alert"}</button>
            {error && <ErrorNote message={error} />}
          </div>
        </form>
      )}
      {note && <p role="status" className={`mt-3 text-[0.8125rem] ${note.ok ? "text-verified" : "text-risk"}`}>{note.text}</p>}
    </div>
  );
}
