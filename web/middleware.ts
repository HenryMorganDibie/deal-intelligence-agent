import { NextResponse, type NextFetchEvent, type NextRequest } from "next/server";
import { createRemoteJWKSet, jwtVerify, type JWTPayload } from "jose";
import { AUTH_STATE_COOKIE, AUTH_STATE_TTL_SECONDS, readAuthState, signAuthState } from "./lib/auth-state";

// The app lives at the site's own addresses (/deals, /markets, /companies...); its pages are files under app/app/ and
// are served there by a rewrite here. Old /app/... links redirect permanently to the short address.
//   - App-only pages (/companies, /countries, /investors...) need a signed-in account.
//   - The home page (/) is the public site for everyone; the app's home is /briefs.
//   - Shared pages (/deals, /deals/<id>, /markets, /coverage) also have a public version: a signed-in visitor
//     gets the app, everyone else (and search engines) the public page.
// A signed-in account is checked here:
//   1. the session token's signature is verified against Supabase's published signing key (ES256);
//   2. an expired session is renewed with the refresh token;
//   3. an account with an authenticator app must have completed the second step (aal2);
//   4. an account must have chosen a username.
// Otherwise the visitor goes to the right page with a return path.

const ACCESS = "di_portfolio_access";
const REFRESH = "di_portfolio_refresh";
const SUPABASE_URL = (process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/+$/, "");
const SUPABASE_KEY = process.env.SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || "";
const STATE_SECRET = process.env.AUTH_STATE_SECRET || "";
const JWKS = SUPABASE_URL ? createRemoteJWKSet(new URL(`${SUPABASE_URL}/auth/v1/.well-known/jwks.json`)) : null;

type Claims = JWTPayload & { aal?: string; sub: string };

async function verify(token: string | undefined): Promise<Claims | null> {
  if (!token || !JWKS) return null;
  try {
    const { payload } = await jwtVerify(token, JWKS, { issuer: `${SUPABASE_URL}/auth/v1`, audience: "authenticated" });
    return payload.sub ? (payload as Claims) : null;
  } catch {
    return null;
  }
}

