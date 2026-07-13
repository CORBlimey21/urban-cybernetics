import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:8011",
    headless: true,
    browserName: "chromium",
    launchOptions: {
      executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    },
  },
  webServer: {
    command: "../.venv/bin/uc-visualisation serve --port 8011",
    url: "http://127.0.0.1:8011/api/v1/health",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
