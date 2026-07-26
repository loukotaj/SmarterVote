// Relocated from scratch/social-capture/ (task/scratch-to-mcp cleanup) — a campaign-specific
// variant of capture.mjs for the TX Senate launch carousel assets (my-ballot matched races,
// issue comparison, source list). Outputs to ../../artifacts/social-launch-final/. Run
// `npm install` in this directory once, then `node capture-launch-carousel.mjs`. Requires a
// local Chrome install; update `chromePath` below if it's not at the default Windows location.
import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright-core";
import sharp from "sharp";

const repoRoot = path.resolve(import.meta.dirname, "../..");
const outputDir = path.join(repoRoot, "artifacts", "social-launch-final");
const rawDir = path.join(import.meta.dirname, "raw");
const chromePath = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const compareUrl =
  "https://smarter.vote/races/tx-senate-2026/compare?candidates=james-talarico,ken-paxton";

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(rawDir, { recursive: true });

const browser = await chromium.launch({
  executablePath: chromePath,
  headless: true,
  args: ["--hide-scrollbars", "--force-color-profile=srgb"],
});

const captureCss = `
  *, *::before, *::after {
    animation-duration: 0s !important;
    animation-delay: 0s !important;
    transition-duration: 0s !important;
    transition-delay: 0s !important;
    caret-color: transparent !important;
  }
  html { scroll-behavior: auto !important; scrollbar-width: none !important; }
  html::-webkit-scrollbar, body::-webkit-scrollbar, *::-webkit-scrollbar {
    width: 0 !important;
    height: 0 !important;
    display: none !important;
  }
  body, body * { cursor: none !important; }
`;

async function createPage() {
  const context = await browser.newContext({
    viewport: { width: 540, height: 675 },
    deviceScaleFactor: 2,
    colorScheme: "light",
    reducedMotion: "reduce",
    locale: "en-US",
  });
  const page = await context.newPage();
  return { context, page };
}

async function settle(page) {
  await page.waitForTimeout(750);
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      [...document.images]
        .filter((image) => {
          const rect = image.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        })
        .map((image) =>
          image.complete && image.naturalWidth > 0
            ? undefined
            : Promise.race([
                image.decode().catch(() => undefined),
                new Promise((resolve) => setTimeout(resolve, 2_000)),
              ]),
        ),
    );
  });
  await page.addStyleTag({ content: captureCss });
  await page.waitForTimeout(100);
}

async function save(page, filename) {
  const rawPath = path.join(rawDir, filename);
  const outputPath = path.join(outputDir, filename);
  await page.screenshot({
    path: rawPath,
    fullPage: false,
    animations: "disabled",
    caret: "hide",
    scale: "device",
    type: "png",
  });
  await fs.copyFile(rawPath, outputPath);
  const metadata = await sharp(outputPath).metadata();
  if (metadata.width !== 1080 || metadata.height !== 1350) {
    throw new Error(
      `${filename} rendered at ${metadata.width}x${metadata.height}, expected 1080x1350`,
    );
  }
  console.log(`Captured ${outputPath}`);
}

async function openComparison(page) {
  await page.goto(compareUrl, { waitUntil: "networkidle", timeout: 45_000 });
  await settle(page);
  const issue = page.getByLabel("Compare an issue");
  await issue.waitFor({ state: "visible", timeout: 15_000 });
  await issue.selectOption({ label: "Healthcare" });
  const ted = page.getByRole("checkbox", { name: "Ted Brown (L)" });
  if (await ted.isChecked()) await ted.uncheck();
  await page.waitForTimeout(100);
}

