/**
 * API utilities and authentication store
 */
import { writable } from 'svelte/store';
import { getAuth0Client } from '$lib/auth';
import type { Auth0Client } from '@auth0/auth0-spa-js';

interface ApiState {
  auth0: Auth0Client | null;
  token: string;
  isAuthenticated: boolean;
}

const initialState: ApiState = {
  auth0: null,
  token: '',
  isAuthenticated: false
};

export const apiStore = writable<ApiState>(initialState);

/**
 * Initialize authentication
 */
export async function initializeAuth() {
  try {
    const auth0 = await getAuth0Client();
    const token = await auth0.getTokenSilently();
    
    apiStore.update(state => ({
      ...state,
      auth0,
      token,
      isAuthenticated: true
    }));
    
    return { auth0, token };
  } catch (error) {
    console.error('Failed to initialize auth:', error);
    throw error;
  }
}

/**
 * Fetch with authentication and smart timeout handling
 */
export async function fetchWithAuth(
  url: string, 
  options: RequestInit = {}, 
  timeoutMs?: number
): Promise<Response> {
  let currentToken = '';
  let currentAuth0: Auth0Client | null = null;
  
  // Get current auth state
  const unsubscribe = apiStore.subscribe(state => {
    currentToken = state.token;
    currentAuth0 = state.auth0;
  });
  unsubscribe();

  // Refresh token if needed
  if (!currentToken && currentAuth0) {
    try {
      const auth0Client = currentAuth0 as Auth0Client;
      currentToken = await auth0Client.getTokenSilently();
      apiStore.update(state => ({ ...state, token: currentToken }));
    } catch (error) {
      console.error('Failed to refresh token:', error);
      throw new Error('Authentication token refresh failed');
    }
  }

  // Different timeout strategies based on operation type
  let defaultTimeout = 30000; // 30 seconds for most operations

  // Determine if this is a long-running operation that shouldn't timeout
  const isLongRunningOperation =
    url.includes('/run/') || // Pipeline execution
    url.includes('/continue') || // Pipeline continuation
    (options.method === 'POST' && url.includes('/run')); // Any run operation

  // Use provided timeout, or no timeout for long operations, or default
  const actualTimeout = timeoutMs !== undefined ? timeoutMs :
    (isLongRunningOperation ? null : defaultTimeout);

  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  if (actualTimeout !== null) {
    timeoutId = setTimeout(() => controller.abort(), actualTimeout);
  }

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        ...(options.headers || {}),
        Authorization: `Bearer ${currentToken}`,
      },
    });

    if (timeoutId) clearTimeout(timeoutId);
    return response;
  } catch (error) {
    if (timeoutId) clearTimeout(timeoutId);
    if (error instanceof Error && error.name === 'AbortError') {
      const timeoutText = actualTimeout ? `after ${actualTimeout / 1000} seconds` : 'due to abort signal';
      throw new Error(`Request timed out ${timeoutText}`);
    }
    throw error;
  }
}