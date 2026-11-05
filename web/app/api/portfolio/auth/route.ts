import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import {
  clearPortfolioAuthCookies,
  getPortfolioSession,
  isSameSiteJsonRequest,
  portfolioConfig,
  setPortfolioAuthCookies,
} from "../../../../lib/portfolio-server";
import { AUTH_STATE_COOKIE } from "../../../../lib/auth-state";
import { displayNameProblem, normaliseUsername, passwordProblems, usernameProblem } from "../../../../lib/password-policy";
import { passwordBreached } from "../../../../lib/pwned";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Factor = { id: string; factor_type?: string; status?: string; friendly_name?: string };
type AuthUser = { id: string; email?: string | null; factors?: Factor[] };
type AuthPayload = {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  user?: AuthUser;
  message?: string;
  msg?: string;
};
type Body = {
  action?: string; email?: string; password?: string; confirmPassword?: string; currentPassword?: string;
  username?: string; displayName?: string; refreshToken?: unknown; tokenHash?: unknown; type?: unknown; code?: unknown;
  factorId?: unknown;
};

const NO_STORE = { "Cache-Control": "no-store" };
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function ok(body: Record<string, unknown> = {}, status = 200) {
  return NextResponse.json({ ok: true, ...body }, { status, headers: NO_STORE });
}

function fail(error: string, status = 400) {
  return NextResponse.json({ error }, { status, headers: NO_STORE });
}

