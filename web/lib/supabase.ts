import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Supabase handles sign-in (GitHub, Google, or email and password) and stores
 * each user's briefs. The browser keeps the Supabase session; the API checks
 * its access token, and row level security limits every read to the owner.
 */
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
const SUPABASE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();

export type OAuthProvider = "github" | "google";

export const isAuthConfigured = Boolean(SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY);

let client: SupabaseClient | null = null;

export function supabase(): SupabaseClient {
  if (!SUPABASE_URL || !SUPABASE_PUBLISHABLE_KEY) throw new Error("auth_not_configured");
  client ??= createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    auth: { flowType: "pkce", persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
  });
  return client;
}

/** Only same-site paths are allowed as a post-sign-in destination. */
export function safeNext(next: string | null | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/app";
}

/** Starts the OAuth redirect; the provider sends the browser back to /auth/callback. */
export async function startOAuth(provider: OAuthProvider, next: string) {
  const redirectTo = `${window.location.origin}/auth/callback?next=${encodeURIComponent(safeNext(next))}`;
  const { error } = await supabase().auth.signInWithOAuth({ provider, options: { redirectTo } });
  if (error) throw error;
}

export async function currentSession(): Promise<Session | null> {
  const { data } = await supabase().auth.getSession();
  return data.session;
}
