import { NextRequest, NextResponse } from "next/server";
import { getPortfolioSession, isSameSiteJsonRequest, portfolioConfig } from "../../../../lib/portfolio-server";

// API keys for the signed-in account. The database functions take the account from the session token and generate
// the key themselves, so a request can only ever see or change its own keys, and the full key exists only in the
// one response that creates it.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const MESSAGES: Record<string, [string, number]> = {
  key_limit: ["Your plan's key limit is reached. Revoke a key you no longer use first.", 429],
  invalid_name: ["Give the key a name of 1 to 60 characters.", 400],
  second_factor_required: ["Enter a code from your authenticator app first.", 403],
  not_authenticated: ["Sign in to manage API keys.", 401],
};

function fail(error: string, status: number) {
  return NextResponse.json({ error }, { status, headers: NO_STORE });
}

async function rpc(fn: string, token: string, body: Record<string, unknown> = {}) {
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
  return { ok: false as const, error: known ? MESSAGES[known] : (["API keys are temporarily unavailable.", 502] as [string, number]) };
}

async function session() {
  try {
    return (await getPortfolioSession()) ?? fail("Sign in to manage API keys.", 401);
  } catch {
    return fail("Sign-in is temporarily unavailable.", 503);
  }
}

export async function GET() {
  const s = await session();
  if (s instanceof NextResponse) return s;
  const r = await rpc("my_api_access", s.accessToken);
  return r.ok ? NextResponse.json(r.data, { headers: NO_STORE }) : fail(...r.error);
}

export async function POST(request: NextRequest) {
  if (!isSameSiteJsonRequest(request)) return fail("Invalid request.", 400);
  const s = await session();
  if (s instanceof NextResponse) return s;
  const body = (await request.json().catch(() => ({}))) as { name?: unknown };
  const name = typeof body.name === "string" ? body.name.trim() : "";
  if (!name || name.length > 60) return fail(...MESSAGES.invalid_name);
  const r = await rpc("create_my_api_key", s.accessToken, { p_name: name });
  return r.ok ? NextResponse.json(r.data, { status: 201, headers: NO_STORE }) : fail(...r.error);
}

export async function DELETE(request: NextRequest) {
  if (!isSameSiteJsonRequest(request)) return fail("Invalid request.", 400);
  const s = await session();
  if (s instanceof NextResponse) return s;
  const body = (await request.json().catch(() => ({}))) as { id?: unknown };
  const id = typeof body.id === "string" ? body.id : "";
  if (!UUID_RE.test(id)) return fail("Key not found.", 404);
  const r = await rpc("revoke_my_api_key", s.accessToken, { p_id: id });
  if (!r.ok) return fail(...r.error);
  return r.data ? NextResponse.json({ revoked: true }, { headers: NO_STORE }) : fail("Key not found.", 404);
}
