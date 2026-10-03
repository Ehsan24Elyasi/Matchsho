import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser",
  timeout: 30000,
  expect: { timeout: 8000 },
  fullyParallel: true,
  workers: 2,
  reporter: [["list"], ["json", { outputFile: "test-results/results.json" }]],
  use: {
    baseURL: process.env.BASE_URL || "http://127.0.0.1:4173",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: process.env.BASE_URL
    ? undefined
    : {
        command: "npm run build && npm run serve:test",
        url: "http://127.0.0.1:4173",
        reuseExistingServer: !process.env.CI,
      },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
