import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

const isFastBuild =
  process.env.FAST_BUILD === "true" ||
  process.env.npm_lifecycle_event === "build" ||
  process.env.npm_lifecycle_event === "build:fast" ||
  process.env.npm_lifecycle_event === "build:cloudflare" ||
  process.argv.includes("fast") ||
  process.argv.includes("--mode=fast");

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: "build",
      assets: "build",
      fallback: "200.html",
      precompress: false,
      strict: true,
    }),
    prerender: {
      crawl: !isFastBuild,
      entries: [
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
        "/terms/",
      ],
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
