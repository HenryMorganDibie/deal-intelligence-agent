import { NextRequest, NextResponse } from "next/server";
import { apiHeaders, apiUrl } from "../../../../lib/api-base";
import { getPortfolioSession, isSameSiteJsonRequest, portfolioConfig } from "../../../../lib/portfolio-server";

// Billing for the signed-in account. GET reads the account's plan and subscription (as the account, through its
// own session). POST starts a Paystack checkout or opens Paystack's subscription page; the account's id comes from
// the verified session, never from the browser, and the API call carries the app's server secret.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };

function fail(error: string, status: number) {
  return NextResponse.json({ error }, { status, headers: NO_STORE });
}

async function session() {
  try {
    return (await getPortfolioSession()) ?? fail("Sign in to manage your plan.", 401);
  } catch {
    return fail("Sign-in is temporarily unavailable.", 503);
  }
}

export async function GET() {
  const s = await session();
  if (s instanceof NextResponse) return s;
  const config = portfolioConfig();
  const r = await fetch(`${config.url}/rest/v1/rpc/my_billing`, {
    method: "POST",
    headers: { apikey: config.key, Authorization: `Bearer ${s.accessToken}`, "Content-Type": "application/json" },
    body: "{}",
    cache: "no-store",
  });
  if (!r.ok) return fail("Your plan could not be loaded.", 502);
  return NextResponse.json({ ...(await r.json()), email: s.user.email ?? null }, { headers: NO_STORE });
}

export async function POST(request: NextRequest) {
  if (!isSameSiteJsonRequest(request)) return fail("Invalid request.", 400);
  const s = await session();
  if (s instanceof NextResponse) return s;
  const body = (await request.json().catch(() => ({}))) as { action?: string; plan?: string; interval?: string };
  let path: string;
  let payload: Record<string, unknown>;
  if (body.action === "checkout") {
    if (body.plan !== "pro" && body.plan !== "team") return fail("Choose Pro or Team.", 400);
    const interval = body.interval === "annually" ? "annually" : "monthly";
    path = "/api/billing/checkout";
    payload = { user_id: s.user.id, plan: body.plan, interval };
  } else if (body.action === "manage") {
    path = "/api/billing/manage";
    payload = { user_id: s.user.id };
  } else {
    return fail("Unknown action.", 400);
  }
  const r = await fetch(apiUrl(path), {
    method: "POST",
    headers: apiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const data = (await r.json().catch(() => ({}))) as { detail?: string };
  if (!r.ok) return fail(typeof data.detail === "string" ? data.detail : "Payments are temporarily unavailable.", r.status);
  return NextResponse.json(data, { headers: NO_STORE });
}
