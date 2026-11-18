const { test, expect } = require("@playwright/test");
const fs = require("node:fs/promises");

const routes = [
  "/markets",
  "/markets/screener",
  "/markets/investments",
  "/markets/valuation",
  "/markets/portfolio",
  "/markets/compare",
  "/markets/portfolio/cloud",
  "/companies",
  "/research",
  "/deals",
  "/watchlists",
  "/coverage",
];

test("Markets and adjacent workspaces render without route failures", async ({ page }) => {
  for (const path of routes) {
    const response = await page.goto(path);
    expect(response, path + " should return a document").not.toBeNull();
    expect(response.status(), path + " should return HTTP 200").toBe(200);
    const heading = page.locator("h1").first();
    await expect(heading, path + " should render a visible page heading").toBeVisible();
    expect((await heading.innerText()).trim().length, path + " heading should not be empty").toBeGreaterThan(2);
  }
});

test("Markets overview keeps Research and Coverage in their own workspaces", async ({ page }) => {
  await page.goto("/markets");
  await expect(page.getByRole("heading", { name: "African equity markets today" })).toBeVisible();
  await expect(page.getByLabel("Search listed companies")).toBeVisible();
  await expect(page.getByText("Research a company", { exact: false })).toHaveCount(0);
  await expect(page.getByText("Search country, exchange or currency", { exact: false })).toHaveCount(0);
});

test("local portfolio supports add, persistence, CSV backup, clear and import", async ({ page }) => {
  await page.goto("/markets/portfolio");
  await expect(page.getByRole("heading", { name: "Portfolio", exact: true })).toBeVisible();

  await page.getByLabel("Company or investment name *").fill("Browser Test Equity");
  await page.getByLabel("Ticker / identifier").fill("BTE");
  await page.getByLabel("Country / market").fill("Nigeria");
  await page.getByLabel("Sector").fill("Technology");
  await page.getByLabel("Quantity / units *").fill("4");
  await page.getByLabel(/Cost per unit/).fill("25");
  await page.getByLabel(/Current price/).fill("30");
  await page.getByRole("button", { name: "Add holding" }).click();

  await expect(page.getByRole("status").filter({ hasText: "Holding added" })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "Browser Test Equity" })).toBeVisible();
  await expect.poll(async () => page.evaluate(() => {
    const saved = JSON.parse(localStorage.getItem("deal-intelligence-markets-portfolio-v1") || "{}");
    return saved.holdings?.length || 0;
  })).toBe(1);

  await page.getByRole("tab", { name: "Import & backup" }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV backup" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("deal-intelligence-portfolio.csv");
  const downloadPath = await download.path();
  expect(downloadPath).toBeTruthy();
  const csv = await fs.readFile(downloadPath, "utf8");
  expect(csv).toContain("Browser Test Equity");
  expect(csv).toContain("name,ticker,country,sector,asset_type,currency");

  const excelPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export Excel backup" }).click();
  const excelDownload = await excelPromise;
  expect(excelDownload.suggestedFilename()).toBe("deal-intelligence-portfolio.xlsx");
  const excelPath = await excelDownload.path();
  expect(excelPath).toBeTruthy();
  expect((await fs.readFile(excelPath)).byteLength).toBeGreaterThan(1000);

  await page.reload();                                       // reopens on the tab in the address (#import)
  await expect(page.getByRole("tab", { name: "Import & backup" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Holdings" }).click();
  await expect(page.getByRole("row").filter({ hasText: "Browser Test Equity" })).toBeVisible();

  await page.getByRole("tab", { name: "Import & backup" }).click();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Clear portfolio" }).click();
  await page.getByRole("tab", { name: "Holdings" }).click();
  await expect(page.getByText("Your portfolio starts here.")).toBeVisible();

  await page.getByRole("tab", { name: "Import & backup" }).click();
  await page.getByLabel("Choose CSV file").setInputFiles({
    name: "valid-portfolio.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("name,ticker,country,sector,asset_type,currency,quantity,cost_per_unit,current_price,fx_to_base\nImported Test,IMP,Kenya,Banking,Stock,KES,2,10,12,0.0075\n"),
  });
  await expect(page.getByRole("status").filter({ hasText: "Imported 1 holding" })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "Imported Test" })).toBeVisible();

  await page.getByRole("tab", { name: "Import & backup" }).click();
  await page.getByLabel("Choose CSV file").setInputFiles({
    name: "malformed.csv",
    mimeType: "text/csv",
    buffer: Buffer.from('name,currency,quantity,cost_per_unit\n"broken,USD,1,2\n'),
  });
  await expect(page.getByText(/unclosed quoted field/i)).toBeVisible();
  await page.getByRole("tab", { name: "Holdings" }).click();
  await expect(page.getByRole("row").filter({ hasText: "Imported Test" })).toBeVisible();

  await page.getByRole("tab", { name: "Import & backup" }).click();

  await page.getByLabel(/Choose Excel workbook/).setInputFiles(excelPath);
  await expect(page.getByRole("status").filter({ hasText: "Imported 1 holding" })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "Browser Test Equity" })).toBeVisible();
});


