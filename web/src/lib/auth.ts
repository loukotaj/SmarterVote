// auth.ts
import { createAuth0Client, type Auth0Client } from "@auth0/auth0-spa-js";

let clientPromise: Promise<Auth0Client> | null = null;

export function getAuth0Client(): Promise<Auth0Client> {
  console.log(`${window.location.origin}/admin`);
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
