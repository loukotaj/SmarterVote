// Relocated from scratch/social-capture/ (task/scratch-to-mcp cleanup) — this is the
// general-purpose capture script: a list of named `capture()` definitions (URL, viewport,
// optional DOM `prepare`/`verify` steps), each producing one PNG under ../../social-assets/.
// Run `npm install` in this directory once, then `node capture.mjs` (optionally pass one or
// more output filenames as CLI args to capture only a subset). Requires a local Chrome
// install; update `chromePath` below if it's not at the default Windows location.
import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright-core";
import sharp from "sharp";

const repoRoot = path.resolve(import.meta.dirname, "../..");
const outputDir = path.join(repoRoot, "social-assets");
const rawDir = path.join(import.meta.dirname, "raw");
const chromePath = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const compareUrl =
  "https://smarter.vote/races/tx-senate-2026/compare?candidates=james-talarico,ken-paxton,ted-brown";
const requestedFiles = new Set(process.argv.slice(2));

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(rawDir, { recursive: true });

const browser = await chromium.launch({
  executablePath: chromePath,
  headless: true,
  args: ["--hide-scrollbars", "--force-color-profile=srgb"],
});

const results = [];

const globalCaptureCss = `
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

async function waitForStablePage(page) {
  await page.waitForTimeout(1_000);
  await page.evaluate(async () => {
    await document.fonts.ready;
    const visibleImages = [...document.images].filter((image) => {
      const rect = image.getBoundingClientRect();
      return (
        rect.width > 0 &&
        rect.height > 0 &&
        rect.bottom > 0 &&
        rect.top < window.innerHeight &&
        rect.right > 0 &&
        rect.left < window.innerWidth
      );
    });
    await Promise.all(
      visibleImages.map(async (image) => {
        if (image.complete && image.naturalWidth > 0) return;
        await Promise.race([
          image.decode().catch(() => undefined),
          new Promise((resolve) => setTimeout(resolve, 2_000)),
        ]);
      }),
    );
  });
  await page.addStyleTag({ content: globalCaptureCss });
  await page.waitForTimeout(100);
}

async function assertReady(page) {
  const readiness = await page.evaluate(() => {
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return (
        rect.width > 0 &&
        rect.height > 0 &&
        rect.bottom > 0 &&
        rect.top < window.innerHeight &&
        rect.right > 0 &&
        rect.left < window.innerWidth &&
        style.visibility !== "hidden" &&
        style.display !== "none"
      );
    };
    const badImages = [...document.images]
      .filter(visible)
      .filter((image) => !image.complete || image.naturalWidth === 0)
      .map((image) => image.alt || image.src);
    const loaders = [...document.querySelectorAll(".animate-spin,.animate-pulse,[aria-busy=true]")]
      .filter(visible)
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return !(element.classList.contains("animate-pulse") && rect.width <= 16 && rect.height <= 16);
      })
      .map((element) => String(element.textContent || element.getAttribute("aria-label") || "loader").trim());
    const populatedAddresses = [...document.querySelectorAll("input")]
      .filter((input) => /address/i.test(`${input.id} ${input.name} ${input.placeholder} ${input.getAttribute("aria-label") || ""}`))
      .filter((input) => input.value.trim().length > 0)
      .map((input) => input.value);
    return { badImages, loaders, populatedAddresses };
  });
  if (readiness.badImages.length) throw new Error(`Unloaded images: ${readiness.badImages.join(", ")}`);
  if (readiness.loaders.length) throw new Error(`Visible loading states: ${readiness.loaders.join(", ")}`);
  if (readiness.populatedAddresses.length) throw new Error("An address field contains a value");
}

async function createPage({ width, height, colorScheme = "light" }) {
  const context = await browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: 2,
    colorScheme,
    reducedMotion: "reduce",
    locale: "en-US",
  });
  const page = await context.newPage();
  return { context, page };
}

async function saveScreenshot({ page, filename, desktop = false }) {
  await assertReady(page);
  const rawPath = path.join(rawDir, filename);
  const finalPath = path.join(outputDir, filename);
  await page.screenshot({
    path: rawPath,
    fullPage: false,
    animations: "disabled",
    caret: "hide",
    scale: "device",
    type: "png",
  });
  if (desktop) {
    await sharp(rawPath)
      .resize(1440, 900, { fit: "fill", kernel: sharp.kernel.lanczos3 })
      .png({ compressionLevel: 9, adaptiveFiltering: true })
      .toFile(finalPath);
  } else {
    await fs.copyFile(rawPath, finalPath);
  }
  const metadata = await sharp(finalPath).metadata();
  return { finalPath, width: metadata.width, height: metadata.height };
}

async function capture(definition) {
  if (requestedFiles.size && !requestedFiles.has(definition.filename)) return;
  console.log(`Capturing ${definition.filename}...`);
  const { context, page } = await createPage(definition);
  const deviations = [];
  try {
    await page.goto(definition.url, { waitUntil: "networkidle", timeout: 45_000 });
    await waitForStablePage(page);
    if (definition.prepare) await definition.prepare(page, deviations);
    await page.waitForTimeout(100);
    if (definition.verify) await definition.verify(page);
    const saved = await saveScreenshot({
      page,
      filename: definition.filename,
      desktop: definition.desktop,
    });
    results.push({
      filename: definition.filename,
      url: definition.url,
      viewport: `${definition.width}x${definition.height} @2x`,
      output: `${saved.width}x${saved.height}`,
      deviations,
      status: "captured",
    });
    console.log(`Captured ${definition.filename}.`);
  } catch (error) {
    results.push({
      filename: definition.filename,
      url: definition.url,
      viewport: `${definition.width}x${definition.height} @2x`,
      output: null,
      deviations: [error instanceof Error ? error.message : String(error)],
      status: "failed",
    });
    console.log(`Failed ${definition.filename}: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    await context.close();
  }
}

