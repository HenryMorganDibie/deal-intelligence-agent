const { test, expect } = require("@playwright/test");
const fs = require("node:fs/promises");

const routes = [
  ["/app/markets", "Explore Investments"],
  ["/app/markets/valuation", "Valuation"],
  ["/app/markets/portfolio", "Your portfolio, in context."],
  ["/app/markets/compare", "Compare"],
  ["/app/markets/monitoring", "Developments that may affect your holdings"],
  ["/app/markets/portfolio/cloud", "Cloud"],
  ["/app/companies", "Companies"],
  ["/app/research", "Research"],
  ["/app/deals", "Deals"],
  ["/app/alerts", "Alerts"],
  ["/app/watchlists", "Watchlists"],
  ["/app/coverage", "Coverage"],
];

test("Markets and adjacent workspaces render without route failures", async ({ page }) => {
  for (const [path, expectedText] of routes) {
    const response = await page.goto(path);
    expect(response, path + " should return a document").not.toBeNull();
    expect(response.status(), path + " should return HTTP 200").toBe(200);
    await expect(page.getByText(expectedText, { exact: false }).first(), path + " expected page content").toBeVisible();
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
  expect([401, 503]).toContain(response.status());
  const body = await response.json();
  expect(body).not.toHaveProperty("portfolios");
  expect(body).not.toHaveProperty("user");
});
