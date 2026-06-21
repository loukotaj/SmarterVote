import fs from "node:fs/promises";
import path from "node:path";

const SITE_URL = "https://smarter.vote";
const API_BASE = process.env.VITE_RACES_API_URL;
const PUBLIC_DATA_URL = process.env.VITE_PUBLIC_DATA_URL;

function candidateSlug(name) {
  return String(name)
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function urlEntry(loc, lastmod, changefreq, priority) {
  const lines = ["  <url>", `    <loc>${escapeXml(loc)}</loc>`];
  if (lastmod)
    lines.push(`    <lastmod>${escapeXml(lastmod.slice(0, 10))}</lastmod>`);
  lines.push(`    <changefreq>${changefreq}</changefreq>`);
  lines.push(`    <priority>${priority}</priority>`);
  lines.push("  </url>");
  return lines.join("\n");
}

let races;
const localPath = path.resolve("..", "data", "published", "summaries.json");
try {
  const content = await fs.readFile(localPath, "utf8");
  races = JSON.parse(content);
  console.log(`Loaded ${races.length} races from local path ${localPath} for sitemap.`);
} catch (err) {
  console.log(`Could not read local sitemap source: ${err.message}. Fetching from network...`);

  const summariesUrl = PUBLIC_DATA_URL
    ? `${PUBLIC_DATA_URL.replace(/\/$/, "")}/summaries.json`
    : API_BASE
    ? `${API_BASE.replace(/\/$/, "")}/races/summaries`
    : null;

  if (!summariesUrl) {
    throw new Error(
      "Set VITE_PUBLIC_DATA_URL or VITE_RACES_API_URL to generate the sitemap from published race data."
    );
  }

  const res = await fetch(summariesUrl);
  if (!res.ok) {
    throw new Error(`Failed to fetch race summaries for sitemap: ${res.status}`);
  }

  races = await res.json();
}
const entries = [
  urlEntry(`${SITE_URL}/`, new Date().toISOString(), "weekly", "1.0"),
  urlEntry(`${SITE_URL}/about/`, new Date().toISOString(), "monthly", "0.8"),
];

for (const race of races) {
  entries.push(
    urlEntry(`${SITE_URL}/races/${race.id}/`, race.updated_utc, "weekly", "0.9")
  );
  for (const candidate of race.candidates ?? []) {
    entries.push(
      urlEntry(
        `${SITE_URL}/races/${race.id}/${candidateSlug(candidate.name)}/`,
        race.updated_utc,
        "weekly",
        "0.7"
      )
    );
  }
}

const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${entries.join(
  "\n"
)}\n</urlset>\n`;
const sitemapPath = path.resolve("static", "sitemap.xml");
await fs.writeFile(sitemapPath, xml, "utf8");
console.log(`Generated ${sitemapPath} with ${entries.length} URLs`);
