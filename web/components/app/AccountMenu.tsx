"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

type Session = {
  authenticated: boolean;
  user?: { email?: string | null };
  profile?: { username: string; displayName: string } | null;
};

/** The signed-in account in the app header: who you are, profile and security settings, and sign out. */
export function AccountMenu() {
  const [session, setSession] = useState<Session | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/portfolio/auth", { cache: "no-store" })
      .then(async (r) => setSession(r.ok ? ((await r.json()) as Session) : { authenticated: false }))
      .catch(() => setSession({ authenticated: false }));
  }, []);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onClick); document.removeEventListener("keydown", onKey); };
  }, [open]);

  async function signOut() {
    setBusy(true);
    try {
      await fetch("/api/portfolio/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "sign-out" }),
      });
    } finally {
      // A full page load clears everything the app holds in memory for this account.
      window.location.assign("/account");
    }
  }

  if (session === null) return <span className="h-8 w-8 shrink-0" aria-hidden="true" />;
  if (!session.authenticated) {
    return <Link href="/account" className="btn btn-ghost h-8 shrink-0 px-3 text-[0.8125rem]">Sign in</Link>;
  }

  const name = session.profile?.displayName || session.profile?.username || (session.user?.email || "Account").split("@")[0];
  const initial = name.trim().charAt(0).toUpperCase() || "?";
  const itemClass = "block w-full rounded-lg px-3 py-2 text-left text-sm text-[color:var(--muted)] transition-colors hover:bg-white/[0.04] hover:text-[color:var(--text)]";

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${name}`}
        className="flex h-8 items-center gap-2 rounded-full border hairline pl-1 pr-1 text-[0.8125rem] transition-colors hover:bg-white/[0.04] sm:pr-3"
      >
        <span aria-hidden="true" className="grid h-6 w-6 place-items-center rounded-full bg-white/90 text-xs font-semibold text-black">{initial}</span>
        <span className="hidden max-w-[9rem] truncate sm:inline">{name}</span>
      </button>
      {open && (
        <div role="menu" aria-label="Account" className="absolute right-0 top-full mt-2 w-60 rounded-xl border hairline bg-raised/[0.98] p-2 shadow-xl">
          <div className="border-b hairline px-3 pb-2 pt-1">
            <p className="truncate text-sm font-medium text-[color:var(--text)]">{name}</p>
            {session.profile?.username ? <p className="truncate text-xs text-[color:var(--muted)]">@{session.profile.username}</p> : null}
            {session.user?.email ? <p className="truncate text-xs text-[color:var(--muted)]" title={session.user.email}>{session.user.email}</p> : null}
          </div>
          <div className="pt-1">
            <Link role="menuitem" href="/account/profile" className={itemClass} onClick={() => setOpen(false)}>Profile</Link>
            <Link role="menuitem" href="/account/security" className={itemClass} onClick={() => setOpen(false)}>Password and security</Link>
            <Link role="menuitem" href="/account/billing" className={itemClass} onClick={() => setOpen(false)}>Plan and billing</Link>
            <Link role="menuitem" href="/api-keys" className={itemClass} onClick={() => setOpen(false)}>API keys</Link>
            <button role="menuitem" type="button" onClick={signOut} disabled={busy} className={`${itemClass} disabled:opacity-60`}>
              {busy ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