function inViewport(box, width, height, padding = 0) {
  return (
    box &&
    box.left >= padding &&
    box.top >= padding &&
    box.right <= width - padding &&
    box.bottom <= height - padding
  );
}

await capture({
  filename: "01-homepage-desktop-1440x900.png",
  url: "https://smarter.vote/",
  width: 1600,
  height: 1000,
  desktop: true,
  prepare: async (page, deviations) => {
    await page.addStyleTag({
      content: `
        [data-desktop-candidate-comparison] > div { min-width: 0 !important; }
        [data-desktop-candidate-comparison] [style*="grid-template-columns"] {
          grid-template-columns: 150px repeat(3, minmax(0, 1fr)) !important;
        }
        [data-desktop-candidate-comparison] a.block.truncate {
          white-space: normal !important;
          overflow: visible !important;
          text-overflow: clip !important;
          line-height: 1.15 !important;
        }
        [data-desktop-candidate-comparison] .border-r.p-6,
        [data-desktop-candidate-comparison] .border-r.border-stroke.p-6 {
          padding: 12px !important;
          font-size: 12.5px !important;
          line-height: 16px !important;
        }
        [data-desktop-candidate-comparison] .flex.items-center.gap-3.border-r {
          gap: 8px !important;
          padding-left: 12px !important;
          padding-right: 12px !important;
        }
        [data-desktop-candidate-comparison] .h-12.w-12 { width: 40px !important; height: 40px !important; }
        [aria-label="Scrollable featured comparison"] > .pointer-events-none { display: none !important; }
      `,
    });
    await page.evaluate(() => {
      const comparison = document.querySelector("[data-desktop-candidate-comparison]");
      const divide = comparison?.querySelector(".divide-y");
      if (divide) [...divide.children].slice(2).forEach((element) => (element.style.display = "none"));
      const scrollArea = document.querySelector('[aria-label="Scrollable featured comparison"]');
      if (scrollArea) {
        scrollArea.scrollTop = 0;
        scrollArea.scrollLeft = 0;
        const featuredCard = scrollArea.closest("div.flex.flex-col.overflow-hidden.rounded-2xl");
        if (featuredCard) {
          featuredCard.style.height = "760px";
          featuredCard.style.minHeight = "760px";
        }
      }
      if (comparison) comparison.scrollLeft = 0;
      window.scrollTo(0, 0);
    });
    deviations.push("Captured at 1600x1000 CSS and downsampled to 1440x900; capture-only comparison sizing fits all three candidates.");
  },
  verify: async (page) => {
    const state = await page.evaluate(() => {
      const comparison = document.querySelector("[data-desktop-candidate-comparison]");
      const names = ["James Talarico", "Ken Paxton", "Ted Brown"].map((name) => {
        const link = [...(comparison?.querySelectorAll("a") || [])].find(
          (element) => element.textContent?.trim() === name,
        );
        if (!link) return null;
        const box = link.getBoundingClientRect();
        return { name, left: box.left, right: box.right, top: box.top, bottom: box.bottom };
      });
      const compBox = comparison?.getBoundingClientRect();
      const scrollArea = document.querySelector('[aria-label="Scrollable featured comparison"]');
      return {
        names,
        compBox: compBox
          ? { left: compBox.left, right: compBox.right, top: compBox.top, bottom: compBox.bottom }
          : null,
        overflows: comparison ? comparison.scrollWidth > comparison.clientWidth + 1 : true,
        scrollTop: scrollArea?.scrollTop ?? -1,
        scrollHeight: scrollArea?.scrollHeight ?? -1,
        clientHeight: scrollArea?.clientHeight ?? -1,
        overlayVisible: [...document.querySelectorAll("div")].some(
          (element) => element.textContent?.trim() === "Scroll for more issues ↓" && getComputedStyle(element).display !== "none",
        ),
      };
    });
    if (!state.compBox || state.names.some((entry) => !entry)) throw new Error("Candidate comparison names are missing");
    if (state.overflows) throw new Error("Candidate comparison still overflows horizontally");
    if (state.overlayVisible) throw new Error("Scroll hint overlay is still visible");
    if (state.scrollTop !== 0) throw new Error("Comparison did not start at the top");
    if (state.scrollHeight > state.clientHeight + 1) {
      throw new Error(`Comparison is vertically clipped (${state.scrollHeight}px content / ${state.clientHeight}px frame)`);
    }
    if (
      state.names.some(
        (entry) => entry.left < state.compBox.left || entry.right > state.compBox.right,
      )
    ) {
      throw new Error("At least one candidate name is clipped");
    }
  },
});

