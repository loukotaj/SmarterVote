import { describe, expect, it } from "vitest";
import { getLogClass, getStatusClass } from "./pipelineUtils";

/**
 * These map domain states to Tailwind classes. The value of testing them is not
 * the exact class strings — it is that every known state maps to a *distinct*
 * style and that unknown input degrades to the neutral surface rather than
 * returning undefined and rendering an unstyled badge.
 */

const RUN_STATUSES = [
  "running",
  "completed",
  "failed",
  "cancelled",
  "continued",
] as const;

const LOG_LEVELS = ["error", "warning", "info", "debug"] as const;

describe("getStatusClass", () => {
  it.each(RUN_STATUSES)("returns a non-empty class for %s", (status) => {
    expect(getStatusClass(status)).toBeTruthy();
  });

  it("gives each run status a visually distinct style", () => {
    const classes = RUN_STATUSES.map(getStatusClass);
    expect(new Set(classes).size).toBe(RUN_STATUSES.length);
  });

  it.each([
    ["running", "blue"],
    ["completed", "green"],
    ["failed", "red"],
    ["cancelled", "yellow"],
    ["continued", "purple"],
  ])("colours %s with the %s ramp", (status, hue) => {
    expect(getStatusClass(status)).toContain(hue);
  });

  it("supplies both light and dark variants for every status", () => {
    for (const status of RUN_STATUSES) {
      expect(getStatusClass(status)).toContain("dark:");
    }
  });

  it.each(["pending", "unknown", "", "COMPLETED"])(
    "falls back to the neutral surface for %j",
    (status) => {
      expect(getStatusClass(status)).toBe(
        "bg-surface-alt text-content border-stroke",
      );
    },
  );
});

describe("getLogClass", () => {
  it.each(LOG_LEVELS)("returns a non-empty class for %s", (level) => {
    expect(getLogClass(level)).toBeTruthy();
  });

  it.each([
    ["error", "red"],
    ["warning", "yellow"],
    ["info", "blue"],
  ])("colours %s with the %s ramp", (level, hue) => {
    expect(getLogClass(level)).toContain(hue);
  });

  it("gives every level a left border so the log gutter reads as a rail", () => {
    for (const level of LOG_LEVELS) {
      expect(getLogClass(level)).toContain("border-l-");
    }
  });

  // debug and the default branch intentionally share styling — debug output is
  // not an exceptional state. Pinned so a future divergence is deliberate.
  it("styles debug the same as an unrecognised level", () => {
    expect(getLogClass("debug")).toBe(getLogClass("something-else"));
  });

  it.each(["", "ERROR", "trace"])(
    "falls back to the muted surface for %j",
    (level) => {
      expect(getLogClass(level)).toBe(
        "bg-surface-alt text-content-muted border-l-stroke",
      );
    },
  );
});
