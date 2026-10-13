"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { safeNext, supabase } from "../../../lib/supabase";

/** OAuth and email-confirmation return leg: PKCE code -> Supabase session. */
function Callback() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const next = safeNext(params.get("next"));
    const code = params.get("code");
    if (!code) {
      setError(params.get("error_description") ?? "Sign-in was cancelled.");
      return;
    }
    supabase()
      .auth.exchangeCodeForSession(code)
      .then(({ data, error: err }) => {
        if (err || !data.session) throw err ?? new Error("no session");
        router.replace(next);
      })
      .catch(() => setError("We couldn't finish signing you in. The link may have expired; please try again."));
  }, [params, router]);

  return (
    <main className="mx-auto grid min-h-screen max-w-sm place-items-center px-6">
      {error ? (
        <div role="alert" className="text-center">
          <h1 className="h3 mb-3 text-xl">Sign-in did not complete</h1>
          <p className="mb-6 text-sm text-[color:var(--muted)]">{error}</p>
          <Link href="/login" className="btn btn-primary">
            Back to sign in
          </Link>
        </div>
      ) : (
        <p className="text-[color:var(--muted)]">Signing you in...</p>
      )}
    </main>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense>
      <Callback />
    </Suspense>
  );
}
