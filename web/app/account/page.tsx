"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Container } from "../../components/primitives";
import { AuthCard, MatchHint, Notice, PasswordInput, PasswordStrength, authAction, safeNext } from "../../components/auth/AuthUi";
import { displayNameProblem, normaliseUsername, passwordProblems, usernameProblem } from "../../lib/password-policy";

type Session = {
  authenticated: boolean;
  user?: { id: string; email?: string | null };
  profile?: { username: string; displayName: string } | null;
  mfa?: { enrolled: boolean; aal: string | null };
};

export default function AccountPage() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [next, setNext] = useState("/deals");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [usernameState, setUsernameState] = useState<{ checking: boolean; available: boolean | null; problem: string | null }>({ checking: false, available: null, problem: null });
  const [showRecovery, setShowRecovery] = useState(false);
  const [recoveryEmail, setRecoveryEmail] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setNext(safeNext(params.get("next")));
    if (params.get("mode") === "sign-up") setMode("sign-up");
    if (params.get("error") === "oauth_unavailable") setError("Google sign-in is temporarily unavailable. Please try again.");
    fetch("/api/portfolio/auth", { cache: "no-store" })
      .then(async (r) => {
        const s = r.ok ? ((await r.json()) as Session) : { authenticated: false };
        // Already signed in and sent here on the way to a page (an "Open the app" button): go straight there.
        if (s.authenticated && params.get("next")) { router.replace(safeNext(params.get("next"))); return; }
        setSession(s);
      })
      .catch(() => setSession({ authenticated: false }));
  }, [router]);

  // Live username availability, debounced.
  useEffect(() => {
    if (mode !== "sign-up" || !username) { setUsernameState({ checking: false, available: null, problem: null }); return; }
    const problem = usernameProblem(username);
    if (problem) { setUsernameState({ checking: false, available: false, problem }); return; }
    setUsernameState((s) => ({ ...s, checking: true }));
    const t = setTimeout(async () => {
      const { ok, data } = await authAction<{ available: boolean; problem: string | null }>({ action: "check-username", username });
      setUsernameState({ checking: false, available: ok ? data.available : null, problem: ok ? data.problem : null });
    }, 400);
    return () => clearTimeout(t);
  }, [username, mode]);

  function switchMode(m: "sign-in" | "sign-up") {
    setMode(m); setError(""); setMessage(""); setPassword(""); setConfirm("");
  }

  async function signIn(e: FormEvent) {
    e.preventDefault();
    setError(""); setMessage(""); setBusy(true);
    const { ok, data } = await authAction<{ mfaRequired?: boolean }>({ action: "sign-in", email, password });
    setBusy(false);
    if (!ok) { setError(data.error || "Sign-in failed."); return; }
    setPassword("");
    router.push(data.mfaRequired ? `/account/mfa?next=${encodeURIComponent(next)}` : next);
  }

  const ctx = { email, username: normaliseUsername(username) };
  const passwordOk = passwordProblems(password, ctx).length === 0;
  const canSignUp = passwordOk && password === confirm && !usernameProblem(username) && usernameState.available !== false
    && !displayNameProblem(displayName) && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

  async function signUp(e: FormEvent) {
    e.preventDefault();
    setError(""); setMessage("");
    if (!canSignUp) { setError("Complete every field: the password must meet each rule and both passwords must match."); return; }
    setBusy(true);
    const { ok, data } = await authAction<{ needsEmailConfirmation?: boolean; message?: string }>({
      action: "sign-up", email, password, confirmPassword: confirm, username: normaliseUsername(username), displayName: displayName.trim(),
    });
    setBusy(false);
    if (!ok) { setError(data.error || "Account creation failed."); return; }
    setPassword(""); setConfirm("");
    if (data.needsEmailConfirmation) {
      setMessage(`If ${email.trim()} is new here, a confirmation link is on its way; open it to activate your account (it expires in 24 hours). If that email already has an account, including one created with Google, no email is sent: sign in, or use "Forgot password?" to set a password.`);
      setMode("sign-in");
      return;
    }
    router.push(next);
  }

  async function requestRecovery(e: FormEvent) {
    e.preventDefault();
    setError(""); setMessage(""); setBusy(true);
    const { ok, data } = await authAction({ action: "recover-password", email: recoveryEmail });
    setBusy(false);
    if (!ok) { setError(data.error || "Could not request a reset link."); return; }
    setMessage("If an account exists for that email, a password-reset link is on its way.");
    setShowRecovery(false);
  }

  async function signOut() {
    await authAction({ action: "sign-out" });
    setSession({ authenticated: false });
    setMessage("You have signed out.");
  }

  if (session?.authenticated) {
    return (
      <Container className="py-10 lg:py-16">
        <AuthCard title="Your account">
          <p className="mt-3 text-sm text-[color:var(--muted)]">
            Signed in as <strong className="text-[color:var(--text)]">{session.profile?.displayName || session.user?.email}</strong>
            {session.profile ? <> (@{session.profile.username})</> : null}.
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            <Link className="btn btn-primary" href={next}>Open the app</Link>
            <Link className="btn btn-ghost" href="/account/profile">Profile</Link>
            <Link className="btn btn-ghost" href="/account/security">Security{session.mfa?.enrolled ? "" : " · set up two-factor"}</Link>
            <button className="btn btn-ghost" type="button" onClick={signOut}>Sign out</button>
          </div>
          <Notice error={error} message={message} />
        </AuthCard>
      </Container>
    );
  }

  return (
    <Container className="py-10 lg:py-16">
      <AuthCard title={mode === "sign-in" ? "Sign in to Deal Intelligence" : "Create your account"}>
        <div className="mt-5 grid grid-cols-2 gap-1 rounded-full border border-[color:var(--line)] p-1 text-sm" role="tablist" aria-label="Account">
          {(["sign-in", "sign-up"] as const).map((m) => (
            <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => switchMode(m)}
              className={`rounded-full py-1.5 ${mode === m ? "bg-white/[0.08] text-[color:var(--text)]" : "text-[color:var(--muted)]"}`}>
              {m === "sign-in" ? "Sign in" : "Create account"}
            </button>
          ))}
        </div>

        {/* The forms appear once the page is interactive and the session is known, so an early click is never lost. */}
        {session === null ? <p className="mt-6 text-sm text-[color:var(--muted)]" role="status">Checking your session…</p> : null}

        {session === null ? null : mode === "sign-in" ? (
          <form className="mt-6 space-y-4" onSubmit={signIn} noValidate>
            <div>
              <label className="mb-2 block text-sm" htmlFor="signin-email">Email</label>
              <input id="signin-email" className="field w-full" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <PasswordInput id="signin-password" label="Password" value={password} onChange={setPassword} autoComplete="current-password" />
            <button className="btn btn-primary w-full justify-center" type="submit" disabled={busy || !email || !password}>{busy ? "Signing in…" : "Sign in"}</button>
            <div className="flex justify-between text-sm">
              <button type="button" className="underline underline-offset-4" onClick={() => { setShowRecovery((v) => !v); setRecoveryEmail(email); }}>Forgot password?</button>
            </div>
          </form>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={signUp} noValidate>
            <div>
              <label className="mb-2 block text-sm" htmlFor="signup-email">Email</label>
              <input id="signup-email" className="field w-full" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <label className="mb-2 block text-sm" htmlFor="signup-username">Username</label>
              <div className="relative">
                <span className="pointer-events-none absolute inset-y-0 left-3 my-auto h-5 text-sm text-[color:var(--dim)]">@</span>
                <input id="signup-username" className="field w-full pl-7" autoComplete="username" required maxLength={20} value={username}
                  onChange={(e) => setUsername(e.target.value.replace(/\s/g, "").toLowerCase())} aria-describedby="username-hint" spellCheck={false} autoCapitalize="off" />
              </div>
              <p id="username-hint" className={`mt-1 text-xs ${usernameState.available === false ? "text-risk" : usernameState.available ? "text-verified" : "text-[color:var(--dim)]"}`} aria-live="polite">
                {!username ? "3 to 20 letters, numbers or underscores. Public, and unique to you."
                  : usernameState.checking ? "Checking…" : usernameState.problem ? usernameState.problem : usernameState.available ? `✓ @${normaliseUsername(username)} is available` : ""}
              </p>
            </div>
            <div>
              <label className="mb-2 block text-sm" htmlFor="signup-name">Nickname</label>
              <input id="signup-name" className="field w-full" autoComplete="nickname" required maxLength={40} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
              <p className="mt-1 text-xs text-[color:var(--dim)]">The name shown in the app. You can change it later.</p>
            </div>
            <div>
              <PasswordInput id="signup-password" label="Password" value={password} onChange={setPassword} autoComplete="new-password" describedBy="signup-strength" invalid={Boolean(password) && !passwordOk} />
              <PasswordStrength id="signup-strength" password={password} ctx={ctx} />
            </div>
            <div>
              <PasswordInput id="signup-confirm" label="Retype password" value={confirm} onChange={setConfirm} autoComplete="new-password" invalid={Boolean(confirm) && confirm !== password} />
              <MatchHint password={password} confirm={confirm} />
            </div>
            <button className="btn btn-primary w-full justify-center" type="submit" disabled={busy || !canSignUp}>{busy ? "Creating account…" : "Create account"}</button>
            <p className="text-xs text-[color:var(--dim)]">
              Passwords are checked against known data breaches without sending the password anywhere. We email a link to confirm your address before the account works.
            </p>
          </form>
        )}

        {session === null ? null : (
          <>
            <div className="my-6 flex items-center gap-3 text-xs text-[color:var(--muted)]"><span className="h-px flex-1 bg-[color:var(--line)]" />or<span className="h-px flex-1 bg-[color:var(--line)]" /></div>
            <a className="btn btn-ghost w-full justify-center" href="/api/portfolio/auth/google">Continue with Google</a>
          </>
        )}

        {showRecovery && mode === "sign-in" ? (
          <form className="mt-5 space-y-3 rounded-xl border border-[color:var(--line)] p-4" onSubmit={requestRecovery}>
            <label className="block text-sm" htmlFor="recovery-email">Send a reset link to</label>
            <input id="recovery-email" className="field w-full" type="email" autoComplete="email" required maxLength={254} value={recoveryEmail} onChange={(e) => setRecoveryEmail(e.target.value)} />
            <button className="btn btn-ghost" type="submit" disabled={busy}>{busy ? "Sending…" : "Send password-reset link"}</button>
          </form>
        ) : null}

        <Notice error={error} message={message} />
      </AuthCard>
    </Container>
  );
}
