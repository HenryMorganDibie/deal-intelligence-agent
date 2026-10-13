"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { AuthForm } from "../../components/app/AuthForm";
import { LogoMark } from "../../components/primitives";
import { isAuthConfigured, safeNext, supabase } from "../../lib/supabase";

function Login() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));

  useEffect(() => {
    if (!isAuthConfigured) return;
    supabase()
      .auth.getSession()
      .then(({ data }) => data.session && router.replace(next));
  }, [next, router]);

  return (
    <main className="noise relative grid min-h-screen place-items-center overflow-hidden px-4 py-16">
      <div aria-hidden className="grid-bg absolute inset-0" />
      <div className="relative w-full max-w-sm">
        <Link href="/" className="mb-10 flex items-center justify-center gap-2.5 text-[0.9375rem] font-medium">
          <LogoMark />
          Deal Intelligence
        </Link>
        <div className="panel p-6 sm:p-7">
          <h1 className="h3 text-xl">Sign in to run briefs</h1>
          <p className="mt-2 text-sm leading-relaxed text-[color:var(--muted)]">
            Free while in beta. Your briefs are private to your account.
          </p>
          <div className="mt-6">
            <AuthForm next={next} />
          </div>
        </div>
        <p className="mt-6 text-center text-xs leading-relaxed text-[color:var(--dim)]">
          Research tooling, not investment advice. Briefs are AI-assisted and should be reviewed before use.
        </p>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <Login />
    </Suspense>
  );
}
