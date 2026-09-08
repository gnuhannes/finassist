import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    // Unit/component tests only. Playwright specs in e2e/ are run by `make e2e`.
    include: ["tests/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/**/*.d.ts", "src/vite-env.d.ts", "src/i18n/**"],
      reporter: ["text-summary", "html"],
      // Starting floor — a ratchet, like the backend's MIN_COVERAGE. Raise these
      // as coverage grows; never lower them.
      thresholds: {
        lines: 38,
        functions: 24,
        branches: 32,
        statements: 38,
      },
    },
  },
});
