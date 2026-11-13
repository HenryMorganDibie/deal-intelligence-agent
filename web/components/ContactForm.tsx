"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../lib/api";
import { post } from "../lib/market";
import { CONTACT_EMAIL, CONTACT_TOPICS, type ContactTopic } from "../lib/site";

/** The site's contact form: sends to the team's inbox through the API, so it works without a mail app. */
export function ContactForm({ initialTopic = "demo" }: { initialTopic?: ContactTopic }) {
  const [topic, setTopic] = useState<ContactTopic>(initialTopic);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [organisation, setOrganisation] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState("");          // hidden from people
  const opened = useRef(Date.now());
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setTopic(initialTopic); }, [initialTopic]);
  const hint = CONTACT_TOPICS.find(([k]) => k === topic)?.[2];

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setDone(null);
    try {
      const r = await post<{ sent: boolean; reply_to: string | null }>("/api/contact", {
        topic, name: name.trim(), email: email.trim(), organisation: organisation.trim() || null, message: message.trim(),
        website, elapsed_ms: Date.now() - opened.current,
      });
      setDone(`Thank you. Your request has been sent${r.reply_to ? `, and the reply will go to ${r.reply_to}` : ""}.`);
      setMessage("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `The request could not be sent. You can also write to ${CONTACT_EMAIL}.`);
    } finally { setBusy(false); }
  }

  return (
    <form id="form" onSubmit={submit} className="panel space-y-4 p-6">
      <label className="block text-[0.8125rem] text-[color:var(--muted)]">
        What is it about?
        <select value={topic} onChange={(e) => setTopic(e.target.value as ContactTopic)} className="field mt-1.5">
          {CONTACT_TOPICS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-[0.8125rem] text-[color:var(--muted)]">
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} autoComplete="name" className="field mt-1.5" />
        </label>
        <label className="block text-[0.8125rem] text-[color:var(--muted)]">
          Work email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={254} autoComplete="email" className="field mt-1.5" />
        </label>
      </div>
      <label className="block text-[0.8125rem] text-[color:var(--muted)]">
        Organisation and role (optional)
        <input value={organisation} onChange={(e) => setOrganisation(e.target.value)} maxLength={120} autoComplete="organization" className="field mt-1.5" />
      </label>
      <label className="block text-[0.8125rem] text-[color:var(--muted)]">
        Message
        <textarea value={message} onChange={(e) => setMessage(e.target.value)} required minLength={10} maxLength={4000} rows={5}
                  placeholder={hint} className="field mt-1.5 min-h-[8rem]" />
      </label>
      {/* People never see this field; automated senders fill it in. */}
      <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
        <label>Website<input tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} /></label>
      </div>
      <button type="submit" disabled={busy} className="btn btn-primary">{busy ? "Sending…" : "Send request"}</button>
      {done && <p role="status" className="text-[0.875rem] text-verified">{done}</p>}
      {error && <p role="alert" className="text-[0.875rem] text-risk">{error}</p>}
    </form>
  );
}
