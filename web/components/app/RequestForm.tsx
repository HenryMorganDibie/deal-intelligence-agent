"use client";

import { useState, type FormEvent } from "react";
import { ApiError } from "../../lib/api";
import { post } from "../../lib/market";
import { CONTACT_EMAIL } from "../../lib/site";

type Topic = "institutional" | "election_alerts" | "election_coverage";

/** A request sent from the page to the team's inbox, replacing a mailto link (which does nothing on devices
 * without a mail app). The reply goes to the account's confirmed email. */
export function RequestForm({ topic, label, detail, placeholder, className }: {
  topic: Topic; label: string; detail?: string; placeholder?: string; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [organisation, setOrganisation] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const r = await post<{ sent: boolean; reply_to: string | null }>("/api/contact", {
        topic, message: message.trim(), organisation: organisation.trim() || null, subject_detail: detail ?? null,
      });
      setDone(r.reply_to ? `Sent. We will reply to ${r.reply_to}.` : "Sent. Confirm your account's email address so we can reply.");
      setMessage(""); setOrganisation("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `The request could not be sent. You can also write to ${CONTACT_EMAIL}.`);
    } finally { setBusy(false); }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => { setOpen(true); setDone(null); }} className={className ?? "underline"}>
        {label}
      </button>
    );
  }
  return (
    <form onSubmit={submit} className="mt-3 w-full basis-full space-y-3 rounded-lg border hairline p-4">
      <p className="text-[0.875rem] text-[color:var(--text)]">{label}{detail ? `: ${detail}` : ""}</p>
      <input value={organisation} onChange={(e) => setOrganisation(e.target.value)} maxLength={120}
             placeholder="Organisation (optional)" className="field" aria-label="Organisation" />
      <textarea value={message} onChange={(e) => setMessage(e.target.value)} required minLength={10} maxLength={4000} rows={4}
                placeholder={placeholder ?? "What you need, and roughly when"} className="field min-h-[7rem]" aria-label="Message" />
      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" disabled={busy || message.trim().length < 10} className="btn btn-primary text-[0.8125rem]">
          {busy ? "Sending…" : "Send request"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="btn btn-ghost text-[0.8125rem]">Close</button>
      </div>
      {done && <p role="status" className="text-[0.8125rem] text-verified">{done}</p>}
      {error && <p role="alert" className="text-[0.8125rem] text-risk">{error}</p>}
      <p className="text-[0.75rem] text-[color:var(--dim)]">Or write to {CONTACT_EMAIL}.</p>
    </form>
  );
}
