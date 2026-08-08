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
// Pipeline store limits
// ---------------------------------------------------------------------------

/** Maximum log entries retained in the pipeline store before oldest are dropped. */
export const MAX_LOG_ENTRIES = 500;

/** JSON output size (bytes) beyond which "too large" warning is shown. */
export const OUTPUT_TOO_LARGE_BYTES = 5_000_000;

/** Truncation threshold (bytes) for the safe-output-display derived store. */
export const OUTPUT_DISPLAY_MAX_BYTES = 500_000;

/** Object key count beyond which we show a "large object" placeholder. */
export const LARGE_OBJECT_KEY_THRESHOLD = 1_000;
