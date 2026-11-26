import { NextRequest, NextResponse } from "next/server";
import { getPortfolioSession, isSameSiteJsonRequest, portfolioConfig } from "../../../../../lib/portfolio-server";

// Keeps a portfolio's alerts watchlist in step with its holdings: the signed-in owner adds and removes company names.
// The database function takes the account from the session token and changes only that account's own watchlist.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MESSAGES: Record<string, [string, number]> = {
  watchlist_not_found: ["That alerts watchlist no longer exists.", 404],
  watchlist_empty: ["A watchlist needs at least one company or country. Delete it instead.", 422],
  too_many_companies: ["A watchlist can follow up to 200 companies.", 422],
  second_factor_required: ["Enter a code from your authenticator app first.", 403],
  not_signed_in: ["Sign in to update your alerts.", 401],
};

function fail(error: string, status: number) {
  return NextResponse.json({ error }, { status, headers: NO_STORE });
}

function names(value: unknown): string[] | null {
  if (!Array.isArray(value) || value.length > 200) return null;
  if (!value.every((v) => typeof v === "string")) return null;
  return (value as string[]).map((v) => v.trim().slice(0, 80)).filter(Boolean);
}

export async function POST(request: NextRequest, props: { params: Promise<{ id: string }> }) {
  const params = await props.params;
  if (!isSameSiteJsonRequest(request)) return fail("Invalid request.", 403);
  if (!UUID_RE.test(params.id)) return fail("That alerts watchlist no longer exists.", 404);
  let session;
  try {
    session = await getPortfolioSession();
  } catch {
    return fail("Sign-in is temporarily unavailable.", 503);
  }
  if (!session) return fail("Sign in to update your alerts.", 401);
  let body: { add?: unknown; remove?: unknown };
  try {
    body = (await request.json()) as { add?: unknown; remove?: unknown };
  } catch {
    return fail("Invalid request.", 400);
  }
  const add = names(body.add ?? []);
  const remove = names(body.remove ?? []);
  if (!add || !remove) return fail("Invalid request.", 400);
  const config = portfolioConfig();
  const r = await fetch(`${config.url}/rest/v1/rpc/update_my_watchlist_companies`, {
    method: "POST",
    headers: { apikey: config.key, Authorization: `Bearer ${session.accessToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ p_id: params.id, p_add: add, p_remove: remove }),
    cache: "no-store",
  });
  if (!r.ok) {
    const text = await r.text();
    const known = Object.keys(MESSAGES).find((code) => text.includes(code));
    return fail(...(known ? MESSAGES[known] : (["Alerts could not be updated.", 502] as [string, number])));
  }
  return NextResponse.json({ companies: (await r.json()) as string[] }, { headers: NO_STORE });
}
