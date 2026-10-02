import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: true,
  use: {
    serviceWorkers: "block",
    baseURL: "http://127.0.0.1:4173",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {},
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-light", use: { viewport: { width: 1180, height: 757 }, colorScheme: "light" } },
    { name: "desktop-dark", use: { viewport: { width: 1180, height: 757 }, colorScheme: "dark" } },
    { name: "mobile-light", use: { viewport: { width: 390, height: 844 }, colorScheme: "light" } },
    { name: "mobile-dark", use: { viewport: { width: 390, height: 844 }, colorScheme: "dark" } },
    { name: "narrow-mobile", use: { viewport: { width: 320, height: 740 }, colorScheme: "light" } },
  ],
  webServer: {
    command: "node ../../scripts/preview-static.mjs dist 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    env: { ASTRO_TELEMETRY_DISABLED: "1" },
  },
});
