import { NextRequest, NextResponse } from "next/server";
import { getPortfolioSession, isSameSiteJsonRequest, portfolioConfig } from "../../../lib/portfolio-server";

// Facts a person at a company submits about it. The database function takes the account from the session token and
// checks that its confirmed email is at the company's own website domain: a match publishes, no known website holds
// the submission for review, a mismatch or a free-mail address is refused.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const MESSAGES: Record<string, [string, number]> = {
  not_signed_in: ["Sign in to add details for a company.", 401],
  second_factor_required: ["Enter a code from your authenticator app first.", 403],
  email_not_confirmed: ["Confirm your email address first.", 403],
  company_email_required: ["Use your company email address, not a personal one (Gmail, Yahoo, Outlook and similar).", 422],
  email_domain_mismatch: ["Your email address is not at this company's website domain, so the details cannot be published as the company's.", 403],
  invalid_employees: ["Choose a headcount range from the list.", 422],
  invalid_revenue: ["Choose a revenue range from the list.", 422],
  invalid_founded: ["Enter the year the company was founded, e.g. 2016.", 422],
  invalid_raised: ["Enter the total raised in US dollars, as a number.", 422],
  no_facts: ["Add at least one detail.", 422],
  invalid_company: ["This company cannot take submissions.", 422],
};

function fail(error: string, status: number) {
  return NextResponse.json({ error }, { status, headers: NO_STORE });
}

export async function POST(request: NextRequest) {
  if (!isSameSiteJsonRequest(request)) return fail("Invalid request.", 403);
  let session;
  try {
    session = await getPortfolioSession();
  } catch {
    return fail("Sign-in is temporarily unavailable.", 503);
  }
  if (!session) return fail(...MESSAGES.not_signed_in);
  let body: { name_key?: unknown; company?: unknown; facts?: unknown };
  try {
    body = await request.json();
  } catch {
    return fail("Invalid request.", 400);
  }
  const { name_key: key, company, facts } = body;
  if (typeof key !== "string" || key.length < 2 || key.length > 120 || typeof company !== "string"
      || company.trim().length < 2 || company.length > 200 || !facts || typeof facts !== "object" || Array.isArray(facts)) {
    return fail("Invalid request.", 400);
  }
  const config = portfolioConfig();
  const r = await fetch(`${config.url}/rest/v1/rpc/submit_company_facts`, {
    method: "POST",
    headers: { apikey: config.key, Authorization: `Bearer ${session.accessToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ p_name_key: key, p_company: company.trim(), p_facts: facts }),
    cache: "no-store",
  });
  if (!r.ok) {
    const text = await r.text();
    const known = Object.keys(MESSAGES).find((code) => text.includes(code));
    return fail(...(known ? MESSAGES[known] : (["The details could not be saved.", 502] as [string, number])));
  }
  const status = (await r.json()) as string;
  return NextResponse.json({ status }, { headers: NO_STORE });
}
