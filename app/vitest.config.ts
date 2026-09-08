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
  },
});
