import { defineConfig, devices } from "@playwright/test";

/**
 * E2E config. Playwright boots the real stack: the FastAPI backend against a
 * throwaway SQLite DB (migrated fresh each run) and the Vite dev server, which
 * proxies `/api` to the backend. See docs/adr/0005-testing-strategy.md.
 *
 * Everything is pinned to the IPv4 loopback (127.0.0.1). Vite otherwise binds
 * `localhost`, which resolves to ::1 first on CI runners and makes the 127.0.0.1
 * baseURL unreachable.
 */
const HOST = "127.0.0.1";
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
    baseURL: `http://${HOST}:${WEB_PORT}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "bash -c 'mkdir -p .e2e && rm -f .e2e/e2e.sqlite && " +
        "poetry run alembic upgrade head && " +
        `exec poetry run uvicorn my_private_finances.main:app --host ${HOST} --port ${API_PORT} --log-level warning'`,
      cwd: "../api",
      url: `http://${HOST}:${API_PORT}/api/accounts`,
      reuseExistingServer: !isCI,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
      env: {
        DATABASE_URL: "sqlite+aiosqlite:///./.e2e/e2e.sqlite",
        DATA_DIR: ".e2e",
        LOG_LEVEL: "WARNING",
      },
    },
    {
      command: `pnpm exec vite --host ${HOST} --port ${WEB_PORT} --strictPort`,
      url: `http://${HOST}:${WEB_PORT}`,
      reuseExistingServer: !isCI,
      timeout: 60_000,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
