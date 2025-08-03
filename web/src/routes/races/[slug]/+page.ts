import { PUBLIC_API_BASE_URL } from '$env/static/public';
import { error } from '@sveltejs/kit';

export const ssr = false;

export const load = async ({ fetch, params }) => {
    const res = await fetch(`${PUBLIC_API_BASE_URL ?? ''}/races/${params.slug}`);
    if (!res.ok) throw error(res.status, 'Race not found');
    return { race: await res.json() };
};
