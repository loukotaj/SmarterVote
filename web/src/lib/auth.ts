// auth.ts
import { createAuth0Client, type Auth0Client } from "@auth0/auth0-spa-js";

let clientPromise: Promise<Auth0Client> | null = null;

const REQUIRED_AUTH0_ENV = [
  "VITE_AUTH0_DOMAIN",
  "VITE_AUTH0_CLIENT_ID",
  "VITE_AUTH0_AUDIENCE",
] as const;

type RequiredAuth0Env = (typeof REQUIRED_AUTH0_ENV)[number];

/**
 * Returns true when Auth0 should be skipped (local development).
 * Set VITE_SKIP_AUTH=true in web/.env to bypass authentication locally.
 * Always false in production builds.
 */
export function isAuthSkipped(): boolean {
  if (import.meta.env.PROD) return false;
  return import.meta.env.VITE_SKIP_AUTH === "true";
}

function readAuth0Env(key: RequiredAuth0Env): string {
  const value = import.meta.env[key];
  return typeof value === "string" ? value.trim() : "";
}

export function getAuth0ConfigError(): string | null {
  if (isAuthSkipped()) return null;
  const missing = REQUIRED_AUTH0_ENV.filter((key) => !readAuth0Env(key));
  if (!missing.length) return null;
  return `Auth0 is not configured. Missing frontend env var${
    missing.length === 1 ? "" : "s"
  }: ${missing.join(", ")}.`;
}

/** Stub that satisfies the Auth0Client surface used by SmarterVote. */
function createMockClient(): Auth0Client {
  return {
    isAuthenticated: async () => true,
    loginWithRedirect: async () => {},
    handleRedirectCallback: async () => ({ appState: {} }),
    getTokenSilently: async () => "dev-token",
    logout: async () => {},
  } as unknown as Auth0Client;
}

export function getAuth0Client(): Promise<Auth0Client> {
  if (isAuthSkipped()) {
    return Promise.resolve(createMockClient());
  }
  const configError = getAuth0ConfigError();
  if (configError) {
    return Promise.reject(new Error(configError));
  }
  if (!clientPromise) {
    // Only call this on the client (not during SSR)
    clientPromise = createAuth0Client({
      domain: readAuth0Env("VITE_AUTH0_DOMAIN"),
      clientId: readAuth0Env("VITE_AUTH0_CLIENT_ID"),
      authorizationParams: {
        redirect_uri: `${window.location.origin}/admin`,
        audience: readAuth0Env("VITE_AUTH0_AUDIENCE"),
      },
    });
  }
  return clientPromise;
}
