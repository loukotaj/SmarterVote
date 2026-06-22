import { afterEach, describe, expect, it, vi } from "vitest";

describe("Auth0 frontend config", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("reports missing required Auth0 env vars", async () => {
    vi.stubEnv("VITE_SKIP_AUTH", "false");
    vi.stubEnv("VITE_AUTH0_DOMAIN", "");
    vi.stubEnv("VITE_AUTH0_CLIENT_ID", "");
    vi.stubEnv("VITE_AUTH0_AUDIENCE", "https://api.example.test");

    const { getAuth0ConfigError, getAuth0Client } = await import("./auth");

    expect(getAuth0ConfigError()).toContain("VITE_AUTH0_DOMAIN");
    expect(getAuth0ConfigError()).toContain("VITE_AUTH0_CLIENT_ID");
    await expect(getAuth0Client()).rejects.toThrow("Auth0 is not configured");
  });
});
