"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Container } from "../../../components/primitives";
import { AuthCard, MatchHint, Notice, PasswordInput, PasswordStrength, authAction } from "../../../components/auth/AuthUi";
import { passwordProblems } from "../../../lib/password-policy";

type State = { user?: { email?: string | null }; profile?: { username: string } | null; mfa?: { enrolled: boolean; factorId: string | null; aal: string | null } };
type Enrolment = { factorId: string; qrCode?: string; secret?: string };

export default function SecurityPage() {
  const router = useRouter();
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [enrolment, setEnrolment] = useState<Enrolment | null>(null);
  const [code, setCode] = useState("");

  const load = useCallback(async () => {
    const r = await fetch("/api/portfolio/auth", { cache: "no-store" });
    if (r.status === 401) { router.replace(`/account?next=${encodeURIComponent("/account/security")}`); return; }
    setState((await r.json()) as State);
  }, [router]);

  useEffect(() => { void load(); }, [load]);

  const ctx = { email: state?.user?.email ?? undefined, username: state?.profile?.username };
  const canChange = current.length > 0 && passwordProblems(password, ctx).length === 0 && password === confirm;

  async function changePassword(e: FormEvent) {
    e.preventDefault();
    setError(""); setMessage(""); setBusy(true);
    const { ok, data } = await authAction({ action: "change-password", currentPassword: current, password, confirmPassword: confirm });
    setBusy(false);
    if (!ok) { setError(data.error || "The password could not be changed."); return; }
    setCurrent(""); setPassword(""); setConfirm("");
    setMessage("Password changed. Other devices stay signed in until you sign them out below.");
  }

  async function startEnrol() {
    setError(""); setMessage(""); setBusy(true);
    const { ok, data } = await authAction<Enrolment>({ action: "mfa-enroll" });
    setBusy(false);
    if (!ok) { setError(data.error || "Two-factor setup could not start."); return; }
    setEnrolment({ factorId: data.factorId, qrCode: data.qrCode, secret: data.secret });
  }

  async function confirmEnrol(e: FormEvent) {
    e.preventDefault();
    if (!enrolment) return;
    setError(""); setBusy(true);
    const { ok, data } = await authAction({ action: "mfa-verify", factorId: enrolment.factorId, code });
    setBusy(false);
    if (!ok) { setError(data.error || "That code did not work."); setCode(""); return; }
    setEnrolment(null); setCode("");
    setMessage("Two-factor sign-in is on. You will be asked for a code each time you sign in.");
    await load();
  }

  async function removeFactor() {
    if (!state?.mfa?.factorId) return;
    if (!window.confirm("Turn off two-factor sign-in? Your account will be protected by your password alone.")) return;
    setError(""); setMessage(""); setBusy(true);
    const { ok, data } = await authAction({ action: "mfa-unenroll", factorId: state.mfa.factorId });
    setBusy(false);
    if (!ok) { setError(data.error || "Two-factor could not be turned off."); return; }
    setMessage("Two-factor sign-in is off.");
    await load();
  }

  async function signOutEverywhere() {
    if (!window.confirm("Sign out on every device, including this one?")) return;
    await authAction({ action: "sign-out-everywhere" });
    router.replace("/account");
  }

  return (
    <Container className="py-10 lg:py-16">
      <AuthCard title="Security" wide>
        {!state ? <p className="mt-6 text-sm text-[color:var(--muted)]" role="status">Loading…</p> : (
          <div className="mt-6 space-y-10">
            <section aria-labelledby="pw-h">
              <h2 id="pw-h" className="text-lg font-semibold">Change password</h2>
              <form className="mt-4 space-y-4" onSubmit={changePassword} noValidate>
                <PasswordInput id="current-password" label="Current password" value={current} onChange={setCurrent} autoComplete="current-password" />
                <div>
                  <PasswordInput id="new-password" label="New password" value={password} onChange={setPassword} autoComplete="new-password" describedBy="new-strength" />
                  <PasswordStrength id="new-strength" password={password} ctx={ctx} />
                </div>
                <div>
                  <PasswordInput id="confirm-password" label="Retype new password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
                  <MatchHint password={password} confirm={confirm} />
                </div>
                <button className="btn btn-primary" type="submit" disabled={busy || !canChange}>{busy ? "Saving…" : "Change password"}</button>
              </form>
            </section>

            <section aria-labelledby="mfa-h">
              <h2 id="mfa-h" className="text-lg font-semibold">Two-factor sign-in</h2>
              <p className="mt-1 text-sm text-[color:var(--muted)]">
                With an authenticator app (Google Authenticator, Microsoft Authenticator, 1Password, Authy), signing in needs your password and a code from your phone.
              </p>
              {state.mfa?.enrolled ? (
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <span className="text-sm text-verified">✓ On</span>
                  <button className="btn btn-ghost" type="button" onClick={removeFactor} disabled={busy}>Turn off</button>
                </div>
              ) : enrolment ? (
                <form className="mt-4 space-y-4" onSubmit={confirmEnrol}>
                  <p className="text-sm">1. Scan this code with your authenticator app.</p>
                  {enrolment.qrCode ? (
                    // The QR code is an SVG data URI generated by Supabase for this enrolment.
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={enrolment.qrCode} alt="QR code for your authenticator app" className="h-48 w-48 rounded-lg bg-white p-2" />
                  ) : null}
                  {enrolment.secret ? <p className="text-xs text-[color:var(--muted)]">Can&apos;t scan? Enter this key: <code className="kbd break-all">{enrolment.secret}</code></p> : null}
                  <label className="block text-sm" htmlFor="enrol-code">2. Enter the 6-digit code it shows</label>
                  <input id="enrol-code" className="field w-44 text-center text-xl tracking-[0.3em]" inputMode="numeric" autoComplete="one-time-code"
                    maxLength={6} required value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
                  <div className="flex gap-2">
                    <button className="btn btn-primary" type="submit" disabled={busy || code.length !== 6}>{busy ? "Checking…" : "Turn on"}</button>
                    <button className="btn btn-ghost" type="button" onClick={() => { setEnrolment(null); setCode(""); }}>Cancel</button>
                  </div>
                </form>
              ) : (
                <button className="btn btn-primary mt-4" type="button" onClick={startEnrol} disabled={busy}>Set up an authenticator app</button>
              )}
            </section>

            <section aria-labelledby="sessions-h">
              <h2 id="sessions-h" className="text-lg font-semibold">Sessions</h2>
              <p className="mt-1 text-sm text-[color:var(--muted)]">If you signed in on a device you no longer use, or think someone else has your password, sign out everywhere.</p>
              <button className="btn btn-ghost mt-4" type="button" onClick={signOutEverywhere}>Sign out of all devices</button>
            </section>
          </div>
        )}
        <p className="mt-8 text-sm"><Link className="underline underline-offset-4" href="/account">Back to your account</Link></p>
        <Notice error={error} message={message} />
      </AuthCard>
    </Container>
  );
}
