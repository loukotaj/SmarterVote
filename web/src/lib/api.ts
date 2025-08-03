import type { Race } from './types';

const API_BASE = import.meta.env.VITE_RACES_API_URL || 'http://localhost:8080';

export async function getRace(id: string, fetchFn: typeof fetch = fetch): Promise<Race> {
  const res = await fetchFn(`${API_BASE}/races/${id}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch race: ${res.status}`);
  }
  return (await res.json()) as Race;
}
