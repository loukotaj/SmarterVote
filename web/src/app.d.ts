// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
  namespace App {
    // interface Error {}
    // interface Locals {}
    // interface PageData {}
    // interface PageState {}
    // interface Platform {}
  }
}

declare module 'topojson-client' {
  import type { GeoJSON } from 'geojson';
  export function feature(topology: object, object: object): GeoJSON.FeatureCollection;
  export function mesh(topology: object, object?: object, filter?: (a: object, b: object) => boolean): GeoJSON.MultiLineString;
}

export {};
