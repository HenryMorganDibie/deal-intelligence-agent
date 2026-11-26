import { NextRequest, NextResponse } from "next/server";
import { getPortfolioSession, isSameSiteJsonRequest, portfolioConfig } from "../../../../../lib/portfolio-server";

// Price-move alerts for one watchlist: the signed-in owner sets the daily move (in percent) that triggers an alert,
// or turns them off. The database function takes the account from the session token.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MESSAGES: Record<string, [string, number]> = {
  watchlist_not_found: ["Only the account that made this watchlist can change its price alerts.", 404],
  invalid_threshold: ["Choose a move between 2% and 50%.", 422],
  second_factor_required: ["Enter a code from your authenticator app first.", 403],
  not_signed_in: ["Sign in to change price alerts.", 401],
};

function fail(error: string, status: number) {
  return NextResponse.json({ error }, { status, headers: NO_STORE });
}

export async function POST(request: NextRequest, props: { params: Promise<{ id: string }> }) {
  const params = await props.params;
  if (!isSameSiteJsonRequest(request)) return fail("Invalid request.", 403);
  if (!UUID_RE.test(params.id)) return fail("Watchlist not found.", 404);
  let session;
  try {
    session = await getPortfolioSession();
  } catch {
    return fail("Sign-in is temporarily unavailable.", 503);
  }
  if (!session) return fail("Sign in to change price alerts.", 401);
  let pct: unknown;
  try {
    pct = ((await request.json()) as { pct?: unknown }).pct;
  } catch {
    return fail("Invalid request.", 400);
  }
  if (pct !== null && (typeof pct !== "number" || !Number.isFinite(pct) || pct < 2 || pct > 50)) {
    return fail("Choose a move between 2% and 50%.", 422);
  }
  const config = portfolioConfig();
  const r = await fetch(`${config.url}/rest/v1/rpc/set_my_watchlist_price_moves`, {
    method: "POST",
    headers: { apikey: config.key, Authorization: `Bearer ${session.accessToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ p_id: params.id, p_pct: pct }),
    cache: "no-store",
  });
  if (!r.ok) {
    const text = await r.text();
    const known = Object.keys(MESSAGES).find((code) => text.includes(code));
    return fail(...(known ? MESSAGES[known] : (["Price alerts could not be updated.", 502] as [string, number])));
  }
  return NextResponse.json({ pct }, { headers: NO_STORE });
}