async function captureMatchedRaces() {
  const { context, page } = await createPage();
  try {
    await page.goto("https://smarter.vote/my-ballot/", {
      waitUntil: "networkidle",
      timeout: 45_000,
    });
    await page.getByRole("combobox", { name: "Home address" }).fill(
      "1100 Congress Ave, Austin, TX 78701",
    );
    await page.getByRole("button", { name: "Show my elections" }).click();
    await page
      .getByRole("heading", { name: "Your matched races" })
      .waitFor({ state: "visible", timeout: 30_000 });
    await page.getByRole("tab", { name: "U.S. Senate" }).click();
    await page
      .getByRole("heading", {
        name: "2026 U.S. Senate election in Texas",
      })
      .waitFor({ state: "visible", timeout: 15_000 });
    const ted = page.getByRole("checkbox", { name: "Ted Brown (L)" });
    if (await ted.isChecked()) await ted.uncheck();
    await settle(page);

    const frame = await page.evaluate(() => {
      const explore = [...document.querySelectorAll("p")].find(
        (element) => element.textContent?.trim() === "Explore your races",
      );
      const candidates = document.querySelector(
        '[aria-label="Candidates in this comparison"]',
      );
      const issue = document.querySelector('select[id^="mobile-compare-issue"]');
      const issueLabel = issue?.labels?.[0];
      if (!explore || !candidates || !issue || !issueLabel) {
        throw new Error("Matched-race capture landmarks were not found");
      }
      const top = explore.getBoundingClientRect().top + window.scrollY;
      window.scrollTo(0, Math.max(0, top - 23));
      const candidateBox = candidates.getBoundingClientRect();
      const issueBox = issueLabel.getBoundingClientRect();
      return {
        candidateBottom: candidateBox.bottom,
        issueTop: issueBox.top,
      };
    });
    if (frame.candidateBottom > 675 || frame.issueTop < 675) {
      throw new Error(
        `Matched-race frame missed its boundary (candidates ${frame.candidateBottom}px, issue ${frame.issueTop}px)`,
      );
    }
    await save(page, "14-my-ballot-results-feed-1080x1350.png");
  } finally {
    await context.close();
  }
}

async function captureIssueComparison() {
  const { context, page } = await createPage();
  try {
    await openComparison(page);
    const frame = await page.evaluate(() => {
      const articles = [...document.querySelectorAll('article[aria-label*=" position on "]')];
      const forecastLabel = [...document.querySelectorAll("p")].find(
        (element) => element.textContent?.trim() === "Forecast",
      );
      if (articles.length !== 2 || !forecastLabel) {
        throw new Error("Expected two issue cards and a forecast banner");
      }
      const forecast = forecastLabel.closest("div.rounded-2xl") ?? forecastLabel.parentElement;
      const top = articles[0].getBoundingClientRect().top + window.scrollY;
      window.scrollTo(0, Math.max(0, top - 8));
      return {
        firstTop: articles[0].getBoundingClientRect().top,
        lastBottom: articles[1].getBoundingClientRect().bottom,
        forecastBottom: forecast?.getBoundingClientRect().bottom ?? 9999,
        showMoreButtons: articles.filter((article) =>
          [...article.querySelectorAll("button")].some(
            (button) => button.textContent?.includes("Show more"),
          ),
        ).length,
        confidences: articles.filter((article) =>
          /\bhigh\b/i.test(article.innerText),
        ).length,
      };
    });
    if (
      frame.firstTop < 0 ||
      frame.lastBottom > 675 ||
      frame.forecastBottom > 675 ||
      frame.showMoreButtons !== 2 ||
      frame.confidences !== 2
    ) {
      throw new Error(`Issue-comparison frame is incomplete: ${JSON.stringify(frame)}`);
    }
    await save(page, "15-race-issues-feed-v2-1080x1350.png");
  } finally {
    await context.close();
  }
}

async function captureSources() {
  const { context, page } = await createPage();
  try {
    await openComparison(page);
    await page
      .getByRole("button", { name: "Show more for James Talarico" })
      .click();
    await page
      .getByRole("button", {
        name: "Show 4 more sources for James Talarico",
      })
      .click();
    await page
      .getByRole("button", {
        name: "Show fewer sources for James Talarico",
      })
      .waitFor({ state: "visible", timeout: 10_000 });
    await settle(page);

    const frame = await page.evaluate(() => {
      const article = [...document.querySelectorAll('article[aria-label*=" position on "]')].find(
        (element) =>
          element.getAttribute("aria-label")?.startsWith("James Talarico"),
      );
      if (!article) throw new Error("James Talarico issue card was not found");
      const links = [...article.querySelectorAll("a")];
      const top = article.getBoundingClientRect().top + window.scrollY;
      const height = article.getBoundingClientRect().height;
      window.scrollTo(0, Math.max(0, top - (675 - height) / 2));
      return {
        top: article.getBoundingClientRect().top,
        bottom: article.getBoundingClientRect().bottom,
        links: links.length,
        toggle: [...article.querySelectorAll("button")].some(
          (button) => button.textContent?.includes("Show fewer sources"),
        ),
      };
    });
    if (
      frame.top < 0 ||
      frame.bottom > 675 ||
      frame.links !== 5 ||
      !frame.toggle
    ) {
      throw new Error(`Source frame is incomplete: ${JSON.stringify(frame)}`);
    }
    await save(page, "16-race-sources-feed-v2-1080x1350.png");
  } finally {
    await context.close();
  }
}

try {
  await captureMatchedRaces();
  await captureIssueComparison();
  await captureSources();
} finally {
  await browser.close();
}
