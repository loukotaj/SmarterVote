declare module '$app/stores' {
	import type { Readable } from 'svelte/store';
	import type { Page } from '@sveltejs/kit';

	export const page: Readable<Page>;
	export const navigating: Readable<any>;
	export const updated: Readable<boolean>;
}