test("valuation history JSON backup exports, restores and rejects malformed data safely", async ({ page }) => {
  const today = new Date().toISOString().slice(0, 10);
  const snapshot = {
    id: "browser-valuation-1",
    company: "Example Bank",
    ticker: "EXBANK",
    country: "Nigeria",
    method: "ddm",
    modelFit: "financial-institution",
    modelFitConfirmed: true,
    currency: "NGN",
    statementSourceUrl: "https://example.com/annual-report",
    statementPeriod: today,
    quotePrice: 100,
    quoteDate: today,
    quoteSourceUrl: "https://example.com/quote",
    bearPerShare: 90,
    basePerShare: 110,
    bullPerShare: 120,
    calculatedAt: new Date().toISOString(),
  };
  const key = "deal-intelligence-markets-valuations-v1";
  await page.addInitScript(({ storageKey, initial }) => localStorage.setItem(storageKey, JSON.stringify(initial)), {
    storageKey: key,
    initial: [snapshot],
  });
  await page.goto("/markets/valuation");
  await page.getByRole("tab", { name: /Saved valuations/ }).click();
  await expect(page.getByRole("row").filter({ hasText: "Example Bank" })).toBeVisible();

  const exportPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export saved valuation history" }).click();
  const download = await exportPromise;
  expect(download.suggestedFilename()).toBe("deal-intelligence-valuation-history.json");
  const path = await download.path();
  const backup = JSON.parse(await fs.readFile(path, "utf8"));
  expect(backup.version).toBe(1);
  expect(backup.valuations).toHaveLength(1);
  expect(backup.valuations[0].id).toBe(snapshot.id);

  await page.evaluate(storageKey => localStorage.setItem(storageKey, "[]"), key);
  page.once("dialog", dialog => dialog.accept());
  await page.getByLabel(/Restore valuation history from JSON backup/).setInputFiles({
    name: "valuation-history.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(backup)),
  });
  await expect(page.getByRole("status").filter({ hasText: "Restored 1 saved valuation snapshot" })).toBeVisible();
  expect(await page.evaluate(storageKey => JSON.parse(localStorage.getItem(storageKey) || "[]").map(item => item.id), key)).toEqual([snapshot.id]);

  await page.getByLabel(/Restore valuation history from JSON backup/).setInputFiles({
    name: "malformed-history.json",
    mimeType: "application/json",
    buffer: Buffer.from('{"version":999,"valuations":[]}'),
  });
  await expect(page.getByText(/not a valid Deal Intelligence valuation-history backup/i)).toBeVisible();
  expect(await page.evaluate(storageKey => JSON.parse(localStorage.getItem(storageKey) || "[]").map(item => item.id), key)).toEqual([snapshot.id]);
});


test("currency conversion inputs update when the reporting currency changes", async ({ page }) => {
  await page.goto("/markets/portfolio");
  await page.getByLabel("Company or investment name *").fill("FX Test Equity");
  await page.getByLabel("Holding currency").selectOption("NGN");
  await page.getByLabel("Quantity / units *").fill("10");
  await page.getByLabel(/Cost per unit/).fill("50");
  await page.getByLabel(/Current price/).fill("100");
  await page.getByLabel(/FX to USD/).fill("0.001");
  await page.getByRole("button", { name: "Add holding" }).click();

  const before = await page.evaluate(() => JSON.parse(localStorage.getItem("deal-intelligence-markets-portfolio-v1") || "{}"));
  expect(before.baseCurrency).toBe("USD");
  expect(before.holdings[0].fxToBase).toBe(0.001);

  page.once("dialog", dialog => dialog.accept());
  await page.getByLabel("Portfolio reporting currency").selectOption("NGN");
  await expect.poll(async () => page.evaluate(() => JSON.parse(localStorage.getItem("deal-intelligence-markets-portfolio-v1") || "{}").baseCurrency)).toBe("NGN");
  const after = await page.evaluate(() => JSON.parse(localStorage.getItem("deal-intelligence-markets-portfolio-v1") || "{}"));
  expect(after.holdings[0].fxToBase).toBe(1);
  expect(after.holdings[0].currency).toBe("NGN");
});

