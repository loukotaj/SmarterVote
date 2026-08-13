import { describe, expect, it } from "vitest";
import { LEGACY_MODEL_ALIASES, MODEL_LABELS } from "$lib/config/modelCatalog";
import { candidateSlug, formatModelName } from "./format";

// modelCatalog.ts is generated from shared/model_catalog.py, so its contents
// change whenever the roster does. Derive fixtures from the catalog rather than
// hardcoding IDs — otherwise a routine model swap turns into a red test.
const [canonicalId, canonicalLabel] = Object.entries(MODEL_LABELS)[0];
const bareAlias = Object.entries(LEGACY_MODEL_ALIASES).find(
  ([, target]) => MODEL_LABELS[target] !== undefined,
)!;

describe("formatModelName", () => {
  it("returns falsy input unchanged", () => {
    expect(formatModelName("")).toBe("");
  });

  it("labels a current catalog model", () => {
    expect(formatModelName(canonicalId)).toBe(canonicalLabel);
  });

  it("resolves a bare alias through the catalog", () => {
    const [alias, target] = bareAlias;
    expect(formatModelName(alias)).toBe(MODEL_LABELS[target]);
  });

  it("labels pre-catalog models that only appear in old run records", () => {
    expect(formatModelName("gpt-4o")).toBe("GPT-4o");
    expect(formatModelName("claude-sonnet-4-20250514")).toBe("Claude Sonnet 4");
    expect(formatModelName("grok-3")).toBe("Grok 3");
  });

  it("maps historical pipeline generator tags to the model they actually used", () => {
    expect(formatModelName("pipeline-agent")).toBe("GPT-4o Mini");
    expect(formatModelName("pipeline-v2-agent")).toBe("GPT-4o Mini");
  });

  // The documented rule: a run renders as the model it ran on, never as
  // whatever replaced it. A direct label must win over alias redirection.
  it("prefers a direct label over alias redirection", () => {
    const aliasedArchived = Object.keys(LEGACY_MODEL_ALIASES).find(
      (key) => key === "gpt-4o",
    );
    // Only meaningful if the catalog ever aliases an archived name; when it
    // does not, the direct-hit path is still the one exercised above.
    if (aliasedArchived) {
      expect(formatModelName("gpt-4o")).toBe("GPT-4o");
    }
    expect(formatModelName(canonicalId)).toBe(canonicalLabel);
  });

  it("falls back to the raw id for anything unrecognised", () => {
    expect(formatModelName("some/unknown-model-9")).toBe(
      "some/unknown-model-9",
    );
  });

  it("does not resolve an alias whose target has no label", () => {
    // Guards the `aliased && MODEL_LABELS[aliased]` conjunction: a dangling
    // alias must fall through to the raw id, not return undefined.
    const dangling = Object.entries(LEGACY_MODEL_ALIASES).find(
      ([, target]) => MODEL_LABELS[target] === undefined,
    );
    if (dangling) {
      expect(formatModelName(dangling[0])).toBe(dangling[0]);
    }
  });
});

describe("candidateSlug", () => {
  it.each([
    ["Jane Doe", "jane-doe"],
    ["Jane Q. Doe", "jane-q-doe"],
    ["O'Brien", "o-brien"],
    ["Mary-Jane Watson", "mary-jane-watson"],
    ["  Leading and trailing  ", "leading-and-trailing"],
    ["UPPERCASE NAME", "uppercase-name"],
    ["Name123", "name123"],
  ])("slugifies %j to %j", (input, expected) => {
    expect(candidateSlug(input)).toBe(expected);
  });

  it("collapses runs of separators into a single dash", () => {
    expect(candidateSlug("A  ---  B")).toBe("a-b");
  });

  it("strips leading and trailing dashes", () => {
    expect(candidateSlug("!!!Jane!!!")).toBe("jane");
  });

  it("returns an empty string when nothing survives", () => {
    expect(candidateSlug("")).toBe("");
    expect(candidateSlug("!!!")).toBe("");
  });

  // Non-ASCII letters become separators rather than being transliterated, so an
  // accented name fragments: "José Ñuñez" -> "jos-u-ez", not "jose-nunez".
  // Pinned deliberately — switching to transliteration would change every
  // existing candidate URL, so it must be a conscious migration, not a drive-by.
  it("turns non-ASCII characters into separators instead of transliterating", () => {
    expect(candidateSlug("José Ñuñez")).toBe("jos-u-ez");
    expect(candidateSlug("Müller")).toBe("m-ller");
  });

  it("produces a stable slug for the same name", () => {
    expect(candidateSlug("Jane Doe")).toBe(candidateSlug("Jane  Doe"));
  });
});
