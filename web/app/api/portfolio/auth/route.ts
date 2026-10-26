import { NextRequest, NextResponse } from "next/server";
import {
  clearPortfolioAuthCookies,
  getPortfolioSession,
  isSameSiteJsonRequest,
  portfolioConfig,
  setPortfolioAuthCookies,
} from "../../../../lib/portfolio-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type AuthPayload = {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  user?: { id: string; email?: string | null };
  message?: string;
  msg?: string;
};

export async function GET() {
  try {
    const session = await getPortfolioSession();
    if (!session) return NextResponse.json({ authenticated: false }, { status: 401, headers: { "Cache-Control": "no-store" } });
    return NextResponse.json({ authenticated: true, user: session.user }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "Portfolio authentication is not configured or is temporarily unavailable." }, { status: 503 });
  }
}

export async function POST(request: NextRequest) {
  if (!isSameSiteJsonRequest(request)) return NextResponse.json({ error: "Invalid request." }, { status: 403 });
  let body: { action?: string; email?: string; password?: string; refreshToken?: unknown; tokenHash?: unknown; type?: unknown; code?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  try {
    const config = portfolioConfig();

    if (body.action === "recover-password") {
      const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) {
        return NextResponse.json({ error: "Enter a valid account email." }, { status: 400 });
      }
      const response = await fetch(config.url + "/auth/v1/recover?redirect_to=" + encodeURIComponent(request.nextUrl.origin + "/auth/callback?next=password-reset"), {
        method: "POST",
        headers: { apikey: config.key, "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
        cache: "no-store",
      });
      if (!response.ok && response.status !== 429) {
        return NextResponse.json({ error: "Could not request a password reset. Please try again later." }, { status: 503 });
      }
      if (response.status === 429) {
        return NextResponse.json({ error: "Too many requests. Please wait before trying again." }, { status: 429 });
      }
      return NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "update-password") {
      const password = typeof body.password === "string" ? body.password : "";
      if (password.length < 10 || password.length > 128) {
        return NextResponse.json({ error: "Use a password between 10 and 128 characters." }, { status: 400 });
      }
      const session = await getPortfolioSession();
      if (!session) return NextResponse.json({ error: "Your reset session has expired. Request a new password-reset link." }, { status: 401 });
      const response = await fetch(config.url + "/auth/v1/user", {
        method: "PUT",
        headers: { apikey: config.key, Authorization: "Bearer " + session.accessToken, "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
        cache: "no-store",
      });
      if (!response.ok) {
        return NextResponse.json({ error: "The password could not be updated. Request a fresh reset link and try again." }, { status: response.status === 429 ? 429 : 400 });
      }
      return NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "complete-oauth") {
      const code = typeof body.code === "string" ? body.code : "";
      const verifier = request.cookies.get("di_portfolio_oauth_verifier")?.value || "";
      if (!code || code.length > 4096 || !/^[A-Za-z0-9._~-]{43,128}$/.test(verifier)) {
        const response = NextResponse.json({ error: "Google sign-in could not be completed. Start again." }, { status: 400 });
        response.cookies.set("di_portfolio_oauth_verifier", "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 0 });
        return response;
      }
      const exchange = await fetch(config.url + "/auth/v1/token?grant_type=pkce", {
        method: "POST",
        headers: { apikey: config.key, "Content-Type": "application/json" },
        body: JSON.stringify({ auth_code: code, code_verifier: verifier }),
        cache: "no-store",
      });
      const payload = (await exchange.json().catch(() => ({}))) as AuthPayload;
      const response = !exchange.ok || !payload.access_token || !payload.refresh_token || !payload.user?.id
        ? NextResponse.json({ error: "Google sign-in failed or the sign-in link expired. Please try again." }, { status: 400 })
        : NextResponse.json({ ok: true, user: payload.user }, { headers: { "Cache-Control": "no-store" } });
      if (exchange.ok && payload.access_token && payload.refresh_token && payload.user?.id) setPortfolioAuthCookies(payload);
      response.cookies.set("di_portfolio_oauth_verifier", "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 0 });
      return response;
    }

    if (body.action === "complete-email") {
      const refreshToken = typeof body.refreshToken === "string" ? body.refreshToken : "";
      if (refreshToken.length < 20 || refreshToken.length > 4096) {
        return NextResponse.json({ error: "The confirmation link is invalid or expired." }, { status: 400 });
      }
      const response = await fetch(config.url + "/auth/v1/token?grant_type=refresh_token", {
        method: "POST",
        headers: { apikey: config.key, "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
        cache: "no-store",
      });
      const payload = (await response.json().catch(() => ({}))) as AuthPayload;
      if (!response.ok || !payload.access_token || !payload.refresh_token || !payload.user?.id) {
        return NextResponse.json({ error: "The confirmation link is invalid or expired." }, { status: 400 });
      }
      setPortfolioAuthCookies(payload);
      return NextResponse.json({ ok: true, user: payload.user }, { headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "verify-email") {
      const tokenHash = typeof body.tokenHash === "string" ? body.tokenHash : "";
      const type = typeof body.type === "string" ? body.type : "";
      if (!/^[a-f0-9]{32,128}$/i.test(tokenHash) || !["signup", "email", "invite", "recovery"].includes(type)) {
        return NextResponse.json({ error: "The confirmation link is invalid or expired." }, { status: 400 });
      }
      const response = await fetch(config.url + "/auth/v1/verify", {
        method: "POST",
        headers: { apikey: config.key, "Content-Type": "application/json" },
        body: JSON.stringify({ token_hash: tokenHash, type }),
        cache: "no-store",
      });
      const payload = (await response.json().catch(() => ({}))) as AuthPayload;
      if (!response.ok || !payload.access_token || !payload.refresh_token || !payload.user?.id) {
        return NextResponse.json({ error: "The confirmation link is invalid or expired." }, { status: 400 });
      }
      setPortfolioAuthCookies(payload);
      return NextResponse.json({ ok: true, user: payload.user }, { headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "sign-out") {
      const session = await getPortfolioSession().catch(() => null);
      if (session) {
        await fetch(config.url + "/auth/v1/logout", {
          method: "POST",
          headers: { apikey: config.key, Authorization: "Bearer " + session.accessToken },
          cache: "no-store",
        }).catch(() => undefined);
      }
      clearPortfolioAuthCookies();
      return NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
    }

    const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
    const password = typeof body.password === "string" ? body.password : "";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || password.length < 10 || password.length > 128) {
      return NextResponse.json({ error: "Enter a valid email and a password between 10 and 128 characters." }, { status: 400 });
    }

    const signUp = body.action === "sign-up";
    if (!signUp && body.action !== "sign-in") {
      return NextResponse.json({ error: "Unsupported authentication action." }, { status: 400 });
    }

    const response = await fetch(config.url + (signUp ? "/auth/v1/signup" : "/auth/v1/token?grant_type=password"), {
      method: "POST",
      headers: { apikey: config.key, "Content-Type": "application/json" },
      body: JSON.stringify(signUp ? { email, password, options: { emailRedirectTo: request.nextUrl.origin + "/auth/callback" } } : { email, password }),
      cache: "no-store",
    });
    const payload = (await response.json().catch(() => ({}))) as AuthPayload;
    if (!response.ok) {
      return NextResponse.json(
        { error: signUp ? "Account creation failed. Check the details or try signing in." : "Sign-in failed. Check your email and password." },
        { status: response.status === 429 ? 429 : 400 },
      );
    }

    if (payload.access_token && payload.refresh_token && payload.user?.id) {
      setPortfolioAuthCookies(payload);
      return NextResponse.json({ ok: true, user: payload.user }, { headers: { "Cache-Control": "no-store" } });
    }

    if (signUp) {
      return NextResponse.json({ ok: true, needsEmailConfirmation: true, message: "Check your email to confirm your account, then sign in." }, { status: 202, headers: { "Cache-Control": "no-store" } });
    }
    return NextResponse.json({ error: "Authentication did not return a valid session." }, { status: 400 });
  } catch {
    clearPortfolioAuthCookies();
    return NextResponse.json({ error: "Portfolio authentication is not configured or is temporarily unavailable." }, { status: 503 });
  }
}
