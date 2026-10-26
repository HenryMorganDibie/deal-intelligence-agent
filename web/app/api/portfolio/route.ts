import { createHash, randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import {
  getPortfolioSession,
  portfolioConfig,
  portfolioErrorResponse,
  portfolioRest,
  isSameSiteJsonRequest,
} from "../../../lib/portfolio-server";
import { ASSET_TYPES, normalizeAssetType } from "../../../lib/markets-portfolio";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const currencyPattern = /^[A-Z]{3}$/;
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const transactionTypes = ["BUY", "SELL", "DIVIDEND", "DEPOSIT", "WITHDRAWAL", "FEE", "SPLIT", "TRANSFER_IN", "TRANSFER_OUT", "ADJUSTMENT"];

/** A trimmed string field capped at `limit` characters, or null. */
function shortText(value: unknown, limit: number): string | null {
  return typeof value === "string" ? value.trim().slice(0, limit) || null : null;
}

function jsonError(message: string, status: number) {
  return NextResponse.json({ error: message }, { status, headers: { "Cache-Control": "no-store" } });
}

function isPastOrTodayDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value + "T00:00:00Z");
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value && date.getTime() <= Date.now();
}

export async function GET(request: NextRequest) {
  try {
    const session = await getPortfolioSession();
    if (!session) return jsonError("Sign in to access cloud portfolios.", 401);

    const resource = request.nextUrl.searchParams.get("resource") || "portfolios";
    if (resource === "portfolios") {
      const rows = await portfolioRest<unknown[]>(session.accessToken,
        "portfolios?select=id,name,base_currency,owner_user_id,organization_id,archived_at,created_at,updated_at&archived_at=is.null&order=updated_at.desc");
      return NextResponse.json(rows, { headers: { "Cache-Control": "no-store" } });
    }

    if (resource === "organizations") {
      const memberships = await portfolioRest<Array<{ organization_id: string; role: string }>>(
        session.accessToken,
        "organization_memberships?select=organization_id,role&user_id=eq." + session.user.id,
      );
      if (!memberships.length) return NextResponse.json([], { headers: { "Cache-Control": "no-store" } });
      const ids = memberships.map((item) => item.organization_id).filter((id) => uuidPattern.test(id));
      if (!ids.length) return NextResponse.json([], { headers: { "Cache-Control": "no-store" } });
      const organizations = await portfolioRest<Array<{ id: string; name: string; slug: string; archived_at: string | null }>>(
        session.accessToken,
        "organizations?select=id,name,slug,archived_at&id=in.(" + ids.join(",") + ")",
      );
      const roles = new Map(memberships.map((item) => [item.organization_id, item.role]));
      return NextResponse.json(organizations.map((item) => ({ ...item, role: roles.get(item.id) || "viewer" })), {
        headers: { "Cache-Control": "no-store" },
      });
    }

    if (resource === "portfolio-data") {
      const portfolioId = request.nextUrl.searchParams.get("portfolioId") || "";
      if (!uuidPattern.test(portfolioId)) return jsonError("Invalid portfolio identifier.", 400);
      const portfolios = await portfolioRest<Array<Record<string, unknown>>>(
        session.accessToken,
        "portfolios?select=id,name,base_currency,owner_user_id,organization_id,archived_at&id=eq." + portfolioId + "&limit=1",
      );
      if (!portfolios.length) return jsonError("Portfolio not found.", 404);
      const [instruments, transactions] = await Promise.all([
        portfolioRest<unknown[]>(session.accessToken,
          "portfolio_instruments?select=id,portfolio_id,name,ticker,market,country,sector,asset_type,currency,current_price,price_as_of,fx_to_base,fx_as_of&portfolio_id=eq." + portfolioId + "&order=name.asc"),
        portfolioRest<unknown[]>(session.accessToken,
          "portfolio_transactions?select=id,portfolio_id,instrument_id,transaction_date,transaction_type,quantity,unit_price,cash_amount,fees,currency,fx_to_base,external_id,notes,created_at&portfolio_id=eq." + portfolioId + "&order=transaction_date.desc,created_at.desc"),
      ]);
      return NextResponse.json({ portfolio: portfolios[0], instruments, transactions }, { headers: { "Cache-Control": "no-store" } });
    }

    if (resource === "valuations") {
      const portfolioId = request.nextUrl.searchParams.get("portfolioId") || "";
      if (!uuidPattern.test(portfolioId)) return jsonError("Invalid portfolio identifier.", 400);
      const rows = await portfolioRest<unknown[]>(session.accessToken,
        "portfolio_valuations?select=id,valuation_date,base_currency,model,snapshot,notes,created_at&portfolio_id=eq." + portfolioId + "&order=valuation_date.desc,created_at.desc&limit=100");
      return NextResponse.json(rows, { headers: { "Cache-Control": "no-store" } });
    }

    if (resource === "members" || resource === "invites") {
      const organizationId = request.nextUrl.searchParams.get("organizationId") || "";
      if (!uuidPattern.test(organizationId)) return jsonError("Invalid organization identifier.", 400);
      const rpc = resource === "members" ? "list_organization_members" : "list_organization_invites";
      const rows = await portfolioRest<unknown>(session.accessToken, "rpc/" + rpc, { method: "POST", body: JSON.stringify({ p_organization_id: organizationId }) });
      return NextResponse.json(rows, { headers: { "Cache-Control": "no-store" } });
    }
    return jsonError("Unsupported portfolio resource.", 400);
  } catch (error) {
    const mapped = portfolioErrorResponse(error);
    return jsonError(mapped.message, mapped.status);
  }
}

