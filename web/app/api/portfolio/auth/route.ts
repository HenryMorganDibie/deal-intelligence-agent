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
import { MINIMUM_AGE, TERMS_VERSION } from "../../../../lib/legal";


const VERIFY_TYPES = ["signup", "email", "invite", "recovery", "magiclink", "email_change"];
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
  factorId?: unknown; ageConfirmed?: unknown; termsVersion?: unknown; missing?: unknown;
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
async function dropAuthState() {
  (await cookies()).set(AUTH_STATE_COOKIE, "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 0 });
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

/** Note a failed attempt for the owner's "Sign-in trouble" list: the address and what went wrong, never a password.
 * Best effort: a failure to record never changes the answer the person gets. */
async function recordTrouble(action: string, reason: string, email?: string) {
  try {
    await supabase("/rest/v1/rpc/record_auth_trouble", {
      method: "POST",
      body: JSON.stringify({ p_action: action, p_reason: reason.slice(0, 300), p_email: email || null }),
      signal: AbortSignal.timeout(2000),
    });
  } catch {
    // Recording is a convenience for support; the person's request has already been answered on its merits.
  }
}

let siteSettingsMemo: { at: number; signups: { open?: boolean; message?: string | null } } | null = null;

/** Whether the owner has paused new sign-ups (set in admin), read at most once a minute; open if unknown. */
async function signupsSetting(fresh = false) {
  if (!fresh && siteSettingsMemo && Date.now() - siteSettingsMemo.at < 60_000) return siteSettingsMemo.signups;
  try {
    const r = await supabase("/rest/v1/rpc/site_settings_public", { method: "POST", body: "{}", signal: AbortSignal.timeout(2000) });
    const data = r.ok ? ((await r.json()) as { signups?: { open?: boolean; message?: string | null } }) : {};
    siteSettingsMemo = { at: Date.now(), signups: data.signups ?? { open: true } };
  } catch {
    siteSettingsMemo = { at: Date.now(), signups: { open: true } };
  }
  return siteSettingsMemo.signups;
}

/** The answer for a failed attempt, recorded for the owner first. */
async function troubled(action: string, email: string, error: string, status = 400) {
  await recordTrouble(action, error, email);
  return fail(error, status);
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
    // getPortfolioSession already verifies the access token with /auth/v1/user.
    // Reuse that response; only request user details again after a refresh response
    // that did not include factor metadata needed for the MFA status.
    const [user, profile] = await Promise.all([
      session.user.factors !== undefined
        ? Promise.resolve(session.user as AuthUser)
        : supabase("/auth/v1/user", { token: session.accessToken }).then(async (r) =>
            r.ok ? ((await r.json()) as AuthUser) : (session.user as AuthUser)
          ),
      profileOf(session.accessToken, session.user.id),
    ]);
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

    if (action === "report-blocked") {
      // The sign-up form was submitted with something still missing; only the address and the missing items arrive.
      const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
      const missing: unknown[] = Array.isArray(body.missing) ? body.missing : [];
      const reason = missing.filter((m): m is string => typeof m === "string").map((m) => m.slice(0, 120)).slice(0, 6).join("; ");
      if (EMAIL_RE.test(email) && reason) await recordTrouble("sign-up", `Form not complete: ${reason}`, email);
      return ok();
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
      if (response.status === 429) return troubled("recover-password", email, "Too many requests. Please wait before trying again.", 429);
      if (!response.ok) return troubled("recover-password", email, "Could not request a password reset. Please try again later.", 503);
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
      if (success) { await setPortfolioAuthCookies(payload); await dropAuthState(); }
      response.cookies.set("di_portfolio_oauth_verifier", "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 0 });
      return response;
    }

    if (action === "complete-email") {
      const refreshToken = typeof body.refreshToken === "string" ? body.refreshToken : "";
      if (refreshToken.length < 20 || refreshToken.length > 4096) return fail("The confirmation link is invalid or expired.");
      const response = await supabase("/auth/v1/token?grant_type=refresh_token", { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) });
      const payload = (await response.json().catch(() => ({}))) as AuthPayload;
      if (!response.ok || !payload.access_token || !payload.refresh_token || !payload.user?.id) return fail("The confirmation link is invalid or expired.");
      await setPortfolioAuthCookies(payload);
      await dropAuthState();
      return ok({ user: { id: payload.user.id, email: payload.user.email ?? null } });
    }

    if (action === "verify-email") {
      const tokenHash = typeof body.tokenHash === "string" ? body.tokenHash : "";
      const type = typeof body.type === "string" ? body.type : "";
      if (!/^(pkce_)?[a-f0-9]{32,128}$/i.test(tokenHash) || !VERIFY_TYPES.includes(type)) {
        return fail("The confirmation link is invalid or expired.");
      }
      const response = await supabase("/auth/v1/verify", { method: "POST", body: JSON.stringify({ token_hash: tokenHash, type }) });
      const payload = (await response.json().catch(() => ({}))) as AuthPayload;
      // With secure email change, the first of the two links is accepted without a session:
      // the change completes once the other address confirms as well.
      if (response.ok && type === "email_change" && !payload.access_token) return ok({ pending: true });
      if (!response.ok || !payload.access_token || !payload.refresh_token || !payload.user?.id) return fail("The confirmation link is invalid or expired.");
      await setPortfolioAuthCookies(payload);
      await dropAuthState();
      return ok({ user: { id: payload.user.id, email: payload.user.email ?? null } });
    }

    if (action === "sign-out" || action === "sign-out-everywhere") {
      const session = await getPortfolioSession().catch(() => null);
      if (session) {
        // Supabase's logout defaults to every device; a plain sign-out ends only this session.
        await supabase(`/auth/v1/logout?scope=${action === "sign-out-everywhere" ? "global" : "local"}`, { method: "POST", token: session.accessToken }).catch(() => undefined);
      }
      await clearPortfolioAuthCookies();
      await dropAuthState();
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
        await dropAuthState();
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
        await setPortfolioAuthCookies(payload);
        await dropAuthState();
        return ok();
      }

      if (action === "mfa-unenroll") {
        const factorId = typeof body.factorId === "string" ? body.factorId : "";
        if (!/^[0-9a-f-]{36}$/i.test(factorId)) return fail("Unknown authenticator.");
        if (aalOf(session.accessToken) !== "aal2") return fail("Enter a code from your authenticator app first.", 403);
        const r = await supabase(`/auth/v1/factors/${factorId}`, { method: "DELETE", token: session.accessToken });
        if (!r.ok) return fail("The authenticator could not be removed.", r.status === 403 ? 403 : 400);
        await dropAuthState();
        return ok();
      }
    }

    if (action === "sign-up") {
      const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
      const password = typeof body.password === "string" ? body.password : "";
      const username = normaliseUsername(typeof body.username === "string" ? body.username : "");
      const displayName = (typeof body.displayName === "string" ? body.displayName : "").trim();
      if (!EMAIL_RE.test(email) || email.length > 254) return fail("Enter a valid email address.");
      const signups = await signupsSetting();
      if (signups.open === false) {
        return troubled("sign-up", email, signups.message || "New sign-ups are paused for a short while. Please try again soon.", 403);
      }
      if (body.ageConfirmed !== true) return troubled("sign-up", email, `You must be ${MINIMUM_AGE} or older to create an account.`);
      const termsVersion = typeof body.termsVersion === "string" && /^\d{4}-\d{2}-\d{2}$/.test(body.termsVersion) ? body.termsVersion : TERMS_VERSION;
      const fieldProblem = usernameProblem(username) || displayNameProblem(displayName);
      if (fieldProblem) return troubled("sign-up", email, fieldProblem);
      const problem = await newPasswordProblem(password, typeof body.confirmPassword === "string" ? body.confirmPassword : "", { email, username });
      if (problem) return troubled("sign-up", email, problem);
      const available = await supabase("/rest/v1/rpc/username_available", { method: "POST", body: JSON.stringify({ p_username: username }) });
      if (available.ok && (await available.json()) !== true) return troubled("sign-up", email, "That username is taken or reserved. Choose another.", 409);
      const response = await supabase("/auth/v1/signup", {
        method: "POST",
        body: JSON.stringify({ email, password, data: { username, display_name: displayName, age_confirmed_at: new Date().toISOString(), terms_version: termsVersion }, options: { emailRedirectTo: request.nextUrl.origin + "/auth/callback" } }),
      });
      const payload = (await response.json().catch(() => ({}))) as AuthPayload;
      if (!response.ok) {
        const text = JSON.stringify(payload);
        if (response.status === 429) return troubled("sign-up", email, "Too many sign-up attempts. Please wait a few minutes.", 429);
        // The database refused the new account: sign-ups were paused a moment ago, or the profile trigger rejected the
        // username (taken a moment ago). Those are the only database errors a valid request can hit.
        if (response.status >= 500 || /database error/i.test(text)) {
          const now = await signupsSetting(true);
          if (now.open === false) return troubled("sign-up", email, now.message || "New sign-ups are paused for a short while. Please try again soon.", 403);
          return troubled("sign-up", email, "That username was just taken. Choose another.", 409);
        }
        if (/password/i.test(text)) return troubled("sign-up", email, "That password is not accepted. Choose a longer or more varied one.");
        return troubled("sign-up", email, "Account creation failed. Check the details and try again.");
      }
      if (payload.access_token && payload.refresh_token && payload.user?.id) {
        await setPortfolioAuthCookies(payload);
        await dropAuthState();
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
        if (response.status === 429) return troubled("sign-in", email, "Too many sign-in attempts. Please wait a few minutes.", 429);
        const text = JSON.stringify(payload);
        if (/email not confirmed/i.test(text)) return troubled("sign-in", email, "Confirm your email first: use the link we sent you.", 403);
        await recordTrouble("sign-in", "Wrong email or password", email);
        return fail("Sign-in failed. Check your email and password.");
      }
      await setPortfolioAuthCookies(payload);
      await dropAuthState();
      const factor = verifiedFactor(payload.user);
      return ok({ user: { id: payload.user.id, email: payload.user.email ?? null }, mfaRequired: Boolean(factor), factorId: factor?.id ?? null });
    }

    return fail("Unsupported authentication action.");
  } catch {
    return fail("Authentication is not configured or is temporarily unavailable.", 503);
  }
}