test("the old Monitoring address forwards to Portfolio, which offers alerts for the holdings", async ({ page }) => {
  await page.goto("/markets/monitoring");
  await expect(page).toHaveURL(/\/markets\/portfolio$/);
  await page.getByLabel("Company or investment name *").fill("Example Bank");
  await page.getByLabel("Quantity / units *").fill("10");
  await page.getByLabel(/Cost per unit/).fill("5");
  await page.getByRole("button", { name: "Add holding" }).click();
  await expect(page.getByRole("button", { name: "Get alerts for these holdings" })).toBeVisible();
});

test("portfolio inputs support keyboard focus navigation", async ({ page }) => {
  await page.goto("/markets/portfolio");
  const name = page.getByLabel("Company or investment name *");
  const ticker = page.getByLabel("Ticker / identifier");
  await name.focus();
  await page.keyboard.press("Tab");
  await expect(ticker).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Asset type")).toBeFocused();
});

test("portfolio page remains usable at a narrow mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/markets/portfolio");
  await expect(page.getByRole("heading", { name: "Portfolio", exact: true })).toBeVisible();
  await expect(page.getByLabel("Company or investment name *")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add holding" })).toBeVisible();
});

test("cloud portfolio API does not disclose portfolio data without a session", async ({ request }) => {
  const response = await request.get("/api/portfolio?resource=portfolios");
  expect(response.status()).toBe(401);
  const body = await response.json();
  expect(body).not.toHaveProperty("portfolios");
  expect(body).not.toHaveProperty("user");

  const write = await request.post("/api/portfolio", {
    data: { action: "create-portfolio", name: "Must Not Be Created", baseCurrency: "USD" },
  });
  expect(write.status()).toBe(401);
  const writeBody = await write.json();
  expect(writeBody.error).toContain("Sign in");
});

test("password recovery validates email and never confirms whether an account exists", async ({ request }) => {
  const invalid = await request.post("/api/portfolio/auth", {
    data: { action: "recover-password", email: "not-an-email" },
  });
  expect(invalid.status()).toBe(400);
  expect(await invalid.json()).toMatchObject({ error: "Enter a valid account email." });

  const expired = await request.post("/api/portfolio/auth", {
    data: { action: "update-password", password: "LongEnoughPassword123" },
  });
  expect(expired.status()).toBe(401);
  expect(await expired.json()).toMatchObject({
    error: "Your reset session has expired. Request a new password-reset link.",
  });
});

test("Google OAuth authorization starts with PKCE and a same-site callback", async ({ request }) => {
  const response = await request.get("/api/portfolio/auth/google", { maxRedirects: 0 });
  expect(response.status()).toBe(307);
  const location = new URL(response.headers().location);
  expect(location.origin).toBe("https://test-project.supabase.co");
  expect(location.pathname).toBe("/auth/v1/authorize");
  expect(location.searchParams.get("provider")).toBe("google");
  expect(location.searchParams.get("redirect_to")).toBe("https://test.example/auth/callback");
  expect(location.searchParams.get("code_challenge_method")).toBe("s256");
  expect(location.searchParams.get("code_challenge")).toMatch(/^[A-Za-z0-9_-]{43}$/);
  expect(response.headers()["set-cookie"]).toContain("di_portfolio_oauth_verifier=");
  expect(response.headers()["set-cookie"]).toContain("HttpOnly");
});

