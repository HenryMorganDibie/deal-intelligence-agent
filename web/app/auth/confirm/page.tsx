"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Container } from "../../../components/primitives";
import { AuthCard, Notice, authAction } from "../../../components/auth/AuthUi";

// Links in account emails land here. The token is spent only when the reader presses the button,
// so mail scanners that open links in advance cannot use up a single-use link.
const COPY: Record<string, { title: string; body: string; button: string }> = {
  signup: { title: "Confirm your email", body: "Press the button to confirm your email address and open your account.", button: "Confirm email address" },
  invite: { title: "Accept your invitation", body: "Press the button to accept the invitation. You will then choose a password.", button: "Accept invitation" },
  magiclink: { title: "Sign in", body: "Press the button to finish signing in on this device.", button: "Sign in" },
  recovery: { title: "Reset your password", body: "Press the button to continue. You will then choose a new password.", button: "Continue" },
  email_change: { title: "Confirm the email change", body: "Press the button to confirm the change of your account's email address.", button: "Confirm the change" },
  email: { title: "Confirm your email", body: "Press the button to confirm your email address.", button: "Confirm" },
};

export default function AuthConfirmPage() {
  const router = useRouter();
  const [link, setLink] = useState<{ tokenHash: string; type: string } | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tokenHash = params.get("token_hash") || "";
    const type = params.get("type") || "";
    // Keep the token out of the address bar, history and any later Referer header.
    window.history.replaceState({}, document.title, window.location.pathname);
    if (tokenHash && COPY[type]) setLink({ tokenHash, type });
    else setError("This link is incomplete or has expired. Return to sign in and request a new one.");
  }, []);

  async function confirm() {
    if (!link) return;
    setBusy(true); setError(""); setMessage("");
    const { ok, data } = await authAction<{ pending?: boolean }>({ action: "verify-email", tokenHash: link.tokenHash, type: link.type });
    setBusy(false);
    if (!ok) { setError(data.error || "This link is invalid or has expired. Request a new one."); return; }
    setDone(true);
    if (data.pending) {
      setMessage("Thank you. To finish the change, also press the link we sent to your other email address.");
      return;
    }
    if (link.type === "recovery" || link.type === "invite") router.replace("/account/reset-password");
    else if (link.type === "email_change") {
      setMessage("Your email address has been changed.");
      router.replace("/account/security");
    } else router.replace("/app");
  }

  const copy = link ? COPY[link.type] : null;
  return (
    <Container className="py-12">
      <AuthCard title={copy?.title || "Account link"}>
        {copy && !done ? <p className="mt-3 text-sm text-[color:var(--muted)]">{copy.body}</p> : null}
        <Notice error={error} message={message} />
        {copy && !done ? (
          <button type="button" className="btn btn-primary mt-6 h-11 w-full" onClick={confirm} disabled={busy} aria-busy={busy}>
            {busy ? "Confirming…" : copy.button}
          </button>
        ) : null}
        <a className="mt-5 inline-flex text-sm underline" href="/account">Return to sign in</a>
      </AuthCard>
    </Container>
  );
}
