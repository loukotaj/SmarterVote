/**
 * Shared numeric constants for the SmarterVote frontend.
 *
 * Centralises magic numbers that were previously inlined across
 * pipelineApiService and components.
 */

// ---------------------------------------------------------------------------
// API timeouts (ms)
// ---------------------------------------------------------------------------

/** Default timeout for short read-only API calls. */
export const API_TIMEOUT_SHORT = 10_000;

/** Default timeout for standard API calls (run details, publishes, etc.). */
export const API_TIMEOUT_DEFAULT = 15_000;

/** Timeout for artifact downloads which may be large. */
export const API_TIMEOUT_ARTIFACT = 20_000;

// ---------------------------------------------------------------------------
// Pipeline log limits
// ---------------------------------------------------------------------------

/** Maximum log entries retained in the run drawer before oldest are dropped. */
export const MAX_LOG_ENTRIES = 500;
