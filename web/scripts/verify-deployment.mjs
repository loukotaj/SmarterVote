const site = process.env.PUBLIC_SITE_URL ?? "https://smarter.vote";
const attempts = Number(process.env.DEPLOY_VERIFY_ATTEMPTS ?? 120);
const delayMs = Number(process.env.DEPLOY_VERIFY_DELAY_MS ?? 5000);
const pages = ["/", "/elections/", "/support/"];
const modulePattern =
  /(?:src|href)=\x22([^\x22]*\/_app\/immutable\/[^\x22]+\.(?:js|wasm))\x22/g;

const wait = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

async function fetchUncached(url) {
  return fetch(url, {
    cache: "no-store",
    headers: { "Cache-Control": "no-cache" },
    redirect: "follow",
    signal: AbortSignal.timeout(30_000),
  });
}

async function verify() {
  const modules = new Set();
  for (const path of pages) {
    const url = new URL(path, site);
    const response = await fetchUncached(url);
    const type = response.headers.get("content-type") ?? "";
    if (!response.ok || !type.includes("text/html")) {
      throw new Error(
        String(url) + " returned " + response.status + " " + type,
      );
    }
    const html = await response.text();
    for (const match of html.matchAll(modulePattern)) {
      modules.add(new URL(match[1], url).href);
    }
  }
  if (modules.size === 0) throw new Error("No Svelte modules found");

  const failures = (
    await Promise.all(
      [...modules].map(async (url) => {
        try {
          const response = await fetchUncached(url);
          const type = response.headers.get("content-type") ?? "";
          const validType =
            type.includes("javascript") ||
            type.includes("ecmascript") ||
            type.includes("application/wasm");
          return response.ok && validType
            ? null
            : url + " returned " + response.status + " " + type;
        } catch (error) {
          return url + " failed: " + String(error);
        }
      }),
    )
  ).filter(Boolean);
  if (failures.length) {
    throw new Error("Module verification failed:\n" + failures.join("\n"));
  }
  console.log(
    "Verified " +
      pages.length +
      " public pages and " +
      modules.size +
      " Svelte modules.",
  );
}

let latestError;
for (let attempt = 1; attempt <= attempts; attempt += 1) {
  try {
    await verify();
    latestError = undefined;
    break;
  } catch (error) {
    latestError = error;
    if (attempt < attempts) {
      console.warn("Verification attempt " + attempt + " failed; retrying.");
      await wait(delayMs);
    }
  }
}
if (latestError) throw latestError;
