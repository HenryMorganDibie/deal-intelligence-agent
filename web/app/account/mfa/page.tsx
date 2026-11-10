"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Container } from "../../../components/primitives";
import { AuthCard, Notice, authAction, safeNext } from "../../../components/auth/AuthUi";

// The second sign-in step for accounts with an authenticator app.
export default function MfaPage() {
  const router = useRouter();
  const [next, setNext] = useState("/app/deals");
  const [factorId, setFactorId] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const target = safeNext(new URLSearchParams(window.location.search).get("next"));
    setNext(target);
    fetch("/api/portfolio/auth", { cache: "no-store" }).then(async (r) => {
      if (r.status === 401) { router.replace(`/account?next=${encodeURIComponent(target)}`); return; }
      const s = (await r.json()) as { mfa?: { enrolled: boolean; factorId: string | null; aal: string | null } };
      if (!s.mfa?.enrolled || s.mfa.aal === "aal2") { router.replace(target); return; }
      setFactorId(s.mfa.factorId);
    }).catch(() => setError("Could not load your sign-in. Try again."));
  }, [router]);

  async function verify(e: FormEvent) {
    e.preventDefault();
    if (!factorId) return;
    setError(""); setBusy(true);
    const { ok, data } = await authAction({ action: "mfa-verify", factorId, code });
    setBusy(false);
    if (!ok) { setError(data.error || "That code did not work."); setCode(""); return; }
    router.replace(next);
  }

  async function cancel() {
    await authAction({ action: "sign-out" });
    router.replace("/account");
  }

  return (
    <Container className="py-10 lg:py-16">
      <AuthCard title="Enter your authenticator code">
        <p className="mt-2 text-sm text-[color:var(--muted)]">Open your authenticator app and enter the 6-digit code for Deal Intelligence.</p>
        <form className="mt-6 space-y-4" onSubmit={verify}>
          <label className="block text-sm" htmlFor="mfa-code">Code</label>
          <input id="mfa-code" className="field w-full text-center text-2xl tracking-[0.4em]" inputMode="numeric" autoComplete="one-time-code"
            pattern="\d{6}" maxLength={6} required autoFocus value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
          <button className="btn btn-primary w-full justify-center" type="submit" disabled={busy || code.length !== 6 || !factorId}>{busy ? "Checking…" : "Verify"}</button>
        </form>
        <button className="mt-4 text-sm underline underline-offset-4" type="button" onClick={cancel}>Use a different account</button>
        <Notice error={error} />
      </AuthCard>
    </Container>
  );
}
