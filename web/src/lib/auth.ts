// auth.ts
import { createAuth0Client, type Auth0Client } from "@auth0/auth0-spa-js";

let clientPromise: Promise<Auth0Client> | null = null;

/**
 * Returns true when Auth0 should be skipped (local development).
 * Set VITE_SKIP_AUTH=true in web/.env to bypass authentication locally.
 * Always false in production builds.
 */
export function isAuthSkipped(): boolean {
  if (import.meta.env.PROD) return false;
  return import.meta.env.VITE_SKIP_AUTH === "true";
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
  if (!clientPromise) {
    // Only call this on the client (not during SSR)
    clientPromise = createAuth0Client({
      domain: import.meta.env.VITE_AUTH0_DOMAIN!,
      clientId: import.meta.env.VITE_AUTH0_CLIENT_ID!,
      authorizationParams: {
        redirect_uri: `${window.location.origin}/admin`,
      },
    });
  }
  return clientPromise;
}
