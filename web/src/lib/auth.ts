import createAuth0Client, { type Auth0Client } from "@auth0/auth0-spa-js";

let client: Auth0Client | null = null;

export async function getAuth0Client(): Promise<Auth0Client> {
  if (!client) {
    client = await createAuth0Client({
      domain: import.meta.env.VITE_AUTH0_DOMAIN,
      clientId: import.meta.env.VITE_AUTH0_CLIENT_ID,
      authorizationParams: {
        redirect_uri: window.location.origin + "/admin",
      },
    });
  }
  return client;
}
