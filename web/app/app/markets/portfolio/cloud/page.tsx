"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { Container } from "../../../../../components/primitives";
import { ErrorNote, PageHeader } from "../../../../../components/app/ui";
import { parseCsv } from "../../../../../lib/markets-csv";
import { parsePortfolioWorkbook } from "../../../../../lib/markets-excel";

type User = { id: string; email?: string | null };
type Portfolio = { id: string; name: string; base_currency: string; owner_user_id: string | null; organization_id: string | null; archived_at: string | null };
type Organization = { id: string; name: string; slug: string; role: string; archived_at: string | null };
type OrganizationMember = { user_id: string; email: string | null; role: string; joined_at: string };
type OrganizationInvite = { id: string; role: string; expires_at: string; use_count: number; max_uses: number; revoked_at: string | null; created_at: string };
type Instrument = { id: string; portfolio_id: string; name: string; ticker: string | null; market: string | null; country: string | null; sector: string | null; asset_type: string; currency: string; current_price: number | null; price_as_of: string | null; fx_to_base: number | null; fx_as_of: string | null };
type Transaction = { id: string; portfolio_id: string; instrument_id: string | null; transaction_date: string; transaction_type: string; quantity: number; unit_price: number; cash_amount: number; fees: number; currency: string; fx_to_base: number | null; notes: string | null };
type PortfolioData = { portfolio: Portfolio; instruments: Instrument[]; transactions: Transaction[] };
type CloudValuation = { id: string; valuation_date: string; base_currency: string; model: string; snapshot: Record<string, unknown>; notes: string | null; created_at: string };
type ImportedTransaction = { transaction_date: string; transaction_type: string; instrument_id: string | null; quantity: number; unit_price: number; cash_amount: number; fees: number; currency: string; fx_to_base: number | null; external_id: string | null; notes: string | null };
type ImportPreview = { filename: string; key: string; rows: ImportedTransaction[]; errors: string[]; sourceRows: number };

const currencies = ["USD", "NGN", "KES", "GHS", "ZAR", "EGP", "XOF", "XAF", "GBP", "EUR"];
const today = new Date().toISOString().slice(0, 10);

async function readJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "The portfolio request failed.");
  return payload as T;
}

async function postJson<T>(body: Record<string, unknown>): Promise<T> {
  const response = await fetch("/api/portfolio", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "The portfolio request failed.");
  return payload as T;
}

function derivePosition(instrument: Instrument, transactions: Transaction[]) {
  let quantity = 0;
  let cost = 0;
  const warnings: string[] = [];
  const rows = transactions
    .filter((item) => item.instrument_id === instrument.id)
    .slice()
    .sort((a, b) => a.transaction_date.localeCompare(b.transaction_date));

  for (const transaction of rows) {
    const q = Number(transaction.quantity);
    const price = Number(transaction.unit_price);
    const fees = Number(transaction.fees || 0);
    if (["BUY", "TRANSFER_IN", "ADJUSTMENT"].includes(transaction.transaction_type)) {
      quantity += q;
      cost += q * price + fees;
    } else if (["SELL", "TRANSFER_OUT"].includes(transaction.transaction_type)) {
      const available = Math.max(0, quantity);
      const sold = Math.min(available, q);
      const averageCost = available > 0 ? cost / available : 0;
      cost = Math.max(0, cost - averageCost * sold);
      quantity -= q;
      if (q > sold) warnings.push("A sell/transfer exceeds recorded units.");
    } else if (transaction.transaction_type === "SPLIT") {
      warnings.push("Share-split transactions need specialist reconciliation.");
    }
  }

  if (quantity < 0) {
    warnings.push("Net quantity is negative; reconcile the transaction ledger.");
    quantity = 0;
    cost = 0;
  }
  const averageCost = quantity > 0 ? cost / quantity : null;
  const currentPrice = instrument.current_price == null ? null : Number(instrument.current_price);
  const valueLocal = currentPrice == null ? null : quantity * currentPrice;
  const fx = Number(instrument.fx_to_base || 0);
  return { quantity, averageCost, currentPrice, valueLocal, fx, warnings };
}

function money(value: number | null | undefined, currency: string) {
  if (value == null || !Number.isFinite(value)) return "Not available";
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
  } catch {
    return value.toLocaleString("en", { maximumFractionDigits: 2 }) + " " + currency;
  }
}

