import { sveltekit } from "@sveltejs/kit/vite";
import { svelteTesting } from "@testing-library/svelte/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [sveltekit(), svelteTesting()],
  server: {
    port: 3000,
    host: true,
  },
  build: {
    target: "es2022",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    coverage: {
      provider: "v8",
      include: ["src/lib/**/*.{ts,svelte}"],
      exclude: [
        "src/lib/**/*.test.ts",
        "src/lib/**/*.d.ts",
        "src/lib/types.ts",
        "src/lib/sampleData.ts",
        "src/lib/config/modelCatalog.ts",
      ],
      thresholds: {
        statements: 35,
        branches: 25,
        functions: 35,
        lines: 40,
      },
      reporter: ["text", "json-summary"],
    },
  },
});
