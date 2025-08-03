declare module "$app/stores" {
  import type { Readable } from "svelte/store";
  import type { Page, Navigation } from "@sveltejs/kit";

  export const page: Readable<Page>;
  export const navigating: Readable<Navigation | null>;
  export const updated: Readable<boolean>;
}
