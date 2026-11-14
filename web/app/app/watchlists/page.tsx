"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { ProBadge } from "../../../components/app/PlanLinks";
import { ElectionAlerts } from "../../../components/app/ElectionAlerts";
import { UPCOMING_AFRICA } from "../../../lib/elections";
import { usePlan } from "../../../lib/plan";
import { RequestForm } from "../../../components/app/RequestForm";
import { Container } from "../../../components/primitives";
import { Chip, Segmented } from "../../../components/app/Chip";
import { ErrorNote, Field, words } from "../../../components/app/ui";
import { ApiError } from "../../../lib/api";
import { SIGNAL_TYPES, post } from "../../../lib/market";
import { DESTINATION_LABEL, webhookDestination } from "../../../lib/webhooks";

const KEY = "deal-intel:watchlists";
type Saved = { id: string; name: string; created_at: string };

function readSaved(): Saved[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

function writeSaved(rows: Saved[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(rows));
  } catch {
    /* storage unavailable: the link still works */
  }
}

export default function WatchlistsPage() {
  const plan = usePlan();
  // Free accounts keep a few alerts; the label appears once they are all in use.
  const alertsLocked = plan !== null && plan.alerts_used >= plan.alerts_max;
  const [saved, setSaved] = useState<Saved[]>([]);
  const [name, setName] = useState("");
  const [companies, setCompanies] = useState("");
  const [countries, setCountries] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [deals, setDeals] = useState(true);
  const [emailMe, setEmailMe] = useState(true);
  const [webhook, setWebhook] = useState("");
  const [frequency, setFrequency] = useState<"daily" | "weekly">("daily");
  const [testing, setTesting] = useState(false);
  const [testNote, setTestNote] = useState<{ ok: boolean; text: string } | null>(null);
  const destination = webhookDestination(webhook);

  async function sendTest() {
    setTesting(true);
    setTestNote(null);
    try {
      const r = await post<{ delivered: boolean; label: string; status_code: number | null; error: string | null }>(
        "/api/webhooks/test", { url: webhook.trim(), name: name.trim() || "Your watchlist" });
      setTestNote(r.delivered
        ? { ok: true, text: `Test message sent to ${r.label}. Check the channel.` }
        : { ok: false, text: `${r.label} did not accept the message${r.status_code ? ` (HTTP ${r.status_code})` : ""}. Check the URL and that the webhook is still active.` });
    } catch (err) {
      setTestNote({ ok: false, text: err instanceof ApiError ? err.message : "The test message could not be sent." });
    } finally {
      setTesting(false);
    }
  }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prefillNotice, setPrefillNotice] = useState<string | null>(null);
  const [tab, setTab] = useState<"watchlists" | "elections">("watchlists");
  const [formOpen, setFormOpen] = useState(false);
  // The tab follows the address (#elections), so links from the results pages open the right one.
  const pick = (k: "watchlists" | "elections") => {
    setTab(k);
    try { window.history.replaceState(null, "", k === "elections" ? "#elections" : window.location.pathname + window.location.search); } catch { /* ignore */ }
  };

  useEffect(() => {
    const rows = readSaved();
    setSaved(rows);
    if (/^#(elections|election-alerts-title)$/.test(window.location.hash)) setTab("elections");
    if (rows.length === 0 && !/^#elections/.test(window.location.hash)) setFormOpen(true);
    const params = new URLSearchParams(window.location.search);
    const follow = params.get("follow");
    if (follow) {
      // "Follow this investor" from a profile: a local draft, sent only if the form is submitted.
      setFormOpen(true);
      setName(`Deals involving ${follow}`);
      setCompanies(follow);
      setPrefillNotice(`${follow} was added to this draft. Alerts cover every deal it takes part in, under any of its known names.`);
      return;
    }
    if (params.get("from") !== "portfolio") return;
    try {
      const raw = window.sessionStorage.getItem("deal-intelligence:portfolio-watchlist-prefill");
      if (!raw) return;
      const parsed = JSON.parse(raw) as { name?: unknown; companies?: unknown };
      setFormOpen(true);
      if (typeof parsed.name === "string") setName(parsed.name);
      if (Array.isArray(parsed.companies)) {
        const names = parsed.companies.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
        setCompanies(names.join("\n"));
        if (names.length) setPrefillNotice("Portfolio holdings were copied into this draft locally. They are sent to the watchlist service only if you submit this form.");
      }
      window.sessionStorage.removeItem("deal-intelligence:portfolio-watchlist-prefill");
    } catch {
      setError("The portfolio watchlist draft could not be loaded. You can enter company names manually.");
    }
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const webhookValue = webhook.trim();
    if (webhookValue) {
      try {
        const parsedWebhook = new URL(webhookValue);
        if (parsedWebhook.protocol !== "https:" || !parsedWebhook.hostname) {
          setError("Webhook URL must use HTTPS.");
          return;
        }
      } catch {
        setError("Enter a valid HTTPS webhook URL.");
        return;
      }
    }
    setBusy(true);
    setError(null);
    try {
      const split = (s: string) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);
      const r = await post<{ id: string }>("/api/watchlists", {
        name: name.trim() || "Watchlist",
        companies: split(companies),
        countries: split(countries).map((c) => c.toUpperCase()),
        signal_types: types,
        include_deals: deals,
        webhook_url: webhook.trim() || null,
        delivery_frequency: frequency,
      });
      const rows = [{ id: r.id, name: name.trim() || "Watchlist", created_at: new Date().toISOString() }, ...readSaved()];
      writeSaved(rows);
      if (emailMe) {
        // Email goes only to the account's confirmed address; if it is not confirmed, the watchlist page says so.
        await fetch(`/api/watchlists/${encodeURIComponent(r.id)}/email`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: true }),
        }).catch(() => undefined);
      }
      window.location.href = `/watchlists/${r.id}`;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The watchlist could not be created.");
      setBusy(false);
    }
  }

  const live = UPCOMING_AFRICA.filter((e) => e.date >= new Date().toISOString().slice(0, 10));
  const dateLabel = (e: (typeof UPCOMING_AFRICA)[number]) => e.label.replace(/ \(expected\)$/, "");

  return (
    <Container className="max-w-5xl py-10 lg:py-14">
      <header className="mb-6">
        <h1 className="h2 text-[1.75rem] sm:text-[2rem]">Alerts</h1>
        <p className="mt-2 text-[0.9375rem] text-[color:var(--muted)]">Hear about what you follow as it happens, by email or in your team&apos;s channel.</p>
      </header>

      <div role="tablist" aria-label="Alert type" className="mb-8 flex gap-6 border-b hairline">
        {([["watchlists", "Watchlists", saved.length], ["elections", "Elections", null]] as const).map(([k, label, n]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => pick(k)}
                  className={`-mb-px border-b-2 pb-2.5 text-[0.9375rem] transition-colors ${
                    tab === k ? "border-[color:var(--text)] text-[color:var(--text)]" : "border-transparent text-[color:var(--muted)] hover:text-[color:var(--text)]"}`}>
            {label}{n ? <span className="ml-1.5 text-[color:var(--dim)]">{n}</span> : null}
          </button>
        ))}
      </div>

      {tab === "watchlists" && (
        <section aria-label="Watchlists">
          {prefillNotice && <p className="mb-4 rounded-lg border hairline p-3 text-sm leading-relaxed text-[color:var(--muted)]" role="status">{prefillNotice}</p>}

          {!formOpen && (
            <>
              <div className="flex items-center justify-between gap-3">
                <p className="text-[0.875rem] text-[color:var(--muted)]">
                  {saved.length ? `${saved.length} watchlist${saved.length === 1 ? "" : "s"}` : "Follow companies and countries: every deal and corporate event that involves them."}
                </p>
                <button type="button" onClick={() => setFormOpen(true)} className="btn btn-primary shrink-0">New watchlist</button>
              </div>
              {saved.length > 0 && (
                <ul className="mt-4 divide-y divide-white/[0.07] border-y hairline">
                  {saved.map((w) => (
                    <li key={w.id}>
                      <Link href={`/watchlists/${w.id}`} className="flex items-center justify-between gap-3 py-3 text-[0.9375rem] hover:text-[color:var(--text)]">
                        <span>{w.name}</span>
                        <span className="kbd text-[0.75rem] text-[color:var(--dim)]">{w.created_at.slice(0, 10)} →</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-4 text-[0.75rem] text-[color:var(--dim)]">Kept in this browser; a watchlist&apos;s link is its key, so bookmark it and keep it private.</p>
            </>
          )}

          {formOpen && (
            <form onSubmit={submit} className="panel divide-y divide-white/[0.07]">
              <div className="flex items-center justify-between gap-3 p-5">
                <h2 className="h3">New watchlist</h2>
                <button type="button" onClick={() => setFormOpen(false)} className="text-[0.8125rem] text-[color:var(--muted)] hover:text-[color:var(--text)]">Cancel</button>
              </div>

              <div className="grid gap-5 p-5 md:grid-cols-[13rem_1fr]">
                <div>
                  <h3 className="text-[0.9375rem] text-[color:var(--text)]">What to watch</h3>
                  <p className="mt-1 text-[0.8125rem] text-[color:var(--dim)]">Companies, countries, and the events that matter. Leave event types empty for all of them.</p>
                </div>
                <div className="space-y-4">
                  <Field label="Name">
                    <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="Nigerian banks" className="field" />
                  </Field>
                  <div className="grid gap-4 sm:grid-cols-[2fr_1fr]">
                    <Field label="Companies">
                      <textarea value={companies} onChange={(e) => setCompanies(e.target.value)} rows={2} placeholder="Access Holdings, Zenith Bank, Dangote" className="field" />
                    </Field>
                    <Field label="Countries">
                      <textarea value={countries} onChange={(e) => setCountries(e.target.value)} rows={2} placeholder="NG, GH" className="field kbd uppercase" />
                    </Field>
                  </div>
                  <div>
                    <p className="mb-2 text-[0.8125rem] text-[color:var(--muted)]">Events</p>
                    <div className="flex flex-wrap gap-1.5">
                      {SIGNAL_TYPES.map((t) => (
                        <Chip key={t} on={types.includes(t)} onClick={() => setTypes(types.includes(t) ? types.filter((x) => x !== t) : [...types, t])}>{words(t)}</Chip>
                      ))}
                    </div>
                  </div>
                  <label className="flex items-center gap-2.5 text-[0.875rem] text-[color:var(--muted)]">
                    <input type="checkbox" checked={deals} onChange={(e) => setDeals(e.target.checked)} className="h-4 w-4 accent-verified" />
                    Include their deals
                  </label>
                </div>
              </div>

              <div className="grid gap-5 p-5 md:grid-cols-[13rem_1fr]">
                <div>
                  <h3 className="text-[0.9375rem] text-[color:var(--text)]">Where to send it</h3>
                  <p className="mt-1 text-[0.8125rem] text-[color:var(--dim)]">Your email, a Slack, Teams, Discord or Google Chat channel, or both.</p>
                </div>
                <div className="space-y-4">
                  <label className="flex items-center gap-2.5 text-[0.875rem] text-[color:var(--muted)]">
                    <input type="checkbox" checked={emailMe} onChange={(e) => setEmailMe(e.target.checked)} className="h-4 w-4 accent-verified" />
                    Email me
                  </label>
                  <Field label="Channel webhook (optional)">
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <input value={webhook} onChange={(e) => { setWebhook(e.target.value); setTestNote(null); }}
                             placeholder="https://hooks.slack.com/…" className="field kbd" aria-describedby="webhook-help" />
                      <button type="button" onClick={sendTest} disabled={!destination || testing} className="btn btn-ghost shrink-0">
                        {testing ? "Sending…" : "Send test"}
                      </button>
                    </div>
                    <p id="webhook-help" className="mt-1.5 text-[0.75rem] text-[color:var(--dim)]">
                      {destination
                        ? <>Formatted for <span className="text-[color:var(--text)]">{DESTINATION_LABEL[destination]}</span>.</>
                        : <><Link href="/developers#chat" className="underline">How to get a webhook URL</Link></>}
                    </p>
                    {testNote && <p role="status" className={`mt-1 text-[0.8125rem] ${testNote.ok ? "text-verified" : "text-risk"}`}>{testNote.text}</p>}
                  </Field>
                  <div>
                    <p className="mb-2 text-[0.8125rem] text-[color:var(--muted)]">How often</p>
                    <Segmented label="How often" value={frequency} onChange={setFrequency}
                               options={[["daily", "Daily"], ["weekly", "Weekly, on Fridays"]]} />
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 p-5">
                <button type="submit" disabled={busy} className="btn btn-primary">{busy ? "Creating…" : "Create watchlist"}</button>
                {alertsLocked && (
                  <span className="inline-flex items-center text-sm text-[color:var(--muted)]">
                    {plan?.alerts_max ? `All ${plan.alerts_max} alerts on your plan are in use. Pro has 100` : "Watchlist alerts are part of Pro"}<ProBadge source="watchlist_create" />
                  </span>
                )}
                {error && <ErrorNote message={error} />}
              </div>
            </form>
          )}
        </section>
      )}

      {tab === "elections" && (
        <section aria-labelledby="election-alerts-title">
          <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
            <h2 id="election-alerts-title" className="sr-only">Election alerts</h2>
            <p className="max-w-2xl text-[0.875rem] text-[color:var(--muted)]">
              Incidents, coverage and results as they&apos;re reported, one message per incident however many outlets carry it.
            </p>
            <p className="flex gap-4 text-[0.8125rem]">
              <Link href="/elections/gambia" className="text-[color:var(--muted)] hover:text-[color:var(--text)]">Gambia results</Link>
              <Link href="/elections/nigeria" className="text-[color:var(--muted)] hover:text-[color:var(--text)]">Nigeria results</Link>
              <Link href="/elections/nigeria/governorship" className="text-[color:var(--muted)] hover:text-[color:var(--text)]">Governorship</Link>
              <Link href="/developers#elections" className="text-[color:var(--muted)] hover:text-[color:var(--text)]">API</Link>
            </p>
          </div>

          <ElectionAlerts />

          <h3 className="mt-12 text-[0.9375rem] text-[color:var(--text)]">Coming up</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-[0.875rem]">
              <tbody className="divide-y divide-white/[0.07] border-y hairline">
                {live.map((e) => (
                  <tr key={e.country + e.date}>
                    <td className="kbd w-36 py-2.5 pr-4 text-[0.8125rem] text-[color:var(--muted)]">{dateLabel(e)}{e.label.endsWith("(expected)") ? "*" : ""}</td>
                    <td className="py-2.5 pr-4 text-[color:var(--text)]">{e.country}</td>
                    <td className="py-2.5 pr-4 text-[color:var(--muted)]">{e.kind}</td>
                    <td className="py-2.5 text-right">
                      {e.key ? (
                        <span className="inline-flex items-center gap-1.5 text-[0.8125rem] text-[color:var(--muted)]">
                          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--verified,#6ee7c8)]" />Covered
                        </span>
                      ) : (
                        <RequestForm topic="election_coverage" label="Request coverage" detail={`${e.country}, ${e.kind}, ${e.label}`}
                                     className="text-[0.8125rem] text-[color:var(--muted)] underline-offset-2 hover:underline"
                                     placeholder="What you would want covered (incidents, news, results) and when you need it" />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">Dates from national electoral commissions, checked November 2026.{live.some((e) => e.label.endsWith("(expected)")) ? " *Expected." : ""}</p>

          <p className="mt-8 text-[0.75rem] text-[color:var(--dim)]">
            Alerts running at once: Pro 2, Team 5, Institutional 25. Messages are not capped. <Link href="/pricing" className="underline">Plans</Link> ·{" "}
            <RequestForm topic="institutional" label="Ask about Institutional" className="underline"
                         placeholder="Tell us what you need: countries, elections, alerts, results, API volume, and timing" />
          </p>
        </section>
      )}
    </Container>
  );
}