/** The gate caches account facts (second factor, username); anything that changes them drops the cache. */
function dropAuthState() {
  cookies().set(AUTH_STATE_COOKIE, "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 0 });
}

function verifiedFactor(user?: AuthUser): Factor | undefined {
  return (user?.factors || []).find((f) => f.status === "verified" && (f.factor_type || "totp") === "totp");
}

/** Rules, confirmation and the breached-password check, in that order; the first failure as a message. */
async function newPasswordProblem(password: string, confirm: string | undefined, ctx: { email?: string; username?: string }) {
  const problems = passwordProblems(password, ctx);
  if (problems.length) return `Your password needs: ${problems.join(", ").toLowerCase()}.`;
  if (confirm !== undefined && password !== confirm) return "The two passwords do not match.";
  if (await passwordBreached(password)) {
    return "This password has appeared in a known data breach. Choose a different one.";
  }
  return null;
}

async function supabase(path: string, init: RequestInit & { token?: string } = {}) {
  const config = portfolioConfig();
  const headers = new Headers(init.headers || {});
  headers.set("apikey", config.key);
  if (init.token) headers.set("Authorization", "Bearer " + init.token);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return fetch(config.url + path, { ...init, headers, cache: "no-store" });
}

async function profileOf(accessToken: string, userId: string) {
  const r = await supabase(`/rest/v1/profiles?select=username,display_name&user_id=eq.${encodeURIComponent(userId)}`, { token: accessToken });
  if (!r.ok) return null;
  const rows = (await r.json()) as { username: string; display_name: string }[];
  return rows[0] ? { username: rows[0].username, displayName: rows[0].display_name } : null;
}

function aalOf(accessToken: string): string | null {
  try {
    return (JSON.parse(Buffer.from(accessToken.split(".")[1], "base64url").toString("utf8")) as { aal?: string }).aal ?? null;
  } catch {
    return null;
  }
}

export async function GET() {
  try {
    const session = await getPortfolioSession();
    if (!session) return NextResponse.json({ authenticated: false }, { status: 401, headers: NO_STORE });
    const [userRes, profile] = await Promise.all([supabase("/auth/v1/user", { token: session.accessToken }), profileOf(session.accessToken, session.user.id)]);
    const user = userRes.ok ? ((await userRes.json()) as AuthUser) : session.user;
    const factor = verifiedFactor(user);
    return NextResponse.json({
      authenticated: true,
      user: { id: user.id, email: user.email ?? null },
      profile,
      mfa: { enrolled: Boolean(factor), factorId: factor?.id ?? null, aal: aalOf(session.accessToken) },
    }, { headers: NO_STORE });
  } catch {
    return fail("Authentication is not configured or is temporarily unavailable.", 503);
  }
}

export async function POST(request: NextRequest) {
  if (!isSameSiteJsonRequest(request)) return fail("Invalid request.", 403);
  let body: Body;
  try {
    body = await request.json();
  } catch {
    return fail("Invalid request body.");
  }

  try {
    const config = portfolioConfig();
    const action = body.action;

    if (action === "check-username") {
      const username = normaliseUsername(typeof body.username === "string" ? body.username : "");
      const problem = usernameProblem(username);
      if (problem) return ok({ available: false, problem });
      const r = await supabase("/rest/v1/rpc/username_available", { method: "POST", body: JSON.stringify({ p_username: username }) });
      if (!r.ok) return fail("Could not check that username right now.", 503);
      const available = (await r.json()) === true;
      return ok({ available, problem: available ? null : "That username is taken or reserved." });
    }

    if (action === "recover-password") {
      const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
      if (!EMAIL_RE.test(email) || email.length > 254) return fail("Enter a valid account email.");
      const response = await fetch(config.url + "/auth/v1/recover?redirect_to=" + encodeURIComponent(request.nextUrl.origin + "/auth/callback?next=password-reset"), {
        method: "POST",
        headers: { apikey: config.key, "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
        cache: "no-store",
      });
      if (response.status === 429) return fail("Too many requests. Please wait before trying again.", 429);
      if (!response.ok) return fail("Could not request a password reset. Please try again later.", 503);
      // The same answer whether or not the address has an account.
      return ok();
    }

    if (action === "update-password") {
      const password = typeof body.password === "string" ? body.password : "";
      const session = await getPortfolioSession();
      if (!session) return fail("Your reset session has expired. Request a new password-reset link.", 401);
      const problem = await newPasswordProblem(password, typeof body.confirmPassword === "string" ? body.confirmPassword : undefined, { email: session.user.email ?? undefined });
      if (problem) return fail(problem);
      const response = await supabase("/auth/v1/user", { method: "PUT", token: session.accessToken, body: JSON.stringify({ password }) });
      if (!response.ok) return fail("The password could not be updated. Request a fresh reset link and try again.", response.status === 429 ? 429 : 400);
      return ok();
    }

    if (action === "complete-oauth") {
      const code = typeof body.code === "string" ? body.code : "";
      const verifier = request.cookies.get("di_portfolio_oauth_verifier")?.value || "";
      if (!code || code.length > 4096 || !/^[A-Za-z0-9._~-]{43,128}$/.test(verifier)) {
        const response = fail("Google sign-in could not be completed. Start again.");
        response.cookies.set("di_portfolio_oauth_verifier", "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 0 });
        return response;
      }
      const exchange = await supabase("/auth/v1/token?grant_type=pkce", { method: "POST", body: JSON.stringify({ auth_code: code, code_verifier: verifier }) });
      const payload = (await exchange.json().catch(() => ({}))) as AuthPayload;
      const success = exchange.ok && payload.access_token && payload.refresh_token && payload.user?.id;
      const response = success ? ok({ user: { id: payload.user!.id, email: payload.user!.email ?? null } })
        : fail("Google sign-in failed or the sign-in link expired. Please try again.");
      if (success) { setPortfolioAuthCookies(payload); dropAuthState(); }
      response.cookies.set("di_portfolio_oauth_verifier", "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 0 });
      return response;
    }

    if (action === "complete-email") {
      const refreshToken = typeof body.refreshToken === "string" ? body.refreshToken : "";
      if (refreshToken.length < 20 || refreshToken.length > 4096) return fail("The confirmation link is invalid or expired.");
      const response = await supabase("/auth/v1/token?grant_type=refresh_token", { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) });
      const payload = (await response.json().catch(() => ({}))) as AuthPayload;
      if (!response.ok || !payload.access_token || !payload.refresh_token || !payload.user?.id) return fail("The confirmation link is invalid or expired.");
      setPortfolioAuthCookies(payload);
      dropAuthState();
      return ok({ user: { id: payload.user.id, email: payload.user.email ?? null } });
    }

    if (action === "verify-email") {
      const tokenHash = typeof body.tokenHash === "string" ? body.tokenHash : "";
      const type = typeof body.type === "string" ? body.type : "";
      if (!/^[a-f0-9]{32,128}$/i.test(tokenHash) || !["signup", "email", "invite", "recovery"].includes(type)) {
        return fail("The confirmation link is invalid or expired.");
      }
      const response = await supabase("/auth/v1/verify", { method: "POST", body: JSON.stringify({ token_hash: tokenHash, type }) });
      const payload = (await response.json().catch(() => ({}))) as AuthPayload;
      if (!response.ok || !payload.access_token || !payload.refresh_token || !payload.user?.id) return fail("The confirmation link is invalid or expired.");
      setPortfolioAuthCookies(payload);
      dropAuthState();
      return ok({ user: { id: payload.user.id, email: payload.user.email ?? null } });
    }

    if (action === "sign-out" || action === "sign-out-everywhere") {
      const session = await getPortfolioSession().catch(() => null);
      if (session) {
        // Supabase's logout defaults to every device; a plain sign-out ends only this session.
        await supabase(`/auth/v1/logout?scope=${action === "sign-out-everywhere" ? "global" : "local"}`, { method: "POST", token: session.accessToken }).catch(() => undefined);
      }
      clearPortfolioAuthCookies();
      dropAuthState();
      return ok();
    }

    // Everything below needs a signed-in session.
    if (["set-profile", "change-password", "mfa-enroll", "mfa-verify", "mfa-unenroll"].includes(action || "")) {
      const session = await getPortfolioSession();
      if (!session) return fail("Please sign in again.", 401);

      if (action === "set-profile") {
        const username = normaliseUsername(typeof body.username === "string" ? body.username : "");
        const displayName = (typeof body.displayName === "string" ? body.displayName : "").trim();
        const problem = usernameProblem(username) || displayNameProblem(displayName);
        if (problem) return fail(problem);
        const r = await supabase("/rest/v1/rpc/set_my_profile", { method: "POST", token: session.accessToken, body: JSON.stringify({ p_username: username, p_display_name: displayName }) });
        if (!r.ok) {
          const text = await r.text();
          return fail(text.includes("username_taken") ? "That username is taken. Choose another." : "The profile could not be saved.", text.includes("username_taken") ? 409 : 400);
        }
        dropAuthState();
        return ok({ profile: { username, displayName } });
      }

      if (action === "change-password") {
        const email = session.user.email || "";
        const current = typeof body.currentPassword === "string" ? body.currentPassword : "";
        const password = typeof body.password === "string" ? body.password : "";
        if (!email || !current) return fail("Enter your current password.");
        if (current === password) return fail("Choose a password different from your current one.");
        const profile = await profileOf(session.accessToken, session.user.id);
        const problem = await newPasswordProblem(password, typeof body.confirmPassword === "string" ? body.confirmPassword : undefined, { email, username: profile?.username });
        if (problem) return fail(problem);
        // Re-authenticate with the current password; the session that check creates is closed straight away.
        const check = await supabase("/auth/v1/token?grant_type=password", { method: "POST", body: JSON.stringify({ email, password: current }) });
        if (!check.ok) return fail("Your current password is incorrect.", check.status === 429 ? 429 : 400);
        const checked = (await check.json().catch(() => ({}))) as AuthPayload;
        if (checked.access_token) await supabase("/auth/v1/logout?scope=local", { method: "POST", token: checked.access_token }).catch(() => undefined);
        const r = await supabase("/auth/v1/user", { method: "PUT", token: session.accessToken, body: JSON.stringify({ password }) });
        if (!r.ok) return fail(r.status === 403 ? "Confirm your authenticator code first, then change your password." : "The password could not be changed.", r.status === 429 ? 429 : 400);
        return ok();
      }

      if (action === "mfa-enroll") {
        const userRes = await supabase("/auth/v1/user", { token: session.accessToken });
        const user = userRes.ok ? ((await userRes.json()) as AuthUser) : null;
        if (verifiedFactor(user ?? undefined)) return fail("An authenticator app is already set up.");
        // Clear any half-finished enrolment first.
        for (const f of (user?.factors || []).filter((x) => x.status !== "verified")) {
          await supabase(`/auth/v1/factors/${f.id}`, { method: "DELETE", token: session.accessToken }).catch(() => undefined);
        }
        const r = await supabase("/auth/v1/factors", { method: "POST", token: session.accessToken, body: JSON.stringify({ factor_type: "totp", friendly_name: `Authenticator ${new Date().toISOString().slice(0, 10)}`, issuer: "Deal Intelligence" }) });
        const factor = (await r.json().catch(() => ({}))) as { id?: string; totp?: { qr_code?: string; secret?: string; uri?: string } };
        if (!r.ok || !factor.id || !factor.totp) return fail("Two-factor setup could not be started. Try again.", 503);
        return ok({ factorId: factor.id, qrCode: factor.totp.qr_code, secret: factor.totp.secret, uri: factor.totp.uri });
      }

      if (action === "mfa-verify") {
        const factorId = typeof body.factorId === "string" ? body.factorId : "";
        const code = typeof body.code === "string" ? body.code.replace(/\s/g, "") : "";
        if (!/^[0-9a-f-]{36}$/i.test(factorId) || !/^\d{6}$/.test(code)) return fail("Enter the 6-digit code from your authenticator app.");
        const challenge = await supabase(`/auth/v1/factors/${factorId}/challenge`, { method: "POST", token: session.accessToken, body: "{}" });
        const c = (await challenge.json().catch(() => ({}))) as { id?: string };
        if (!challenge.ok || !c.id) return fail("Could not start the verification. Try again.", challenge.status === 429 ? 429 : 400);
        const verify = await supabase(`/auth/v1/factors/${factorId}/verify`, { method: "POST", token: session.accessToken, body: JSON.stringify({ challenge_id: c.id, code }) });
        const payload = (await verify.json().catch(() => ({}))) as AuthPayload;
        if (!verify.ok || !payload.access_token || !payload.refresh_token) return fail("That code is not right or has expired. Try the current one.", verify.status === 429 ? 429 : 400);
        setPortfolioAuthCookies(payload);
        dropAuthState();
        return ok();
      }

      if (action === "mfa-unenroll") {
        const factorId = typeof body.factorId === "string" ? body.factorId : "";
        if (!/^[0-9a-f-]{36}$/i.test(factorId)) return fail("Unknown authenticator.");
        if (aalOf(session.accessToken) !== "aal2") return fail("Enter a code from your authenticator app first.", 403);
        const r = await supabase(`/auth/v1/factors/${factorId}`, { method: "DELETE", token: session.accessToken });
        if (!r.ok) return fail("The authenticator could not be removed.", r.status === 403 ? 403 : 400);
        dropAuthState();
        return ok();
      }
    }

    if (action === "sign-up") {
      const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
      const password = typeof body.password === "string" ? body.password : "";
      const username = normaliseUsername(typeof body.username === "string" ? body.username : "");
      const displayName = (typeof body.displayName === "string" ? body.displayName : "").trim();
      if (!EMAIL_RE.test(email) || email.length > 254) return fail("Enter a valid email address.");
      const fieldProblem = usernameProblem(username) || displayNameProblem(displayName);
      if (fieldProblem) return fail(fieldProblem);
      const problem = await newPasswordProblem(password, typeof body.confirmPassword === "string" ? body.confirmPassword : "", { email, username });
      if (problem) return fail(problem);
      const available = await supabase("/rest/v1/rpc/username_available", { method: "POST", body: JSON.stringify({ p_username: username }) });
      if (available.ok && (await available.json()) !== true) return fail("That username is taken or reserved. Choose another.", 409);
      const response = await supabase("/auth/v1/signup", {
        method: "POST",
        body: JSON.stringify({ email, password, data: { username, display_name: displayName }, options: { emailRedirectTo: request.nextUrl.origin + "/auth/callback" } }),
      });
      const payload = (await response.json().catch(() => ({}))) as AuthPayload;
      if (!response.ok) {
        const text = JSON.stringify(payload);
        if (response.status === 429) return fail("Too many sign-up attempts. Please wait a few minutes.", 429);
        // The profile trigger rejected the username (taken a moment ago): the only database error a valid request can hit.
        if (response.status >= 500 || /database error/i.test(text)) return fail("That username was just taken. Choose another.", 409);
        if (/password/i.test(text)) return fail("That password is not accepted. Choose a longer or more varied one.");
        return fail("Account creation failed. Check the details and try again.");
      }
      if (payload.access_token && payload.refresh_token && payload.user?.id) {
        setPortfolioAuthCookies(payload);
        dropAuthState();
        return ok({ user: { id: payload.user.id, email: payload.user.email ?? null } });
      }
      // The same answer whether or not the address already had an account.
      return ok({ needsEmailConfirmation: true, message: "Check your email to confirm your account, then sign in." }, 202);
    }

    if (action === "sign-in") {
      const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
      const password = typeof body.password === "string" ? body.password : "";
      if (!EMAIL_RE.test(email) || !password || password.length > 128) return fail("Enter your email and password.");
      const response = await supabase("/auth/v1/token?grant_type=password", { method: "POST", body: JSON.stringify({ email, password }) });
      const payload = (await response.json().catch(() => ({}))) as AuthPayload;
      if (!response.ok || !payload.access_token || !payload.refresh_token || !payload.user?.id) {
        if (response.status === 429) return fail("Too many sign-in attempts. Please wait a few minutes.", 429);
        const text = JSON.stringify(payload);
        if (/email not confirmed/i.test(text)) return fail("Confirm your email first: use the link we sent you.", 403);
        return fail("Sign-in failed. Check your email and password.");
      }
      setPortfolioAuthCookies(payload);
      dropAuthState();
      const factor = verifiedFactor(payload.user);
      return ok({ user: { id: payload.user.id, email: payload.user.email ?? null }, mfaRequired: Boolean(factor), factorId: factor?.id ?? null });
    }

    return fail("Unsupported authentication action.");
  } catch {
    return fail("Authentication is not configured or is temporarily unavailable.", 503);
  }
}
