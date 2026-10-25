const { test, expect } = require("@playwright/test");
const fs = require("node:fs/promises");

const routes = [
  "/app/markets",
  "/app/markets/valuation",
  "/app/markets/portfolio",
  "/app/markets/compare",
  "/app/markets/monitoring",
  "/app/markets/portfolio/cloud",
  "/app/companies",
  "/app/research",
  "/app/deals",
  "/app/watchlists",
  "/app/coverage",
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
  await page.goto("/app/markets");
  await expect(page.getByText("Explore Investments", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("Research a company", { exact: false })).toHaveCount(0);
  await expect(page.getByText("Search country, exchange or currency", { exact: false })).toHaveCount(0);
});

test("local portfolio supports add, persistence, CSV backup, clear and import", async ({ page }) => {
  await page.goto("/app/markets/portfolio");
  await expect(page.getByRole("heading", { name: "Your portfolio, in context." })).toBeVisible();

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

  await page.reload();
  await expect(page.getByRole("row").filter({ hasText: "Browser Test Equity" })).toBeVisible();

  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Clear portfolio" }).click();
  await expect(page.getByText("Your portfolio starts here.")).toBeVisible();

  await page.getByLabel("Choose CSV file").setInputFiles({
    name: "valid-portfolio.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("name,ticker,country,sector,asset_type,currency,quantity,cost_per_unit,current_price,fx_to_base\nImported Test,IMP,Kenya,Banking,Stock,KES,2,10,12,0.0075\n"),
  });
  await expect(page.getByRole("status").filter({ hasText: "Imported 1 holding" })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "Imported Test" })).toBeVisible();

  await page.getByLabel("Choose CSV file").setInputFiles({
    name: "malformed.csv",
    mimeType: "text/csv",
    buffer: Buffer.from('name,currency,quantity,cost_per_unit\n"broken,USD,1,2\n'),
  });
  await expect(page.getByText(/unclosed quoted field/i)).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "Imported Test" })).toBeVisible();

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
  await page.goto("/app/markets/valuation");

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
  await page.goto("/app/markets/portfolio");
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

test("monitoring presents explicit empty and feed-error states", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("deal-intelligence-markets-portfolio-v1", JSON.stringify({
    version: 1,
    baseCurrency: "USD",
    holdings: [{ id: "monitor-h1", name: "Example Bank", ticker: "EXBANK", country: "Nigeria" }],
  })));
  const eventsRoute = /\/api\/events(?:\?.*)?$/;
  await page.route(eventsRoute, route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ events: [], count: 0 }),
  }));
  await page.goto("/app/markets/monitoring");
  await expect(page.getByText(/No events were returned for this period/i)).toBeVisible();

  await page.unroute(eventsRoute);
  await page.route(eventsRoute, route => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Market events temporarily unavailable." }),
  }));
  await page.getByRole("button", { name: "Refresh events" }).click();
  await expect(page.getByText(/service unavailable|temporarily unavailable|market events could not be loaded/i)).toBeVisible();
});

test("portfolio inputs support keyboard focus navigation", async ({ page }) => {
  await page.goto("/app/markets/portfolio");
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
  await page.goto("/app/markets/portfolio");
  await expect(page.getByRole("heading", { name: "Your portfolio, in context." })).toBeVisible();
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

test("Google sign-in starts a PKCE flow with a same-site callback and protected verifier cookie", async ({ request }) => {
  const response = await request.get("/api/portfolio/auth/google", { maxRedirects: 0 });
  expect(response.status()).toBe(307);
  const location = new URL(response.headers().location);
  expect(location.origin).toBe("https://test-project.supabase.co");
  expect(location.pathname).toBe("/auth/v1/authorize");
  expect(location.searchParams.get("provider")).toBe("google");
  expect(location.searchParams.get("redirect_to")).toBe("https://test.example/auth/callback");
  expect(location.searchParams.get("code_challenge_method")).toBe("s256");
  expect(location.searchParams.get("code_challenge")).toMatch(/^[A-Za-z0-9_-]{43}$/);
  const cookie = response.headers()["set-cookie"];
  expect(cookie).toContain("di_portfolio_oauth_verifier=");
  expect(cookie.toLowerCase()).toContain("httponly");
  expect(cookie.toLowerCase()).toContain("secure");
  expect(cookie.toLowerCase()).toContain("samesite=lax");
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
  await page.getByLabel("Send reset link to").fill("recovery@example.test");
  await page.getByRole("button", { name: "Send password-reset link" }).click();
  await expect(page.getByRole("status")).toContainText("If an account exists for that email");
  expect(submitted).toEqual({ action: "recover-password", email: "recovery@example.test" });
});

test("password reset page validates confirmation and submits only the new password", async ({ page }) => {
  let submitted;
  await page.route("**/api/portfolio/auth", async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
  });
  await page.goto("/account/reset-password");
  await page.getByLabel("New password", { exact: true }).fill("long-test-password-123");
  await page.getByLabel("Confirm new password").fill("different-password-456");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("alert")).toContainText("passwords do not match");
  expect(submitted).toBeUndefined();

  await page.getByLabel("Confirm new password").fill("long-test-password-123");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("status")).toContainText("Your password has been updated");
  expect(submitted).toEqual({ action: "update-password", password: "long-test-password-123" });
});
