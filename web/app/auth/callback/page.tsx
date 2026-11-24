"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Container } from "../../../components/primitives";
import { apiUrl } from "../../../lib/api-base";

export default function AuthCallbackPage() {
  const router = useRouter();
  const [message, setMessage] = useState("Completing sign-in…");

  useEffect(() => {
    let active = true;
    async function complete() {
      const params = new URLSearchParams(window.location.search);
      const oauthCode = params.get("code") || "";
      const oauthError = params.get("error_description") || params.get("error") || "";
      const tokenHash = params.get("token_hash") || "";
      const type = params.get("type") || "";
      const next = params.get("next") === "password-reset" ? "password-reset" : "";
      const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
      const refreshToken = fragment.get("refresh_token") || "";
      const fragmentType = fragment.get("type") || "";

      window.history.replaceState({}, document.title, window.location.pathname);

      try {
        let response: Response;
        if (oauthError) {
          // A new Google account refused while the owner has paused sign-ups arrives as a database error.
          let text = oauthError;
          if (/database error|signups_paused/i.test(oauthError)) {
            const settings = await fetch(apiUrl("/api/site-settings")).then((r) => (r.ok ? r.json() : null)).catch(() => null) as
              { signups?: { open?: boolean; message?: string | null } } | null;
            if (settings?.signups?.open === false) {
              text = settings.signups.message || "New sign-ups are paused for a short while. If you already have an account, sign in as usual.";
            }
          }
          if (active) setMessage(text);
          return;
        } else if (oauthCode) {
          response = await fetch("/api/portfolio/auth", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "complete-oauth", code: oauthCode }),
          });
        } else if (tokenHash && type) {
          response = await fetch("/api/portfolio/auth", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "verify-email", tokenHash, type }),
          });
        } else if (refreshToken && ["signup", "email", "invite", "recovery", "magiclink"].includes(fragmentType)) {
          response = await fetch("/api/portfolio/auth", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "complete-email", refreshToken }),
          });
        } else {
          if (active) setMessage("This confirmation link is incomplete or has expired. Return to sign in and request a new link.");
          return;
        }

        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          if (active) setMessage(payload.error || "The confirmation link is invalid or expired.");
          return;
        }
        router.replace(type === "recovery" || fragmentType === "recovery" || next === "password-reset" ? "/account/reset-password" : "/deals");
      } catch {
        if (active) setMessage("Could not confirm the account. Return to sign in and try again.");
      }
    }
    void complete();
    return () => { active = false; };
  }, [router]);

  return (
    <Container className="py-12">
      <div className="mx-auto max-w-xl rounded-2xl border border-[color:var(--border)] p-6">
        <h1 className="text-xl font-semibold">Account confirmation</h1>
        <p className="mt-3 text-sm text-[color:var(--muted)]" role="status">{message}</p>
        <a className="mt-5 inline-flex text-sm underline" href="/account">Return to sign in</a>
      </div>
    </Container>
  );
}