export default function CloudPortfolioPage() {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [invites, setInvites] = useState<OrganizationInvite[]>([]);
  const [memberRoleEdits, setMemberRoleEdits] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState("");
  const [data, setData] = useState<PortfolioData | null>(null);
  const [valuations, setValuations] = useState<CloudValuation[]>([]);
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [migrationBusy, setMigrationBusy] = useState(false);
  const [migrationComplete, setMigrationComplete] = useState(false);
  const [migrationBusy, setMigrationBusy] = useState(false);
  const [migrationComplete, setMigrationComplete] = useState(false);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [portfolioName, setPortfolioName] = useState("");
  const [baseCurrency, setBaseCurrency] = useState("USD");
  const [ownership, setOwnership] = useState<"personal" | "organization">("personal");
  const [organizationId, setOrganizationId] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [newInvite, setNewInvite] = useState("");
  const [inviteRole, setInviteRole] = useState("analyst");
  const [instrument, setInstrument] = useState({ name: "", ticker: "", country: "", sector: "", assetType: "Stock", currency: "USD", currentPrice: "", priceAsOf: "", fxToBase: "", fxAsOf: "" });
  const [transaction, setTransaction] = useState({ instrumentId: "", transactionType: "BUY", transactionDate: today, quantity: "1", unitPrice: "", fees: "0", notes: "" });

  const loadLists = useCallback(async function loadLists() {
    const [portfolioRows, organizationRows] = await Promise.all([
      readJson<Portfolio[]>("/api/portfolio?resource=portfolios"),
      readJson<Organization[]>("/api/portfolio?resource=organizations"),
    ]);
    setPortfolios(portfolioRows);
    setOrganizations(organizationRows);
    setSelectedId((current) => current || portfolioRows[0]?.id || "");
    setOrganizationId((current) => current || organizationRows.find((item) => !item.archived_at && (item.role === "owner" || item.role === "admin" || item.role === "manager"))?.id || organizationRows.find((item) => !item.archived_at)?.id || "");
  }, []);

  useEffect(() => {
    let active = true;
    readJson<{ authenticated: boolean; user: User }>("/api/portfolio/auth")
      .then(async (payload) => {
        if (!active) return;
        setUser(payload.user);
        await loadLists();
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Sign in to use cloud portfolios.");
      })
      .finally(() => { if (active) setAuthLoading(false); });
    return () => { active = false; };
  }, [loadLists]);

  useEffect(() => {
    const selectedOrganization = organizations.find((item) => item.id === organizationId && !item.archived_at);
    if (!user || !selectedOrganization || !["owner", "admin"].includes(selectedOrganization.role)) { setMembers([]); setInvites([]); return; }
    let active = true;
    Promise.all([
      readJson<OrganizationMember[]>("/api/portfolio?resource=members&organizationId=" + encodeURIComponent(organizationId)),
      readJson<OrganizationInvite[]>("/api/portfolio?resource=invites&organizationId=" + encodeURIComponent(organizationId)),
    ]).then(([memberRows, inviteRows]) => { if (active) { setMembers(memberRows); setInvites(inviteRows); setMemberRoleEdits(Object.fromEntries(memberRows.map((member) => [member.user_id, member.role]))); } })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Could not load organization members."); });
    return () => { active = false; };
  }, [organizationId, organizations, user]);
  useEffect(() => {
    if (!selectedId || !user) { setData(null); return; }
    let active = true;
    setLoadingData(true);
    Promise.all([
      readJson<PortfolioData>("/api/portfolio?resource=portfolio-data&portfolioId=" + encodeURIComponent(selectedId)),
      readJson<CloudValuation[]>("/api/portfolio?resource=valuations&portfolioId=" + encodeURIComponent(selectedId)),
    ])
      .then(([payload, valuationRows]) => { if (active) { setData(payload); setValuations(valuationRows); } })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Could not load portfolio."); })
      .finally(() => { if (active) setLoadingData(false); });
    return () => { active = false; };
  }, [selectedId, user]);

  const positions = useMemo(() => {
    if (!data) return [];
    return data.instruments.map((item) => ({ instrument: item, ...derivePosition(item, data.transactions) })).filter((item) => item.quantity > 0);
  }, [data]);

  async function handleCreatePortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(""); setMessage(""); setNewInvite("");
    try {
      const created = await postJson<Portfolio>({
        action: "create-portfolio", name: portfolioName, baseCurrency, ownership,
        organizationId: ownership === "organization" ? organizationId : "",
      });
      setPortfolioName("");
      await loadLists();
      setSelectedId(created.id);
      setMessage("Cloud portfolio created.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not create portfolio."); }
  }

  async function handleCreateOrganization(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setMessage("");
    try {
      await postJson({ action: "create-organization", name: organizationName });
      setOrganizationName("");
      await loadLists();
      setMessage("Organization workspace created. Generate an invite code to add teammates.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not create organization."); }
  }

  async function handleInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setMessage(""); setNewInvite("");
    try {
      const result = await postJson<{ inviteCode: string; expiresAt: string; role: string }>({ action: "create-invite", organizationId, role: inviteRole });
      setNewInvite(result.inviteCode);
      await refreshOrganizationAdmin();
      setMessage("Invite code created. Copy it now and share it with the intended teammate. It expires in seven days and can be used once.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not create invite."); }
  }

  async function handleAcceptInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setMessage("");
    try {
      await postJson({ action: "accept-invite", inviteCode });
      setInviteCode("");
      await loadLists();
      setMessage("You joined the organization workspace.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not accept invite."); }
  }

  async function handleCreateInstrument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId) return;
    setError(""); setMessage("");
    try {
      await postJson({ action: "create-instrument", portfolioId: selectedId, ...instrument });
      setInstrument({ name: "", ticker: "", country: "", sector: "", assetType: "Stock", currency: data?.portfolio.base_currency || "USD", currentPrice: "", priceAsOf: "", fxToBase: "", fxAsOf: "" });
      const refreshed = await readJson<PortfolioData>("/api/portfolio?resource=portfolio-data&portfolioId=" + encodeURIComponent(selectedId));
      setData(refreshed);
      setMessage("Instrument added. Record transactions to derive its position.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not add instrument."); }
  }

  async function handleCreateTransaction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId || !transaction.instrumentId) return;
    const selectedInstrument = data?.instruments.find((item) => item.id === transaction.instrumentId);
    if (!selectedInstrument) return;
    setError(""); setMessage("");
    try {
      await postJson({
        action: "create-transaction", portfolioId: selectedId, instrumentId: transaction.instrumentId,
        transactionType: transaction.transactionType, transactionDate: transaction.transactionDate,
        quantity: transaction.quantity, unitPrice: transaction.unitPrice, fees: transaction.fees,
        currency: selectedInstrument.currency, notes: transaction.notes,
      });
      const refreshed = await readJson<PortfolioData>("/api/portfolio?resource=portfolio-data&portfolioId=" + encodeURIComponent(selectedId));
      setData(refreshed);
      setTransaction({ ...transaction, quantity: "1", unitPrice: "", fees: "0", notes: "" });
      setMessage("Transaction recorded. Positions are recalculated from the ledger.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not record transaction."); }
  }

  async function handleSaveValuation() {
    if (!data || !selectedId) return;
    setError(""); setMessage("");
    try {
      const holdings = positions.map((item) => ({
        instrumentId: item.instrument.id, name: item.instrument.name, ticker: item.instrument.ticker,
        currency: item.instrument.currency, quantity: item.quantity, averageCost: item.averageCost,
        currentPrice: item.currentPrice, fxToBase: item.instrument.currency === data.portfolio.base_currency ? 1 : (item.fx || null),
        marketValue: item.valueLocal == null ? null : item.valueLocal * (item.instrument.currency === data.portfolio.base_currency ? 1 : item.fx),
        warnings: item.warnings,
      }));
      const totalValue = holdings.reduce((sum, item) => sum + (item.marketValue ?? 0), 0);
      await postJson({
        action: "save-valuation", portfolioId: selectedId, valuationDate: today,
        baseCurrency: data.portfolio.base_currency, model: "ledger-mark-to-market",
        snapshot: { portfolioName: data.portfolio.name, baseCurrency: data.portfolio.base_currency, holdings, totalValue, note: "Snapshot of recorded transactions and manually entered prices/FX, not a return calculation." },
        notes: "Saved from the cloud portfolio workspace.",
      });
      const rows = await readJson<CloudValuation[]>("/api/portfolio?resource=valuations&portfolioId=" + encodeURIComponent(selectedId));
      setValuations(rows);
      setMessage("Valuation snapshot saved to cloud history.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save valuation snapshot."); }
  }
  async function handleTransactionFile(file: File | null) {
    setImportPreview(null); setError(""); setMessage("");
    if (!file) return;
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error("Import files must be 5 MB or smaller.");
      if (!data) throw new Error("Select a portfolio before importing transactions.");
      const rows = /\.xlsx$/i.test(file.name) ? parsePortfolioWorkbook(await file.arrayBuffer()) : parseCsv(await file.text());
      if (rows.length < 2) throw new Error("The file must include a header row and at least one transaction.");
      if (rows.length > 5001) throw new Error("The transaction import is limited to 5,000 data rows.");
      const headers = rows[0].map((h) => h.trim().toLowerCase().replace(/[ -]+/g, "_"));
      const required = ["transaction_date", "transaction_type", "currency"];
      const missing = required.filter((h) => !headers.includes(h));
      if (missing.length) throw new Error("Missing required columns: " + missing.join(", "));
      const cell = (row: string[], name: string) => { const i = headers.indexOf(name); return i < 0 ? "" : (row[i] ?? "").trim(); };
      const imported: ImportedTransaction[] = [];
      const errors: string[] = [];
      const types = ["BUY","SELL","DIVIDEND","DEPOSIT","WITHDRAWAL","FEE","SPLIT","TRANSFER_IN","TRANSFER_OUT","ADJUSTMENT"];
      const instrumentTypes = ["BUY","SELL","SPLIT","TRANSFER_IN","TRANSFER_OUT","ADJUSTMENT"];
      const externalIds = new Set<string>();
      for (let i = 1; i < rows.length; i += 1) {
        const row = rows[i];
        const date = cell(row, "transaction_date");
        const type = cell(row, "transaction_type").toUpperCase();
        const currency = cell(row, "currency").toUpperCase();
        const quantity = cell(row, "quantity") === "" ? 0 : Number(cell(row, "quantity"));
        const unitPrice = cell(row, "unit_price") === "" ? 0 : Number(cell(row, "unit_price"));
        const cashAmount = cell(row, "cash_amount") === "" ? 0 : Number(cell(row, "cash_amount"));
        const fees = cell(row, "fees") === "" ? 0 : Number(cell(row, "fees"));
        const fxText = cell(row, "fx_to_base"); const fx = fxText === "" ? null : Number(fxText);
        const externalId = cell(row, "external_id") || null;
        let instrumentId = cell(row, "instrument_id");
        const ticker = cell(row, "ticker").toUpperCase();
        const instrumentName = cell(row, "instrument_name").toLowerCase();
        if (!instrumentId && (ticker || instrumentName)) {
          const matches = data.instruments.filter((item) => ticker ? (item.ticker || "").toUpperCase() === ticker : item.name.toLowerCase() === instrumentName);
          if (matches.length === 1) instrumentId = matches[0].id;
          else { errors.push("Row " + (i + 1) + ": instrument name/ticker is missing or ambiguous."); continue; }
        }
        if (instrumentId && !data.instruments.some((item) => item.id === instrumentId)) { errors.push("Row " + (i + 1) + ": instrument_id is not in the selected portfolio."); continue; }
        const dateParsed = /^\d{4}-\d{2}-\d{2}$/.test(date) ? new Date(date + "T00:00:00Z") : null;
        if (!dateParsed || !Number.isFinite(dateParsed.getTime()) || dateParsed.toISOString().slice(0,10) !== date || date > today || !types.includes(type) || !/^[A-Z]{3}$/.test(currency) || ![quantity,unitPrice,cashAmount,fees].every(Number.isFinite) || quantity < 0 || unitPrice < 0 || fees < 0 || (fx !== null && (!Number.isFinite(fx) || fx <= 0))) { errors.push("Row " + (i + 1) + ": invalid date, type, currency or numeric value."); continue; }
        if (instrumentTypes.includes(type) && (!instrumentId || quantity <= 0)) { errors.push("Row " + (i + 1) + ": " + type + " requires an instrument and positive quantity."); continue; }
        const instrumentRow = instrumentId ? data.instruments.find((item) => item.id === instrumentId) : null;
        if (instrumentRow && instrumentRow.currency !== currency) { errors.push("Row " + (i + 1) + ": currency does not match the instrument."); continue; }
        if (externalId && externalIds.has(externalId)) { errors.push("Row " + (i + 1) + ": duplicate external_id in this file."); continue; }
        if (externalId) externalIds.add(externalId);
        imported.push({ transaction_date: date, transaction_type: type, instrument_id: instrumentId || null, quantity, unit_price: unitPrice, cash_amount: cashAmount, fees, currency, fx_to_base: fx, external_id: externalId, notes: cell(row, "notes") || null });
      }
      setImportPreview({ filename: file.name, key: crypto.randomUUID(), rows: imported, errors, sourceRows: rows.length - 1 });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not read the transaction file."); }
  }

  async function commitTransactionImport() {
    if (!importPreview || !selectedId || importPreview.errors.length || !importPreview.rows.length) return;
    setImportBusy(true); setError(""); setMessage("");
    try {
      const result = await postJson<{ total_rows: number; accepted_rows: number; replayed: boolean }>({ action: "import-transactions", portfolioId: selectedId, importKey: importPreview.key, filename: importPreview.filename, rows: importPreview.rows });
      const [payload, valuationRows] = await Promise.all([readJson<PortfolioData>("/api/portfolio?resource=portfolio-data&portfolioId=" + encodeURIComponent(selectedId)), readJson<CloudValuation[]>("/api/portfolio?resource=valuations&portfolioId=" + encodeURIComponent(selectedId))]);
      setData(payload); setValuations(valuationRows); setImportPreview(null);
      setMessage("Transaction import " + (result.replayed ? "was already committed" : "completed") + ": " + result.accepted_rows + " of " + result.total_rows + " rows accepted atomically.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not import transactions."); }
    finally { setImportBusy(false); }
  }
  async function handleMigrateLocalPortfolio() {
    if (!selectedId || !data) return;
    setError(""); setMessage(""); setMigrationBusy(true);
    try {
      const raw = window.localStorage.getItem("deal-intelligence-markets-portfolio-v1");
      if (!raw) throw new Error("No browser-local portfolio was found in this browser.");
      const local = JSON.parse(raw) as { version?: unknown; baseCurrency?: unknown; holdings?: unknown };
      if (local.version !== 1 || !Array.isArray(local.holdings) || typeof local.baseCurrency !== "string" || !/^[A-Z]{3}$/.test(local.baseCurrency)) throw new Error("The local portfolio could not be validated. Its data was left untouched.");
      if (local.baseCurrency !== data.portfolio.base_currency) throw new Error("The selected cloud portfolio uses " + data.portfolio.base_currency + " but the local portfolio uses " + local.baseCurrency + ". Create a cloud portfolio with the same reporting currency before migrating.");
      let savedValuations: unknown[] = [];
      const valuationRaw = window.localStorage.getItem("deal-intelligence-markets-valuations-v1");
      if (valuationRaw) { const parsed: unknown = JSON.parse(valuationRaw); if (!Array.isArray(parsed)) throw new Error("Local valuation reviews could not be validated. No data was migrated."); savedValuations = parsed; }
      if (local.holdings.length > 5000 || savedValuations.length > 1000) throw new Error("Migration supports up to 5,000 holdings and 1,000 saved valuation reviews.");
      const keyName = "deal-intelligence-cloud-migration-v1:" + selectedId;
      let migrationKey = window.localStorage.getItem(keyName);
      if (!migrationKey) { migrationKey = crypto.randomUUID(); window.localStorage.setItem(keyName, migrationKey); }
      const result = await postJson<{ holdings_count: number; valuations_count: number; replayed: boolean }>({ action: "migrate-local-portfolio", portfolioId: selectedId, migrationKey, baseCurrency: local.baseCurrency, holdings: local.holdings, valuations: savedValuations });
      const [portfolioRows, valuationRows] = await Promise.all([readJson<PortfolioData>("/api/portfolio?resource=portfolio-data&portfolioId=" + encodeURIComponent(selectedId)), readJson<CloudValuation[]>("/api/portfolio?resource=valuations&portfolioId=" + encodeURIComponent(selectedId))]);
      setData(portfolioRows); setValuations(valuationRows); setMigrationComplete(true);
      setMessage("Local migration " + (result.replayed ? "was already completed" : "completed") + ": " + result.holdings_count + " holding(s) and " + result.valuations_count + " valuation review(s). The browser-local data remains unchanged as a backup.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not migrate local portfolio."); }
    finally { setMigrationBusy(false); }
  }
  async function refreshOrganizationAdmin() {
    if (!organizationId) return;
    const [memberRows, inviteRows] = await Promise.all([readJson<OrganizationMember[]>("/api/portfolio?resource=members&organizationId=" + encodeURIComponent(organizationId)), readJson<OrganizationInvite[]>("/api/portfolio?resource=invites&organizationId=" + encodeURIComponent(organizationId))]);
    setMembers(memberRows); setInvites(inviteRows);
    setMemberRoleEdits(Object.fromEntries(memberRows.map((member) => [member.user_id, member.role])));
  }

  async function handleMemberRoleSave(userId: string) {
    try {
      await postJson({ action: "change-member-role", organizationId, userId, role: memberRoleEdits[userId] });
      await refreshOrganizationAdmin(); setMessage("Organization member role updated."); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not update member role."); }
  }

  async function handleMemberRemove(userId: string) {
    if (!window.confirm("Remove this person from the selected organization? Their personal portfolios will not be affected.")) return;
    try {
      await postJson({ action: "remove-member", organizationId, userId });
      await refreshOrganizationAdmin(); setMessage("Organization membership removed."); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not remove organization member."); }
  }

  async function handleInviteRevoke(inviteId: string) {
    if (!window.confirm("Revoke this invitation? Anyone holding the code will no longer be able to use it.")) return;
    try {
      await postJson({ action: "revoke-invite", inviteId });
      await refreshOrganizationAdmin(); setMessage("Invitation revoked."); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not revoke invitation."); }
  }
  async function signOut() {
    await fetch("/api/portfolio/auth", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "sign-out" }) });
    window.location.href = "/account";
  }

  return (
    <Container className="py-8 lg:py-12">
      <PageHeader eyebrow="Markets · Cloud Portfolio" title="Portfolio workspaces">
        Save portfolio data to your account, share organization-owned portfolios with teammates, and record transactions so current positions can be derived from the ledger. Cloud storage is separate from the browser-only portfolio.
      </PageHeader>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Link href="/app/markets/portfolio" className="text-sm text-[color:var(--muted)] underline-offset-4 hover:underline">Browser-only portfolio</Link>
        <div className="flex items-center gap-3 text-sm">
          {user ? <span className="text-[color:var(--muted)]">{user.email || user.id}</span> : null}
          {user ? <button type="button" className="btn btn-secondary" onClick={signOut}>Sign out</button> : <Link className="btn btn-primary" href="/account">Sign in</Link>}
        </div>
      </div>

      {authLoading ? <p className="text-sm text-[color:var(--muted)]">Checking account…</p> : null}
      {!authLoading && !user ? (
        <div className="rounded-xl border border-[color:var(--border)] p-5">
          <h2 className="text-lg font-semibold">Sign in to use cloud portfolios</h2>
          <p className="mt-2 text-sm text-[color:var(--muted)]">Your browser-only portfolio remains available without an account. Sign in to create personal portfolios or collaborate with an organization.</p>
          <Link className="btn btn-primary mt-4 inline-flex" href="/account">Sign in or create account</Link>
        </div>
      ) : null}

      {user ? (
        <div className="space-y-6">
          {error ? <ErrorNote message={error} /> : null}
          {message ? <p role="status" className="text-sm text-[color:var(--muted)]">{message}</p> : null}

          <section className="grid gap-5 lg:grid-cols-2">
            <div className="rounded-xl border border-[color:var(--border)] p-5">
              <h2 className="text-lg font-semibold">Create a portfolio</h2>
              <form className="mt-4 space-y-3" onSubmit={handleCreatePortfolio}>
                <label className="block text-sm">Portfolio name<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" required maxLength={160} value={portfolioName} onChange={(event) => setPortfolioName(event.target.value)} /></label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block text-sm">Reporting currency<select className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" value={baseCurrency} onChange={(event) => setBaseCurrency(event.target.value)}>{currencies.map((currency) => <option key={currency} value={currency}>{currency}</option>)}</select></label>
                  <label className="block text-sm">Owner<select className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" value={ownership} onChange={(event) => setOwnership(event.target.value as "personal" | "organization")}><option value="personal">Just me</option><option value="organization">Organization</option></select></label>
                </div>
                {ownership === "organization" ? <label className="block text-sm">Organization<select className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" required value={organizationId} onChange={(event) => setOrganizationId(event.target.value)}>{organizations.filter((item) => !item.archived_at).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.role}</option>)}</select></label> : null}
                <button className="btn btn-primary" type="submit" disabled={ownership === "organization" && !organizationId}>Create portfolio</button>
              </form>
            </div>

            <div className="rounded-xl border border-[color:var(--border)] p-5">
              <h2 className="text-lg font-semibold">Organization workspaces</h2>
              {organizations.length ? <ul className="mt-3 space-y-2 text-sm">{organizations.map((item) => <li key={item.id} className="flex flex-wrap justify-between gap-2"><span>{item.name} <span className="text-[color:var(--muted)]">({item.role})</span></span>{item.archived_at ? <span>Archived</span> : null}</li>)}</ul> : <p className="mt-2 text-sm text-[color:var(--muted)]">No organization yet. Create one to share portfolios with teammates.</p>}
              <form className="mt-4 flex flex-wrap gap-2" onSubmit={handleCreateOrganization}>
                <input className="min-w-0 flex-1 rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2 text-sm" placeholder="New organization name" required maxLength={120} value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} />
                <button className="btn btn-secondary" type="submit">Create workspace</button>
              </form>
              {organizations.some((item) => item.role === "owner" || item.role === "admin") ? (
                <form className="mt-4 space-y-2" onSubmit={handleInvite}>
                  <label className="block text-sm">Create invite for<select className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" required value={organizationId} onChange={(event) => setOrganizationId(event.target.value)}>{organizations.filter((item) => !item.archived_at && (item.role === "owner" || item.role === "admin")).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                  <label className="block text-sm">Role<select className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" value={inviteRole} onChange={(event) => setInviteRole(event.target.value)}><option value="analyst">Analyst</option><option value="viewer">Viewer</option><option value="manager">Manager</option><option value="admin">Admin (owner only)</option></select></label>
                  <button className="btn btn-secondary" type="submit">Generate one-time invite code</button>
                  {newInvite ? <div className="rounded-lg border border-[color:var(--border)] p-3"><p className="text-xs text-[color:var(--muted)]">Copy this code now. It is not shown again.</p><code className="mt-2 block break-all text-sm">{newInvite}</code><button className="mt-2 text-sm underline" type="button" onClick={() => navigator.clipboard.writeText(newInvite)}>Copy code</button></div> : null}
                </form>
              ) : null}
              {organizations.some((item) => item.id === organizationId && !item.archived_at && (item.role === "owner" || item.role === "admin")) ? <div className="mt-5 space-y-4">
                <div><h3 className="font-medium">Workspace members</h3>
                  {members.length ? <ul className="mt-2 space-y-2">{members.map((member) => <li key={member.user_id} className="flex flex-wrap items-center gap-2 rounded-lg border border-[color:var(--border)] p-3 text-sm"><div className="min-w-0 flex-1"><strong className="break-all">{member.email || member.user_id}</strong><span className="ml-2 text-xs text-[color:var(--muted)]">{member.role}</span></div>{member.role !== "owner" ? <><select className="rounded-lg border border-[color:var(--border)] bg-transparent px-2 py-1" aria-label={"Role for " + (member.email || member.user_id)} value={memberRoleEdits[member.user_id] || member.role} onChange={(event) => setMemberRoleEdits((current) => ({ ...current, [member.user_id]: event.target.value }))}><option value="admin" disabled={!organizations.some((org) => org.id === organizationId && org.role === "owner")}>Admin</option><option value="manager">Manager</option><option value="analyst">Analyst</option><option value="viewer">Viewer</option></select><button type="button" className="text-xs underline" onClick={() => { void handleMemberRoleSave(member.user_id); }}>Save role</button><button type="button" className="text-xs underline" onClick={() => { void handleMemberRemove(member.user_id); }}>Remove</button></> : <span className="text-xs text-[color:var(--muted)]">Owner</span>}</li>)}</ul> : <p className="mt-2 text-xs text-[color:var(--muted)]">No members loaded yet.</p>}</div>
                <div><h3 className="font-medium">Invite codes</h3>
                  {invites.length ? <ul className="mt-2 space-y-2">{invites.map((invite) => <li key={invite.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[color:var(--border)] p-3 text-sm"><span>{invite.role} · {invite.use_count}/{invite.max_uses} used · expires {new Date(invite.expires_at).toLocaleDateString()} {invite.revoked_at ? "· revoked" : invite.use_count >= invite.max_uses ? "· used" : new Date(invite.expires_at) <= new Date() ? "· expired" : "· active"}</span>{!invite.revoked_at && invite.use_count < invite.max_uses && new Date(invite.expires_at) > new Date() ? <button type="button" className="text-xs underline" onClick={() => { void handleInviteRevoke(invite.id); }}>Revoke</button> : null}</li>)}</ul> : <p className="mt-2 text-xs text-[color:var(--muted)]">No invitations yet.</p>}</div>
              </div> : null}
              <form className="mt-4 flex flex-wrap gap-2" onSubmit={handleAcceptInvite}>
                <input className="min-w-0 flex-1 rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2 text-sm" placeholder="Paste an invite code" required value={inviteCode} onChange={(event) => setInviteCode(event.target.value)} />
                <button className="btn btn-secondary" type="submit">Join workspace</button>
              </form>
            </div>
          </section>

          <section className="rounded-xl border border-[color:var(--border)] p-5">
            <h2 className="text-lg font-semibold">Your accessible portfolios</h2>
            {portfolios.length ? <div className="mt-3 flex flex-wrap items-center gap-3"><select className="min-w-0 max-w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>{portfolios.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.base_currency}{item.organization_id ? " · shared" : " · personal"}</option>)}</select><span className="text-xs text-[color:var(--muted)]">Members can only see portfolios granted through their own account or organization.</span></div> : <p className="mt-2 text-sm text-[color:var(--muted)]">Create a portfolio above to begin.</p>}
          </section>

          {data ? (
            <section className="space-y-5">
              <div className="rounded-xl border border-[color:var(--border)] p-5">
                <h2 className="text-lg font-semibold">{data.portfolio.name}: positions derived from transactions</h2>
                <p className="mt-1 text-sm text-[color:var(--muted)]">Average cost is based on the recorded ledger. Current values use manually entered prices and FX; they are not live quotes or comprehensive performance.</p>
                {loadingData ? <p className="mt-3 text-sm">Refreshing portfolio…</p> : null}
                {positions.length ? (
                  <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead><tr className="border-b border-[color:var(--border)] text-[color:var(--muted)]"><th className="py-2 pr-3">Instrument</th><th className="py-2 pr-3">Quantity</th><th className="py-2 pr-3">Average cost</th><th className="py-2 pr-3">Current price</th><th className="py-2 pr-3">Value</th><th className="py-2 pr-3">Data quality</th></tr></thead><tbody>{positions.map((item) => { const fx = item.instrument.currency === data.portfolio.base_currency ? 1 : item.fx; const valueBase = item.valueLocal == null || !fx ? null : item.valueLocal * fx; return <tr key={item.instrument.id} className="border-b border-[color:var(--border)]"><td className="py-3 pr-3"><strong>{item.instrument.name}</strong><span className="block text-xs text-[color:var(--muted)]">{item.instrument.ticker || item.instrument.country || item.instrument.asset_type}</span></td><td className="py-3 pr-3">{item.quantity.toLocaleString("en", { maximumFractionDigits: 6 })}</td><td className="py-3 pr-3">{money(item.averageCost, item.instrument.currency)}</td><td className="py-3 pr-3">{money(item.currentPrice, item.instrument.currency)}{item.instrument.price_as_of ? <span className="block text-xs text-[color:var(--muted)]">As of {item.instrument.price_as_of}</span> : null}</td><td className="py-3 pr-3">{money(valueBase, data.portfolio.base_currency)}</td><td className="py-3 pr-3">{item.warnings.length ? item.warnings.join(" ") : item.currentPrice == null ? "Price missing" : item.instrument.currency !== data.portfolio.base_currency && !item.fx ? "FX missing" : "Entered data"}</td></tr>; })}</tbody></table></div>
                ) : <p className="mt-3 text-sm text-[color:var(--muted)]">No positions yet. Add an instrument and record a buy transaction below.</p>}
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                <div className="rounded-xl border border-[color:var(--border)] p-5">
                  <h3 className="text-lg font-semibold">Add instrument</h3>
                  <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={handleCreateInstrument}>
                    <label className="block text-sm sm:col-span-2">Name<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" required maxLength={200} value={instrument.name} onChange={(event) => setInstrument({ ...instrument, name: event.target.value })} /></label>
                    <label className="block text-sm">Ticker<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" value={instrument.ticker} onChange={(event) => setInstrument({ ...instrument, ticker: event.target.value })} /></label>
                    <label className="block text-sm">Asset type<select className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" value={instrument.assetType} onChange={(event) => setInstrument({ ...instrument, assetType: event.target.value })}><option>Stock</option><option>ETF</option><option>Bond</option><option>Treasury bill</option><option>Money-market fund</option><option>Mutual fund</option><option>REIT</option><option>Fixed deposit</option><option>Other</option></select></label>
                    <label className="block text-sm">Country<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" value={instrument.country} onChange={(event) => setInstrument({ ...instrument, country: event.target.value })} /></label>
                    <label className="block text-sm">Sector<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" value={instrument.sector} onChange={(event) => setInstrument({ ...instrument, sector: event.target.value })} /></label>
                    <label className="block text-sm">Currency<select className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" value={instrument.currency} onChange={(event) => setInstrument({ ...instrument, currency: event.target.value })}>{currencies.map((currency) => <option key={currency}>{currency}</option>)}</select></label>
                    <label className="block text-sm">Current price<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" type="number" min="0.00000001" step="any" value={instrument.currentPrice} onChange={(event) => setInstrument({ ...instrument, currentPrice: event.target.value })} /></label>
                    <label className="block text-sm">Price date<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" type="date" max={today} value={instrument.priceAsOf} onChange={(event) => setInstrument({ ...instrument, priceAsOf: event.target.value })} /></label>
                    <label className="block text-sm">FX to reporting currency<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" type="number" min="0.000000000001" step="any" value={instrument.fxToBase} onChange={(event) => setInstrument({ ...instrument, fxToBase: event.target.value })} /></label>
                    <label className="block text-sm">FX date<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" type="date" max={today} value={instrument.fxAsOf} onChange={(event) => setInstrument({ ...instrument, fxAsOf: event.target.value })} /></label>
                    <button className="btn btn-primary sm:col-span-2" type="submit">Add instrument</button>
                  </form>
                </div>

                <div className="rounded-xl border border-[color:var(--border)] p-5">
                  <h3 className="text-lg font-semibold">Record transaction</h3>
                  <form className="mt-4 space-y-3" onSubmit={handleCreateTransaction}>
                    <label className="block text-sm">Instrument<select className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" required value={transaction.instrumentId} onChange={(event) => setTransaction({ ...transaction, instrumentId: event.target.value })}><option value="">Select instrument</option>{data.instruments.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.currency}</option>)}</select></label>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="block text-sm">Type<select className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" value={transaction.transactionType} onChange={(event) => setTransaction({ ...transaction, transactionType: event.target.value })}><option value="BUY">Buy</option><option value="SELL">Sell</option><option value="TRANSFER_IN">Transfer in</option><option value="TRANSFER_OUT">Transfer out</option><option value="ADJUSTMENT">Opening adjustment</option></select></label>
                      <label className="block text-sm">Transaction date<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" type="date" required max={today} value={transaction.transactionDate} onChange={(event) => setTransaction({ ...transaction, transactionDate: event.target.value })} /></label>
                      <label className="block text-sm">Quantity<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" type="number" min="0.00000001" step="any" required value={transaction.quantity} onChange={(event) => setTransaction({ ...transaction, quantity: event.target.value })} /></label>
                      <label className="block text-sm">Unit price<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" type="number" min="0" step="any" required value={transaction.unitPrice} onChange={(event) => setTransaction({ ...transaction, unitPrice: event.target.value })} /></label>
                      <label className="block text-sm">Fees<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" type="number" min="0" step="any" value={transaction.fees} onChange={(event) => setTransaction({ ...transaction, fees: event.target.value })} /></label>
                    </div>
                    <label className="block text-sm">Notes<input className="mt-1 w-full rounded-lg border border-[color:var(--border)] bg-transparent px-3 py-2" maxLength={500} value={transaction.notes} onChange={(event) => setTransaction({ ...transaction, notes: event.target.value })} /></label>
                    <button className="btn btn-primary" type="submit" disabled={!data.instruments.length}>Record transaction</button>
                  </form>
                </div>
              </div>

              <div className="rounded-xl border border-[color:var(--border)] p-5">
                <h3 className="text-lg font-semibold">Valuation snapshots</h3>
                <p className="mt-2 text-sm text-[color:var(--muted)]">Save a dated snapshot of ledger-derived positions and manually entered prices/FX. This is not a return calculation or live valuation.</p>
                <button className="btn btn-secondary mt-3" type="button" disabled={!positions.length || loadingData} onClick={() => { void handleSaveValuation(); }}>Save current snapshot</button>
                {valuations.length ? <ol className="mt-4 space-y-2">{valuations.slice(0,10).map((item) => <li key={item.id} className="rounded-lg border border-[color:var(--border)] p-3 text-sm"><div className="flex flex-wrap justify-between gap-2"><strong>{item.valuation_date} · {item.model}</strong><span>{item.base_currency}</span></div><p className="mt-1 text-xs text-[color:var(--muted)]">{item.notes || "Saved portfolio snapshot"} · {new Date(item.created_at).toLocaleString()}</p></li>)}</ol> : <p className="mt-3 text-sm text-[color:var(--muted)]">No saved snapshots yet.</p>}
              </div>
              <section className="rounded-xl border border-[color:var(--border)] p-5">
                <h3 className="text-lg font-semibold">Migrate existing browser portfolio</h3>
                <p className="mt-2 text-sm text-[color:var(--muted)]">This copies local holdings into the selected cloud portfolio as opening adjustments and saves local valuation reviews as historical snapshots. The migration is atomic and retry-safe. The original browser data is not deleted. Reporting currencies must match.</p>
                <button className="btn btn-secondary mt-3" type="button" disabled={migrationBusy || migrationComplete} onClick={() => { void handleMigrateLocalPortfolio(); }}>{migrationBusy ? "Migrating…" : migrationComplete ? "Migration completed in this session" : "Migrate local data to this portfolio"}</button>
              </section>
              <div className="rounded-xl border border-[color:var(--border)] p-5">
                <h3 className="text-lg font-semibold">Import transaction ledger</h3>
                <p className="mt-2 text-sm text-[color:var(--muted)]">Upload CSV or XLSX with transaction_date, transaction_type, currency, quantity, unit_price, cash_amount, fees, fx_to_base, external_id, notes and instrument_id, ticker or instrument_name. Trade rows must resolve to an instrument in this portfolio. Every row is checked before the server commits the batch atomically.</p>
                <input className="mt-4 block w-full text-sm" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-label="Choose transaction CSV or Excel file" onChange={(event) => { void handleTransactionFile(event.target.files?.[0] || null); event.currentTarget.value = ""; }} />
                {importPreview ? <div className="mt-4 space-y-3"><p className="text-sm">{importPreview.filename}: {importPreview.rows.length} valid row(s) of {importPreview.sourceRows}; {importPreview.errors.length} error(s).</p>{importPreview.errors.length ? <ul className="max-h-40 list-disc space-y-1 overflow-auto pl-5 text-xs text-red-400">{importPreview.errors.slice(0,50).map((item,index) => <li key={index}>{item}</li>)}{importPreview.errors.length > 50 ? <li>Showing first 50 errors.</li> : null}</ul> : <p className="text-xs text-[color:var(--muted)]">All rows passed client validation. The server validates again before writing.</p>}<button className="btn btn-primary" type="button" disabled={importBusy || importPreview.errors.length > 0 || !importPreview.rows.length} onClick={() => { void commitTransactionImport(); }}>{importBusy ? "Importing…" : "Validate and commit all rows"}</button></div> : null}
              </div>
              <div className="rounded-xl border border-[color:var(--border)] p-5">
                <h3 className="text-lg font-semibold">Transaction ledger</h3>
                {data.transactions.length ? <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[650px] text-left text-sm"><thead><tr className="border-b border-[color:var(--border)] text-[color:var(--muted)]"><th className="py-2 pr-3">Date</th><th className="py-2 pr-3">Instrument</th><th className="py-2 pr-3">Type</th><th className="py-2 pr-3">Quantity</th><th className="py-2 pr-3">Unit price</th><th className="py-2 pr-3">Fees</th></tr></thead><tbody>{data.transactions.map((item) => <tr key={item.id} className="border-b border-[color:var(--border)]"><td className="py-3 pr-3">{item.transaction_date}</td><td className="py-3 pr-3">{data.instruments.find((instrumentItem) => instrumentItem.id === item.instrument_id)?.name || "Cash movement"}</td><td className="py-3 pr-3">{item.transaction_type}</td><td className="py-3 pr-3">{Number(item.quantity).toLocaleString("en", { maximumFractionDigits: 6 })}</td><td className="py-3 pr-3">{money(Number(item.unit_price), item.currency)}</td><td className="py-3 pr-3">{money(Number(item.fees), item.currency)}</td></tr>)}</tbody></table></div> : <p className="mt-2 text-sm text-[color:var(--muted)]">No transactions recorded.</p>}
              </div>
            </section>
          ) : selectedId ? <p className="text-sm text-[color:var(--muted)]">Loading selected portfolio…</p> : null}
        </div>
      ) : null}
    </Container>
  );
}
