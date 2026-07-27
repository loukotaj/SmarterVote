const site = process.env.PUBLIC_SITE_URL ?? "https://smarter.vote";
const attempts = Number(process.env.DEPLOY_VERIFY_ATTEMPTS ?? 120);
const delayMs = Number(process.env.DEPLOY_VERIFY_DELAY_MS ?? 5000);
const pages = ["/", "/elections/", "/support/"];
const modulePattern =
  /(?:src|href)=\x22([^\x22]*\/_app(?:-[a-f0-9]+)?\/immutable\/[^\x22]+\.(?:js|wasm))\x22/g;
const nestedModulePattern =
  /[\x22']((?:\/_app(?:-[a-f0-9]+)?\/immutable\/|\.\.?\/)[^\x22']+\.(?:js|wasm))[\x22']/g;

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

  const failures = [];
  const checked = new Set();
  const pending = [...modules];
  while (pending.length > 0) {
    const url = pending.shift();
    if (checked.has(url)) continue;
    checked.add(url);
    try {
      const response = await fetchUncached(url);
      const type = response.headers.get("content-type") ?? "";
      const isWasm = new URL(url).pathname.endsWith(".wasm");
      const validType = isWasm
        ? type.includes("application/wasm")
        : type.includes("javascript") || type.includes("ecmascript");
      if (!response.ok || !validType) {
        failures.push(url + " returned " + response.status + " " + type);
        continue;
      }
      if (!isWasm) {
        const source = await response.text();
        for (const match of source.matchAll(nestedModulePattern)) {
          const dependency = new URL(match[1], url).href;
          if (!checked.has(dependency)) pending.push(dependency);
        }
      }
    } catch (error) {
      failures.push(url + " failed: " + String(error));
    }
    if (checked.size + pending.length > 5000) {
      failures.push("Module graph exceeded the 5000-module safety limit");
      break;
    }
  }

  const appPath = new URL([...modules][0]).pathname.match(
    /^(\/_app(?:-[a-f0-9]+)?)\/immutable\//,
  )?.[1];
  if (!appPath) throw new Error("Could not determine Svelte app path");
  const missingUrl = new URL(
    appPath + "/immutable/entry/__deployment-verifier-missing__.js",
    site,
  );
  const missingResponse = await fetchUncached(missingUrl);
  if (missingResponse.ok) {
    failures.push(
      String(missingUrl) +
        " unexpectedly returned " +
        missingResponse.status +
        " " +
        (missingResponse.headers.get("content-type") ?? ""),
    );
  }

  if (failures.length) {
    throw new Error("Module verification failed:\n" + failures.join("\n"));
  }
  console.log(
    "Verified " +
      pages.length +
      " public pages and " +
      checked.size +
      " recursively discovered Svelte modules, plus missing-module 404 behavior.",
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
