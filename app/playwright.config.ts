import { defineConfig, devices } from "@playwright/test";

/**
 * E2E config. Playwright boots the real stack: the FastAPI backend against a
 * throwaway SQLite DB (migrated fresh each run) and the Vite dev server, which
 * proxies `/api` to the backend. See docs/adr/0005-testing-strategy.md.
 */
const API_PORT = 5179;
const WEB_PORT = 5173;
const isCI = !!process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: isCI ? 1 : undefined,
  reporter: isCI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "bash -c 'mkdir -p .e2e && rm -f .e2e/e2e.sqlite && " +
        "poetry run alembic upgrade head && " +
        "exec poetry run uvicorn my_private_finances.main:app --port 5179 --log-level warning'",
      cwd: "../api",
      port: API_PORT,
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: {
        DATABASE_URL: "sqlite+aiosqlite:///./.e2e/e2e.sqlite",
        DATA_DIR: ".e2e",
        LOG_LEVEL: "WARNING",
      },
    },
    {
      command: `pnpm exec vite --port ${WEB_PORT} --strictPort`,
      port: WEB_PORT,
      reuseExistingServer: !isCI,
      timeout: 60_000,
    },
  ],
});