function cookieOptions(maxAge: number) {
  return { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax" as const, path: "/", maxAge };
}

function redirectTo(request: NextRequest, pathname: string): NextResponse {
  const url = request.nextUrl.clone();
  url.pathname = pathname;
  url.search = `?next=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}`;
  return NextResponse.redirect(url);
}

async function accountFacts(accessToken: string, sub: string): Promise<{ mfa: boolean; profile: boolean } | null> {
  const headers = { apikey: SUPABASE_KEY, Authorization: `Bearer ${accessToken}` };
  try {
    const [user, profile] = await Promise.all([
      fetch(`${SUPABASE_URL}/auth/v1/user`, { headers, cache: "no-store" }),
      fetch(`${SUPABASE_URL}/rest/v1/profiles?select=username&user_id=eq.${encodeURIComponent(sub)}`, { headers, cache: "no-store" }),
    ]);
    if (!user.ok || !profile.ok) return null;
    const factors = ((await user.json()) as { factors?: { status?: string }[] }).factors || [];
    const rows = (await profile.json()) as unknown[];
    return { mfa: factors.some((f) => f.status === "verified"), profile: Array.isArray(rows) && rows.length > 0 };
  } catch {
    return null;
  }
}

// Browser calls to the data API arrive at this site's /api/data/* and are forwarded to the API's /api/* with the
// web app's secret added here, on the server. The API refuses /api/* requests without it, so its internal routes
// cannot be used as a free substitute for the key-authenticated /v1. Cookies stay on this site: the API never
// sees sign-in tokens. The visitor's address travels in a header the API trusts only alongside the secret, so
// per-visitor limits keep working.
const API_ORIGIN = (process.env.NEXT_PUBLIC_API_URL || "").trim().replace(/\/$/, "");
const WEB_SECRET = process.env.DEAL_INTEL_WEB_SECRET || "";

async function proxyToApi(request: NextRequest): Promise<NextResponse> {
  if (!API_ORIGIN) return NextResponse.json({ detail: "The API is not configured." }, { status: 503 });
  const rest = request.nextUrl.pathname.slice("/api/data/".length);
  const target = new URL(`${API_ORIGIN}/api/${rest}${request.nextUrl.search}`);
  const headers = new Headers(request.headers);
  // The signed-in account, from a verified session token only; whatever a browser sends in this header is dropped.
  headers.delete("x-deal-intel-user");
  const claims = await verify(request.cookies.get(ACCESS)?.value);
  if (claims?.sub) headers.set("x-deal-intel-user", claims.sub);
  headers.delete("cookie");
  headers.delete("authorization");
  if (WEB_SECRET) headers.set("x-deal-intel-client", WEB_SECRET);
  const ip = request.ip || (request.headers.get("x-forwarded-for") || "").split(",")[0].trim();
  if (ip) headers.set("x-deal-intel-client-ip", ip);
  else headers.delete("x-deal-intel-client-ip");
  return NextResponse.rewrite(target, { request: { headers } });
}

const SHARED = [/^\/deals$/, /^\/deals\/[^/]+$/, /^\/markets$/, /^\/coverage$/];
const APP_ONLY = [
  /^\/api-keys$/, /^\/briefs$/, /^\/briefs\/[^/]+$/, /^\/companies$/, /^\/countries(\/[^/]+)?$/, /^\/elections(\/.*)?$/, /^\/evaluation$/,
  /^\/investors(\/[^/]+)?$/, /^\/market-briefs\/.+$/, /^\/research$/, /^\/watchlists(\/[^/]+)?$/,
  /^\/markets\/(compare|investments|monitoring|portfolio|portfolio\/cloud|screener|valuation)$/,
];

/** Which kind of page a path is: one only the app has, one with a public version too, or neither. */
function pageKind(path: string): "app" | "shared" | null {
  if (APP_ONLY.some((re) => re.test(path))) return "app";
  if (SHARED.some((re) => re.test(path))) return "shared";
  return null;
}

function appRewrite(request: NextRequest): NextResponse {
  const url = request.nextUrl.clone();
  // /briefs is the app's home page (app/app/page.tsx); every other page sits at /app + its address.
  url.pathname = request.nextUrl.pathname === "/briefs" ? "/app" : `/app${request.nextUrl.pathname}`;
  return NextResponse.rewrite(url);
}

export async function middleware(request: NextRequest, event: NextFetchEvent) {
  const path = request.nextUrl.pathname;
  if (path.startsWith("/api/data/")) return await proxyToApi(request);
  if (path === "/app" || path.startsWith("/app/")) {             // old links: the short address, permanently
    const url = request.nextUrl.clone();
    url.pathname = path.slice(4) || "/briefs";
    return NextResponse.redirect(url, 308);
  }
  const kind = pageKind(path);
  if (!kind) return NextResponse.next();
  // Browser tests run against a local production build without an account; never in a Vercel production deploy.
  if (process.env.DI_E2E_AUTH_BYPASS === "1" && process.env.VERCEL_ENV !== "production") return appRewrite(request);
  // A visitor with no session at all sees a shared page's public version straight away.
  if (kind === "shared" && !request.cookies.get(ACCESS)?.value && !request.cookies.get(REFRESH)?.value) return NextResponse.next();
  if (!SUPABASE_URL || !SUPABASE_KEY) return kind === "shared" ? NextResponse.next() : redirectTo(request, "/account");

  let accessToken = request.cookies.get(ACCESS)?.value;
  let claims = await verify(accessToken);
  const renewed: { access_token?: string; refresh_token?: string; expires_in?: number } = {};

  if (!claims) {
    const refreshToken = request.cookies.get(REFRESH)?.value;
    if (refreshToken) {
      try {
        const r = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`, {
          method: "POST",
          headers: { apikey: SUPABASE_KEY, "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
          cache: "no-store",
        });
        if (r.ok) Object.assign(renewed, await r.json());
      } catch { /* treated as signed out */ }
      accessToken = renewed.access_token;
      claims = await verify(accessToken);
    }
  }
  if (!claims || !accessToken) {
    const response = kind === "shared" ? NextResponse.next() : redirectTo(request, "/account");
    response.cookies.set(ACCESS, "", cookieOptions(0));
    response.cookies.set(REFRESH, "", cookieOptions(0));
    return response;
  }

  let stateCookie: string | null = null;
  let state = await readAuthState(request.cookies.get(AUTH_STATE_COOKIE)?.value, STATE_SECRET, claims.sub);
  if (!state) {
    const facts = await accountFacts(accessToken, claims.sub);
    if (!facts) return kind === "shared" ? NextResponse.next() : redirectTo(request, "/account");
    state = { sub: claims.sub, ...facts, exp: 0 };
    // Record that this account used the app today (for the owner's admin page). This runs only when the
    // 30-minute account check is renewed, never per page, and never delays the response.
    event.waitUntil(
      fetch(`${SUPABASE_URL}/rest/v1/rpc/touch_my_activity`, {
        method: "POST",
        headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
        body: "{}",
        cache: "no-store",
      }).catch(() => undefined),
    );
    if (STATE_SECRET) stateCookie = await signAuthState({ sub: claims.sub, ...facts }, STATE_SECRET);
  }

  let response: NextResponse;
  if (state.mfa && claims.aal !== "aal2") response = redirectTo(request, "/account/mfa");
  else if (!state.profile) response = redirectTo(request, "/account/profile");
  else response = appRewrite(request);

  if (renewed.access_token && renewed.refresh_token) {
    response.cookies.set(ACCESS, renewed.access_token, cookieOptions(Math.max(60, renewed.expires_in || 3600)));
    response.cookies.set(REFRESH, renewed.refresh_token, cookieOptions(60 * 60 * 24 * 60));
  }
  if (stateCookie) response.cookies.set(AUTH_STATE_COOKIE, stateCookie, cookieOptions(AUTH_STATE_TTL_SECONDS));
  return response;
}

export const config = {
  matcher: ["/app", "/app/:path*", "/api/data/:path*", "/api-keys", "/briefs/:path*", "/companies", "/countries/:path*",
            "/coverage", "/deals/:path*", "/elections/:path*", "/evaluation", "/investors/:path*", "/market-briefs/:path*",
            "/markets/:path*", "/research", "/watchlists/:path*"],
};
