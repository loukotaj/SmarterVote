const SCRIPT_ID = "google-maps-javascript-api";

export interface AddressSuggestion {
  id: string;
  text: string;
  resolveAddress: () => Promise<string>;
}

interface GooglePlacePrediction {
  placeId: string;
  text: { toString(): string };
  toPlace(): {
    formattedAddress?: string;
    fetchFields(request: { fields: string[] }): Promise<void>;
  };
}

interface GooglePlacesLibrary {
  AutocompleteSessionToken: new () => unknown;
  AutocompleteSuggestion: {
    fetchAutocompleteSuggestions(request: {
      input: string;
      includedPrimaryTypes: string[];
      includedRegionCodes: string[];
      sessionToken: unknown;
    }): Promise<{
      suggestions: Array<{ placePrediction?: GooglePlacePrediction }>;
    }>;
  };
}

interface GoogleMapsWindow extends Window {
  google?: {
    maps: {
      importLibrary(name: "places"): Promise<GooglePlacesLibrary>;
    };
  };
}

let libraryPromise: Promise<GooglePlacesLibrary> | undefined;
let sessionToken: unknown;

function loadPlacesLibrary(apiKey: string): Promise<GooglePlacesLibrary> {
  if (libraryPromise) return libraryPromise;

  const loading = new Promise<GooglePlacesLibrary>((resolve, reject) => {
    const googleWindow = window as GoogleMapsWindow;
    const loadLibrary = () =>
      googleWindow.google?.maps
        .importLibrary("places")
        .then(resolve)
        .catch(reject);

    if (googleWindow.google?.maps) {
      void loadLibrary();
      return;
    }

    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement;
    if (existing) {
      existing.addEventListener("load", loadLibrary, { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error("Google Maps failed to load.")),
        { once: true },
      );
      return;
    }

    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.async = true;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&loading=async`;
    script.addEventListener("load", loadLibrary, { once: true });
    script.addEventListener(
      "error",
      () => reject(new Error("Google Maps failed to load.")),
      { once: true },
    );
    document.head.appendChild(script);
  }).catch((error) => {
    libraryPromise = undefined;
    throw error;
  });
  libraryPromise = loading;

  return loading;
}

export async function suggestUsAddresses(
  input: string,
  apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY,
): Promise<AddressSuggestion[]> {
  if (!apiKey || input.trim().length < 5) return [];

  const places = await loadPlacesLibrary(apiKey);
  sessionToken ??= new places.AutocompleteSessionToken();
  const response =
    await places.AutocompleteSuggestion.fetchAutocompleteSuggestions({
      input: input.trim(),
      includedPrimaryTypes: ["street_address", "premise", "subpremise"],
      includedRegionCodes: ["us"],
      sessionToken,
    });

  return response.suggestions
    .flatMap((suggestion) =>
      suggestion.placePrediction ? [suggestion.placePrediction] : [],
    )
    .slice(0, 5)
    .map((prediction) => ({
      id: prediction.placeId,
      text: prediction.text.toString(),
      resolveAddress: async () => {
        const place = prediction.toPlace();
        await place.fetchFields({ fields: ["formattedAddress"] });
        sessionToken = undefined;
        return place.formattedAddress || prediction.text.toString();
      },
    }));
}

export function abandonAddressSession(): void {
  sessionToken = undefined;
}
