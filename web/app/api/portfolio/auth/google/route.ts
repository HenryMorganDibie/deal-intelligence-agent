import { createHash, randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { portfolioConfig } from "../../../../../lib/portfolio-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const VERIFIER_COOKIE = "di_portfolio_oauth_verifier";

export async function GET(request: NextRequest) {
  try {
    const config = portfolioConfig();
    const verifier = randomBytes(32).toString("base64url");
    const challenge = createHash("sha256").update(verifier).digest("base64url");
    const configuredSiteUrl = process.env.NEXT_PUBLIC_SITE_URL;
    // Preview sign-in must return to the same preview deployment, not production.
    const siteUrl = (process.env.VERCEL_ENV === "preview" ? request.nextUrl.origin : configuredSiteUrl || request.nextUrl.origin).replace(/\/+$/, "");
    const callbackUrl = siteUrl + "/auth/callback";
    const authorizeUrl = new URL(config.url + "/auth/v1/authorize");
    authorizeUrl.searchParams.set("provider", "google");
    authorizeUrl.searchParams.set("redirect_to", callbackUrl);
    authorizeUrl.searchParams.set("code_challenge", challenge);
    authorizeUrl.searchParams.set("code_challenge_method", "s256");

    const response = NextResponse.redirect(authorizeUrl);
    response.cookies.set(VERIFIER_COOKIE, verifier, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 10 * 60,
    });
    return response;
  } catch {
    const destination = new URL("/account?error=oauth_unavailable", request.nextUrl.origin);
    return NextResponse.redirect(destination);
  }
}
