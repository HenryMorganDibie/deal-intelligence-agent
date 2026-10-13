"use client";

import type { Session } from "@supabase/supabase-js";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { isAuthConfigured, supabase } from "../../lib/supabase";
import { Container, LogoMark } from "../primitives";

const SessionContext = createContext<Session | null>(null);

/** The signed-in session. Only valid inside <AppShell>, which renders nothing until it exists. */
export function useSession(): Session {
  const s = useContext(SessionContext);
  if (!s) throw new Error("useSession outside AppShell");
  return s;
}

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    const toLogin = () => router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    if (!isAuthConfigured) return toLogin();
    const auth = supabase().auth;
    auth.getSession().then(({ data }) => (data.session ? setSession(data.session) : toLogin()));
    const { data } = auth.onAuthStateChange((_event, s) => {
      if (s) setSession(s);
      else toLogin();
    });
    return () => data.subscription.unsubscribe();
  }, [pathname, router]);

  if (!session) {
    return (
      <div className="grid min-h-screen place-items-center">
        <p className="kbd text-[color:var(--muted)]">Loading...</p>
      </div>
    );
  }

  return (
    <SessionContext.Provider value={session}>
      <header className="sticky top-0 z-40 border-b hairline bg-[rgba(7,8,10,0.85)] backdrop-blur-xl">
        <Container className="flex h-14 items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-6">
            <Link href="/" className="flex shrink-0 items-center gap-2.5 text-[0.9375rem] font-medium tracking-tight">
              <LogoMark />
              <span className="hidden sm:inline">Deal Intelligence</span>
            </Link>
            <nav aria-label="App">
              <Link
                href="/app"
                className={`text-sm transition-colors ${
                  pathname === "/app" ? "text-[color:var(--text)]" : "text-[color:var(--muted)] hover:text-[color:var(--text)]"
                }`}
              >
                Briefs
              </Link>
            </nav>
          </div>
          <div className="flex min-w-0 items-center gap-3">
            <span className="hidden truncate text-[0.8125rem] text-[color:var(--muted)] sm:block">{session.user.email}</span>
            <button
              type="button"
              className="btn btn-ghost h-8 shrink-0 px-3 text-[0.8125rem]"
              onClick={async () => {
                await supabase().auth.signOut();
                router.replace("/");
              }}
            >
              Sign out
            </button>
          </div>
        </Container>
      </header>
      <main id="main">{children}</main>
    </SessionContext.Provider>
  );
}