await capture({
  filename: "03-homepage-story-1080x1920.png",
  url: "https://smarter.vote/",
  width: 540,
  height: 960,
  prepare: async (page, deviations) => {
    await page.evaluate(() => {
      const title = [...document.querySelectorAll("h2")].find((element) =>
        element.textContent?.includes("2026 U.S. Senate election in Texas"),
      );
      const card = title?.closest("div.flex.flex-col.overflow-hidden");
      if (card) card.style.marginTop = "250px";
      window.scrollTo(0, 0);
    });
  },
  verify: async (page) => {
    const state = await page.evaluate(() => {
      const browse = [...document.querySelectorAll("a")].find((element) =>
        element.textContent?.includes("Browse all elections"),
      );
      const candidateArea = document.querySelector('[aria-label="Candidates in this comparison"]');
      const browseBox = browse?.getBoundingClientRect();
      const candidateBox = candidateArea?.getBoundingClientRect();
      return {
        browseBottom: browseBox?.bottom ?? null,
        candidateTop: candidateBox?.top ?? null,
      };
    });
    if (state.browseBottom === null || state.browseBottom > 900) throw new Error("Browse card is not fully visible");
    if (state.candidateTop !== null && state.candidateTop < 960) throw new Error("Candidate area enters the story crop");
  },
});

await capture({
  filename: "05-elections-desktop-1440x900.png",
  url: "https://smarter.vote/elections/",
  width: 1440,
  height: 900,
  desktop: true,
  prepare: async (page, deviations) => {
    await page.evaluate(() => {
      const heading = [...document.querySelectorAll("h2")].find(
        (element) => element.textContent?.trim() === "Select a state",
      );
      if (!heading) throw new Error("Select a state heading not found");
      const top = heading.getBoundingClientRect().top + window.scrollY;
      window.scrollTo(0, Math.max(0, top - 55));
      const mapSection = heading.closest("section");
      if (mapSection) mapSection.style.marginTop = "80px";
      const count = [...document.querySelectorAll("*")].find((element) =>
        /^Showing \d+ of \d+ races$/.test(element.textContent?.trim() || ""),
      );
      if (count?.parentElement) count.parentElement.style.visibility = "hidden";
      deviations.push("Header/alpha banner and race-card grid omitted to prioritize the complete map and a clean lower boundary.");
    });
  },
  verify: async (page) => {
    const state = await page.evaluate(() => {
      const heading = [...document.querySelectorAll("h2")].find(
        (element) => element.textContent?.trim() === "Select a state",
      );
      const section = heading?.closest("section");
      const svg = [...(section?.querySelectorAll("svg") || [])].sort(
        (a, b) => b.getBoundingClientRect().width - a.getBoundingClientRect().width,
      )[0];
      const box = svg?.getBoundingClientRect();
      return box ? { left: box.left, right: box.right, top: box.top, bottom: box.bottom } : null;
    });
    if (!inViewport(state, 1440, 900, 12)) throw new Error("The full U.S. map is not inside the viewport");
  },
});