test("OAuth callback rejects a missing PKCE verifier without creating a session", async ({ request }) => {
  const response = await request.post("/api/portfolio/auth", {
    data: { action: "complete-oauth", code: "synthetic-oauth-code" },
  });
  expect(response.status()).toBe(400);
  expect(await response.json()).toMatchObject({
    error: "Google sign-in could not be completed. Start again.",
  });
  expect(response.headers()["set-cookie"]).toContain("di_portfolio_oauth_verifier=");
});



test("password recovery request shows a privacy-preserving confirmation", async ({ page }) => {
  let submitted;
  await page.route("**/api/portfolio/auth", async route => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ authenticated: false }) });
      return;
    }
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
  });

  await page.goto("/account");
  await page.getByRole("button", { name: "Forgot password?" }).click();
  await page.getByLabel("Send a reset link to").fill("recovery@example.test");
  await page.getByRole("button", { name: "Send password-reset link" }).click();
  await expect(page.getByRole("status")).toContainText("If an account exists for that email");
  expect(submitted).toEqual({ action: "recover-password", email: "recovery@example.test" });
});

test("password reset page enforces the rules and the retyped password, and submits only the new password", async ({ page }) => {
  let submitted;
  await page.route("**/api/portfolio/auth", async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
  });
  await page.goto("/account/reset-password");
  const update = page.getByRole("button", { name: "Update password" });
  // A password that breaks the rules cannot be submitted.
  await page.getByLabel("New password", { exact: true }).fill("long-test-password-123");
  await page.getByLabel("Retype new password").fill("long-test-password-123");
  await expect(update).toBeDisabled();
  // Nor can two entries that differ.
  await page.getByLabel("New password", { exact: true }).fill("Kettle-Harbour-91!");
  await page.getByLabel("Retype new password").fill("Kettle-Harbour-91?");
  await expect(page.getByText("Passwords do not match")).toBeVisible();
  await expect(update).toBeDisabled();
  expect(submitted).toBeUndefined();

  await page.getByLabel("Retype new password").fill("Kettle-Harbour-91!");
  await update.click();
  await expect(page.getByRole("status")).toContainText("Your password has been updated");
  expect(submitted).toEqual({ action: "update-password", password: "Kettle-Harbour-91!", confirmPassword: "Kettle-Harbour-91!" });
});

test("sign-up enforces the password rules and the retyped password before it can submit", async ({ page }) => {
  await page.goto("/account?mode=sign-up");
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  await page.getByLabel("Email").fill("ada@example.com");
  await page.getByLabel("Username").fill("ada_l");
  await page.getByLabel("Nickname").fill("Ada");
  const submit = page.getByRole("button", { name: "Create account", exact: true });

  await page.getByLabel("Password", { exact: true }).fill("weakpass");
  await expect(page.getByText("At least 12 characters")).toBeVisible();
  await expect(submit).toBeDisabled();

  await page.getByLabel("Password", { exact: true }).fill("Kettle-Harbour-91!");
  await page.getByLabel("Retype password").fill("Kettle-Harbour-91?");
  await expect(page.getByText("Passwords do not match")).toBeVisible();
  await expect(submit).toBeDisabled();

  await page.getByLabel("Retype password").fill("Kettle-Harbour-91!");
  await expect(page.getByText("✓ Passwords match")).toBeVisible();
  await expect(page.getByText("Very weak")).toHaveCount(0);
  await expect(submit).toBeDisabled();                     // not until the age and terms box is ticked
  await page.getByLabel(/I am 18 or older/).check();
  await expect(submit).toBeEnabled();
});

test("Google sign-up waits for the age confirmation; legal pages are public and linked", async ({ page }) => {
  await page.goto("/account?mode=sign-up");
  await expect(page.getByRole("link", { name: "Continue with Google" })).toHaveCount(0);
  await page.getByRole("button", { name: "Continue with Google" }).click();
  await expect(page.getByText(/confirm you are 18 or older before continuing with Google/)).toBeVisible();
  await page.getByLabel(/I am 18 or older/).check();
  await expect(page.getByRole("link", { name: "Continue with Google" })).toHaveAttribute("href", "/api/portfolio/auth/google");
  for (const [path, heading] of [["/terms", "Terms of Use"], ["/privacy", "Privacy notice"], ["/copyright", "Copyright and DMCA notices"]]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: "Designated agent" })).toBeVisible();
  await expect(page.locator("footer").getByRole("link", { name: "Copyright and DMCA" })).toBeVisible();
});

