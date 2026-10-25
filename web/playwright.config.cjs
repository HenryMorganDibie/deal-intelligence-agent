const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.cjs",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    browserName: "chromium",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run start",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: false,
    timeout: 120_000,
    env: {\n      NODE_ENV: "production",\n      SUPABASE_URL: "https://auth-test.invalid",\n      SUPABASE_PUBLISHABLE_KEY: "test-publishable-key",\n      NEXT_PUBLIC_SITE_URL: "http://127.0.0.1:3000",\n      VERCEL_ENV: "preview",\n    },
  },
  timeout: 30_000,
});
