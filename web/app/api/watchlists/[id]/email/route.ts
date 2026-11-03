import { NextRequest, NextResponse } from "next/server";
import { getPortfolioSession, isSameSiteJsonRequest, portfolioConfig } from "../../../../../lib/portfolio-server";

// Email alerts for one watchlist, for the signed-in account only. The database functions take the account from the
// session token, so a request can only ever subscribe its own verified address.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const MESSAGES: Record<string, [string, number]> = {
  email_not_confirmed: ["Confirm your email address first, then turn on email alerts.", 403],
  email_alert_limit: ["You can receive email alerts for up to 20 watchlists. Turn one off first.", 429],
  watchlist_not_found: ["Watchlist not found.", 404],
  second_factor_required: ["Enter a code from your authenticator app first.", 403],
  not_signed_in: ["Sign in to manage email alerts.", 401],
};

function fail(error: string, status: number) {
  return NextResponse.json({ error }, { status, headers: NO_STORE });
}

async function rpc(fn: string, token: string, body: Record<string, unknown>) {
  const config = portfolioConfig();
  const r = await fetch(`${config.url}/rest/v1/rpc/${fn}`, {
    method: "POST",
    headers: { apikey: config.key, Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (r.ok) return { ok: true as const, data: (await r.json()) as unknown };
  const text = await r.text();
  const known = Object.keys(MESSAGES).find((code) => text.includes(code));
  return { ok: false as const, error: known ? MESSAGES[known] : (["Email alerts could not be updated.", 502] as [string, number]) };
}

async function context(id: string) {
  if (!UUID_RE.test(id)) return { error: fail("Watchlist not found.", 404) };
  try {
    const session = await getPortfolioSession();
    if (!session) return { error: fail("Sign in to manage email alerts.", 401) };
    return { session };
  } catch {
    return { error: fail("Sign-in is temporarily unavailable.", 503) };
  }
}

export async function GET(_request: NextRequest, { params }: { params: { id: string } }) {
  const c = await context(params.id);
  if (c.error) return c.error;
  const r = await rpc("my_watchlist_email_alert", c.session.accessToken, { p_id: params.id });
  if (!r.ok) return fail(...r.error);
  const row = (Array.isArray(r.data) ? r.data[0] : null) as { enabled?: boolean; email?: string; email_confirmed?: boolean } | null;
  return NextResponse.json(
    { enabled: Boolean(row?.enabled), email: row?.email || null, emailConfirmed: Boolean(row?.email_confirmed) },
    { headers: NO_STORE },
  );
}

export async function POST(request: NextRequest, { params }: { params: { id: string } }) {
  if (!isSameSiteJsonRequest(request)) return fail("Invalid request.", 403);
  const c = await context(params.id);
  if (c.error) return c.error;
  let enabled: unknown;
  try {
    enabled = ((await request.json()) as { enabled?: unknown }).enabled;
  } catch {
    return fail("Invalid request.", 400);
  }
  if (typeof enabled !== "boolean") return fail("Invalid request.", 400);
  const r = await rpc("set_my_watchlist_email_alert", c.session.accessToken, { p_id: params.id, p_enabled: enabled });
  if (!r.ok) return fail(...r.error);
  return NextResponse.json({ enabled }, { headers: NO_STORE });
}