test("admin page lists accounts and who is using the app", async ({ page }) => {
  const now = new Date().toISOString();
  await page.route("**/api/data/admin/stats", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    since: "2026-10-05", totals: { views: 10, visitors: 4, users: 2, returning_users: 1, engaged_visitors: 2 },
    days: [], pages: [], actions: [], app_page_activity: [],
  }) }));
  await page.route("**/api/data/admin/feedback", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [] }) }));
  let accountsBody;
  await page.route("**/api/data/admin/accounts", (route) => {
    accountsBody = route.request().postDataJSON();
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      since: "2026-10-05", days: 30,
      totals: { accounts: 2, active_in_period: 1, returning_in_period: 1, new_in_period: 2, active_7d: 1, never_used: 1,
                unconfirmed: 1, with_username: 1, google: 1, two_factor: 0 },
      daily: [{ day: "2026-11-02", signups: 1, active: 0 }, { day: "2026-11-03", signups: 1, active: 1 }],
      accounts: [
        { email: "ada@example.com", username: "ada", display_name: "Ada", created_at: now, confirmed: true,
          last_sign_in_at: now, last_seen_at: now, active_days: 3, providers: ["google"], two_factor: false, email_alerts: 1 },
        { email: "new@example.com", username: null, display_name: null, created_at: now, confirmed: false,
          last_sign_in_at: null, last_seen_at: null, active_days: 0, providers: ["email"], two_factor: false, email_alerts: 0 },
      ],
    }) });
  });
  await page.goto("/admin");
  await page.getByPlaceholder("Admin key").fill("owner-key");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
  await expect(page.getByText("Super admin")).toBeVisible();
  await page.getByRole("navigation", { name: "Admin sections" }).first().getByRole("button", { name: "Accounts" }).click();
  await expect(page.getByRole("heading", { name: "Accounts", exact: true })).toBeVisible();
  await expect(page.getByText("@ada · ada@example.com")).toBeVisible();
  expect(accountsBody).toEqual({ key: "owner-key", days: 30 });
  await expect(page.getByText("Google · 1 watchlist email")).toBeVisible();
  await page.getByLabel("Filter accounts").selectOption("never");
  await expect(page.getByText("new@example.com")).toBeVisible();
  await expect(page.getByText("ada@example.com")).toHaveCount(0);
  await page.screenshot({ path: "test-results/admin-accounts.png", fullPage: true });
});