await capture({
  filename: "06-methodology-desktop-1440x900.png",
  url: "https://smarter.vote/about/",
  width: 1440,
  height: 900,
  desktop: true,
  prepare: async (page) => {
    await page.evaluate(() => window.scrollTo(0, 30));
  },
  verify: async (page) => {
    const state = await page.evaluate(() => {
      const title = [...document.querySelectorAll("h1")].find((element) =>
        element.textContent?.includes("About Smarter.Vote"),
      );
      const aiHeading = [...document.querySelectorAll("h2")].find((element) =>
        element.textContent?.includes("This site uses AI-generated content"),
      );
      const card = aiHeading?.closest("section");
      const corrections = card?.querySelector('a[href="/corrections/"]');
      const titleBox = title?.getBoundingClientRect();
      const cardBox = card?.getBoundingClientRect();
      const correctionsBox = corrections?.getBoundingClientRect();
      return {
        title: titleBox ? { top: titleBox.top, bottom: titleBox.bottom, left: titleBox.left, right: titleBox.right } : null,
        card: cardBox ? { top: cardBox.top, bottom: cardBox.bottom, left: cardBox.left, right: cardBox.right } : null,
        corrections: correctionsBox
          ? { top: correctionsBox.top, bottom: correctionsBox.bottom, left: correctionsBox.left, right: correctionsBox.right }
          : null,
      };
    });
    if (!state.title || state.title.top > 160) throw new Error("About title is not near the top of the frame");
    if (!inViewport(state.card, 1440, 900, 12)) throw new Error("AI-generated content card is not fully visible");
    if (!inViewport(state.corrections, 1440, 900, 12)) throw new Error("Corrections-process link is not visible");
  },
});

async function prepareComparisonFeed(page, { sources }) {
  await page.addStyleTag({
    content: `
      [aria-label="Candidates in this comparison"],
      [aria-label="Candidates in this comparison"] + p { display: none !important; }
      article[aria-label*=" position on "] {
        padding: 8px !important;
        border-radius: 12px !important;
        min-width: 0 !important;
      }
      article[aria-label*=" position on "] h3 { font-size: 12px !important; line-height: 15px !important; }
      article[aria-label*=" position on "] p { font-size: 10.5px !important; line-height: 14px !important; margin-top: 6px !important; }
      article[aria-label*=" position on "] button { display: none !important; }
      article[aria-label*=" position on "] a { font-size: 10.5px !important; line-height: 13px !important; }
      article[aria-label*=" position on "] .mt-3.border-t { margin-top: 6px !important; padding-top: 6px !important; }
      select[id^="mobile-compare-issue"] { min-height: 40px !important; margin-top: 4px !important; font-size: 13px !important; }
    `,
  });
  await page.evaluate((showSources) => {
    const select = document.querySelector("select[id^=mobile-compare-issue]");
    const articles = [...document.querySelectorAll('article[aria-label*=" position on "]')];
    const grid = articles[0]?.parentElement;
    if (!select || articles.length !== 3 || !grid) throw new Error("Expected three candidate issue cards");
    grid.style.display = "grid";
    grid.style.gridTemplateColumns = "repeat(3, minmax(0, 1fr))";
    grid.style.gap = "6px";
    for (const article of articles) {
      for (const child of article.children) {
        if (!showSources && child.matches(".mt-3.border-t")) child.style.display = "none";
      }
    }
    const mobileComparison = select.closest("div.overflow-hidden.rounded-2xl");
    if (!mobileComparison) throw new Error("Mobile comparison container not found");
    const forecast = [...mobileComparison.children].find((element) =>
      element.textContent?.trim().startsWith("Forecast"),
    );
    if (forecast) forecast.style.display = "none";
    const top = mobileComparison.getBoundingClientRect().top + window.scrollY;
    window.scrollTo(0, Math.max(0, top - 24));
    const footer = document.querySelector("footer");
    if (footer) footer.style.visibility = "hidden";
  }, sources);
  await page.waitForTimeout(100);
}

async function verifyComparisonFeed(page, { requireSources }) {
  const state = await page.evaluate(() => {
    const articles = [...document.querySelectorAll('article[aria-label*=" position on "]')];
    const boxes = articles.map((article) => {
      const box = article.getBoundingClientRect();
      return {
        label: article.getAttribute("aria-label"),
        left: box.left,
        right: box.right,
        top: box.top,
        bottom: box.bottom,
        confidence: /\b(high|medium|low)\b/i.test(article.innerText),
      };
    });
    const sourceBoxes = [...document.querySelectorAll('article[aria-label*=" position on "] a')]
      .filter((link) => getComputedStyle(link).display !== "none")
      .map((link) => {
        const box = link.getBoundingClientRect();
        return { text: link.textContent?.trim(), left: box.left, right: box.right, top: box.top, bottom: box.bottom };
      });
    return { boxes, sourceBoxes };
  });
  if (state.boxes.length !== 3) throw new Error("All three candidate issue cards are not present");
  if (state.boxes.some((box) => !inViewport(box, 540, 675, 6))) {
    throw new Error("At least one candidate issue card is clipped");
  }
  if (state.boxes.some((box) => !box.confidence)) throw new Error("At least one confidence level is missing");
  if (requireSources) {
    const visibleSources = state.sourceBoxes.filter((box) => inViewport(box, 540, 675, 4));
    if (visibleSources.length < 3) throw new Error("Fewer than three complete source links are visible");
  }
}

