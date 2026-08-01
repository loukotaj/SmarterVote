import { beforeEach, describe, expect, it, vi } from "vitest";

describe("Google Places address suggestions", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    if (typeof document !== "undefined" && document.head) {
      document.head.innerHTML = "";
    }
    if (typeof window !== "undefined") {
      delete (window as Window & { google?: unknown }).google;
    }
  });

  it("does not load Google when the key is absent or input is too short", async () => {
    const { suggestUsAddresses } = await import("./googlePlaces");

    await expect(suggestUsAddresses("1600 Pennsylvania", "")).resolves.toEqual(
      [],
    );
    await expect(suggestUsAddresses("1600", "key")).resolves.toEqual([]);
    expect(document.querySelector("script")).toBeNull();
  });

  it("limits U.S. address predictions and requests only the formatted address", async () => {
    const fetchFields = vi.fn().mockResolvedValue(undefined);
    const predictions = Array.from({ length: 6 }, (_, index) => ({
      placePrediction: {
        placeId: `place-${index}`,
        text: { toString: () => `Address ${index}` },
        toPlace: () => ({
          formattedAddress:
            "1600 Pennsylvania Avenue NW, Washington, DC 20500, USA",
          fetchFields,
        }),
      },
    }));
    const fetchAutocompleteSuggestions = vi
      .fn()
      .mockResolvedValue({ suggestions: predictions });
    (window as Window & { google?: unknown }).google = {
      maps: {
        importLibrary: vi.fn().mockResolvedValue({
          AutocompleteSessionToken: class {},
          AutocompleteSuggestion: { fetchAutocompleteSuggestions },
        }),
      },
    };
    const { suggestUsAddresses } = await import("./googlePlaces");

    const suggestions = await suggestUsAddresses("1600 Pennsylvania", "key");
    expect(suggestions).toHaveLength(5);
    expect(fetchAutocompleteSuggestions).toHaveBeenCalledWith(
      expect.objectContaining({
        includedPrimaryTypes: ["street_address", "premise", "subpremise"],
        includedRegionCodes: ["us"],
      }),
    );
    await expect(suggestions[0].resolveAddress()).resolves.toContain(
      "Washington",
    );
    expect(fetchFields).toHaveBeenCalledWith({
      fields: ["formattedAddress"],
    });
  });

  it("waits for Google's ready callback instead of the script load event", async () => {
    const fetchAutocompleteSuggestions = vi.fn().mockResolvedValue({
      suggestions: [],
    });
    const importLibrary = vi.fn().mockResolvedValue({
      AutocompleteSessionToken: class {},
      AutocompleteSuggestion: { fetchAutocompleteSuggestions },
    });
    const { suggestUsAddresses } = await import("./googlePlaces");

    const pending = suggestUsAddresses("1600 Pennsylvania", "key");
    const script = document.getElementById(
      "google-maps-javascript-api",
    ) as HTMLScriptElement;
    expect(script.src).toContain("callback=__smarterVoteGoogleMapsReady");

    (window as Window & { google?: unknown }).google = {
      maps: { importLibrary },
    };
    const callback = (window as unknown as Record<string, () => void>)
      .__smarterVoteGoogleMapsReady;
    callback();

    await expect(pending).resolves.toEqual([]);
    expect(importLibrary).toHaveBeenCalledWith("places");
  });
});
