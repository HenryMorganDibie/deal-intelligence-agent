import { NextRequest, NextResponse } from "next/server";
import { portfolioConfig, setPortfolioAuthCookies } from "../../../lib/portfolio-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const tokenHash = request.nextUrl.searchParams.get("token_hash") || "";
  const type = request.nextUrl.searchParams.get("type") || "";
  const allowedTypes = ["signup", "email", "invite", "recovery", "magiclink"];

  if (!tokenHash || !allowedTypes.includes(type)) {
    return NextResponse.redirect(new URL("/account", request.url));
  }

  try {
    const config = portfolioConfig();
    const response = await fetch(config.url + "/auth/v1/verify", {
      method: "POST",
      headers: { apikey: config.key, "Content-Type": "application/json" },
      body: JSON.stringify({ token_hash: tokenHash, type }),
      cache: "no-store",
    });
    if (!response.ok) return NextResponse.redirect(new URL("/account", request.url));

    const session = await response.json();
    if (session.access_token && session.refresh_token && session.user?.id) {
      setPortfolioAuthCookies(session);
      return NextResponse.redirect(new URL("/app/markets/portfolio/cloud", request.url));
    }
    return NextResponse.redirect(new URL("/account", request.url));
  } catch {
    return NextResponse.redirect(new URL("/account", request.url));
  }
}
