"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError } from "../../lib/api";
import { INCIDENT_TYPES, NG_STATES } from "../../lib/elections";
import { del, get, post } from "../../lib/market";
import { DESTINATION_LABEL, webhookDestination } from "../../lib/webhooks";
import { ProBadge } from "./PlanLinks";
import { ErrorNote, Field } from "./ui";

type Alert = { id: string; name: string; filters: Record<string, unknown>; destination: string; webhook: string | null; email?: boolean; active?: boolean; sent?: number; created_at?: string };
type ElectionInfo = { key: string; country: string; label: string; dates: { date: string; name: string }[]; body: string; region_word: string; regions: string[]; coverage: string[] };
type State = { alerts: Alert[]; allowance: number; plan: string; full_features: boolean; elections: Record<string, string>; election_details?: ElectionInfo[] };
type TestResult = { delivered: boolean; destination?: string; error?: string | null };

// Elections with live results (src/election_live.py ELECTIONS).
const LIVE_RESULTS = "gm-2026";

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
      setName(""); setWebhook(""); setStates([]); setTypes([]); setStarter(false); setEmailMe(true);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The alert could not be created.");
    } finally { setBusy(false); }
  }

  if (loadError) return <p className="mt-4 text-sm text-[color:var(--muted)]">{loadError}</p>;
  if (!data) return <p className="mt-4 text-sm text-[color:var(--dim)]">Loading your election alerts…</p>;
  if (data.allowance === 0) {
    return (
      <p className="mt-4 inline-flex flex-wrap items-center gap-1 text-sm text-[color:var(--muted)]">
        Election alerts start with the Pro plan<ProBadge source="election_alerts" />
      </p>
    );
  }

  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const chip = "flex items-center gap-1.5 rounded-full border hairline px-2.5 py-1 text-[0.75rem] cursor-pointer";

  return (
    <div className="mt-5">
      <p className="text-[0.8125rem] text-[color:var(--dim)]">
        {data.alerts.length} of {data.allowance} election alert{data.allowance === 1 ? "" : "s"} in use on your {data.plan.charAt(0).toUpperCase() + data.plan.slice(1)} plan.
      </p>

      {data.alerts.length > 0 && (
        <ul className="mt-3 divide-y divide-white/[0.07] border-y hairline">
          {data.alerts.map((a) => (
            <li key={a.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-[0.875rem] text-[color:var(--text)]">{a.name}</p>
                <p className="text-[0.75rem] text-[color:var(--muted)]">{summary(a.filters, info)}</p>
                <p className="text-[0.75rem] text-[color:var(--dim)]">
                  {a.destination} · {a.sent ?? 0} sent{a.active === false ? " · Paused" : ""}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <button type="button" onClick={() => testSaved(a.id)} disabled={testing === a.id} className="btn btn-ghost text-[0.8125rem]">
                  {testing === a.id ? "Sending…" : "Send test"}
                </button>
                {a.active === false && (
                  <button type="button" onClick={() => setActive(a.id, true)} className="btn btn-ghost text-[0.8125rem]">Resume</button>
                )}
                <button type="button" onClick={() => remove(a.id)} className="btn btn-ghost text-[0.8125rem]">Delete</button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {atLimit ? (
        <p className="mt-4 inline-flex flex-wrap items-center gap-1 text-sm text-[color:var(--muted)]">
          All {data.allowance} election alerts on your plan are in use. Delete one, or upgrade for more<ProBadge source="election_alerts_limit" />
        </p>
      ) : (
        <form onSubmit={submit} className="mt-5 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name">
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder={`${current.country} incidents`} className="field" />
            </Field>
            <Field label="Country and election">
              <select value={election} onChange={(e) => { setElection(e.target.value); setStates([]); if (e.target.value !== LIVE_RESULTS && kind === "results") setKind("incidents"); }} className="field">
                {(details.length ? details : Object.keys(data.elections).map(info)).map((e) => {
                  const next = nextDate(e);
                  return <option key={e.key} value={e.key}>{e.label}{next ? ` · next vote ${next}` : ""}</option>;
                })}
              </select>
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Send">
              <select value={kind} onChange={(e) => setKind(e.target.value as "incidents" | "news" | "results")} className="field">
                <option value="incidents">Incidents</option>
                <option value="news" disabled={!full}>All election coverage{full ? "" : " (Team and above)"}</option>
                {election === LIVE_RESULTS && <option value="results">Results, each constituency as it is declared</option>}
              </select>
            </Field>
            {kind === "incidents" && (
              <Field label="Minimum severity">
                <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="field">
                  <option value="high">High only (deaths, gunfire, arson, abductions)</option>
                  <option value="medium">Medium and high (attacks, injuries, ballot snatching)</option>
                  <option value="low">All incidents</option>
                </select>
              </Field>
            )}
          </div>
          <fieldset>
            <legend className="mb-2 text-[0.8125rem] text-[color:var(--muted)]">
              {current.region_word === "County" ? "Counties" : `${current.region_word}s`} (none selected = all of {current.country})
            </legend>
            <div className="flex flex-wrap gap-1.5">
              {current.regions.map((s) => (
                <label key={s} className={chip}>
                  <input type="checkbox" checked={states.includes(s)} onChange={() => toggle(states, setStates, s)} className="accent-verified" />{s}
                </label>
              ))}
            </div>
          </fieldset>
          {kind === "incidents" && (
            <fieldset>
              <legend className="mb-2 text-[0.8125rem] text-[color:var(--muted)]">Incident types (none selected = all)</legend>
              <div className="flex flex-wrap gap-1.5">
                {INCIDENT_TYPES.map(([k, label]) => (
                  <label key={k} className={chip}>
                    <input type="checkbox" checked={types.includes(k)} onChange={() => toggle(types, setTypes, k)} className="accent-verified" />{k === "technology_failure" ? technologyLabel : label}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <label className="flex items-center gap-3 text-[0.875rem] text-[color:var(--muted)]">
            <input type="checkbox" checked={emailMe} onChange={(e) => setEmailMe(e.target.checked)} className="h-4 w-4 accent-verified" />
            Email me (to your account&apos;s confirmed address, at most one email an hour, with an unsubscribe link)
          </label>
          <Field label="And/or send to Slack, Teams, Discord, Google Chat or any webhook (optional)">
            <div className="flex flex-col gap-2 sm:flex-row">
              <input value={webhook} onChange={(e) => { setWebhook(e.target.value); setNote(null); }} placeholder="Paste the channel's webhook URL" className="field kbd" />
              <button type="button" onClick={testNew} disabled={!destination || testing === "new"} className="btn btn-ghost shrink-0">
                {testing === "new" ? "Sending…" : "Send test message"}
              </button>
            </div>
            <p className="mt-2 text-[0.8125rem] text-[color:var(--dim)]">
              {destination
                ? <>Alerts will arrive formatted for <span className="text-[color:var(--text)]">{DESTINATION_LABEL[destination]}</span>.</>
                : <>Formatted for the tool automatically. <Link href="/developers#chat" className="underline">How to get a webhook URL</Link>.</>}
            </p>
          </Field>
          <label className={`flex items-center gap-3 text-[0.875rem] ${full ? "text-[color:var(--muted)]" : "text-[color:var(--dim)]"}`}>
            <input type="checkbox" checked={starter} disabled={!full} onChange={(e) => setStarter(e.target.checked)} className="h-4 w-4 accent-verified" />
            Start with matching incidents from the last 7 days{full ? "" : " (Team and above)"}
          </label>
          <button type="submit" disabled={busy || (!destination && !emailMe) || (!!webhook.trim() && !destination)} className="btn btn-primary">{busy ? "Creating…" : "Create election alert"}</button>
          {error && <ErrorNote message={error} />}
        </form>
      )}
      {note && <p role="status" className={`mt-3 text-[0.8125rem] ${note.ok ? "text-verified" : "text-risk"}`}>{note.text}</p>}
    </div>
  );
}
