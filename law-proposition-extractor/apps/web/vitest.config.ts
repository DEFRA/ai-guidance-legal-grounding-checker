import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  esbuild: {
    jsx: "automatic",
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "node",
    globals: false,
    environmentMatchGlobs: [["**/*.test.tsx", "jsdom"]],
    include: ["components/**/*.test.ts", "components/**/*.test.tsx", "lib/**/*.test.ts"],
  },
});