await capture({
  filename: "10-race-sources-feed-1080x1350.png",
  url: compareUrl,
  width: 540,
  height: 675,
  prepare: async (page) => prepareComparisonFeed(page, { sources: true }),
  verify: async (page) => verifyComparisonFeed(page, { requireSources: true }),
});

await capture({
  filename: "11-race-issues-feed-1080x1350.png",
  url: compareUrl,
  width: 540,
  height: 675,
  prepare: async (page) => prepareComparisonFeed(page, { sources: false }),
  verify: async (page) => verifyComparisonFeed(page, { requireSources: false }),
});

await capture({
  filename: "12-forecast-desktop-1440x900.png",
  url: "https://smarter.vote/forecast/",
  width: 1440,
  height: 900,
  desktop: true,
  prepare: async (page) => {
    await page.evaluate(() => {
      window.scrollTo(0, 0);
      const summaryHeading = [...document.querySelectorAll("h2")].find((element) =>
        element.textContent?.includes("2026 House Election Summary"),
      );
      const summaryCard = summaryHeading?.closest("section") || summaryHeading?.closest("div.rounded-2xl");
      if (summaryCard) summaryCard.style.marginBottom = "100px";
    });
  },
  verify: async (page) => {
    const state = await page.evaluate(() => {
      const text = document.body.innerText;
      const visiblePartySignals = [...document.querySelectorAll("body *")]
        .filter((element) => {
          const content = element.textContent?.trim() || "";
          if (!/Democrat|Republican/i.test(content) || content.length > 80) return false;
          const box = element.getBoundingClientRect();
          return box.top >= 0 && box.bottom <= 900 && box.width > 0 && box.height > 0;
        })
        .map((element) => element.textContent?.trim());
      return {
        hasError: /failed to load|error loading/i.test(text),
        hasDemocratic: visiblePartySignals.some((text) => /Democrat/i.test(text || "")),
        hasRepublican: visiblePartySignals.some((text) => /Republican/i.test(text || "")),
        titleVisible: [...document.querySelectorAll("h1")].some((heading) => {
          const box = heading.getBoundingClientRect();
          return heading.textContent?.includes("2026 Election Forecast") && box.top >= 0 && box.bottom <= 900;
        }),
      };
    });
    if (state.hasError) throw new Error("Forecast page rendered an error");
    if (!state.titleVisible) throw new Error("Forecast title is not visible");
    if (state.hasDemocratic !== state.hasRepublican) {
      throw new Error("Top forecast frame shows only one party signal");
    }
  },
});

await capture({
  filename: "13-homepage-dark-1080x1350.png",
  url: "https://smarter.vote/",
  width: 540,
  height: 675,
  prepare: async (page) => {
    const toggle = page.getByRole("button", { name: "Switch to dark mode" });
    if ((await toggle.count()) !== 1) throw new Error("Dark-mode toggle was not uniquely available");
    await toggle.click();
    await page.waitForTimeout(1_000);
    const isDark = await page.evaluate(() => document.documentElement.classList.contains("dark"));
    if (!isDark) throw new Error("Dark mode did not activate");
    await page.evaluate(() => window.scrollTo(0, 0));
  },
  verify: async (page) => {
    const state = await page.evaluate(() => {
      const browse = [...document.querySelectorAll("a")].find((element) =>
        element.textContent?.includes("Browse all elections"),
      );
      const candidateArea = document.querySelector('[aria-label="Candidates in this comparison"]');
      const browseBox = browse?.getBoundingClientRect();
      const candidateBox = candidateArea?.getBoundingClientRect();
      return {
        dark: document.documentElement.classList.contains("dark"),
        browseBottom: browseBox?.bottom ?? null,
        candidateTop: candidateBox?.top ?? null,
      };
    });
    if (!state.dark) throw new Error("Dark mode is not active");
    if (state.browseBottom === null || state.browseBottom > 675) throw new Error("Browse card is clipped");
    if (state.candidateTop !== null && state.candidateTop < 675) throw new Error("Candidate comparison enters the dark feed crop");
  },
});

await browser.close();

console.log(JSON.stringify(results, null, 2));
if (results.some((result) => result.status === "failed")) process.exitCode = 1;
