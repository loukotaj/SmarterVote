import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * `isDev` is captured once at module load, so each case has to reset the module
 * registry and re-import after stubbing the env. The production branch is the
 * one worth pinning: the logger deliberately swallows output there, and a
 * regression that starts logging to a user's console is silent in dev.
 */
async function loadLogger(dev: boolean) {
  vi.resetModules();
  vi.stubEnv("DEV", dev);
  const { logger } = await import("./logger");
  return logger;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  vi.resetModules();
});

describe("logger in development", () => {
  it.each([
    ["error", "error"],
    ["warn", "warn"],
    ["info", "info"],
  ] as const)("forwards %s to the console", async (method, consoleMethod) => {
    const spy = vi.spyOn(console, consoleMethod).mockImplementation(() => {});
    const logger = await loadLogger(true);

    logger[method]("a message", { detail: 1 }, "extra");

    expect(spy).toHaveBeenCalledWith("a message", { detail: 1 }, "extra");
  });

  it("forwards a message with no extra arguments", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const logger = await loadLogger(true);

    logger.error("bare");

    expect(spy).toHaveBeenCalledWith("bare");
  });
});

describe("logger in production", () => {
  it.each([
    ["error", "error"],
    ["warn", "warn"],
    ["info", "info"],
  ] as const)("suppresses %s entirely", async (method, consoleMethod) => {
    const spy = vi.spyOn(console, consoleMethod).mockImplementation(() => {});
    const logger = await loadLogger(false);

    logger[method]("should not appear", "nor this");

    expect(spy).not.toHaveBeenCalled();
  });

  it("still returns undefined rather than throwing", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const logger = await loadLogger(false);

    expect(logger.error("quiet")).toBeUndefined();
  });
});
