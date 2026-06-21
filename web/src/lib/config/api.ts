const LOCAL_RACES_API_URL = "http://127.0.0.1:8080";
const PRODUCTION_RACES_API_URL =
  "https://races-api-dev-ddsvfazica-uc.a.run.app";

function cleanUrl(value: string | undefined): string | undefined {
  const trimmed = value?.trim().replace(/\/$/, "");
  return trimmed || undefined;
}

export function racesApiBase(): string {
  return (
    cleanUrl(import.meta.env.VITE_RACES_API_URL) ??
    (import.meta.env.DEV ? LOCAL_RACES_API_URL : PRODUCTION_RACES_API_URL)
  );
}

export function publicDataBase(): string | undefined {
  return cleanUrl(import.meta.env.VITE_PUBLIC_DATA_URL);
}
