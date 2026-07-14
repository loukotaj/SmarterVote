const SCRIPT_ID = "google-maps-javascript-api";
const READY_CALLBACK = "__smarterVoteGoogleMapsReady";

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
    const loadLibrary = () => {
      const importLibrary = googleWindow.google?.maps?.importLibrary;
      if (typeof importLibrary !== "function") {
        reject(new Error("Google Maps did not initialize correctly."));
        return;
      }
      importLibrary
        .call(googleWindow.google?.maps, "places")
        .then(resolve)
        .catch(reject);
    };

    if (googleWindow.google?.maps) {
      void loadLibrary();
      return;
    }

    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement;
    if (existing) {
      reject(new Error("Google Maps is already loading."));
      return;
    }

    const callbackWindow = window as unknown as Record<string, unknown>;
    callbackWindow[READY_CALLBACK] = () => {
      delete callbackWindow[READY_CALLBACK];
      loadLibrary();
    };
    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.async = true;
    const params = new URLSearchParams({
      key: apiKey,
      loading: "async",
      callback: READY_CALLBACK,
      v: "weekly",
    });
    script.src = `https://maps.googleapis.com/maps/api/js?${params}`;
    script.addEventListener(
      "error",
      () => {
        delete callbackWindow[READY_CALLBACK];
        reject(new Error("Google Maps failed to load."));
      },
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
