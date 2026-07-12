import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

const source = resolve(
  "Smarter.Vote visual system/Smarter.Vote Brand Assets.dc.html"
);
const exports = [
  ["banner-x", "exports/banners/x-twitter-header-1500x500.png"],
  ["banner-li", "exports/banners/linkedin-banner-1584x396.png"],
  ["banner-fb", "exports/banners/facebook-cover-820x312.png"],
  ["banner-yt", "exports/banners/youtube-channel-art-2560x1440.png"],
  ["banner-og", "exports/banners/og-image-1200x630.png"],
];

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 3000, height: 1800 } });

try {
  await page.goto(pathToFileURL(source).href, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);

  for (const [id, output] of exports) {
    const canvas = page.locator(`#${id}`);
    await canvas.evaluate((element) => {
      element.style.transform = "none";
      const preview = element.parentElement;
      preview.style.width = element.style.width;
      preview.style.height = element.style.height;
      preview.style.overflow = "visible";
    });

    const outputPath = resolve("Smarter.Vote visual system", output);
    await mkdir(dirname(outputPath), { recursive: true });
    await canvas.screenshot({ path: outputPath });
    console.log(`Exported ${output}`);
  }
} finally {
  await browser.close();
}
