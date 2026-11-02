"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Container } from "../../../components/primitives";
import { AuthCard, Notice, authAction, safeNext } from "../../../components/auth/AuthUi";
import { displayNameProblem, normaliseUsername, usernameProblem } from "../../../lib/password-policy";

export default function ProfilePage() {
  const router = useRouter();
  const [next, setNext] = useState("/app");
  const [loaded, setLoaded] = useState(false);
  const [onboarding, setOnboarding] = useState(true);
  const [username, setUsername] = useState("");
  const [original, setOriginal] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [availability, setAvailability] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    setNext(safeNext(new URLSearchParams(window.location.search).get("next")));
    fetch("/api/portfolio/auth", { cache: "no-store" }).then(async (r) => {
      if (r.status === 401) { router.replace(`/account?next=${encodeURIComponent("/account/profile")}`); return; }
      const s = (await r.json()) as { profile?: { username: string; displayName: string } | null; user?: { email?: string | null } };
      if (s.profile) {
        setOnboarding(false); setUsername(s.profile.username); setOriginal(s.profile.username); setDisplayName(s.profile.displayName);
      } else {
        setDisplayName((s.user?.email || "").split("@")[0].slice(0, 40));
      }
      setLoaded(true);
    }).catch(() => setError("Could not load your profile."));
  }, [router]);

  useEffect(() => {
    const u = normaliseUsername(username);
    if (!u || u === original) { setAvailability(null); return; }
    const problem = usernameProblem(u);
    if (problem) { setAvailability(problem); return; }
    const t = setTimeout(async () => {
      const { ok, data } = await authAction<{ available: boolean; problem: string | null }>({ action: "check-username", username: u });
      setAvailability(ok ? (data.available ? "available" : data.problem) : null);
    }, 400);
    return () => clearTimeout(t);
  }, [username, original]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(""); setMessage("");
    const problem = usernameProblem(username) || displayNameProblem(displayName);
    if (problem) { setError(problem); return; }
    setBusy(true);
    const { ok, data } = await authAction({ action: "set-profile", username: normaliseUsername(username), displayName: displayName.trim() });
    setBusy(false);
    if (!ok) { setError(data.error || "The profile could not be saved."); return; }
    if (onboarding) { router.push(next); return; }
    setOriginal(normaliseUsername(username));
    setMessage("Profile saved.");
  }

  return (
    <Container className="py-10 lg:py-16">
      <AuthCard title={onboarding ? "Choose your username" : "Your profile"}>
        <p className="mt-2 text-sm text-[color:var(--muted)]">
          {onboarding ? "One more step before the app opens: pick a username and the name shown in the app." : "Your username is public and unique; your nickname is how you appear in the app."}
        </p>
        {!loaded ? <p className="mt-6 text-sm text-[color:var(--muted)]" role="status">Loading…</p> : (
          <form className="mt-6 space-y-4" onSubmit={save} noValidate>
            <div>
              <label className="mb-2 block text-sm" htmlFor="profile-username">Username</label>
              <div className="relative">
                <span className="pointer-events-none absolute inset-y-0 left-3 my-auto h-5 text-sm text-[color:var(--dim)]">@</span>
                <input id="profile-username" className="field w-full pl-7" required maxLength={20} value={username} autoComplete="username"
                  onChange={(e) => setUsername(e.target.value.replace(/\s/g, "").toLowerCase())} aria-describedby="profile-username-hint" spellCheck={false} autoCapitalize="off" />
              </div>
              <p id="profile-username-hint" className={`mt-1 text-xs ${availability === "available" ? "text-verified" : availability ? "text-risk" : "text-[color:var(--dim)]"}`} aria-live="polite">
                {availability === "available" ? `✓ @${normaliseUsername(username)} is available` : availability || "3 to 20 letters, numbers or underscores."}
              </p>
            </div>
            <div>
              <label className="mb-2 block text-sm" htmlFor="profile-name">Nickname</label>
              <input id="profile-name" className="field w-full" required maxLength={40} value={displayName} autoComplete="nickname" onChange={(e) => setDisplayName(e.target.value)} />
            </div>
            <button className="btn btn-primary w-full justify-center" type="submit" disabled={busy || (availability !== null && availability !== "available")}>
              {busy ? "Saving…" : onboarding ? "Continue to the app" : "Save profile"}
            </button>
          </form>
        )}
        {!onboarding ? <p className="mt-4 text-sm"><Link className="underline underline-offset-4" href="/account">Back to your account</Link></p> : null}
        <Notice error={error} message={message} />
      </AuthCard>
    </Container>
  );
}
