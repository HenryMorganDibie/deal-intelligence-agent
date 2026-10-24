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
type Instrument = { id: string; portfolio_id: string; name: string; ticker: string | null; market: string | null; country: string | null; sector: string | null; asset_type: string; currency: string; current_price: number | null; price_as_of: string | null; fx_to_base: number | null; fx_as_of: string | null };
type Transaction = { id: string; portfolio_id: string; instrument_id: string | null; transaction_date: string; transaction_type: string; quantity: number; unit_price: number; cash_amount: number; fees: number; currency: string; fx_to_base: number | null; notes: string | null };
type PortfolioData = { portfolio: Portfolio; instruments: Instrument[]; transactions: Transaction[] };
type CloudValuation = { id: string; valuation_date: string; base_currency: string; model: string; snapshot: Record<string, unknown>; notes: string | null; created_at: string };

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
  const [selectedId, setSelectedId] = useState("");
  const [data, setData] = useState<PortfolioData | null>(null);
  const [valuations, setValuations] = useState<CloudValuation[]>([]);
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
