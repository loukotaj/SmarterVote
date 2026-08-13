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
      // Ratchet floors: set a couple of points under measured coverage so a real
      // regression fails the build while ordinary variance does not. They were
      // 35/25/35/40, which measured coverage had outgrown by ~20 points — a
      // floor that far below actual stops being a guard and just reports a
      // number. Raise these whenever coverage climbs; never lower them to make
      // a red build green.
      // Measured at the time of writing: 81.32 / 67.97 / 81.24 / 82.35.
      thresholds: {
        statements: 80,
        branches: 66,
        functions: 79,
        lines: 81,
      },
      reporter: ["text", "json-summary"],
    },
  },
});
