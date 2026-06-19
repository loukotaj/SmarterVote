import fs from "node:fs/promises";
import path from "node:path";

const DEFAULT_ENDPOINT = "https://api.indexnow.org/indexnow";
const DEFAULT_HOST = "smarter.vote";
const MAX_URLS_PER_REQUEST = 10000;

const key = process.env.INDEXNOW_KEY;
const host = process.env.INDEXNOW_HOST || DEFAULT_HOST;
const endpoint = process.env.INDEXNOW_ENDPOINT || DEFAULT_ENDPOINT;
const keyLocation =
  process.env.INDEXNOW_KEY_LOCATION ||
  (key ? `https://${host}/${key}.txt` : undefined);
const sitemapPath = path.resolve(
  process.env.INDEXNOW_SITEMAP_PATH || "static/sitemap.xml"
);
const dryRun = process.env.INDEXNOW_DRY_RUN === "true";

if (!key) {
  console.log("Skipping IndexNow submission: INDEXNOW_KEY is not set.");
  process.exit(0);
}

const sitemapXml = await fs.readFile(sitemapPath, "utf8");
const urls = Array.from(sitemapXml.matchAll(/<loc>([^<]+)<\/loc>/g), (match) =>
  unescapeXml(match[1])
).filter((url) => {
  try {
    return new URL(url).host === host;
  } catch {
    return false;
  }
});

if (urls.length === 0) {
  throw new Error(`No URLs for ${host} found in ${sitemapPath}`);
}

for (let start = 0; start < urls.length; start += MAX_URLS_PER_REQUEST) {
  const urlList = urls.slice(start, start + MAX_URLS_PER_REQUEST);
  const payload = {
    host,
    key,
    keyLocation,
    urlList,
  };

  if (dryRun) {
    console.log(
      `IndexNow dry run: would submit ${urlList.length} URLs to ${endpoint}`
    );
    continue;
  }

  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json; charset=utf-8",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `IndexNow submission failed with ${response.status}: ${body}`
    );
  }

  console.log(`Submitted ${urlList.length} URLs to IndexNow.`);
}

function unescapeXml(value) {
  return value
    .replaceAll("&apos;", "'")
    .replaceAll("&quot;", '"')
    .replaceAll("&gt;", ">")
    .replaceAll("&lt;", "<")
    .replaceAll("&amp;", "&");
}
