import type { PageLoad } from "./$types";
import { getAuth0Client } from "$lib/auth";
import { redirect } from "@sveltejs/kit";

export const ssr = false;

export const load: PageLoad = async () => {
  const auth0 = await getAuth0Client();
  if (!(await auth0.isAuthenticated())) {
    throw redirect(302, "/admin");
  }
  return {};
};
