"use client";

import { useState } from "react";

/** Shares a deal's public page: the phone's share sheet where there is one, else the link is copied. */
export function ShareDeal({ id, title }: { id: string; title: string }) {
  const [note, setNote] = useState("");
  async function share() {
    const url = `${window.location.origin}/deals/${id}`;
    try {
      if (navigator.share) {
        await navigator.share({ title, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setNote("Link copied");
    } catch (e) {
      if ((e as { name?: string })?.name === "AbortError") return;      // the share sheet was closed
      setNote(url);                                                       // no clipboard: show the link to copy
    }
    window.setTimeout(() => setNote(""), 4000);
  }
  return (
    <span className="ml-4 inline-flex flex-wrap items-center gap-3 text-[0.8125rem]">
      <button type="button" onClick={share} className="text-[color:var(--muted)] hover:text-[color:var(--text)]">
        Share this deal ↗
      </button>
      <a href={`/deals/${id}`} target="_blank" rel="noopener" className="text-[color:var(--dim)] hover:text-[color:var(--text)]">
        Preview public page
      </a>
      {note && <span role="status" className="text-verified">{note}</span>}
    </span>
  );
}
