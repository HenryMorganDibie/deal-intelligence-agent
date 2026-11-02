// Signed, short-lived cache of two per-account facts the app gate needs on every navigation: whether the account has
// a verified second factor, and whether it has chosen a username. HMAC-signed with AUTH_STATE_SECRET so it cannot
// be forged; if it is missing, stale or for another account, the gate asks Supabase again, so deleting it cannot
// skip a check. Uses Web Crypto so it runs in middleware and in route handlers alike.

export const AUTH_STATE_COOKIE = "di_auth_state";
export const AUTH_STATE_TTL_SECONDS = 60 * 30;

export type AuthState = { sub: string; mfa: boolean; profile: boolean; exp: number };

const encoder = new TextEncoder();

function b64url(bytes: ArrayBuffer | Uint8Array): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = "";
  arr.forEach((b) => { s += String.fromCharCode(b); });
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromB64url(s: string): string {
  return atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4));
}

async function key(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

export async function signAuthState(state: Omit<AuthState, "exp">, secret: string): Promise<string> {
  const body = b64url(encoder.encode(JSON.stringify({ ...state, exp: Math.floor(Date.now() / 1000) + AUTH_STATE_TTL_SECONDS })));
  const sig = await crypto.subtle.sign("HMAC", await key(secret), encoder.encode(body));
  return `${body}.${b64url(sig)}`;
}

export async function readAuthState(token: string | undefined, secret: string, sub: string): Promise<AuthState | null> {
  if (!token || !secret) return null;
  const [body, sig] = token.split(".");
  if (!body || !sig) return null;
  try {
    const sigBytes = Uint8Array.from(fromB64url(sig), (c) => c.charCodeAt(0));
    const ok = await crypto.subtle.verify("HMAC", await key(secret), sigBytes, encoder.encode(body));
    if (!ok) return null;
    const state = JSON.parse(fromB64url(body)) as AuthState;
    if (state.sub !== sub || state.exp < Math.floor(Date.now() / 1000)) return null;
    return state;
  } catch {
    return null;
  }
}