test("admin can suspend, reinstate and delete an account, with a typed confirmation for deletion", async ({ page }) => {
  const now = new Date().toISOString();
  const json = (body) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/data/admin/stats", (route) => route.fulfill(json({ since: "2026-10-05", totals: {}, days: [], pages: [], actions: [], app_page_activity: [] })));
  await page.route("**/api/data/admin/feedback", (route) => route.fulfill(json({ items: [] })));
  await page.route("**/api/data/admin/accounts", (route) => route.fulfill(json({
    since: "2026-10-05", days: 30, totals: { accounts: 1, active_in_period: 1, returning_in_period: 0, new_in_period: 1 }, daily: [],
    accounts: [{ email: "ada@example.com", username: "ada", display_name: "Ada", created_at: now, confirmed: true, last_sign_in_at: now,
      last_seen_at: now, active_days: 3, providers: ["email"], two_factor: false, email_alerts: 0, subscription_status: "active", suspended: false }],
  })));
  const log = [];
  await page.route("**/api/data/admin/accounts/log", (route) => route.fulfill(json(log)));
  const sent = [];
  await page.route("**/api/data/admin/accounts/suspend", (route) => {
    const body = route.request().postDataJSON();
    sent.push(body);
    log.unshift({ at: now, action: body.suspend ? "suspended" : "reinstated", account: "a***@example.com", reason: body.reason });
    return route.fulfill(json({ email: body.email, suspended: body.suspend, renewal: body.suspend ? "cancelled" : null, warning: null }));
  });
  await page.route("**/api/data/admin/accounts/delete", (route) => {
    sent.push(route.request().postDataJSON());
    return route.fulfill(json({ email: "ada@example.com", result: "deleted", renewal: null }));
  });

  await page.goto("/admin#accounts");
  await page.getByPlaceholder("Admin key").fill("owner-key");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("navigation", { name: "Admin sections" }).first().getByRole("button", { name: "Accounts" }).click();

  await page.getByRole("button", { name: "Suspend", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("stops renewing")).toBeVisible();
  await dialog.getByLabel(/Reason/).fill("scraping");
  await dialog.getByRole("button", { name: "Suspend account" }).click();
  await expect(page.getByText("ada@example.com is suspended. Their Paystack renewal was cancelled.")).toBeVisible();
  await expect(page.locator("table").getByText("Suspended", { exact: true })).toBeVisible();
  await expect(page.getByText("a***@example.com")).toBeVisible();
  expect(sent[0]).toEqual({ key: "owner-key", email: "ada@example.com", suspend: true, reason: "scraping" });

  await page.getByRole("button", { name: "Reinstate", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Reinstate account" }).click();
  await expect(page.getByText("ada@example.com is reinstated.")).toBeVisible();

  await page.getByRole("button", { name: "Delete", exact: true }).click();
  const del = page.getByRole("dialog").getByRole("button", { name: "Delete permanently" });
  await expect(del).toBeDisabled();
  await page.getByLabel("Type the email to confirm").fill("ada@example.com");
  await expect(del).toBeEnabled();
  await page.screenshot({ path: "test-results/admin-delete-dialog.png" });
  await del.click();
  await expect(page.getByText("ada@example.com was deleted.")).toBeVisible();
  await expect(page.getByText("No accounts match.")).toBeVisible();
  expect(sent[2]).toEqual({ key: "owner-key", email: "ada@example.com", confirm: "ada@example.com", reason: "" });
});

test("the app header has an account menu that signs out", async ({ page }) => {
  let signedOut = false;
  let sessionReads = 0;
  await page.route("**/api/portfolio/auth", async (route) => {
    if (route.request().method() === "GET") {
      sessionReads += 1;
      await route.fulfill({ status: signedOut ? 401 : 200, contentType: "application/json", body: JSON.stringify(signedOut
        ? { authenticated: false }
        : { authenticated: true, user: { email: "ada@example.com" }, profile: { username: "ada_l", displayName: "Bola Ade" }, mfa: { enrolled: false } }) });
      return;
    }
    expect(route.request().postDataJSON()).toEqual({ action: "sign-out" });
    signedOut = true;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
  });
  await page.goto("/deals");
  const trigger = page.getByRole("button", { name: "Open account menu" });
  // The header names the account (its initial), read once for the browser session.
  await expect(trigger).toContainText("B");             // the display name's initial, not a placeholder
  await expect.poll(() => sessionReads).toBe(1);
  await page.goto("/companies");
  await expect(trigger).toContainText("B");
  expect(sessionReads).toBe(1);                        // later pages use the kept name, with no request
  await trigger.click();
  await expect(page.getByRole("menu", { name: "Account" })).toContainText("@ada_l");
  expect(sessionReads).toBe(2);                        // opening the menu reads the full account once
  await expect(page.getByRole("menu", { name: "Account" })).toContainText("ada@example.com");
  await expect(page.getByRole("menuitem", { name: "Password and security" })).toHaveAttribute("href", "/account/security");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu", { name: "Account" })).toHaveCount(0);
  await trigger.click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.waitForURL("**/account");
  expect(signedOut).toBe(true);
});

test("each paid plan shows its renewal terms beside the subscribe button", async ({ page }) => {
  await page.goto("/pricing");
  const pro = page.getByTestId("renewal-pro");
  await expect(pro).toContainText(/Renews automatically every month at .+ until you cancel/);
  await expect(pro).toContainText("keep access until the end of the period you paid for");
  await page.getByRole("button", { name: /Yearly/ }).click();
  await expect(pro).toContainText("Renews automatically every year");
});

test("a market brief can be limited to investors from one country", async ({ page }) => {
  await page.goto("/market-briefs/new?investor_country=US&lookback_days=180");
  const from = page.getByLabel("Investors from");
  await expect(from).toHaveValue("US");                     // a link can open the form already set
  await from.selectOption("GB");
  await expect(from).toHaveValue("GB");
  await from.selectOption("KE");                            // African home countries are offered too
  await expect(from).toHaveValue("KE");
  await page.goto("/market-briefs/new?investor_country=ZZ");
  await expect(page.getByLabel("Investors from")).toHaveValue("");   // an unknown code is ignored
});
