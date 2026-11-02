"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Container } from "../../../components/primitives";
import { AuthCard, MatchHint, Notice, PasswordInput, PasswordStrength, authAction } from "../../../components/auth/AuthUi";
import { passwordProblems } from "../../../lib/password-policy";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const valid = passwordProblems(password).length === 0 && password === confirmation;

  async function updatePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(""); setMessage("");
    if (!valid) { setError("The password must meet every rule, and both entries must match."); return; }
    setBusy(true);
    const { ok, data } = await authAction({ action: "update-password", password, confirmPassword: confirmation });
    setBusy(false);
    if (!ok) { setError(data.error || "Could not update your password."); return; }
    setPassword(""); setConfirmation("");
    setMessage("Your password has been updated.");
    window.setTimeout(() => router.replace("/app"), 800);
  }

  return (
    <Container className="py-10 lg:py-16">
      <AuthCard title="Choose a new password">
        <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">Your reset link must still be valid. The new password is checked against known data breaches.</p>
        <form className="mt-6 space-y-4" onSubmit={updatePassword} noValidate>
          <div>
            <PasswordInput id="new-password" label="New password" value={password} onChange={setPassword} autoComplete="new-password" describedBy="reset-strength" />
            <PasswordStrength id="reset-strength" password={password} ctx={{}} />
          </div>
          <div>
            <PasswordInput id="confirm-password" label="Retype new password" value={confirmation} onChange={setConfirmation} autoComplete="new-password" />
            <MatchHint password={password} confirm={confirmation} />
          </div>
          <button className="btn btn-primary w-full justify-center" type="submit" disabled={busy || !valid}>{busy ? "Updating…" : "Update password"}</button>
        </form>
        <p className="mt-4 text-sm"><Link className="underline underline-offset-4" href="/account">Back to sign in</Link></p>
        <Notice error={error} message={message} />
      </AuthCard>
    </Container>
  );
}
