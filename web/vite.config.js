import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";

/** Suppress the `untrack` MISSING_EXPORT warning from @sveltejs/kit when used with Svelte 4. */
function suppressSvelteKitUntrackWarning() {
  return {
    name: "suppress-sveltkit-untrack",
    apply: "build",
    enforce: "pre",
    options(opts) {
      const original = opts.onwarn;
      opts.onwarn = (warning, warn) => {
        if (warning.code === "MISSING_EXPORT" && warning.message?.includes("untrack")) return;
        if (original) original(warning, warn);
        else warn(warning);
      };
      return opts;
    },
  };
}

export default defineConfig({
  plugins: [sveltekit(), suppressSvelteKitUntrackWarning()],
  server: {
    port: 3000,
    host: true,
  },
  build: {
    target: "es2022",
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["svelte"],
        },
      },
    },
  },
  optimizeDeps: {
    include: ["svelte"],
  },
  test: {
    environment: "jsdom",
  },
});
