import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

const isFastBuild =
  process.env.FAST_BUILD === "true" ||
  process.env.npm_lifecycle_event === "build" ||
  process.env.npm_lifecycle_event === "build:fast" ||
  process.env.npm_lifecycle_event === "build:cloudflare" ||
  process.argv.includes("fast") ||
  process.argv.includes("--mode=fast");

const prerenderDynamicRoutes = process.env.VITE_PRERENDER_RACES === "true";
const deploySha = process.env.DEPLOY_SHA?.trim();
if (deploySha && !/^[0-9a-f]{7,64}$/i.test(deploySha)) {
  throw new Error("DEPLOY_SHA must be a Git commit SHA");
}
const appDir = deploySha
  ? `_app-${deploySha.slice(0, 12).toLowerCase()}`
  : "_app";
const fixedPrerenderEntries = [
  "/",
  "/about/",
  "/admin/",
  "/admin/pipeline/",
  "/corrections/",
  "/elections/",
  "/forecast/",
  "/funding-and-editorial-independence/",
  "/methodology/",
  "/my-ballot/",
  "/partners/",
  "/privacy/",
  "/support/",
  "/support/cancel/",
  "/support/success/",
  "/terms/",
];

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    // A release-specific namespace prevents an HTML response cached under an
    // older module URL from breaking hydration after a deployment.
    appDir,
    adapter: adapter({
      pages: "build",
      assets: "build",
      precompress: false,
      strict: true,
    }),
    prerender: {
      crawl: !isFastBuild,
      // Production publishes every known race route so Cloudflare can return a
      // real 404 for unknown URLs without relying on a catch-all SPA fallback.
      entries: prerenderDynamicRoutes ? ["*"] : fixedPrerenderEntries,
      handleUnseenRoutes: "ignore",
    },
    alias: {
      $lib: "src/lib",
    },
    paths: {
      relative: false,
    },
  },
};

export default config;
