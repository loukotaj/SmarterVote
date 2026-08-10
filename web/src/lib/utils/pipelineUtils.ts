/**
 * Pipeline utility functions
 */
import type { RunStatus } from "$lib/types";

/**
 * Get CSS class for run status
 */
export function getStatusClass(status: RunStatus | string): string {
  switch (status) {
    case "running":
      return "bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 border-blue-200 dark:border-blue-700";
    case "completed":
      return "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 border-green-200 dark:border-green-700";
    case "failed":
      return "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 border-red-200 dark:border-red-700";
    case "cancelled":
      return "bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200 border-yellow-200 dark:border-yellow-700";
    case "continued":
      return "bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 border-purple-200 dark:border-purple-700";
    default:
      return "bg-surface-alt text-content border-stroke";
  }
}

/**
 * Get CSS class for log level
 */
export function getLogClass(level: string): string {
  switch (level) {
    case "error":
      return "bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-200 border-l-red-500";
    case "warning":
      return "bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200 border-l-yellow-500";
    case "info":
      return "bg-blue-50 dark:bg-blue-900/20 text-blue-800 dark:text-blue-200 border-l-blue-500";
    case "debug":
      return "bg-surface-alt text-content-muted border-l-stroke";
    default:
      return "bg-surface-alt text-content-muted border-l-stroke";
  }
}
