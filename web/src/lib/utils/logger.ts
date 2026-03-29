/**
 * Lightweight logger utility.
 * In dev mode: passes through to console.
 * In prod mode: suppresses warnings, keeps errors minimal.
 */

const isDev = import.meta.env.DEV;

export const logger = {
  error(message: string, ...args: unknown[]) {
    if (isDev) {
      console.error(message, ...args);
    }
    // In production, silently swallow — errors are already
    // handled by the calling code (fallbacks, user messages, etc.)
  },

  warn(message: string, ...args: unknown[]) {
    if (isDev) {
      console.warn(message, ...args);
    }
  },

  info(message: string, ...args: unknown[]) {
    if (isDev) {
      console.info(message, ...args);
    }
  },
};