export async function POST(request: NextRequest) {
  if (!isSameSiteJsonRequest(request)) return NextResponse.json({ error: "Invalid request." }, { status: 403 });
  try {
    const session = await getPortfolioSession();
    if (!session) return jsonError("Sign in to access cloud portfolios.", 401);

    const body = await request.json().catch(() => null) as Record<string, unknown> | null;
    if (!body || typeof body.action !== "string") return jsonError("Invalid request body.", 400);

    if (body.action === "create-portfolio") {
      const name = typeof body.name === "string" ? body.name.trim() : "";
      const baseCurrency = typeof body.baseCurrency === "string" ? body.baseCurrency : "USD";
      const ownership = body.ownership === "organization" ? "organization" : "personal";
      const organizationId = typeof body.organizationId === "string" ? body.organizationId : "";
      if (name.length < 1 || name.length > 160 || !currencyPattern.test(baseCurrency)) return jsonError("Enter a portfolio name and valid three-letter currency.", 400);
      if (ownership === "organization" && !uuidPattern.test(organizationId)) return jsonError("Choose an organization you manage.", 400);
      const row = {
        name,
        base_currency: baseCurrency,
        owner_user_id: ownership === "personal" ? session.user.id : null,
        organization_id: ownership === "organization" ? organizationId : null,
        created_by: session.user.id,
      };
      const created = await portfolioRest<unknown[]>(session.accessToken, "portfolios?select=id,name,base_currency,owner_user_id,organization_id,archived_at,created_at,updated_at", {
        method: "POST",
        headers: { Prefer: "return=representation" },
        body: JSON.stringify(row),
      });
      return NextResponse.json(Array.isArray(created) ? created[0] : created, { status: 201, headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "create-organization") {
      const name = typeof body.name === "string" ? body.name.trim() : "";
      if (name.length < 2 || name.length > 120) return jsonError("Organization name must be between 2 and 120 characters.", 400);
      const slug = name.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
      if (!slug) return jsonError("Choose a different organization name.", 400);
      const created = await portfolioRest<unknown[]>(session.accessToken, "organizations?select=id,name,slug,created_at", {
        method: "POST",
        headers: { Prefer: "return=representation" },
        body: JSON.stringify({ name, slug, created_by: session.user.id }),
      });
      return NextResponse.json(Array.isArray(created) ? created[0] : created, { status: 201, headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "create-invite") {
      const organizationId = typeof body.organizationId === "string" ? body.organizationId : "";
      const role = typeof body.role === "string" ? body.role : "analyst";
      if (!uuidPattern.test(organizationId) || !["admin", "manager", "analyst", "viewer"].includes(role)) return jsonError("Choose a valid organization and role.", 400);
      const inviteCode = randomBytes(32).toString("base64url");
      const tokenHash = createHash("sha256").update(inviteCode).digest("hex");
      const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
      await portfolioRest(session.accessToken, "organization_invites", {
        method: "POST",
        headers: { Prefer: "return=minimal" },
        body: JSON.stringify({
          organization_id: organizationId,
          token_hash: tokenHash,
          role,
          expires_at: expiresAt,
          max_uses: 1,
          created_by: session.user.id,
        }),
      });
      return NextResponse.json({ inviteCode, expiresAt, role }, { status: 201, headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "accept-invite") {
      const inviteCode = typeof body.inviteCode === "string" ? body.inviteCode.trim() : "";
      if (!/^[A-Za-z0-9_-]{40,60}$/.test(inviteCode)) return jsonError("Enter a valid invitation code.", 400);
      const tokenHash = createHash("sha256").update(inviteCode).digest("hex");
      const result = await portfolioRest<unknown>(session.accessToken, "rpc/accept_organization_invite", {
        method: "POST",
        body: JSON.stringify({ p_token_hash: tokenHash }),
      });
      return NextResponse.json({ ok: true, result }, { headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "create-instrument") {
      const portfolioId = typeof body.portfolioId === "string" ? body.portfolioId : "";
      const name = typeof body.name === "string" ? body.name.trim() : "";
      const currency = typeof body.currency === "string" ? body.currency : "";
      if (!uuidPattern.test(portfolioId) || name.length < 1 || name.length > 200 || !currencyPattern.test(currency)) return jsonError("Instrument name, portfolio and currency are required.", 400);
      const currentPrice = body.currentPrice === "" || body.currentPrice == null ? null : Number(body.currentPrice);
      const fxToBase = body.fxToBase === "" || body.fxToBase == null ? null : Number(body.fxToBase);
      if ((currentPrice !== null && (!Number.isFinite(currentPrice) || currentPrice <= 0)) || (fxToBase !== null && (!Number.isFinite(fxToBase) || fxToBase <= 0))) return jsonError("Price and FX values must be positive numbers.", 400);
      const priceAsOf = body.priceAsOf ? String(body.priceAsOf) : null;
      const fxAsOf = body.fxAsOf ? String(body.fxAsOf) : null;
      if ((priceAsOf && !isPastOrTodayDate(priceAsOf)) || (fxAsOf && !isPastOrTodayDate(fxAsOf))) return jsonError("Price and FX dates must be valid dates that are not in the future.", 400);
      const assetType = normalizeAssetType(typeof body.assetType === "string" ? body.assetType : "Stock");
      if (!assetType) return jsonError("Asset type must be one of: " + ASSET_TYPES.join(", ") + ".", 400);
      const created = await portfolioRest<unknown[]>(session.accessToken, "portfolio_instruments?select=id,portfolio_id,name,ticker,market,country,sector,asset_type,currency,current_price,price_as_of,fx_to_base,fx_as_of", {
        method: "POST",
        headers: { Prefer: "return=representation" },
        body: JSON.stringify({
          portfolio_id: portfolioId,
          name,
          ticker: shortText(body.ticker, 32),
          market: shortText(body.market, 80),
          country: shortText(body.country, 80),
          sector: shortText(body.sector, 80),
          asset_type: assetType,
          currency,
          current_price: currentPrice,
          price_as_of: priceAsOf,
          fx_to_base: fxToBase,
          fx_as_of: fxAsOf,
          created_by: session.user.id,
        }),
      });
      return NextResponse.json(Array.isArray(created) ? created[0] : created, { status: 201, headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "create-transaction") {
      const portfolioId = typeof body.portfolioId === "string" ? body.portfolioId : "";
      const instrumentId = typeof body.instrumentId === "string" ? body.instrumentId : "";
      const transactionDate = typeof body.transactionDate === "string" ? body.transactionDate : "";
      const transactionType = typeof body.transactionType === "string" ? body.transactionType : "";
      const quantity = Number(body.quantity);
      const unitPrice = Number(body.unitPrice);
      const fees = body.fees == null || body.fees === "" ? 0 : Number(body.fees);
      const cashAmount = body.cashAmount == null || body.cashAmount === "" ? 0 : Number(body.cashAmount);
      const currency = typeof body.currency === "string" ? body.currency : "";
      if (!uuidPattern.test(portfolioId) || !transactionTypes.includes(transactionType) || !isPastOrTodayDate(transactionDate) || !currencyPattern.test(currency)) return jsonError("Transaction type, date, portfolio and currency are required.", 400);
      if (!Number.isFinite(quantity) || quantity < 0 || !Number.isFinite(unitPrice) || unitPrice < 0 || !Number.isFinite(fees) || fees < 0 || !Number.isFinite(cashAmount)) return jsonError("Transaction amounts must be valid numbers.", 400);
      const requiresInstrument = ["BUY", "SELL", "SPLIT", "TRANSFER_IN", "TRANSFER_OUT", "ADJUSTMENT"].includes(transactionType);
      if (requiresInstrument && (!uuidPattern.test(instrumentId) || quantity <= 0)) return jsonError("Choose an instrument and enter a positive quantity.", 400);
      if (requiresInstrument) {
        const instrumentRows = await portfolioRest<Array<{ id: string; portfolio_id: string; currency: string }>>(
          session.accessToken,
          "portfolio_instruments?select=id,portfolio_id,currency&id=eq." + instrumentId + "&limit=1",
        );
        if (!instrumentRows.length || instrumentRows[0].portfolio_id !== portfolioId || instrumentRows[0].currency !== currency) return jsonError("The selected instrument does not belong to this portfolio or uses a different currency.", 400);
      }
      const fxToBase = body.fxToBase == null || body.fxToBase === "" ? null : Number(body.fxToBase);
      if (fxToBase !== null && (!Number.isFinite(fxToBase) || fxToBase <= 0)) return jsonError("FX rate must be a positive number.", 400);
      const created = await portfolioRest<unknown[]>(session.accessToken, "portfolio_transactions?select=id,portfolio_id,instrument_id,transaction_date,transaction_type,quantity,unit_price,cash_amount,fees,currency,fx_to_base,external_id,notes,created_at", {
        method: "POST",
        headers: { Prefer: "return=representation" },
        body: JSON.stringify({
          portfolio_id: portfolioId,
          instrument_id: requiresInstrument ? instrumentId : null,
          transaction_date: transactionDate,
          transaction_type: transactionType,
          quantity,
          unit_price: unitPrice,
          cash_amount: cashAmount,
          fees,
          currency,
          fx_to_base: fxToBase,
          external_id: typeof body.externalId === "string" ? body.externalId.trim() || null : null,
          notes: typeof body.notes === "string" ? body.notes.trim() || null : null,
          created_by: session.user.id,
        }),
      });
      return NextResponse.json(Array.isArray(created) ? created[0] : created, { status: 201, headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "save-valuation") {
      const portfolioId = typeof body.portfolioId === "string" ? body.portfolioId : "";
      const valuationDate = typeof body.valuationDate === "string" ? body.valuationDate : "";
      const baseCurrency = typeof body.baseCurrency === "string" ? body.baseCurrency : "";
      const model = typeof body.model === "string" ? body.model.trim() : "";
      const snapshot = body.snapshot;
      if (!uuidPattern.test(portfolioId) || !isPastOrTodayDate(valuationDate) || !currencyPattern.test(baseCurrency) ||
          !model || model.length > 100 || !snapshot || typeof snapshot !== "object" || Array.isArray(snapshot) ||
          JSON.stringify(snapshot).length > 200_000) {
        return jsonError("Enter a valid dated valuation snapshot.", 400);
      }
      const created = await portfolioRest<unknown[]>(session.accessToken, "portfolio_valuations?select=id,valuation_date,base_currency,model,snapshot,notes,created_at", {
        method: "POST",
        headers: { Prefer: "return=representation" },
        body: JSON.stringify({
          portfolio_id: portfolioId, valuation_date: valuationDate, base_currency: baseCurrency,
          model, snapshot, notes: typeof body.notes === "string" ? body.notes.trim().slice(0, 1000) || null : null,
          created_by: session.user.id,
        }),
      });
      return NextResponse.json(Array.isArray(created) ? created[0] : created, { status: 201, headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "import-transactions") {
      const portfolioId = typeof body.portfolioId === "string" ? body.portfolioId : "";
      const importKey = typeof body.importKey === "string" ? body.importKey : "";
      const filename = typeof body.filename === "string" ? body.filename.trim() : "";
      const rows = body.rows;
      if (!uuidPattern.test(portfolioId) || !uuidPattern.test(importKey) || !filename || filename.length > 255 ||
          !Array.isArray(rows) || rows.length < 1 || rows.length > 5000 || JSON.stringify(body).length > 4_000_000) {
        return jsonError("The transaction import is invalid or too large. Use a file with at most 5,000 rows and 4 MB of parsed data.", 400);
      }
      const result = await portfolioRest<unknown>(session.accessToken, "rpc/commit_portfolio_transaction_import", {
        method: "POST",
        body: JSON.stringify({ p_portfolio_id: portfolioId, p_import_key: importKey, p_filename: filename, p_rows: rows }),
      });
      return NextResponse.json(result, { headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "migrate-local-portfolio") {
      const portfolioId = typeof body.portfolioId === "string" ? body.portfolioId : "";
      const migrationKey = typeof body.migrationKey === "string" ? body.migrationKey : "";
      const baseCurrency = typeof body.baseCurrency === "string" ? body.baseCurrency : "";
      const holdings = body.holdings;
      const valuations = body.valuations;
      if (!uuidPattern.test(portfolioId) || !uuidPattern.test(migrationKey) || !currencyPattern.test(baseCurrency) ||
          !Array.isArray(holdings) || holdings.length > 5000 || !Array.isArray(valuations) || valuations.length > 1000 ||
          JSON.stringify(body).length > 4_000_000) {
        return jsonError("The local portfolio migration is invalid or too large. Export a backup and reduce the data size before retrying.", 400);
      }
      const result = await portfolioRest<unknown>(session.accessToken, "rpc/migrate_local_portfolio", {
        method: "POST",
        body: JSON.stringify({
          p_portfolio_id: portfolioId, p_migration_key: migrationKey, p_base_currency: baseCurrency,
          p_holdings: holdings, p_valuations: valuations,
        }),
      });
      return NextResponse.json(result, { headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "change-member-role") {
      const organizationId = typeof body.organizationId === "string" ? body.organizationId : "";
      const userId = typeof body.userId === "string" ? body.userId : "";
      const role = typeof body.role === "string" ? body.role : "";
      if (!uuidPattern.test(organizationId) || !uuidPattern.test(userId) || !["admin","manager","analyst","viewer"].includes(role)) return jsonError("Invalid member role change.", 400);
      const result = await portfolioRest<unknown>(session.accessToken, "rpc/update_organization_member_role", { method: "POST", body: JSON.stringify({ p_organization_id: organizationId, p_user_id: userId, p_role: role }) });
      return NextResponse.json({ ok: true, result }, { headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "remove-member") {
      const organizationId = typeof body.organizationId === "string" ? body.organizationId : "";
      const userId = typeof body.userId === "string" ? body.userId : "";
      if (!uuidPattern.test(organizationId) || !uuidPattern.test(userId)) return jsonError("Invalid member removal request.", 400);
      const result = await portfolioRest<unknown>(session.accessToken, "rpc/remove_organization_member", { method: "POST", body: JSON.stringify({ p_organization_id: organizationId, p_user_id: userId }) });
      return NextResponse.json({ ok: true, result }, { headers: { "Cache-Control": "no-store" } });
    }

    if (body.action === "revoke-invite") {
      const inviteId = typeof body.inviteId === "string" ? body.inviteId : "";
      if (!uuidPattern.test(inviteId)) return jsonError("Invalid invitation identifier.", 400);
      const result = await portfolioRest<unknown>(session.accessToken, "rpc/revoke_organization_invite", { method: "POST", body: JSON.stringify({ p_invite_id: inviteId }) });
      return NextResponse.json({ ok: true, result }, { headers: { "Cache-Control": "no-store" } });
    }
    return jsonError("Unsupported portfolio action.", 400);
  } catch (error) {
    const mapped = portfolioErrorResponse(error);
    return jsonError(mapped.message, mapped.status);
  }
}
