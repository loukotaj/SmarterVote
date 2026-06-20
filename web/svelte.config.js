import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

const isFastBuild =
  process.env.FAST_BUILD === "true" ||
  process.argv.includes("fast") ||
  process.argv.includes("--mode=fast");

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: "build",
      assets: "build",
      precompress: false,
      strict: true,
    }),
    prerender: {
      crawl: !isFastBuild,
      entries: ["/", "/about/", "/admin/", "/admin/pipeline/", "/forecast"],
      handleUnseenRoutes: "ignore",
    },
    alias: {
      $lib: "src/lib",
    },
  },
};

export default config;
