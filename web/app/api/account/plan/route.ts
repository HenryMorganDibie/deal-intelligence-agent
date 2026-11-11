import { NextResponse } from "next/server";
import { getPortfolioSession, portfolioConfig } from "../../../../lib/portfolio-server";

// The signed-in account's plan and allowances (my_limits reads the account from the session token), so the app can
// mark Pro features before a free account runs into them.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };

export async function GET() {
  let s;
  try {
    s = await getPortfolioSession();
  } catch {
    return NextResponse.json({ error: "Sign-in is temporarily unavailable." }, { status: 503, headers: NO_STORE });
  }
  if (!s) return NextResponse.json({ error: "Sign in to see your plan." }, { status: 401, headers: NO_STORE });
  const config = portfolioConfig();
  const r = await fetch(`${config.url}/rest/v1/rpc/my_limits`, {
    method: "POST", cache: "no-store", body: "{}",
    headers: { apikey: config.key, Authorization: `Bearer ${s.accessToken}`, "Content-Type": "application/json" },
  });
  if (!r.ok) return NextResponse.json({ error: "Your plan could not be read." }, { status: 502, headers: NO_STORE });
  return NextResponse.json(await r.json(), { headers: NO_STORE });
}
